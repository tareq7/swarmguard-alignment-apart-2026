import unittest
from pre_sprint.sim import Setting, network, experiment, run_matrix

class TestToyPropagation(unittest.TestCase):
    def test_edges(self):
        self.assertEqual([len(x) for x in network("chain",4)],[1,2,2,1])
        self.assertEqual([len(x) for x in network("star",4)],[3,1,1,1])
        self.assertEqual([len(x) for x in network("complete",4)],[3,3,3,3])
    def test_seed_reproducible(self):
        c=Setting(seed=78,topology="complete")
        self.assertEqual(experiment(c),experiment(c))
    def test_zero_rounds(self):
        self.assertEqual(experiment(Setting(rounds=0))["compromised"],1)
    def test_complete_verification_blocks(self):
        for t in ("chain","star","complete"):
            self.assertEqual(experiment(Setting(topology=t,verification=1.0))["compromised"],1)
    def test_zero_transmission_blocks(self):
        self.assertEqual(experiment(Setting(transmission=0.0))["compromised"],1)
    def test_max_transmission_without_verification(self):
        for t in ("chain","star","complete"):
            self.assertEqual(experiment(Setting(topology=t,agents=5,rounds=5,transmission=1.0))["compromised"],5)
    def test_matrix_rows(self):
        rows=run_matrix(42,3,5,4)
        self.assertEqual(len(rows),27)
        self.assertEqual({r["topology"] for r in rows},{"star","chain","complete"})
    def test_invalid(self):
        with self.assertRaises(ValueError): experiment(Setting(agents=1))
        with self.assertRaises(ValueError): run_matrix(42,0,5,4)

if __name__=="__main__": unittest.main()
