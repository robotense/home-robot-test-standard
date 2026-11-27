"""Scores the two example state traces of worked example 1 (spec/v0.md §10) with the reference checker's command
line, as the README shows, and checks the verdicts. Needs NumPy and PyYAML (spec/checker.py's dependencies); the
tests skip without them.

    python3 -I -m unittest discover -s spec/tests
"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1]
REPO = SPEC.parent
SCENARIO = "spec/examples/scenarios/worked-example-1-mug-in-bowl.yaml"
TRACE = "spec/examples/data/synthetic/worked-example-1-mug-in-bowl.{}.trace.json"
HAVE_DEPS = all(importlib.util.find_spec(m) is not None for m in ("numpy", "yaml"))


def score(which):
    r = subprocess.run([sys.executable, "-I", "spec/checker.py", SCENARIO, TRACE.format(which)], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"spec/checker.py exited {r.returncode}: {r.stderr}")
    return json.loads(r.stdout)


class ExampleTraces(unittest.TestCase):
    def test_traces_are_marked_synthetic(self):
        for which in ("success", "failure"):
            rec = json.loads((REPO / TRACE.format(which)).read_text(encoding="utf-8"))
            self.assertEqual(rec["record"], "spec.state_trace.v0")
            self.assertIs(rec["synthetic"], True)

    @unittest.skipUnless(HAVE_DEPS, "spec/checker.py needs NumPy and PyYAML")
    def test_success_trace(self):
        out = score("success")
        o = out["outcome"]
        self.assertEqual((out["record"], out["scenario_id"]), ("spec.checker_outcome.v0", "kitchen_mug_in_bowl_001"))
        self.assertTrue(o["success"])
        self.assertTrue(o["goal_met"])
        self.assertGreater(o["goal_margin"], 0)
        self.assertEqual((o["stage_reached"], o["stage_class"], o["first_failed"]), ("finish", "S", None))
        self.assertTrue(all(i["value"] for i in out["truth"]["items"].values()))

    @unittest.skipUnless(HAVE_DEPS, "spec/checker.py needs NumPy and PyYAML")
    def test_failure_trace(self):
        out = score("failure")
        o = out["outcome"]
        self.assertFalse(o["success"])
        self.assertLess(o["goal_margin"], 0)
        self.assertEqual((o["stage_reached"], o["stage_class"]), ("acquire", "T"))
        self.assertEqual((o["first_failed"]["stage"], o["first_failed"]["predicate"]),
                         ("transport", "inside(mug, bowl, 0.07)"))
        items = out["truth"]["items"]
        self.assertEqual({k: v["value"] for k, v in items.items()},
                         {"S1": True, "S2": False, "S3": False, "G1": False, "G2": False, "G3": True})


if __name__ == "__main__":
    unittest.main()
