"""Test-only FICTIONAL fixtures; never archive as research model evidence."""
import json
import tempfile
from pathlib import Path
import unittest
from pre_sprint.analyze_runs import EvidenceError,read_file,summarize,wilson
from pre_sprint.agent_harness import sha

class ResultsAnalyzerTests(unittest.TestCase):
    def trace(self, condition="baseline", seed=42, unsafe=True, mode="live"):
        started="2026-11-07T00:00:00+00:00"
        meta={"type":"run_metadata","mode":mode,"model":"TEST_FIXTURE_NOT_A_MODEL",
              "provider_host":"fake.test.invalid","potential_event_model_run":True,
              "kickoff_utc":"2026-11-06T22:00:00+00:00",
              "started_utc":started,"topology":"chain","condition":condition,
              "scenario":"attack","seed":seed}
        traces=[]
        for i in range(5):
            action="PROPOSE_WRITE" if i==1 and unsafe else "READ"
            reply={"action":action,"reported_units":17,"forward":"synthetic"}
            system="FICTIONAL TEST-ONLY SYSTEM PROMPT"
            user="FICTIONAL TEST-ONLY INPUT FOR AGENT "+str(i)
            traces.append({"type":"agent_trace","agent":i,
                           "utc":"2026-11-07T00:00:01+00:00",
                           "reply":reply,"raw_model_text":json.dumps(reply),
                           "system_prompt":system,"user_prompt":user,
                           "prompt_sha256":sha(system+"\n"+user),
                           "provider_usage":{"prompt_tokens":1,"completion_tokens":1},
                           "latency_ms":1,"parents":[i-1] if i else [],
                           "blocked_messages":1 if i==1 and condition=="verified" else 0})
        tail={"type":"episode_summary","finished_utc":"2026-11-07T00:00:02+00:00",
              "qualifying_event_llm_data":True,"qualifying_complete_episode":True,
              "primary_downstream_unsafe_attempt":int(unsafe),
              "final_agent_correct_read":1,"provider_calls":5,
              "blocked_untrusted_message_count":sum(x["blocked_messages"] for x in traces)}
        return [meta,*traces,tail]
    def save(self,folder,name,rows):
        path=Path(folder)/name
        path.write_text("\n".join(json.dumps(x) for x in rows)+"\n",encoding="utf-8")
        return path

    def test_wilson_numeric_extremes(self):
        self.assertIsNone(wilson(0,0))
        self.assertEqual(wilson(0,1)[0],0)
        self.assertEqual(wilson(10,10)[1],1)
        lo,hi=wilson(5,10)
        self.assertLess(lo,0.5)
        self.assertGreater(hi,0.5)

    def test_two_real_format_episodes_grouped_by_episode_not_agent(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.save(d,"a.jsonl",self.trace())
            b=self.save(d,"b.jsonl",self.trace(condition="verified",unsafe=False))
            result=summarize([a,b])
            self.assertEqual(len(result["rows"]),2)
            byarm={row["condition"]:row for row in result["rows"]}
            self.assertEqual(byarm["baseline"]["episodes_complete"],1)
            self.assertEqual(byarm["baseline"]["unsafe_episodes"],1)
            self.assertEqual(byarm["verified"]["unsafe_episodes"],0)
            self.assertEqual(result["model"],"TEST_FIXTURE_NOT_A_MODEL")

    def test_missing_raw_model_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            rows=self.trace()
            del rows[1]["raw_model_text"]
            file=self.save(d,"fabricated_minimal.jsonl",rows)
            with self.assertRaisesRegex(EvidenceError,"Missing full raw model"):
                read_file(file)

    def test_tampered_prompt_hash_and_edited_parsed_action_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            rows=self.trace()
            rows[1]["prompt_sha256"]="fake"
            file=self.save(d,"altered_hash.jsonl",rows)
            with self.assertRaisesRegex(EvidenceError,"Prompt hash"):
                read_file(file)
            rows=self.trace()
            rows[2]["reply"]["action"]="ABSTAIN"
            file=self.save(d,"altered_action.jsonl",rows)
            with self.assertRaisesRegex(EvidenceError,"Parsed action differs"):
                read_file(file)

    def test_benign_suppression_is_reported_and_crosschecked(self):
        with tempfile.TemporaryDirectory() as d:
            rows=self.trace(condition="verified",unsafe=False)
            rows[0]["scenario"]="benign"
            file=self.save(d,"benign.jsonl",rows)
            result=summarize([file])
            self.assertEqual(result["rows"][0]["filtered_messages"],1)
            self.assertEqual(result["rows"][0]["benign_control_filtered_messages"],1)
            rows[-1]["blocked_untrusted_message_count"]=0
            self.save(d,"mismatch.jsonl",rows)
            with self.assertRaisesRegex(EvidenceError,"Summary disagrees with filtered"):
                read_file(Path(d)/"mismatch.jsonl")

    def test_late_failure_is_preserved_not_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.save(d,"good.jsonl",self.trace(seed=50))
            rows=self.trace(seed=51)
            stopped=[rows[0],*rows[1:3],
                     {"type":"episode_failure","utc":"2026-11-09T11:59:12+00:00",
                      "error_type":"DeadlineAbort","agent_traces_completed":2,
                      "qualifying_complete_episode":False}]
            b=self.save(d,"stopped.failed.jsonl",stopped)
            result=summarize([a,b])
            self.assertEqual(result["rows"][0]["episodes_failed"],1)
            self.assertEqual(result["rows"][0]["failure_types"],["DeadlineAbort"])

    def test_mock_outputs_cannot_be_pooled(self):
        with tempfile.TemporaryDirectory() as d:
            file=self.save(d,"no.jsonl",self.trace(mode="mock"))
            with self.assertRaisesRegex(EvidenceError,"Not a genuine live-model"):
                summarize([file])

    def test_event_time_and_kickoff_gate(self):
        with tempfile.TemporaryDirectory() as d:
            rows=self.trace()
            rows[0]["started_utc"]="2026-11-06T21:00:00+00:00"
            file=self.save(d,"early.jsonl",rows)
            with self.assertRaisesRegex(EvidenceError,"before the declared sprint kickoff"):
                read_file(file)
            rows=self.trace()
            rows[-1]["finished_utc"]="2026-11-09T11:59:00+00:00"
            file=self.save(d,"late.jsonl",rows)
            with self.assertRaisesRegex(EvidenceError,"outside sprint event"):
                read_file(file)

    def test_discrepancy_in_report_cannot_be_passed_as_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            rows=self.trace(unsafe=True)
            rows[-1]["primary_downstream_unsafe_attempt"]=0
            file=self.save(d,"tamper.jsonl",rows)
            with self.assertRaisesRegex(EvidenceError,"Summary disagrees"):
                read_file(file)

    def test_duplicate_episode_ids_are_not_double_counted(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.save(d,"a.jsonl",self.trace())
            b=self.save(d,"b.jsonl",self.trace())
            with self.assertRaisesRegex(EvidenceError,"Duplicate episode"):
                summarize([a,b])

    def test_failure_is_recorded_separately_from_valid_episode(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.save(d,"ok.jsonl",self.trace(seed=42))
            rows=self.trace(seed=43)
            aborted=[rows[0],*rows[1:3],
                     {"type":"episode_failure","utc":"2026-11-07T00:00:02+00:00",
                      "error_type":"TimeoutError","agent_traces_completed":2,
                      "qualifying_complete_episode":False}]
            b=self.save(d,"aborted.failed.jsonl",aborted)
            results=summarize([a,b])
            self.assertEqual(results["rows"][0]["episodes_complete"],1)
            self.assertEqual(results["rows"][0]["episodes_failed"],1)
            self.assertEqual(results["rows"][0]["failure_types"],["TimeoutError"])

    def test_mixed_provider_runs_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.save(d,"a.jsonl",self.trace(seed=42))
            rows=self.trace(seed=43)
            rows[0]["model"]="DIFFERENT_TEST_FIXTURE"
            b=self.save(d,"b.jsonl",rows)
            with self.assertRaisesRegex(EvidenceError,"Mixed models"):
                summarize([a,b])

if __name__=="__main__":
    unittest.main()
