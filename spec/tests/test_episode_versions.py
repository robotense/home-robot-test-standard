"""Tests of episode record versions v0, v0.1, v0.2 and v0.3 (spec/v0.md §8.1, §8.4, §14).
Standard library only.

    python3 -I -m unittest discover -s spec/tests
"""
import copy
import json
import sys
import unittest
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEC))

import validate  # noqa: E402

V0 = SPEC / "examples" / "pilot-episodes-mug-in-bowl.jsonl"
V0_1 = SPEC / "examples" / "data" / "synthetic" / "episodes-v0.1-synthetic.jsonl"
V0_1_FIELDS = ("generator", "compute", "scene_seeds", "events", "fork", "trace_sha256", "trace_method",
               "operating_conditions")


def load(path):
    return {f"{path.name}:{i}": json.loads(line)
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if line.strip()}


def problems(records):
    return {n: p for n, p in validate.validate(records).items() if p}


def as_v0(e):
    """The v0 record of a v0.1 record: the v0.1 fields removed."""
    e = copy.deepcopy(e)
    for k in V0_1_FIELDS:
        del e[k]
    del e["outcome"]["checker_version"]
    e["spec_version"] = "v0"
    return e


class Versions(unittest.TestCase):
    def test_v0_example_still_valid(self):
        """Old records keep their label and their rules: the pilot's v0 example validates unchanged."""
        recs = load(V0)
        self.assertTrue(all(r["spec_version"] == "v0" for r in recs.values()))
        self.assertFalse(problems(recs))

    def test_v0_1_example_valid_and_complete(self):
        recs = load(V0_1)
        self.assertEqual(len(recs), 3)
        self.assertFalse(problems(recs))
        for r in recs.values():
            self.assertEqual(r["spec_version"], "v0.1")
            self.assertEqual((r["outcome"]["checker"], r["outcome"]["checker_version"]), ("worktop_v0", "0.1.0"))
            self.assertEqual((r["generator"]["name"], r["generator"]["release"]), ("homegen", "0.5.0"))
            self.assertTrue(r["synthetic"])   # the run marks its records synthetic; an example, never evidence
        devices = {r["policy"]["family"]: r["compute"] for r in recs.values()}
        self.assertEqual(devices["act"]["inference_device"], "cuda")
        self.assertEqual(devices["act"]["kernel_settings"]["CUBLAS_WORKSPACE_CONFIG"], ":4096:8")
        self.assertEqual(devices["scripted"]["inference_device"], "none")

    def test_worktop_record_as_v0_is_valid(self):
        """Records exported before v0.1 with spec_version v0 and checker worktop_v0 validate under v0."""
        recs = {n: as_v0(r) for n, r in load(V0_1).items()}
        self.assertFalse(problems(recs))

    def test_v0_1_fields_need_the_v0_1_label(self):
        e = next(iter(load(V0_1).values()))
        relabelled = dict(e, spec_version="v0")
        self.assertTrue(any("unknown field" in p for p in problems({"e": relabelled})["e"]))

    def test_v0_label_on_a_record_without_checker_release_cannot_be_promoted(self):
        """A v0 record is never relabelled v0.1: it lacks the fields v0.1 requires."""
        e = next(iter(load(V0).values()))
        msgs = problems({"e": dict(e, spec_version="v0.1")})["e"]
        for k in ("generator", "compute", "events", "scene_seeds"):
            self.assertIn(f"missing field `{k}`", msgs)
        self.assertIn("missing field `outcome.checker_version`", msgs)

    def test_fork_snapshot_hash_version(self):
        """`fork.snapshot_hash_version`: absent means 1; 1 or 2 accepted; other values refused, and null
        beside a snapshot hash; a start fork (no snapshot hash) names no version."""
        e = next(r for r in load(V0_1).values() if not r["outcome"]["success"])
        def with_fork(**kw):
            return dict(copy.deepcopy(e), fork=dict(validate.FORK_EXAMPLE, **kw), scene_seeds=[20261127, 1])
        for ok in ({}, {"snapshot_hash_version": 1}, {"snapshot_hash_version": 2}):
            self.assertFalse(problems({"e": with_fork(**ok)}), ok)
        for bad in ({"snapshot_hash_version": 0}, {"snapshot_hash_version": 3}, {"snapshot_hash_version": True},
                    {"snapshot_hash_version": "2"}, {"snapshot_version": 2}, {"snapshot_hash_version": None}):
            self.assertTrue(problems({"e": with_fork(**bad)}), bad)
        start = with_fork(boundary="start", block=0, snapshot_sha256=None, snapshot_hash_version=2)
        self.assertTrue(any("snapshot_hash_version" in m for m in problems({"e": start})["e"]))

    def test_selftest(self):
        recs = {}
        for p in sorted((SPEC / "examples").glob("*.json")):
            recs[p.name] = json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((SPEC / "examples").glob("*.jsonl")) + [V0_1]:
            recs.update(load(p))
        failures, n, m = validate.selftest(recs)
        self.assertFalse(failures)
        self.assertGreaterEqual(n, 165)
        self.assertGreaterEqual(m, 25)


def as_v0_2(e, physics_sha="0" * 64, simulated=True):
    """The v0.2 record of a v0.1 record: `simulated` and the option hash added (example values)."""
    e = copy.deepcopy(e)
    e.update(spec_version="v0.2", simulated=simulated)
    e["simulator"]["physics_options_sha256"] = physics_sha
    return e


class V0_2(unittest.TestCase):
    """`simulated`, `simulator.physics_options_sha256` and the checker molmospaces_pnp_port_v1."""

    def test_old_labels_unchanged(self):
        """v0 and v0.1 records keep their rules: they validate without the v0.2 fields and refuse them."""
        self.assertFalse(problems(load(V0)))
        self.assertFalse(problems(load(V0_1)))
        e = next(iter(load(V0_1).values()))
        self.assertIn("unknown field `simulated`", problems({"e": dict(e, simulated=True)})["e"])

    def test_v0_1_record_relabelled_v0_2_is_refused(self):
        e = next(iter(load(V0_1).values()))
        msgs = problems({"e": dict(e, spec_version="v0.2")})["e"]
        self.assertIn("missing field `simulated`", msgs)
        self.assertIn("missing field `simulator.physics_options_sha256`", msgs)

    def test_v0_2_export_of_v0_1_records(self):
        """A new export of the same source records under v0.2 validates, with the hash given or not recorded."""
        for sha in ("0" * 64, None):
            recs = {n: as_v0_2(r, sha) for n, r in load(V0_1).items()}
            self.assertFalse(problems(recs), sha)

    def test_simulated_and_real_rerun(self):
        e = next(r for r in load(V0_1).values() if not r["outcome"]["success"])
        rerun = {"random_holdout": True, "setup_seconds": 40.0, "initial_poses": None}
        real = dict(as_v0_2(e, None, simulated=False), synthetic=False, real_rerun=rerun)
        self.assertFalse(problems({"e": real}))
        self.assertTrue(problems({"e": dict(real, real_rerun=None)}))   # a real measurement is a real rerun in v0.2
        self.assertFalse(problems({"e": dict(real, real_rerun=None, synthetic=True)}))   # a stand-in for one is not
        self.assertTrue(problems({"e": as_v0_2(dict(real, simulator=dict(real["simulator"])), "a" * 64,
                                               simulated=False)}))
        self.assertTrue(problems({"e": dict(as_v0_2(e), synthetic=False, real_rerun=rerun)}))

    def test_pnp_checker_only_from_v0_2(self):
        e = next(r for r in load(V0_1).values() if not r["outcome"]["success"])
        e = copy.deepcopy(e)
        e["outcome"].update(checker=validate.PNP, stage_reached="lift", stage_class="T", terminal_class="lost_after_lift",
                            episode_margin=-0.5, stage_times={"touch": 3.0, "lift": 6.0},
                            first_failed={"stage": "support", "predicate": "supported", "t": 39.996})
        self.assertTrue(problems({"e": e}))                 # v0.1: checker not in its list
        self.assertFalse(problems({"e": as_v0_2(e)}))      # v0.2: accepted

    def test_pnp_map_is_a_partition(self):
        """Every failure stage maps to one class and its terminal classes; no terminal class is shared."""
        seen = {}
        for reached, (cls, terms, first) in validate.PNP_FAILURE.items():
            self.assertIn(cls, "GTP")
            for t in terms:
                self.assertNotIn(t, seen)
                seen[t] = reached
        self.assertEqual(set(seen), set(validate.PNP_PREDICATES))
        self.assertTrue(set(seen).isdisjoint({"drop", "pulled_off", "knocked", "off_counter", "timeout"}))



def as_v0_3(e, **generator):
    """The v0.3 record of a v0.1 record: the v0.2 fields (option hash not recorded) and the generator updated."""
    e = as_v0_2(e, None)
    e["spec_version"] = "v0.3"
    e["generator"].update(generator)
    return e


class V0_3(unittest.TestCase):
    """`generator.seedless`: a generator that draws no random number, with an empty `generator.seeds`."""

    def setUp(self):
        self.e = next(r for r in load(V0_1).values() if not r["outcome"]["success"])

    def test_old_labels_unchanged(self):
        """v0.1 and v0.2 keep their rules: an empty seed map and the flag are refused under both labels."""
        for label in ("v0.1", "v0.2"):
            e = copy.deepcopy(self.e) if label == "v0.1" else as_v0_2(self.e, None)
            for gen in ({"seeds": {}}, {"seeds": {}, "seedless": True}, {"seedless": False}):
                bad = copy.deepcopy(e)
                bad["generator"].update(gen)
                self.assertTrue(problems({"e": bad}), (label, gen))

    def test_v0_3_exports_of_v0_1_records(self):
        """A new export of the same source records under v0.3 validates with its seeds, with or without the flag."""
        for gen in ({}, {"seedless": False}):
            recs = {n: as_v0_3(r, **gen) for n, r in load(V0_1).items()}
            self.assertFalse(problems(recs), gen)

    def test_seedless_generator(self):
        ok = as_v0_3(self.e, seeds={}, seedless=True, constraints_sha256=None)
        self.assertFalse(problems({"e": ok}))
        self.assertFalse(problems({"e": dict(ok, generator=None)}))   # a stored scenario document, as before

    def test_seedless_rules(self):
        for gen in ({"seedless": True}, {"seeds": {}}, {"seeds": {}, "seedless": False},
                    {"seeds": {}, "seedless": "true"}, {"seeds": {}, "seedless": None}, {"seeds": {}, "seedless": 1}):
            self.assertTrue(problems({"e": as_v0_3(self.e, **gen)}), gen)

    def test_v0_3_needs_the_v0_2_fields(self):
        msgs = problems({"e": dict(self.e, spec_version="v0.3")})["e"]
        self.assertIn("missing field `simulated`", msgs)


if __name__ == "__main__":
    unittest.main()
