"""PRE-EVENT safety/contract tests; MOCK results are NOT hackathon research."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from pre_sprint.agent_harness import MockBackend, parse_reply, run_episode, validate_live_mode

class TestExperimentalHarness(unittest.TestCase):
    def test_deterministic_mock_plumbing_all_topologies(self):
        for topology in ("chain", "star", "complete"):
            baseline, b = run_episode(topology, "baseline", "attack", 42, MockBackend())
            guarded, g = run_episode(topology, "verified", "attack", 42, MockBackend())
            self.assertEqual(len(baseline), 5)
            self.assertEqual(len(guarded), 5)
            # These assertions prove the implementation's synthetic wiring
            # only, NOT a model's vulnerability or defense effectiveness.
            self.assertEqual(b["primary_downstream_unsafe_attempt"], 1)
            self.assertEqual(g["primary_downstream_unsafe_attempt"], 0)
            self.assertEqual(b["final_agent_correct_read"], 0)
            self.assertEqual(g["final_agent_correct_read"], 1)
            self.assertGreater(g["blocked_untrusted_message_count"], 0)
            self.assertEqual(b["blocked_untrusted_message_count"], 0)
            self.assertTrue(all(x["prompt_sha256"] for x in baseline))

    def test_benign_controls(self):
        for topo in ("chain", "star", "complete"):
            for cond in ("baseline", "verified"):
                rows, result = run_episode(topo, cond, "benign", 10, MockBackend())
                self.assertEqual(result["primary_downstream_unsafe_attempt"], 0)
                self.assertEqual(result["final_agent_correct_read"], 1)
                self.assertEqual(len(rows), 5)

    def test_rejects_malformed_model_responses(self):
        for sample in (
            "{bad", "[]", '{"action":"WRITE_STOCK","forward":"x","reported_units":17}',
            '{"action":"READ","forward":false,"reported_units":17}',
            '{"action":"READ","forward":"a","reported_units":"17"}',
            '{"action":"READ","forward":"a","reported_units":true}',
            '{"action":"READ","forward":"a","reported_units":-1}',
            '{"action":"READ","forward":"' + ("x"*2001) + '","reported_units":17}'
        ):
            with self.assertRaises((ValueError, TypeError, json.JSONDecodeError)):
                parse_reply(sample)

    def test_invalid_arms_and_seeds_fail_closed(self):
        for topo, cond, scenario, seed in [
            ("grid","baseline","attack",0), ("chain","bad","attack",0),
            ("chain","verified","bad",0), ("chain","verified","attack",-1)
        ]:
            with self.assertRaises(ValueError):
                run_episode(topo, cond, scenario, seed, MockBackend())

    def test_live_backend_requires_zero_overage_confirmation_and_event_start(self):
        args=argparse.Namespace(mode="live",confirm_free_no_overage=False,
             kickoff_utc="",api_url="https://example.test/v1/chat/completions",
             model="example",max_model_calls=5)
        with self.assertRaises(ValueError):
            validate_live_mode(args)
        args.confirm_free_no_overage=True
        with self.assertRaises(ValueError):
            validate_live_mode(args)
        # Nov 4 is before event; even valid credentials cannot override gate.
        args.kickoff_utc="2026-11-06T00:00:00Z"
        prior=os.environ.pop("SWARM_CONFIRMED_FREE_NO_OVERAGE",None)
        try:
            with self.assertRaises(ValueError): validate_live_mode(args)
        finally:
            if prior is not None:os.environ["SWARM_CONFIRMED_FREE_NO_OVERAGE"]=prior

    def test_atomic_mock_trace_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"mock.jsonl"
            base=[sys.executable,"-m","pre_sprint.agent_harness",
                  "--topology","chain","--condition","verified","--seed","3",
                  "--out",str(target)]
            first=subprocess.run(base,capture_output=True,text=True,timeout=15)
            self.assertEqual(first.returncode,0,first.stderr)
            lines=[json.loads(x) for x in target.read_text().splitlines()]
            self.assertEqual(len(lines),7)
            self.assertEqual(lines[0]["type"],"run_metadata")
            self.assertFalse(lines[0]["qualifying_event_llm_data"])
            self.assertEqual(lines[0]["model"],"MOCK_NO_MODEL")
            self.assertEqual(lines[-1]["type"],"episode_summary")
            second=subprocess.run(base,capture_output=True,text=True,timeout=15)
            self.assertNotEqual(second.returncode,0)
            self.assertIn("Refusing to overwrite",second.stderr)
            self.assertFalse((Path(tmp)/"mock.jsonl.part").exists())

if __name__=="__main__":
    unittest.main()
