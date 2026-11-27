"""Tests of trust entry versions v0 and v0.4 (spec/v0.md §7, §12, §14): the v0 verdict rule, which tests bias and
scatter against the tolerance separately, and the v0.4 limits-of-agreement rule with its padding check, the label
disagree_unresolved, NOT DETERMINED and the demonstrated tolerances. Standard library only.

    python3 -I -m unittest discover -s spec/tests
"""
import copy
import itertools
import json
import sys
import unittest
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEC))

import validate  # noqa: E402

EX = SPEC / "examples"
D = 0.25


def load(*names):
    out = {}
    for name in names:
        path = EX / name
        if path.suffix == ".jsonl":
            out.update({f"{name}:{i}": json.loads(line)
                        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if line.strip()})
        else:
            out[name] = json.loads(path.read_text(encoding="utf-8"))
    return out


def widowx():
    return load("ca-widowx-plan.json", "ca-widowx-calibration-manifest.json", "ca-widowx-cell-agreement.jsonl",
                "ca-widowx-trust-entries.jsonl")


def graded_name(recs):
    return next(n for n, r in recs.items() if r["record"] == "trust_entry" and r["verdict"] != "not_yet_calibrated")


def problems(records):
    return {n: p for n, p in validate.validate(records).items() if p}


def entry(bias_ci, scatter_ci, nf=(None, None, 5), scatter=None, verdict="inconclusive", possible=None, delta=D):
    """A standalone v0.4 graded entry with the given inputs (no plan links); nf = (bias_ci, scatter_ci, n_cells) of
    the non-FLOOR cells, the all-cell inputs when None. Demonstrated tolerances recomputed."""
    nb, ns, n = nf
    nb, ns = nb or bias_ci, ns or scatter_ci
    mid = lambda ci: (ci[0] + ci[1]) / 2
    s_point = scatter if scatter is not None else mid(scatter_ci)
    t = {
        "record": "trust_entry", "spec_version": "v0.4", "assessment_id": "a", "plan_sha256": "0" * 64, "kpi": "k",
        "scope": "failure_stage", "target": "G", "simulator": {"name": "s", "version": None, "config_hash": None},
        "simulator_tier": None, "embodiment": "e", "T_k": None, "interval": None, "ppv_k": None, "ppv_interval": None,
        "bias": {"value": mid(bias_ci), "ci95": list(bias_ci), "ci95_clustered": None},
        "scatter_net": {"value": s_point, "ci95": None if scatter_ci is None else list(scatter_ci)},
        "tolerance": delta, "verdict": verdict, "verdict_possible": possible, "n_cells": max(n, 1),
        "n_real_episodes": 100, "pairing": "cell",
        "referent": {"dataset_ids": ["x"], "producer": "x", "independent_of_vendor": False},
        "validation_domain_ref": None, "calibration_overlap": "unknown", "twin_calibration": "uncalibrated",
        "fitted": "2026-11-26", "synthetic": False, "verdict_rule": "limits_of_agreement", "loa_method": "union_bound",
        "non_floor": {"n_cells": n,
                      "bias": None if n < 2 else {"value": mid(nb), "ci95": list(nb)},
                      "scatter_net": None if n < 2 else {"value": s_point if ns is None else mid(ns),
                                                         "ci95": None if ns is None else list(ns)}},
        "delta_agree": None, "delta_disagree": None,
    }
    t["delta_agree"], t["delta_disagree"] = validate.demonstrated(t)
    return t


def verdict(t):
    return validate.rule_verdict_loa(t)


class WidowXExample(unittest.TestCase):
    def test_published_example_unchanged(self):
        """The published v0 entry validates unchanged and keeps disagree_scatter under the v0 rule."""
        recs = widowx()
        self.assertFalse(problems(recs))
        t = recs[graded_name(recs)]
        self.assertEqual((t["spec_version"], t["verdict"]), ("v0", "disagree_scatter"))

    def test_v0_4_export_keeps_disagree_scatter(self):
        recs = widowx()
        for r in recs.values():
            if r["record"] == "trust_entry":
                validate.as_v0_4(r)
        self.assertFalse(problems(recs))
        t = recs[graded_name(recs)]
        self.assertEqual(verdict(t), ("disagree_scatter", ()))
        # The demonstrated tolerances as computed by our reference implementation of the rule.
        self.assertEqual(round(t["delta_agree"], 3), 1.149)
        self.assertEqual(round(t["delta_disagree"], 3), 0.695)
        cells = [r for r in recs.values() if r["record"] == "cell_agreement"]
        self.assertEqual(t["non_floor"]["n_cells"], sum(c["label"] != "FLOOR" for c in cells))

    def test_v0_style_agree_rejected_under_v0_4(self):
        """Bias interval inside ±δ and scatter upper bound ≤ δ: AGREE under v0, not under v0.4 (U = 0.492 > δ)."""
        recs = widowx()
        g = graded_name(recs)
        inputs = dict(bias={"value": 0.0, "ci95": [-0.1, 0.1], "ci95_clustered": None},
                      scatter_net={"value": 0.1, "ci95": [0.0, 0.2]})
        v0 = copy.deepcopy(recs)
        v0[g].update(verdict="agree", **copy.deepcopy(inputs))
        self.assertFalse(problems(v0))
        v4 = copy.deepcopy(v0)
        validate.as_v0_4(v4[g], recompute=True, non_floor={"n_cells": 14, "bias": {"value": 0.0, "ci95": [-0.1, 0.1]},
                                                         "scatter_net": {"value": 0.1, "ci95": [0.0, 0.2]}})
        self.assertIn("verdict must be inconclusive", " ".join(problems(v4)[g]))
        self.assertAlmostEqual(v4[g]["delta_agree"], 0.1 + 1.96 * 0.2)
        v4[g]["verdict"] = "inconclusive"
        self.assertFalse(problems(v4))


class Labels(unittest.TestCase):
    def test_version_labels(self):
        recs = widowx()
        g = graded_name(recs)
        for label in ("v0.1", "v0.2", "v0.3", "v1"):
            bad = copy.deepcopy(recs)
            bad[g]["spec_version"] = label
            self.assertTrue(problems(bad), label)
        bad = copy.deepcopy(recs)
        bad[g]["verdict"] = "disagree_unresolved"
        self.assertTrue(problems(bad))          # the label exists from v0.4 only

    def test_v0_4_label_needs_the_fields(self):
        recs = widowx()
        g = graded_name(recs)
        recs[g]["spec_version"] = "v0.4"
        msgs = problems(recs)[g]
        for f in ("verdict_rule", "loa_method", "non_floor", "delta_agree", "delta_disagree"):
            self.assertIn(f"missing field `{f}`", msgs)


class Rule(unittest.TestCase):
    def test_each_verdict(self):
        cases = [  # bias interval, scatter interval, verdict
            ((-0.05, 0.05), (0.0, 0.05), "agree"),                       # U = 0.148
            ((-0.1, 0.1), (0.0, 0.2), "inconclusive"),                   # U = 0.492, L = 0
            ((-0.02, 0.02), (0.15, 0.2), "disagree_scatter"),            # 1.96 s_lo = 0.294 > δ
            ((0.3, 0.4), (0.15, 0.2), "disagree_offset_and_scatter"),
            ((0.3, 0.4), (0.0, 0.1), "disagree_offset"),                  # 1.96 s_hi = 0.196 ≤ δ
            ((0.15, 0.25), (0.06, 0.2), "disagree_unresolved"),           # L = 0.268; neither cause alone
        ]
        for b, s, want in cases:
            with self.subTest(want=want):
                self.assertEqual(verdict(entry(b, s)), (want, ()))
                self.assertFalse(validate.check_trust_entry(entry(b, s, verdict=want)))

    def test_boundary(self):
        """AGREE exactly at U = δ; DISAGREE needs L > δ."""
        s_hi = (D - 0.05) / 1.96
        self.assertEqual(verdict(entry((-0.05, 0.05), (0.0, s_hi)))[0], "agree")
        self.assertEqual(verdict(entry((-0.05, 0.05), (0.0, s_hi + 1e-6)))[0], "inconclusive")
        self.assertEqual(verdict(entry((0.25, 0.3), (0.0, 0.05)))[0], "inconclusive")      # L = 0.25 = δ
        self.assertEqual(verdict(entry((0.2501, 0.3), (0.0, 0.05)))[0], "disagree_offset")

    def test_padding_check(self):
        ok = ((-0.05, 0.05), (0.0, 0.05))
        self.assertEqual(verdict(entry(*ok, nf=(None, None, 2)))[0], "agree")
        self.assertEqual(verdict(entry(*ok, nf=((-0.2, 0.2), (0.0, 0.05), 3)))[0], "inconclusive")
        self.assertEqual(verdict(entry(*ok, nf=(None, None, 1)))[0], "inconclusive")
        self.assertEqual(verdict(entry(*ok, nf=(None, None, 0)))[0], "floor")
        # The check applies to AGREE only: DISAGREE stands with fewer than 2 non-FLOOR cells.
        self.assertEqual(verdict(entry((0.3, 0.4), (0.0, 0.1), nf=(None, None, 1)))[0], "disagree_offset")
        t = entry(*ok, nf=(None, None, 1))
        self.assertIsNone(t["delta_agree"])
        t = entry(*ok, nf=((-0.2, 0.2), (0.0, 0.05), 3))
        self.assertAlmostEqual(t["delta_agree"], 0.2 + 1.96 * 0.05)    # the non-FLOOR bound is the larger

    def test_delta_disagree_null_when_l_is_zero(self):
        t = entry((-0.1, 0.1), (0.0, 0.2))
        self.assertIsNone(t["delta_disagree"])
        t = entry((0.3, 0.4), (0.0, 0.1))
        self.assertAlmostEqual(t["delta_disagree"], 0.3)

    def test_demonstrated_tolerances_read_the_verdict(self):
        """At any δ, AGREE exactly when delta_agree ≤ δ and DISAGREE exactly when delta_disagree > δ."""
        grid = [(-0.3, -0.1), (-0.1, 0.05), (0.0, 0.2), (0.12, 0.31)]
        sgrid = [(0.0, 0.03), (0.02, 0.12), (0.1, 0.3)]
        for b, s, nb in itertools.product(grid, sgrid, grid):
            for delta in (0.05, 0.1, 0.2, 0.25, 0.4, 0.7):
                t = entry(b, s, nf=(nb, s, 4), delta=delta)
                v = verdict(t)[0]
                self.assertEqual(v == "agree", t["delta_agree"] <= delta, (b, s, nb, delta))
                self.assertEqual(v.startswith("disagree"), t["delta_disagree"] is not None
                                 and t["delta_disagree"] > delta, (b, s, nb, delta))


class NotDetermined(unittest.TestCase):
    def brute(self, b, s, nf_b, delta, n=60):
        """Verdicts over a dense grid of scatter intervals containing the point s (and the non-FLOOR point s)."""
        lo = [s * i / n for i in range(n + 1)]
        hi = [s + 0.8 * i / n for i in range(n + 1)]
        out = set()
        for a, c in itertools.product(lo, hi):
            for a2, c2 in ((a, c), (0.0, s), (s, s), (0.0, s + 0.8)):
                t = entry(b, (a, c), nf=(nf_b, (a2, c2), 4), delta=delta)
                out.add(verdict(t)[0])
        return out

    def test_possible_verdicts_match_every_interval_containing_the_point(self):
        for b in [(-0.05, 0.05), (0.02, 0.1), (0.15, 0.24), (0.3, 0.4), (-0.4, -0.27)]:
            for s in (0.0, 0.03, 0.09, 0.12, 0.2, 0.36):
                with self.subTest(b=b, s=s):
                    t = entry(b, None, nf=(b, None, 4), scatter=s)
                    v, possible = verdict(t)
                    found = self.brute(b, s, b, D)
                    self.assertEqual(set(possible) if v == "not_determined" else {v}, found)

    def test_mapping_examples(self):
        """The cases spec/v0.md §7 lists for a null scatter interval."""
        # Point bound U_s = max|B| + 1.96 s ≤ δ: AGREE or INCONCLUSIVE.
        self.assertEqual(verdict(entry((-0.05, 0.05), None, nf=((-0.05, 0.05), None, 4), scatter=0.05)),
                         ("not_determined", ("agree", "inconclusive")))
        # L_s ≤ δ < U_s: INCONCLUSIVE outright.
        self.assertEqual(verdict(entry((-0.1, 0.1), None, scatter=0.1)), ("inconclusive", ()))
        # An offset with 1.96 s ≤ δ: the offset alone may or may not explain it.
        self.assertEqual(verdict(entry((0.3, 0.4), None, scatter=0.05)),
                         ("not_determined", ("disagree_offset", "disagree_unresolved")))
        # An offset with 1.96 s > δ.
        self.assertEqual(verdict(entry((0.3, 0.4), None, scatter=0.2)),
                         ("not_determined", ("disagree_offset_and_scatter", "disagree_unresolved")))
        # The WidowX shape without its scatter interval.
        self.assertEqual(verdict(entry((-0.0828, -0.0381), None, scatter=0.364)),
                         ("not_determined", ("disagree_scatter", "disagree_unresolved", "inconclusive")))

    def test_no_demonstrated_tolerance_without_an_interval(self):
        t = entry((0.3, 0.4), None, scatter=0.05)
        self.assertEqual((t["delta_agree"], t["delta_disagree"]), (None, None))


if __name__ == "__main__":
    unittest.main()
