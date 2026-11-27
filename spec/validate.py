#!/usr/bin/env python3
"""Validate spec v0 records: episode records (spec/v0.md §8), trust entries (§7), benchmark records (§11: reference
sets, entry cards), credibility assessment records (§12: cell agreement, assessment plan, calibration manifest) and
twin calibration records (§13). Standard library only.

    python3 -I spec/validate.py              # every record in spec/examples/, then the rejection self-test
    python3 -I spec/validate.py FILE ...     # the named records

A `.json` file holds one record; a `.jsonl` file holds one record per line. A record that links to another (an entry
card to its reference set, a plan to its calibration manifest, a cell agreement record to its plan, a trust entry to
its plan, an entry card or plan to its twin calibration) is checked against it, and the linked record must be among
those validated. Repository paths in `matching_file`, `information_used.rule` and `source_document` must exist and
match their SHA-256. The self-test applies known faults to the examples and fails unless each is rejected, then checks
that valid variants (a complete twin calibration, built in memory) are accepted. Exit status 1 on any problem. Episode
records may carry producer fields under keys that start with `x.`; they are not checked.
"""
import math
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "spec" / "examples"
SHA = re.compile(r"[0-9a-f]{64}")
UTC = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC")
STAGE_CLASSES = "GTPS"
FAILURE_TYPES = ("instruction", "visual", "layout", "object_identity", "object_state", "contact", "long_horizon",
                 "safety_constraint")   # §2
VERDICTS = ("agree", "disagree_offset", "disagree_scatter", "disagree_offset_and_scatter", "inconclusive", "floor",
            "not_determined", "not_yet_calibrated")
VERDICTS_V0_4 = VERDICTS + ("disagree_unresolved",)   # §7, from v0.4
Z_LOA = 1.96                 # 95% limits of agreement, |bias| + 1.96 x scatter (§7, v0.4)
LOA_METHODS = ("union_bound",)   # §7 v0.4: methods that compute the bounds on the limits of agreement
DELTA_TOL = 1e-9             # delta_agree and delta_disagree must equal the recomputed bounds to this
CELL_LABELS = ("DISAGREE", "AGREE", "INCONCLUSIVE", "FLOOR")
REPORTED = ("customer_draft", "customer_final")   # plan statuses whose verdicts reach a customer (§13.3)

# §13.2 tolerances and minimum counts of the twin calibration record, with their sources in spec/v0.md §13.2.
MIN_REFERENCE_POSES = 3      # our calibration process uses 3-5 marked reference poses
MAX_GRIPPER_MM = 5.0         # provisional: our proposed threshold for an SO-101 arm, not a published figure
MAX_REPLAY_DEG = 0.5         # one SO-101 identification: tracking 0.3-0.5 deg, in-sample; applied to held-out replay
MIN_BOARD_IMAGES = 15        # 15-30 board images per camera
MAX_CAMERA_POSE_MM = 4.0     # EasyHeC on a real arm, 0.3-0.4 cm
MAX_DRIFT_PX = 2.6           # SO-101 Bench camera drift <= 2.6 px over its study
MAX_TOUCH_MM = 10.0          # provisional: no published figure; spec §6's +-1 cm


def canonical(record):
    """Bytes hashed for a record: sorted keys, no whitespace, UTF-8 (spec/v0.md §11)."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def record_sha(record):
    return hashlib.sha256(canonical(record)).hexdigest()


# Field types: each returns True if the value is acceptable.
def text(v):
    return isinstance(v, str) and v.strip() != ""


def opt(t):
    return lambda v: v is None or t(v)


def boolean(v):
    return isinstance(v, bool)


def count(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def positive(v):
    return number(v) and v > 0


def nonneg_int(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def pair(v):
    """An interval [lo, hi] with lo <= hi."""
    return isinstance(v, list) and len(v) == 2 and all(map(number, v)) and v[0] <= v[1]


def date(v):
    return isinstance(v, str) and re.fullmatch(r"\d{4}-\d\d-\d\d", v) is not None


def sha256(v):
    return isinstance(v, str) and SHA.fullmatch(v) is not None


def one_of(*values):
    return lambda v: v in values


def list_of(t, nonempty=False):
    return lambda v: isinstance(v, list) and (v or not nonempty) and all(t(x) for x in v)


def map_of(t, nonempty=False):
    return lambda v: isinstance(v, dict) and (v or not nonempty) and all(text(k) and t(x) for k, x in v.items())


def shape(fields, optional=None):
    """An object with exactly these keys, each of the given type, plus any of the `optional` keys (each of its type when
    present). `fields` and `optional` let problems name the inner key."""
    optional = optional or {}

    def check(v):
        return (isinstance(v, dict) and set(fields) <= set(v) <= set(fields) | set(optional)
                and all(t(v[k]) for k, t in fields.items()) and all(t(v[k]) for k, t in optional.items() if k in v))
    check.fields, check.optional = fields, optional
    return check


FILE_REF = shape({"path": text, "sha256": sha256})
GRADER = {"kind": one_of("human_rubric", "human_label", "automatic_rule", "vlm_judge"), "by": text, "rule": text,
          "code": opt(text), "blind_to_policy": opt(boolean), "agreement": opt(text)}
TERMINATION = {"kind": one_of("budget", "operator_judgement", "not_stated"),
               "budget": opt(map_of(shape({"value": positive, "unit": one_of("steps", "frames", "s")}), True)),
               "control_hz": opt(positive), "stops_at_success": opt(boolean), "source": text}
CELL_KEY = lambda c: isinstance(c, list) and len(c) == 2 and all(map(text, c))   # [policy, task]
CELLS = lambda v: v == "all" or list_of(CELL_KEY, True)(v)

REFERENCE_SET = {
    "record": one_of("reference_set"), "spec_version": one_of("v0"), "id": text, "benchmark": text, "track": text,
    "version": count, "status": one_of("draft", "frozen"), "data_seen_before_rules": boolean,
    "source": shape({"citation": text, "url": text, "location": opt(text), "revision": opt(text),
                     "file_sha256": map_of(sha256, True)}),
    "licence": list_of(shape({"part": text, "licence": text, "may_redistribute": opt(boolean)}), True),
    "producer": text, "embodiment": text,
    "policies": map_of(shape({"name": text, "checkpoint": opt(text), "revision": opt(text)}), True),
    "policy_identity": opt(text), "tasks": map_of(text, True), "tasks_excluded": map_of(text), "cells": CELLS,
    "trials_per_cell": lambda v: count(v) or map_of(count, True)(v),
    "units_per_trial": map_of(count, True), "pairing": one_of("cell", "layout", "episode"),
    "real_tables": shape({"primary": text, "ceiling": opt(text)}),
    "grader": shape(GRADER), "termination_rule": shape(TERMINATION),
    "classes": list_of(text, True),
    "class_rule": shape({"primary": text, "sensitivity": list_of(text), "observable": opt(map_of(text, True)),
                         "code": opt(text)}),
    "metrics": list_of(one_of("level", "rank", "stage"), True),
    "information": shape({"real_outcomes_public": boolean,
                          "sealed": list_of(shape({"what": text, "sha256": sha256}))}),
    "matching_file": opt(FILE_REF), "synthetic": boolean,
}

ENTRY_CARD = {
    "record": one_of("entry_card"), "spec_version": one_of("v0"), "id": text, "benchmark": text, "track": text,
    "reference_set": shape({"id": text, "sha256": sha256}),
    "kind": one_of("simulator", "world_model", "baseline", "ceiling"),
    "provenance": one_of("rerun_by_us", "as_submitted", "as_published", "computed"),
    "ours": boolean, "builder": text, "conflict_of_interest": opt(text),
    "simulator": opt(shape({"name": text, "version": opt(text), "config_hash": opt(text)})),
    "assets": list_of(shape({"name": text, "licence": opt(text)})),
    "checkpoints": map_of(shape({"revision": opt(text), "matches_reference": opt(boolean)}), True),
    "twin_calibration": opt(sha256),
    "information_used": shape({"class": one_of("declared_blind", "exposed"), "rule": opt(FILE_REF),
                               "saw": opt(list_of(text)), "tuned_on": opt(list_of(text)),
                               "calibration_manifest": opt(sha256), "note": opt(text)}),
    "grader": shape({**GRADER, "same_as_reference": boolean}), "termination_rule": shape(TERMINATION),
    "episodes_per_cell": count, "cells": CELLS, "seeds": opt(list_of(lambda s: isinstance(s, int))),
    "compute": opt(shape({"machine": text, "hours": opt(positive)})),
    "code": opt(shape({"location": text, "revision": opt(text)})),
    "outputs": shape({"format": one_of("spec_v0_episode_records", "per_trial_records", "cell_counts"),
                      "location": text, "revision": opt(text), "select": opt(text), "licence": opt(text),
                      "hashes": lambda v: text(v) or map_of(sha256, True)(v)}),
    "frozen_at": opt(lambda v: isinstance(v, str) and UTC.fullmatch(v) is not None), "synthetic": boolean,
}

SIMULATOR = shape({"name": text, "version": opt(text), "config_hash": opt(text)})
INDEPENDENCE = one_of(True, False, "unresolved")
CELL = shape({"policy": text, "task": text, "condition": opt(text), "embodiment": text})
COUNTS = shape({"k": nonneg_int, "n": count, "source": text})

TRUST_ENTRY = {
    "record": one_of("trust_entry"), "spec_version": one_of("v0"), "assessment_id": opt(text),
    "plan_sha256": opt(sha256), "kpi": opt(text), "scope": one_of("failure_type", "failure_stage", "aggregate"),
    "target": opt(text), "simulator": SIMULATOR, "simulator_tier": opt(text), "embodiment": text,
    "T_k": opt(lambda v: number(v) and 0 <= v <= 1), "interval": opt(pair), "ppv_k": opt(lambda v: number(v) and 0 <= v <= 1),
    "ppv_interval": opt(pair),
    "bias": shape({"value": opt(number), "ci95": opt(pair), "ci95_clustered": opt(pair)}),
    "scatter_net": shape({"value": opt(lambda v: number(v) and v >= 0), "ci95": opt(pair)}),
    "tolerance": opt(positive), "verdict": one_of(*VERDICTS), "verdict_possible": opt(list_of(one_of(*VERDICTS), True)),
    "n_cells": nonneg_int, "n_real_episodes": nonneg_int, "pairing": one_of("cell", "layout", "episode"),
    "referent": shape({"dataset_ids": list_of(text, True), "producer": text, "independent_of_vendor": INDEPENDENCE}),
    "validation_domain_ref": opt(sha256), "calibration_overlap": one_of(False, "unknown"),
    "twin_calibration": one_of("calibrated", "uncalibrated"), "fitted": opt(date), "synthetic": boolean,
}

# §7, v0.4: the limits-of-agreement verdict rule. Every v0 field keeps its type; `verdict` takes the new rule and the
# value disagree_unresolved; the rule's name, its bound method, the non-FLOOR inputs of the padding check and the two
# demonstrated tolerances are added, all required.
NON_FLOOR = shape({"n_cells": nonneg_int, "bias": opt(shape({"value": number, "ci95": pair})),
                   "scatter_net": opt(shape({"value": lambda v: number(v) and v >= 0, "ci95": opt(pair)}))})
TRUST_ENTRY_V0_4 = dict(
    TRUST_ENTRY, spec_version=one_of("v0.4"), verdict=one_of(*VERDICTS_V0_4),
    verdict_possible=opt(list_of(one_of(*VERDICTS_V0_4), True)),
    verdict_rule=one_of("limits_of_agreement"), loa_method=one_of(*LOA_METHODS), non_floor=opt(NON_FLOOR),
    delta_agree=opt(lambda v: number(v) and v >= 0), delta_disagree=opt(positive),
)
TRUST_VERSIONS = {"v0": TRUST_ENTRY, "v0.4": TRUST_ENTRY_V0_4}

CELL_AGREEMENT = {
    "record": one_of("cell_agreement"), "spec_version": one_of("v0"), "assessment_id": text, "cell": CELL,
    "kpi": text, "sim": COUNTS, "real": COUNTS, "real_repeat": opt(COUNTS),
    "stage_counts": opt(shape({"sim": map_of(nonneg_int, True), "real": map_of(nonneg_int, True)})),
    "d": number, "interval": pair, "interval_method": text, "label": one_of(*CELL_LABELS),
    "in_calibration": boolean, "synthetic": boolean,
}

KPI = shape({"id": text, "kind": one_of("failure_type", "failure_stage", "aggregate"), "target": opt(text),
             "statistic": text, "tolerance": opt(positive), "conditions": opt(text)})
ASSESSMENT_PLAN = {
    "record": one_of("assessment_plan"), "spec_version": one_of("v0"), "id": text, "assessment_version": text,
    "status": one_of("illustration", "internal_dry_run", "customer_draft", "customer_final"),
    "subject": shape({"simulator": SIMULATOR, "embodiment": text, "policies": map_of(opt(sha256), True),
                      "tasks": list_of(text, True), "scenario_hashes": list_of(sha256), "card_hashes": list_of(sha256),
                      "termination_rule": shape(TERMINATION), "twin_calibration": opt(sha256),
                      "note": opt(text)}),
    "route": one_of("desk", "rerun", "commissioned"),
    "declared_use": opt(shape({"decisions": text,
                               "influence_level": one_of("de_risking", "critical_point_analysis", "partial_credit",
                                                         "full_credit"),
                               "consequence": one_of("negligible", "minor", "moderate", "significant")})),
    "declared_domain_ref": opt(sha256),
    "referent": shape({"dataset_ids": list_of(text, True), "producer": text, "grader": shape(GRADER),
                       "termination_rule": shape(TERMINATION), "independent_of_vendor": INDEPENDENCE,
                       "pairing": one_of("cell", "layout", "episode"), "real_repeat": opt(text)}),
    "kpis": list_of(KPI, True),
    "verdict_rules": shape({"cell": text, "type": text, "multiplicity": text,
                            "alpha": lambda v: number(v) and 0 < v < 1}),
    "sensitivity": list_of(text), "calibration_manifest": opt(sha256),
    "fixed_at": lambda v: isinstance(v, str) and UTC.fullmatch(v) is not None, "fixed_before_data": boolean,
    "fixed_note": opt(text), "source_document": opt(FILE_REF), "synthetic": boolean,
}

CALIBRATION_MANIFEST = {
    "record": one_of("calibration_manifest"), "spec_version": one_of("v0"), "id": text, "simulator": SIMULATOR,
    "embodiment": text, "disclosed": boolean, "source": text,
    "items": list_of(shape({"data": text, "cells": opt(lambda v: v == "all" or list_of(CELL_KEY, True)(v)),
                            "parameters": opt(list_of(text, True)), "purpose": text})),
    "frozen_at": opt(lambda v: isinstance(v, str) and UTC.fullmatch(v) is not None), "synthetic": boolean,
}

MEASURED = ("operator", "us")          # sources that count toward a calibrated twin
SOURCE = one_of(*MEASURED, "inferred", "missing")
NONNEG = lambda v: number(v) and v >= 0
XYZ = lambda v: isinstance(v, list) and len(v) == 3 and all(map(number, v))
SIZE = lambda v: XYZ(v) and all(x > 0 for x in v)
QUAT = lambda v: isinstance(v, list) and len(v) == 4 and all(map(number, v))   # unit length: check_twin
POSE = shape({"xyz_m": XYZ, "quat_wxyz": QUAT})
ARTEFACT = shape({"location": text, "sha256": sha256})
TWIN_CALIBRATION = {
    "record": one_of("twin_calibration"), "spec_version": one_of("v0"), "id": text,
    "status": one_of("calibrated", "uncalibrated"), "simulator": SIMULATOR, "embodiment": text,
    "robot_unit": opt(text),
    "sessions": list_of(shape({"id": text, "date": date, "kind": one_of("calibration", "recording")})),
    "joints": shape({"source": SOURCE, "method": opt(text), "names": list_of(text, True), "file": opt(ARTEFACT),
                     "file_format": opt(text),
                     "reference_poses": list_of(shape({"id": text, "joints": map_of(number, True),
                                                       "point_xyz_m": opt(XYZ), "evidence": opt(ARTEFACT),
                                                       "gripper_error_mm": opt(NONNEG)}))}),
    "control": shape({"source": SOURCE, "method": opt(text), "software": opt(shape({"name": text, "version": text})),
                      "gains": opt(map_of(shape({"p": number, "i": number, "d": number}), True)),
                      "control_hz": opt(positive), "speed_limits": opt(text), "image_preprocessing": opt(text),
                      "twin_uses": opt(boolean)}),
    "actuators": shape({"source": SOURCE, "method": opt(text), "excitation": opt(ARTEFACT),
                        "excites": shape({"every_joint": opt(boolean), "varied_speeds": opt(boolean),
                                          "reversals": opt(boolean), "gripper_cycles": opt(boolean),
                                          "deployed_stack": opt(boolean)}),
                        "parameters": opt(ARTEFACT),
                        "replay": opt(shape({"recording": ARTEFACT, "rms_deg": map_of(NONNEG, True)}))}),
    "cameras": list_of(shape({"id": text, "source": SOURCE, "method": opt(text), "mount": text,
                              "board_images": opt(ARTEFACT), "board": opt(one_of("charuco", "checkerboard")),
                              "n_images": opt(nonneg_int), "focus_locked": opt(boolean),
                              "intrinsics": opt(shape({"model": text, "width": count, "height": count, "fx": positive,
                                                       "fy": positive, "cx": number, "cy": number,
                                                       "distortion": list_of(number)})),
                              "reprojection_rms_px": opt(NONNEG), "pose": opt(POSE), "pose_method": opt(text),
                              "pose_error_mm": opt(NONNEG), "session_drift_px": map_of(NONNEG)}), True),
    "scene": shape({"source": SOURCE, "method": opt(text),
                    "fixed_objects": list_of(shape({"name": text, "size_m": opt(SIZE), "mass_kg": opt(positive),
                                                    "pose": opt(POSE),
                                                    "pose_method": opt(one_of("fiducial", "measured")),
                                                    "touch_error_mm": opt(NONNEG)})),
                    "task_objects": list_of(shape({"name": text, "size_m": opt(SIZE), "mass_kg": opt(positive)}), True),
                    "layouts": shape({"method": opt(one_of("measured", "overhead_board")), "record": opt(ARTEFACT),
                                      "episodes": nonneg_int, "episodes_recorded": nonneg_int})}),
    "note": opt(text), "synthetic": boolean,
}

STAGE_NAME = opt(text)
# Checkers whose definitions §8.1 names. worktop_v0 (the checker of our tabletop slice) follows the failsearch_v0
# rules: a margin positive exactly on success, and a failure names its first failed predicate.
CHECKERS = ("spec_v0_grammar", "failsearch_v0", "worktop_v0")
# v0.2 (spec/v0.md §8.4): our port of MolmoSpaces' pick-and-place success rule with our stage map.
PNP = "molmospaces_pnp_port_v1"
CHECKERS_V0_2 = CHECKERS + (PNP,)
PILOT_LIKE = ("failsearch_v0", "worktop_v0", PNP)
# §8.4: stage reached (in order; "none" when no stage) -> (stage class, terminal class, first failed stage) of a failure.
PNP_STAGES = ("touch", "lift", "support", "finish")
PNP_FAILURE = {"none": ("G", ("no_contact",), "touch"), "touch": ("G", ("not_lifted",), "lift"),
               "lift": ("T", ("lost_after_lift",), "support"),
               "support": ("P", ("left_support", "goal_not_held"), "finish")}
PNP_PREDICATES = {"no_contact": ("robot_contact",), "not_lifted": ("lifted_3cm",), "lost_after_lift": ("supported",),
                  "left_support": ("supported_or_carried",),
                  "goal_not_held": ("no_robot_contact", "receptacle_pos_disp", "receptacle_tilt")}
OUTCOME = {"checker": one_of(*CHECKERS), "success": boolean, "goal_margin": opt(number), "episode_margin": number,
           "margin_components": lambda v: v is None or isinstance(v, dict),
           "constraint_margins": map_of(opt(number)), "stage_reached": text,
           "stage_times": map_of(lambda v: number(v) and v >= 0), "stage_class": one_of(*STAGE_CLASSES),
           "first_failed": opt(shape({"stage": STAGE_NAME, "predicate": text, "t": opt(number)})),
           "terminal_class": opt(text)}
EPISODE = {
    "record": one_of("episode"), "spec_version": one_of("v0"), "episode_id": text, "scenario_id": text,
    "scenario_hash": sha256, "nominal_ref": text, "factors": map_of(lambda v: number(v) or text(v), True),
    "perturbed": list_of(shape({"name": text, "failure_type": one_of(*FAILURE_TYPES), "delta_unit": opt(number)})),
    "instruction": opt(text), "embodiment": shape({"id": text, "source_commit": opt(text)}),
    "simulator": shape({"name": text, "version": text, "renderer": opt(text), "tier": opt(text),
                        "physics": lambda v: isinstance(v, dict)}),
    "seed": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "initial_state": lambda v: v is None or isinstance(v, dict) or text(v),
    "policy": shape({"id": text, "family": opt(text), "checkpoint_sha256": opt(sha256),
                     "inference": lambda v: v is None or isinstance(v, dict)}),
    "outcome": shape(OUTCOME),
    "search": opt(shape({"arm": text, "index": opt(nonneg_int), "holdout": opt(boolean),
                         "acquisition_p": opt(lambda v: number(v) and 0 <= v <= 1)})),
    "real_rerun": opt(shape({"random_holdout": boolean, "setup_seconds": opt(number),
                             "initial_poses": lambda v: v is None or isinstance(v, dict)})),
    "frames": opt(text),
    "versions": lambda v: isinstance(v, dict) and "git_commit" in v and isinstance(v.get("git_dirty"), bool),
    "synthetic": boolean,
}

# Episode record v0.1 (spec/v0.md §8.1 rows marked v0.1, §14): v0's fields plus the checker release, the scene
# generator, the inference device with its kernel settings, and the replay fields. A v0 record keeps v0's rules.
SEED_LIST = list_of(nonneg_int, nonempty=True)
SETTING = lambda v: v is None or isinstance(v, (str, bool, int, float))
EVENT = shape({"id": text, "factor": text, "trigger": text, "t": lambda v: number(v) and v >= 0,
               "block": opt(nonneg_int), "stage": opt(text), "v": opt(lambda v: number(v) and 0 <= v <= 1),
               "value": lambda v: number(v) or text(v), "applied": boolean, "reason": opt(text),
               "chunk_phase": opt(nonneg_int), "draw_seed": SEED_LIST})
TRIGGER = re.compile(r"time:(\d+(\.\d+)?)|stage:(\S+)")
DEVICES = ("cpu", "cuda", "mps", "other", "none")
# Snapshot hash versions (spec/v0.md §8.1, `fork`): 1 when the key is absent, or 2.
SNAPSHOT_HASH_VERSIONS = (1, 2)
FORK_EXAMPLE = {"trunk_episode_id": "map-0", "trunk_trace_sha256": None, "boundary": "lift", "block": 59,
                "snapshot_sha256": "0d0d724958b295f9173280be387641443654a217bad0a467807e1d6c0e3fea02"}   # self-test
EPISODE_V0_1 = dict(
    EPISODE, spec_version=one_of("v0.1"),
    outcome=shape(dict(OUTCOME, checker_version=text)),
    generator=opt(shape({"name": text, "release": text, "constraints_sha256": opt(sha256),
                         "seeds": map_of(lambda v: isinstance(v, int) and not isinstance(v, bool), True)})),
    compute=shape({"inference_device": one_of(*DEVICES), "device_name": opt(text), "toolkit": map_of(text),
                   "kernel_settings": map_of(SETTING)}),
    scene_seeds=opt(SEED_LIST),
    events=list_of(EVENT),
    fork=opt(shape({"trunk_episode_id": text, "trunk_trace_sha256": opt(sha256), "boundary": text,
                    "block": nonneg_int, "snapshot_sha256": opt(sha256)},
                   optional={"snapshot_hash_version": opt(lambda v: nonneg_int(v) and v in SNAPSHOT_HASH_VERSIONS)})),
    trace_sha256=opt(sha256), trace_method=opt(text),
    operating_conditions=opt(shape({"id": text, "sha256": sha256,
                                    "time_of_day_h": opt(lambda v: number(v) and 0 <= v < 24)})),
)
# Episode record v0.2 (spec/v0.md §8.1 rows marked v0.2, §14): v0.1's fields plus `simulated`, the hash of
# the simulator's physics option struct, and the checker molmospaces_pnp_port_v1.
EPISODE_V0_2 = dict(
    EPISODE_V0_1, spec_version=one_of("v0.2"),
    outcome=shape(dict(OUTCOME, checker=one_of(*CHECKERS_V0_2), checker_version=text)),
    simulator=shape({"name": text, "version": text, "renderer": opt(text), "tier": opt(text),
                     "physics": lambda v: isinstance(v, dict), "physics_options_sha256": opt(sha256)}),
    simulated=boolean,
)
# Episode record v0.3 (spec/v0.md §8.1 row marked v0.3, §14): v0.2's fields plus the optional `generator.seedless`;
# with it true, `generator.seeds` is the empty map (checked in check_episode_v0_3).
SEED_MAP = map_of(lambda v: isinstance(v, int) and not isinstance(v, bool))
EPISODE_V0_3 = dict(
    EPISODE_V0_2, spec_version=one_of("v0.3"),
    generator=opt(shape({"name": text, "release": text, "constraints_sha256": opt(sha256), "seeds": SEED_MAP},
                        optional={"seedless": boolean})),
)
EPISODE_VERSIONS = {"v0": EPISODE, "v0.1": EPISODE_V0_1, "v0.2": EPISODE_V0_2, "v0.3": EPISODE_V0_3}


def schema_of(rec):
    """The schema for a record: by kind, and for an episode record by its spec_version (unknown versions get v0's
    schema, which then names the bad spec_version)."""
    kind = rec.get("record") if isinstance(rec, dict) else None
    versions = {"episode": (EPISODE_VERSIONS, EPISODE), "trust_entry": (TRUST_VERSIONS, TRUST_ENTRY)}.get(kind)
    if versions is not None:
        sv = rec.get("spec_version")
        return versions[0].get(sv, versions[1]) if isinstance(sv, str) else versions[1]
    return SCHEMAS.get(kind) if isinstance(kind, str) else None


SCHEMAS = {"episode": EPISODE, "reference_set": REFERENCE_SET, "entry_card": ENTRY_CARD, "trust_entry": TRUST_ENTRY,
           "cell_agreement": CELL_AGREEMENT, "assessment_plan": ASSESSMENT_PLAN,
           "calibration_manifest": CALIBRATION_MANIFEST, "twin_calibration": TWIN_CALIBRATION}


def fields(rec, schema, prefix="", optional=()):
    """Problems with the record's keys and field types, naming nested keys of objects. Keys in `optional` may be
    absent."""
    out = [f"unknown field `{prefix}{k}`" for k in rec if k not in schema]
    out += [f"missing field `{prefix}{k}`" for k in schema if k not in rec and k not in optional]
    for k, t in schema.items():
        if k in rec and not t(rec[k]):
            inner = getattr(t, "fields", None)
            if inner is not None and isinstance(rec[k], dict):
                extra = getattr(t, "optional", {})
                out += fields(rec[k], {**inner, **extra}, f"{prefix}{k}.", tuple(extra))
            else:
                out.append(f"field `{prefix}{k}` has the wrong type or value")
    return out


def repo_file(ref, name):
    if ref is None:
        return []
    path = REPO / ref["path"]
    if not path.is_file():
        return [f"{name}: {ref['path']} not found"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
        return [f"{name}: SHA-256 of {ref['path']} differs"]
    return []


def termination(t, tasks, side):
    out = []
    if (t["kind"] == "budget") != (t["budget"] is not None):
        out.append(f"{side} termination_rule: `budget` is required for kind budget and null otherwise")
    keys = set(t["budget"] or ())
    if keys - set(tasks) - {"*"} or ("*" in keys and len(keys) > 1):
        out.append(f"{side} termination_rule: budget keys must be task IDs, or '*' alone")
    return out


def cells(value, ref, side):
    if value == "all":
        return []
    bad = [c for c in value if c[0] not in ref["policies"] or c[1] not in ref["tasks"]]
    return [f"{side} cells: {bad} not policy and task IDs of the reference set"] if bad else []


def check_reference_set(r):
    out = []
    if r["id"] != f"{r['benchmark']}/{r['track']}/{r['version']}":
        out.append("id must be <benchmark>/<track>/<version>")
    if r["synthetic"]:
        out.append("synthetic must be false: a reference set holds real outcomes")
    classes = r["classes"]
    if len(set(classes)) != len(classes) or not (set(classes) == {"S", "F"}
                                                 or ("S" in classes and set(classes) <= set(STAGE_CLASSES))):
        out.append("classes must be [S, F] or distinct stage classes from G, T, P, S including S")
    staged = set(classes) != {"S", "F"}
    if len(set(r["metrics"])) != len(r["metrics"]):
        out.append("metrics repeat")
    if "rank" in r["metrics"] and len(r["policies"]) < 4:
        out.append("metric rank needs at least 4 policies")
    if ("stage" in r["metrics"]) != staged:
        out.append("metric stage is listed exactly when classes are stage classes")
    if set(r["units_per_trial"]) != set(r["tasks"]):
        out.append("units_per_trial must have one entry per task")
    obs = r["class_rule"]["observable"]
    if obs is not None and (set(obs) != set(r["tasks"]) or any(set(v) - set(classes) for v in obs.values())):
        out.append("class_rule.observable: one entry per task, each a string of listed classes")
    if set(r["tasks_excluded"]) & set(r["tasks"]):
        out.append("a task is both scored and excluded")
    out += cells(r["cells"], r, "reference set")
    tpc = r["trials_per_cell"]
    if isinstance(tpc, dict):
        want = ({f"{p}/{t}" for p in r["policies"] for t in r["tasks"]} if r["cells"] == "all"
                else {f"{p}/{t}" for p, t in r["cells"]})
        if set(tpc) != want:
            out.append("trials_per_cell map must have one '<policy>/<task>' entry per cell")
    out += termination(r["termination_rule"], r["tasks"], "real-side")
    out += repo_file(r["matching_file"], "matching_file")
    return out


MIN_EPISODES = 100          # entries we run or that are submitted; published entries rank from MIN_PUBLISHED
MIN_PUBLISHED = 20          # below it a published entry is listed, not ranked: applied by the scoring code


def check_entry_card(e, index):
    out = []
    if not e["id"].startswith(f"{e['benchmark']}/{e['track']}/"):
        out.append("id must start with <benchmark>/<track>/")
    ref, missing = index.find("reference_set", e["reference_set"]["id"])
    if ref is None:
        return out + [missing]
    if record_sha(ref) != e["reference_set"]["sha256"]:
        out.append(f"reference_set.sha256 differs from the canonical SHA-256 of {ref['id']} ({record_sha(ref)})")
    if (e["benchmark"], e["track"]) != (ref["benchmark"], ref["track"]):
        out.append("benchmark and track must match the reference set")
    if e["kind"] in ("simulator", "world_model") and e["simulator"] is None:
        out.append("simulator is required for kind simulator and world_model")
    # §11.2 episodes_per_cell
    if (e["kind"] in ("simulator", "world_model") and e["provenance"] in ("rerun_by_us", "as_submitted")
            and e["episodes_per_cell"] < MIN_EPISODES):
        out.append(f"episodes_per_cell: an entry we run or that is submitted needs at least {MIN_EPISODES}")
    if e["episodes_per_cell"] < 2:
        out.append("episodes_per_cell: at least 2 for every kind (the noise term of the primary score needs 2)")
    if set(e["checkpoints"]) != set(ref["policies"]):
        out.append("checkpoints must have one entry per policy of the reference set")
    info = e["information_used"]
    if info["class"] == "declared_blind" and info["rule"] is None:
        out.append("information_used: a declared_blind entry names its written information rule")
    out += repo_file(info["rule"], "information_used.rule")
    out += cells(e["cells"], ref, "entry")
    out += termination(e["termination_rule"], ref["tasks"], "entry")
    twin = None
    if e["twin_calibration"] is not None:
        if e["kind"] != "simulator":
            out.append("twin_calibration is given only for kind simulator")
        twin, missing = index.find("twin_calibration", e["twin_calibration"])
        if twin is None:
            out.append(missing)
        elif (twin["simulator"], twin["embodiment"]) != (e["simulator"], ref["embodiment"]):
            out.append("twin calibration: simulator must be the entry's and embodiment the reference set's")
    if e["kind"] == "simulator" and e["ours"] and e["frozen_at"] is not None \
            and (twin is None or twin["status"] != "calibrated"):
        out.append("our frozen simulator entry needs a calibrated twin calibration: without one it is uncalibrated and "
                   "its score is not a comparison result (§13.3)")
    return out


def interval_holds(name, value, ci):
    if value is None or ci is None:
        return []
    return [] if ci[0] <= value <= ci[1] else [f"{name}: the interval does not contain the value"]


def rule_verdict(bias_ci, scatter, scatter_ci, delta):
    """Verdict of the spec/v0.md §7 verdict rule from an entry's own inputs, and the verdicts still possible when it is
    not_determined; FLOOR needs the cell labels and is checked in trust_links. Mirrors the rule in our report
    generator."""
    offset = bias_ci[0] > delta or bias_ci[1] < -delta
    bias_inside = -delta <= bias_ci[0] and bias_ci[1] <= delta
    if scatter_ci is None:
        if offset and scatter > delta:          # the scatter interval could still exclude δ from below
            return "not_determined", ("disagree_offset_and_scatter", "disagree_offset")
        if offset:
            return "disagree_offset", ()
        if scatter > delta:
            return "not_determined", ("disagree_scatter", "inconclusive")
        if bias_inside:
            return "not_determined", ("agree", "inconclusive")
        return "inconclusive", ()
    wide = scatter_ci[0] > delta
    if offset and wide:
        return "disagree_offset_and_scatter", ()
    if offset:
        return "disagree_offset", ()
    if wide:
        return "disagree_scatter", ()
    if bias_inside and scatter_ci[1] <= delta:
        return "agree", ()
    return "inconclusive", ()


def loa_bounds(bias_ci, s_lo, s_hi):
    """(L, U): the lower and upper bounds on the limits of agreement |bias| + 1.96 x scatter, by the union bound of
    spec/v0.md §7 (v0.4): L = dist(0, bias interval) + 1.96 s_lo, U = max |bias interval end| + 1.96 s_hi."""
    lo, hi = bias_ci
    dist0 = 0.0 if lo <= 0 <= hi else min(abs(lo), abs(hi))
    return dist0 + Z_LOA * s_lo, max(abs(lo), abs(hi)) + Z_LOA * s_hi


def loa_rule(bias_ci, scatter_ci, delta):
    """The §7 v0.4 verdict over one set of cells, before the padding check. Mirrors our reference implementation of
    the rule and our report generator."""
    L, U = loa_bounds(bias_ci, *scatter_ci)
    if U <= delta:
        return "agree"
    if L <= delta:
        return "inconclusive"
    scatter = Z_LOA * scatter_ci[0] > delta
    if scatter and (bias_ci[0] > delta or bias_ci[1] < -delta):
        return "disagree_offset_and_scatter"
    if scatter:
        return "disagree_scatter"
    if Z_LOA * scatter_ci[1] <= delta:
        return "disagree_offset"
    return "disagree_unresolved"


def scatter_intervals(point, bias_ci, delta):
    """Scatter intervals [s_lo, s_hi] that contain `point`, at least one in every region where the §7 v0.4 rule's
    result is constant: the rule compares s_lo and s_hi only with the cuts below, so the ends 0, `point` and a value
    above every cut, with each cut and its two neighbouring floats, reach every region."""
    lo, hi = bias_ci
    dist0 = 0.0 if lo <= 0 <= hi else min(abs(lo), abs(hi))
    cuts = [delta / Z_LOA, (delta - dist0) / Z_LOA, (delta - max(abs(lo), abs(hi))) / Z_LOA]
    near = {x for c in cuts for x in (math.nextafter(c, -math.inf), c, math.nextafter(c, math.inf))}
    los = {0.0, point} | {x for x in near if 0 <= x <= point}
    his = {point, max(cuts + [point]) + 1.0} | {x for x in near if x >= point}
    return [(a, b) for a in los for b in his]


def loa_outcomes(bias_ci, scatter, scatter_ci, delta):
    """Results of the §7 v0.4 rule (before the padding check) over every scatter interval consistent with the entry:
    its own interval, or, when that is null, every interval that contains the scatter point."""
    if scatter_ci is not None:
        return {loa_rule(bias_ci, scatter_ci, delta)}
    return {loa_rule(bias_ci, iv, delta) for iv in scatter_intervals(scatter, bias_ci, delta)}


def rule_verdict_loa(t):
    """(verdict, verdicts still possible) of the §7 v0.4 rule on a graded entry's own inputs, the padding check
    included: `floor` when no cell is non-FLOOR; AGREE needs the rule's AGREE over all cells and over the non-FLOOR
    cells, so with fewer than 2 non-FLOOR cells an AGREE becomes INCONCLUSIVE; `not_determined` when a null scatter
    interval leaves more than one verdict possible."""
    nf, delta = t["non_floor"], t["tolerance"]
    if nf["n_cells"] == 0:
        return "floor", ()
    outcomes = loa_outcomes(t["bias"]["ci95"], t["scatter_net"]["value"], t["scatter_net"]["ci95"], delta)
    if "agree" in outcomes:
        pad = ({False} if nf["n_cells"] < 2 else
               {v == "agree" for v in loa_outcomes(nf["bias"]["ci95"], nf["scatter_net"]["value"],
                                                   nf["scatter_net"]["ci95"], delta)})
        outcomes = (outcomes - {"agree"}) | ({"agree"} if True in pad else set()) \
            | ({"inconclusive"} if False in pad else set())
    if len(outcomes) == 1:
        return next(iter(outcomes)), ()
    return "not_determined", tuple(sorted(outcomes))


def demonstrated(t):
    """(delta_agree, delta_disagree) of a graded v0.4 entry (§7): delta_agree = max(U over all cells, U over the
    non-FLOOR cells), null with fewer than 2 non-FLOOR cells or a null scatter interval; delta_disagree = L over all
    cells, null when L is 0 or the scatter interval is null."""
    nf, b, sci = t["non_floor"], t["bias"]["ci95"], t["scatter_net"]["ci95"]
    if sci is None:
        return None, None
    L, U = loa_bounds(b, *sci)
    dA = None
    if nf["n_cells"] >= 2 and nf["scatter_net"]["ci95"] is not None:
        dA = max(U, loa_bounds(nf["bias"]["ci95"], *nf["scatter_net"]["ci95"])[1])
    return dA, (L if L > 0 else None)


def same_number(a, b):
    return (a is None) == (b is None) and (a is None or abs(a - b) <= DELTA_TOL)


def check_loa_entry(t):
    """The v0.4 additions to a trust entry (§7): non-FLOOR inputs, the verdict by the limits-of-agreement rule and the
    demonstrated tolerances."""
    v, nf = t["verdict"], t["non_floor"]
    if v == "not_yet_calibrated":
        if nf is not None or t["delta_agree"] is not None or t["delta_disagree"] is not None:
            return ["a not_yet_calibrated entry has non_floor, delta_agree and delta_disagree null"]
        return []
    if nf is None:
        return ["a verdict other than not_yet_calibrated needs non_floor"]
    out = []
    if nf["n_cells"] > t["n_cells"]:
        out.append("non_floor.n_cells exceeds n_cells")
    if (nf["n_cells"] >= 2) != (nf["bias"] is not None) or (nf["n_cells"] >= 2) != (nf["scatter_net"] is not None):
        return out + ["non_floor.bias and non_floor.scatter_net are given exactly when non_floor.n_cells is at least 2"]
    if nf["bias"] is not None:
        out += interval_holds("non_floor.bias.ci95", nf["bias"]["value"], nf["bias"]["ci95"])
        out += interval_holds("non_floor.scatter_net.ci95", nf["scatter_net"]["value"], nf["scatter_net"]["ci95"])
    if out:
        return out
    want, possible = rule_verdict_loa(t)
    if v != want:
        out.append(f"verdict must be {want} by the §7 limits-of-agreement rule on the entry's bias interval "
                   f"(bias.ci95), scatter, non-FLOOR inputs and tolerance")
    elif v == "not_determined" and set(t["verdict_possible"] or ()) != set(possible):
        out.append(f"verdict_possible must be {', '.join(possible)} by the §7 limits-of-agreement rule")
    dA, dD = demonstrated(t)
    if not same_number(t["delta_agree"], dA):
        out.append(f"delta_agree must be {dA}: max(U over all cells, U over the non-FLOOR cells), null with fewer "
                   f"than 2 non-FLOOR cells or without a scatter interval")
    if not same_number(t["delta_disagree"], dD):
        out.append(f"delta_disagree must be {dD}: L over all cells, null when L is 0 or without a scatter interval")
    return out


def check_trust_entry(t):
    out = []
    scope, target = t["scope"], t["target"]
    if (scope == "failure_type" and target not in FAILURE_TYPES) or (scope == "failure_stage" and target not in ("G", "T", "P")) \
            or (scope == "aggregate" and target is not None):
        out.append("target: a failure type of §2 for scope failure_type, G, T or P for failure_stage, null for aggregate")
    if t["synthetic"]:
        out.append("synthetic must be false: synthetic data never populates a trust entry")
    v = t["verdict"]
    if (v == "not_determined") != (t["verdict_possible"] is not None):
        out.append("verdict_possible is given exactly when the verdict is not_determined")
    if t["verdict_possible"] and set(t["verdict_possible"]) & {"not_determined", "not_yet_calibrated"}:
        out.append("verdict_possible lists only verdicts a rule can reach")
    b, sc = t["bias"], t["scatter_net"]
    if (t["T_k"] is None) != (t["interval"] is None):
        out.append("T_k and its interval are given together")
    if (t["ppv_k"] is None) != (t["ppv_interval"] is None):
        out.append("ppv_k and its interval are given together")
    if v == "not_yet_calibrated":
        if t["n_cells"] or t["n_real_episodes"] or t["tolerance"] is not None or t["fitted"] is not None \
                or any(x is not None for x in (*b.values(), *sc.values(), t["T_k"], t["interval"], t["ppv_k"],
                                               t["ppv_interval"])):
            out.append("a not_yet_calibrated entry has no cells, episodes, tolerance, fitted date or estimates")
    elif t["plan_sha256"] is None or t["kpi"] is None or t["tolerance"] is None:
        out.append("a verdict other than not_yet_calibrated needs plan_sha256, kpi and tolerance")
    elif b["ci95"] is None or sc["value"] is None or t["n_cells"] == 0 or t["n_real_episodes"] == 0:
        out.append("a verdict other than not_yet_calibrated needs the bias interval (bias.ci95), scatter and at least "
                   "one cell")
    elif t["spec_version"] == "v0.4":
        out += check_loa_entry(t)
    elif v != "floor":
        want, possible = rule_verdict(b["ci95"], sc["value"], sc["ci95"], t["tolerance"])
        if v != want:
            out.append(f"verdict must be {want} by the §6.3 rule on the entry's bias interval (bias.ci95), scatter "
                       f"and tolerance")
        elif v == "not_determined" and set(t["verdict_possible"] or ()) != set(possible):
            out.append(f"verdict_possible must be {', '.join(possible)} by the §6.3 rule")
    if t["spec_version"] == "v0.4" and v == "not_yet_calibrated":
        out += check_loa_entry(t)
    if t["kpi"] is not None and t["plan_sha256"] is None:
        out.append("kpi names a KPI of a plan, so plan_sha256 is required")
    out += interval_holds("bias.ci95", b["value"], b["ci95"])
    out += interval_holds("bias.ci95_clustered", b["value"], b["ci95_clustered"])
    out += interval_holds("scatter_net.ci95", sc["value"], sc["ci95"])
    out += interval_holds("interval", t["T_k"], t["interval"])
    out += interval_holds("ppv_interval", t["ppv_k"], t["ppv_interval"])
    return out


def check_cell_agreement(c):
    out = []
    for side in ("sim", "real", "real_repeat"):
        if c[side] is not None and c[side]["k"] > c[side]["n"]:
            out.append(f"{side}: k exceeds n")
    sc = c["stage_counts"]
    if sc is not None and any(set(sc[s]) - set(STAGE_CLASSES) for s in ("sim", "real")):
        out.append("stage_counts: keys are stage classes G, T, P, S")
    out += interval_holds("interval", c["d"], c["interval"])
    return out


def check_plan(a):
    out = []
    ids = [k["id"] for k in a["kpis"]]
    if len(set(ids)) != len(ids):
        out.append("KPI ids repeat")
    for k in a["kpis"]:
        if (k["kind"] == "failure_type" and k["target"] not in FAILURE_TYPES) \
                or (k["kind"] == "failure_stage" and k["target"] not in ("G", "T", "P")) \
                or (k["kind"] == "aggregate" and k["target"] is not None):
            out.append(f"KPI {k['id']}: target must suit kind {k['kind']}")
        if k["kind"] != "aggregate" and k["tolerance"] is None:
            out.append(f"KPI {k['id']}: a failure-type or stage KPI declares its tolerance")
    out += termination(a["subject"]["termination_rule"], a["subject"]["tasks"], "subject")
    out += termination(a["referent"]["termination_rule"], a["subject"]["tasks"], "referent")
    out += repo_file(a["source_document"], "source_document")
    return out


def check_manifest(m):
    if not m["disclosed"] and m["items"]:
        return ["an undisclosed calibration history has no items"]
    return []


def twin_gaps(r):
    """What keeps a twin calibration record from status calibrated (§13.3): an item not measured on the physical
    setup, a missing value, or a check outside its §13.2 tolerance. Empty exactly when the twin is calibrated."""
    gaps = []
    j, c, a, s = r["joints"], r["control"], r["actuators"], r["scene"]
    items = [("joints", j), ("control", c), ("actuators", a), ("scene", s)]
    items += [(f"camera {x['id']}", x) for x in r["cameras"]]
    for name, item in items:
        if item["source"] not in MEASURED:
            gaps.append(f"{name}: source {item['source']}; only data measured on the physical setup by its operator or "
                        f"by us count")
        if item["method"] is None:
            gaps.append(f"{name}: method not stated")
    if r["synthetic"]:
        gaps.append("synthetic: a synthetic record never calibrates a twin")
    if r["robot_unit"] is None:
        gaps.append("robot_unit: the physical arm is not identified")
    if j["file"] is None or j["file_format"] is None:
        gaps.append("joints: no calibration file with its format")
    if len(j["reference_poses"]) < MIN_REFERENCE_POSES:
        gaps.append(f"joints: {len(j['reference_poses'])} reference poses; at least {MIN_REFERENCE_POSES}")
    for p in j["reference_poses"]:
        if p["point_xyz_m"] is None or p["evidence"] is None or p["gripper_error_mm"] is None:
            gaps.append(f"reference pose {p['id']}: needs the measured point, its evidence and the gripper error")
        elif p["gripper_error_mm"] > MAX_GRIPPER_MM:
            gaps.append(f"reference pose {p['id']}: gripper error {p['gripper_error_mm']} mm above {MAX_GRIPPER_MM} mm")
    unset = [k for k in ("software", "gains", "control_hz", "speed_limits", "image_preprocessing") if c[k] is None]
    if unset:
        gaps.append(f"control: {', '.join(unset)} not stated")
    if c["twin_uses"] is not True:
        gaps.append("control: the twin's controller is not stated to use these settings")
    if a["excitation"] is None or a["parameters"] is None or a["replay"] is None:
        gaps.append("actuators: needs the excitation recording, the fitted parameters and a replay check")
    if not all(v is True for v in a["excites"].values()):
        gaps.append("actuators: the excitation recording must cover every joint, varied speeds, reversals and gripper "
                    "cycles, on the deployed control stack")
    if a["replay"] is not None:
        if a["excitation"] is not None and a["replay"]["recording"]["sha256"] == a["excitation"]["sha256"]:
            gaps.append("actuators: the replay check uses the fitted recording; it needs one not used in the fit")
        high = sorted(k for k, v in a["replay"]["rms_deg"].items() if v > MAX_REPLAY_DEG)
        if high:
            gaps.append(f"actuators: replay tracking error above {MAX_REPLAY_DEG} deg for {', '.join(high)}")
    recording = [x["id"] for x in r["sessions"] if x["kind"] == "recording"]
    if not recording:
        gaps.append("sessions: no recording session, so no camera drift check was made")
    for x in r["cameras"]:
        unset = [k for k in ("board_images", "board", "n_images", "focus_locked", "intrinsics", "reprojection_rms_px",
                             "pose", "pose_method", "pose_error_mm") if x[k] is None]
        if unset:
            gaps.append(f"camera {x['id']}: {', '.join(unset)} not stated")
        if x["n_images"] is not None and x["n_images"] < MIN_BOARD_IMAGES:
            gaps.append(f"camera {x['id']}: {x['n_images']} board images; at least {MIN_BOARD_IMAGES}")
        if x["focus_locked"] is False:
            gaps.append(f"camera {x['id']}: focus not locked, so the intrinsics do not hold")
        if x["pose_error_mm"] is not None and x["pose_error_mm"] > MAX_CAMERA_POSE_MM:
            gaps.append(f"camera {x['id']}: pose error {x['pose_error_mm']} mm above {MAX_CAMERA_POSE_MM} mm")
        unchecked = [k for k in recording if k not in x["session_drift_px"]]
        if unchecked:
            gaps.append(f"camera {x['id']}: no drift check for recording sessions {', '.join(unchecked)}")
        high = sorted(k for k, v in x["session_drift_px"].items() if v > MAX_DRIFT_PX)
        if high:
            gaps.append(f"camera {x['id']}: drift above {MAX_DRIFT_PX} px in sessions {', '.join(high)}")
    for o in s["fixed_objects"]:
        if o["size_m"] is None or o["pose"] is None or o["pose_method"] is None or o["touch_error_mm"] is None:
            gaps.append(f"fixed object {o['name']}: needs size, pose, pose method and touch error")
        elif o["touch_error_mm"] > MAX_TOUCH_MM:
            gaps.append(f"fixed object {o['name']}: touch error {o['touch_error_mm']} mm above {MAX_TOUCH_MM} mm")
    for o in s["task_objects"]:
        if o["size_m"] is None or o["mass_kg"] is None:
            gaps.append(f"task object {o['name']}: needs measured size and mass")
    lay = s["layouts"]
    if lay["method"] is None or lay["record"] is None or lay["episodes"] == 0 \
            or lay["episodes_recorded"] != lay["episodes"]:
        gaps.append(f"scene: starting layouts recorded for {lay['episodes_recorded']} of {lay['episodes']} episodes, "
                    f"with method and record; every episode needs one")
    return gaps


def check_twin(r):
    """Rules of spec/v0.md §13 within one twin calibration record."""
    out = []
    names = r["joints"]["names"]
    if len(set(names)) != len(names):
        out.append("joints.names repeat")
    keyed = [("reference pose " + p["id"], p["joints"]) for p in r["joints"]["reference_poses"]]
    keyed += [("control.gains", r["control"]["gains"] or dict.fromkeys(names))]
    keyed += [("actuators.replay.rms_deg", (r["actuators"]["replay"] or {}).get("rms_deg") or dict.fromkeys(names))]
    out += [f"{where}: keys must be the joint names" for where, m in keyed if set(m) != set(names)]
    for what, ids in (("sessions", [x["id"] for x in r["sessions"]]), ("cameras", [x["id"] for x in r["cameras"]]),
                      ("reference poses", [p["id"] for p in r["joints"]["reference_poses"]]),
                      ("scene objects", [o["name"] for o in r["scene"]["fixed_objects"] + r["scene"]["task_objects"]])):
        if len(set(ids)) != len(ids):
            out.append(f"{what}: ids repeat")
    recording = {x["id"] for x in r["sessions"] if x["kind"] == "recording"}
    for x in r["cameras"]:
        if set(x["session_drift_px"]) - recording:
            out.append(f"camera {x['id']}: session_drift_px keys must be recording sessions")
    poses = [(f"camera {x['id']}", x["pose"]) for x in r["cameras"]]
    poses += [(f"fixed object {o['name']}", o["pose"]) for o in r["scene"]["fixed_objects"]]
    for where, pose in poses:
        if pose is not None and abs(math.sqrt(sum(q * q for q in pose["quat_wxyz"])) - 1) > 1e-3:
            out.append(f"{where}: pose quaternion is not of unit length")
    lay = r["scene"]["layouts"]
    if lay["episodes_recorded"] > lay["episodes"]:
        out.append("scene.layouts: episodes_recorded exceeds episodes")
    gaps = twin_gaps(r)
    if r["status"] == "calibrated":
        out += [f"status calibrated, but {g}" for g in gaps]
    elif not gaps:
        out.append("status must be calibrated: every item is measured, complete and within tolerance")
    return out


def check_episode(e):
    """Rules of spec/v0.md §8 within one episode record."""
    out, o = [], e["outcome"]
    if any(p["name"] not in e["factors"] for p in e["perturbed"]):
        out.append("perturbed names a factor that is not in factors")
    if len({p["name"] for p in e["perturbed"]}) != len(e["perturbed"]):
        out.append("perturbed repeats a factor")
    violated = [k for k, v in o["constraint_margins"].items() if v is not None and v < 0]
    if o["success"]:
        if violated:
            out.append(f"success with a violated constraint ({', '.join(violated)}): §4 makes it a constraint failure")
        if o["stage_class"] != "S" or o["first_failed"] is not None:
            out.append("a success has stage_class S and no first_failed")
    elif o["first_failed"] is None and o["checker"] in PILOT_LIKE:
        out.append(f"a {o['checker']} failure names its first failed predicate")
    if o["checker"] in PILOT_LIKE and (o["episode_margin"] > 0) != o["success"]:
        out.append(f"a {o['checker']} margin is positive exactly on success")
    if o["checker"] == "spec_v0_grammar" and o["goal_margin"] is None:
        out.append("a spec_v0_grammar checker reports goal_margin")
    if not e["synthetic"] and e["policy"]["family"] is None:
        out.append("a non-synthetic record names its policy family: without one it cannot be told from a scripted run")
    if e["real_rerun"] is not None and e["synthetic"]:
        out.append("a real rerun is never synthetic")
    if e["spec_version"] in ("v0.1", "v0.2", "v0.3"):
        out += check_episode_v0_1(e)
    if e["spec_version"] in ("v0.2", "v0.3"):
        out += check_episode_v0_2(e)
    if e["spec_version"] == "v0.3":
        out += check_episode_v0_3(e)
    return out


def check_episode_v0_3(e):
    """Rules of the v0.3 field (spec/v0.md §8.1): `generator.seedless` true exactly when `generator.seeds` is empty."""
    g = e["generator"]
    if g is None:
        return []
    if g.get("seedless", False):
        return [] if not g["seeds"] else ["generator.seedless true: a generator that draws no random number lists no "
                                          "seeds (seeds is {})"]
    return [] if g["seeds"] else ["generator.seeds: empty only with generator.seedless true (a generator that draws "
                                  "no random number says so); otherwise it names at least one base-scene seed"]


def check_episode_v0_2(e):
    """Rules of the v0.2 fields (spec/v0.md §8.1): where the outcome came from, the option hash, and the stage map of
    molmospaces_pnp_port_v1 (§8.4)."""
    out, o = [], e["outcome"]
    if e["simulated"] and e["real_rerun"] is not None:
        out.append("simulated: a simulated episode has no real_rerun block (real reruns are simulated: false)")
    if not e["simulated"]:
        if e["real_rerun"] is None and not e["synthetic"]:
            out.append("simulated false: v0.2 defines real measurements only as real reruns (real_rerun required)")
        if e["simulator"]["physics_options_sha256"] is not None:
            out.append("simulator.physics_options_sha256: a real episode ran no simulator options")
    if o["checker"] != PNP:
        return out
    reached = o["stage_reached"]
    if reached not in ("none",) + PNP_STAGES:
        out.append(f"{PNP}: stage_reached is one of none, {', '.join(PNP_STAGES)}")
        return out
    if o["goal_margin"] is not None:
        out.append(f"{PNP}: goal_margin is null (the margin is stage progress, §8.4)")
    if o["constraint_margins"]:
        out.append(f"{PNP}: constraint_margins is empty (the receptacle limits are goal terms, §8.4)")
    n_reached = 0 if reached == "none" else PNP_STAGES.index(reached) + 1
    if set(o["stage_times"]) != set(PNP_STAGES[:n_reached]):
        out.append(f"{PNP}: stage_times lists exactly the stages reached")
    else:
        times = [o["stage_times"][s] for s in PNP_STAGES[:n_reached]]
        if any(b < a for a, b in zip(times, times[1:])):
            out.append(f"{PNP}: stage_times do not decrease in stage order (each stage is reached at or after the last)")
    if o["success"]:
        if o["terminal_class"] is not None:
            out.append(f"{PNP}: a success has no terminal class")
        if o["episode_margin"] != 1:
            out.append(f"{PNP}: a success has episode_margin 1")
        if reached == "support":
            out.append(f"{PNP}: a success that reached support also reaches finish at the last step")
        return out
    if reached == "finish":
        out.append(f"{PNP}: stage finish is the goal at the last step, so a failure never reaches it")
        return out
    cls, terminals, first_stage = PNP_FAILURE[reached]
    if o["stage_class"] != cls:
        out.append(f"{PNP}: a failure that reached {reached} has stage_class {cls}")
    if o["terminal_class"] not in terminals:
        out.append(f"{PNP}: a failure that reached {reached} has terminal_class {' or '.join(terminals)}")
    ff = o["first_failed"]
    if ff is not None:
        if ff["stage"] != first_stage:
            out.append(f"{PNP}: first_failed.stage is the first stage not reached ({first_stage})")
        if o["terminal_class"] in PNP_PREDICATES and ff["predicate"] not in PNP_PREDICATES[o["terminal_class"]]:
            out.append(f"{PNP}: first_failed.predicate of {o['terminal_class']} is "
                       f"{' or '.join(PNP_PREDICATES[o['terminal_class']])}")
    if o["episode_margin"] != -(4 - n_reached) / 4:
        out.append(f"{PNP}: a failure that reached {n_reached} of 4 stages has episode_margin {-(4 - n_reached) / 4}")
    return out


def check_episode_v0_1(e):
    """Rules of the v0.1 fields (spec/v0.md §8.1): device, events, fork, trace and scene seeds."""
    out, c = [], e["compute"]
    dev, ks = c["inference_device"], c["kernel_settings"]
    if dev == "none":
        if e["policy"]["checkpoint_sha256"] is not None:
            out.append("compute.inference_device none: a policy with weights names the device that ran them")
    elif c["device_name"] is None:
        out.append(f"compute.device_name: a {dev} device is named (model, and for a GPU its architecture)")
    if dev == "cuda":
        if "CUBLAS_WORKSPACE_CONFIG" not in ks:
            out.append("compute.kernel_settings: a cuda record states CUBLAS_WORKSPACE_CONFIG (null when unset)")
        if not c["toolkit"]:
            out.append("compute.toolkit: a cuda record names its toolkit versions (CUDA, cuDNN, driver, framework)")
    last = -1.0
    for i, ev in enumerate(e["events"]):
        m = TRIGGER.fullmatch(ev["trigger"])
        if m is None:
            out.append(f"events[{i}].trigger is `time:<seconds>` or `stage:<stage id>`")
        elif m.group(3) is not None and ev["stage"] != m.group(3):
            out.append(f"events[{i}]: a stage trigger fires in its own stage")
        if ev["factor"] not in e["factors"]:
            out.append(f"events[{i}].factor names a factor that is not in factors")
        if ev["applied"] == (ev["reason"] is not None):
            out.append(f"events[{i}]: an event not applied gives its reason; an applied event gives none")
        if ev["t"] < last:
            out.append(f"events[{i}]: events are in time order")
        last = ev["t"]
    if (e["events"] or e["fork"] is not None) and e["scene_seeds"] is None:
        out.append("scene_seeds: a record with events or a fork carries the seed list that draws its scene")
    f = e["fork"]
    if f is not None and f["snapshot_sha256"] is None and f.get("snapshot_hash_version") is not None:
        out.append("fork.snapshot_hash_version: a fork without a snapshot hash (the start boundary) names no hash version")
    if f is not None and f["snapshot_sha256"] is not None and "snapshot_hash_version" in f \
            and f["snapshot_hash_version"] is None:
        out.append("fork.snapshot_hash_version: null only without a snapshot hash; with one it is 1 or 2, or absent (1)")
    if (e["trace_sha256"] is None) != (e["trace_method"] is None):
        out.append("trace_sha256 and trace_method are given together: a hash without its definition cannot be checked")
    return out


SINGLE = {"episode": check_episode, "reference_set": check_reference_set, "trust_entry": check_trust_entry,
          "cell_agreement": check_cell_agreement, "assessment_plan": check_plan, "calibration_manifest": check_manifest,
          "twin_calibration": check_twin}


class Index:
    """Records that passed their own checks, by kind and key (id or canonical SHA-256), and keys that failed."""

    def __init__(self):
        self.ok, self.failed = {}, set()

    def add(self, rec, passed):
        kind = rec["record"]
        keys = [record_sha(rec)] + ([rec["id"]] if isinstance(rec.get("id"), str) else [])
        for key in keys:
            if passed:
                self.ok[kind, key] = rec
            else:
                self.failed.add((kind, key))

    def find(self, kind, key):
        """(record, None), or (None, the problem)."""
        if (kind, key) in self.ok:
            return self.ok[kind, key], None
        why = "failed validation" if (kind, key) in self.failed else "is not among the records validated"
        return None, f"{kind.replace('_', ' ')} {key} {why}"


def calibration_cells(manifest, plan):
    """Cells (policy, task) the manifest lists as used to tune, or None if the history is not disclosed."""
    if manifest is None or not manifest["disclosed"]:
        return None
    every = {(p, t) for p in plan["subject"]["policies"] for t in plan["subject"]["tasks"]}
    out = set()
    for item in manifest["items"]:
        out |= every if item["cells"] == "all" else {tuple(c) for c in item["cells"] or ()}
    return out


def plan_links(a, index):
    out = []
    if a["subject"]["twin_calibration"] is not None:
        twin, missing = index.find("twin_calibration", a["subject"]["twin_calibration"])
        if twin is None:
            out.append(missing)
        elif (twin["simulator"], twin["embodiment"]) != (a["subject"]["simulator"], a["subject"]["embodiment"]):
            out.append("twin calibration: simulator and embodiment must match the subject")
    if a["calibration_manifest"] is None:
        return out
    manifest, missing = index.find("calibration_manifest", a["calibration_manifest"])
    if manifest is None:
        return out + [missing]
    if (manifest["simulator"], manifest["embodiment"]) != (a["subject"]["simulator"], a["subject"]["embodiment"]):
        out.append("calibration manifest: simulator and embodiment must match the subject")
    listed = {tuple(c) for item in manifest["items"] if isinstance(item["cells"], list) for c in item["cells"]}
    bad = listed - {(p, t) for p in a["subject"]["policies"] for t in a["subject"]["tasks"]}
    if bad:
        out.append(f"calibration manifest: cells {sorted(bad)} are not cells of the subject")
    return out


def plan_manifest(a, index):
    return index.ok.get(("calibration_manifest", a["calibration_manifest"])) if a["calibration_manifest"] else None


def cell_links(c, index, seen):
    plan, missing = index.find("assessment_plan", c["assessment_id"])
    if plan is None:
        return [missing]
    out = []
    key = (c["assessment_id"], c["kpi"], c["cell"]["policy"], c["cell"]["task"], c["cell"]["condition"])
    if key in seen:
        out.append("duplicate cell for this assessment and KPI")
    seen.add(key)
    kpi = next((k for k in plan["kpis"] if k["id"] == c["kpi"]), None)
    if kpi is None:
        out.append(f"kpi {c['kpi']} is not a KPI of the plan")
    elif kpi["statistic"] == "rate_difference" and abs(c["d"] - (c["sim"]["k"] / c["sim"]["n"] - c["real"]["k"] / c["real"]["n"])) > 1e-9:
        out.append("d must equal sim rate minus real rate")
    subj = plan["subject"]
    if c["cell"]["policy"] not in subj["policies"] or c["cell"]["task"] not in subj["tasks"] \
            or c["cell"]["embodiment"] != subj["embodiment"]:
        out.append("cell: policy, task and embodiment must be the plan subject's")
    tuned = calibration_cells(plan_manifest(plan, index), plan)
    if tuned is not None and c["in_calibration"] != ((c["cell"]["policy"], c["cell"]["task"]) in tuned):
        out.append("in_calibration must be true exactly for cells the calibration manifest lists")
    return out


def plan_twin_status(plan, index):
    """`calibrated` when the plan links a calibrated twin calibration record, else `uncalibrated` (§13.3)."""
    ref = plan["subject"]["twin_calibration"]
    twin = index.ok.get(("twin_calibration", ref)) if ref else None
    return twin["status"] if twin else "uncalibrated"


def trust_links(t, index, cell_records, cells_failed):
    if t["plan_sha256"] is None:
        out = ["assessment_id is given only with plan_sha256"] if t["assessment_id"] is not None else []
        if t["twin_calibration"] != "uncalibrated":
            out.append("twin_calibration must be 'uncalibrated': no plan links a twin calibration")
        return out
    plan, missing = index.find("assessment_plan", t["plan_sha256"])
    if plan is None:
        by_id = index.ok.get(("assessment_plan", t["assessment_id"]))
        if by_id is not None:
            return [f"plan_sha256 differs from the canonical SHA-256 of plan {by_id['id']} ({record_sha(by_id)})"]
        return [missing]
    out = []
    if t["assessment_id"] != plan["id"]:
        out.append("assessment_id must be the plan's id")
    if (t["simulator"], t["embodiment"]) != (plan["subject"]["simulator"], plan["subject"]["embodiment"]):
        out.append("simulator and embodiment must be the plan subject's")
    if (t["pairing"], t["referent"]["independent_of_vendor"]) != (plan["referent"]["pairing"],
                                                                  plan["referent"]["independent_of_vendor"]):
        out.append("pairing and referent independence must be the plan's")
    if t["kpi"] is not None:
        kpi = next((k for k in plan["kpis"] if k["id"] == t["kpi"]), None)
        if kpi is None:
            out.append(f"kpi {t['kpi']} is not a KPI of the plan")
        elif (kpi["kind"], kpi["target"], kpi["tolerance"]) != (t["scope"], t["target"], t["tolerance"]):
            out.append("scope, target and tolerance must be the plan KPI's")
        elif t["scope"] == "aggregate" and kpi["statistic"] != "rate_difference":
            out.append("an aggregate KPI carries a trust entry only when its statistic is rate_difference (§12.4 item 4)")
        cells = [c for c in cell_records if (c["assessment_id"], c["kpi"]) == (plan["id"], t["kpi"])
                 and not c["in_calibration"]]
        if cells and (t["verdict"] == "floor") != all(c["label"] == "FLOOR" for c in cells):
            out.append("verdict is floor exactly when every cell is FLOOR")
        non_floor = sum(c["label"] != "FLOOR" for c in cells)
        if cells and t["spec_version"] == "v0.4" and t["non_floor"] is not None \
                and t["non_floor"]["n_cells"] != non_floor and (plan["id"], t["kpi"]) not in cells_failed:
            out.append(f"non_floor.n_cells must count the plan's cell agreement records not labelled FLOOR ({non_floor})")
        if (plan["id"], t["kpi"]) in cells_failed:
            out.append("n_cells not checked: a cell agreement record of this plan and KPI failed validation")
        elif cells and (t["n_cells"], t["n_real_episodes"]) != (len(cells), sum(c["real"]["n"] for c in cells)):
            out.append(f"n_cells and n_real_episodes must count the plan's cell agreement records "
                       f"({len(cells)}, {sum(c['real']['n'] for c in cells)})")
    twin = plan_twin_status(plan, index)
    if t["twin_calibration"] != twin:
        out.append(f"twin_calibration must be {twin!r}, the plan's twin calibration status")
    if twin == "uncalibrated" and plan["status"] in REPORTED and t["verdict"] != "not_yet_calibrated":
        out.append(f"a {plan['status']} plan on an uncalibrated twin reports no comparison result: the verdict is "
                   f"not_yet_calibrated (§13.3)")
    manifest = plan_manifest(plan, index)
    want = False if manifest is not None and manifest["disclosed"] else "unknown"
    if t["calibration_overlap"] != want:
        out.append(f"calibration_overlap must be {want!r}: the plan's calibration history is "
                   + ("disclosed" if want is False else "not disclosed"))
    return out


def validate(records):
    """Problems per record name, for a dict name -> record."""
    problems, index = {}, Index()
    for name, rec in records.items():
        kind = rec.get("record") if isinstance(rec, dict) else None
        schema = schema_of(rec)
        if schema is None:
            problems[name] = [f"`record` must be one of {', '.join(SCHEMAS)}"]
            continue
        body = {k: v for k, v in rec.items() if not (kind == "episode" and k.startswith("x."))}
        problems[name] = fields(body, schema)
        if not problems[name] and kind in SINGLE:
            problems[name] += SINGLE[kind](rec)
        if kind in ("reference_set", "calibration_manifest", "twin_calibration"):
            index.add(rec, not problems[name])
    valid = lambda kind: [(n, r) for n, r in records.items() if not problems[n] and r["record"] == kind]
    for name, rec in valid("assessment_plan"):
        problems[name] += plan_links(rec, index)
    for name, rec in records.items():
        if isinstance(rec, dict) and rec.get("record") == "assessment_plan":
            index.add(rec, not problems[name])
    for name, rec in valid("entry_card"):
        problems[name] += check_entry_card(rec, index)
    seen = set()
    for name, rec in valid("cell_agreement"):
        problems[name] += cell_links(rec, index, seen)
    cell_records = [r for _, r in valid("cell_agreement")]
    cells_failed = {(r.get("assessment_id"), r.get("kpi")) for n, r in records.items()
                    if problems[n] and isinstance(r, dict) and r.get("record") == "cell_agreement"}
    for name, rec in valid("trust_entry"):
        problems[name] += trust_links(rec, index, cell_records, cells_failed)
    return problems


# The WidowX example's graded entry as a v0.4 export (§7): the non-FLOOR inputs over its 14 non-FLOOR cells and the
# demonstrated tolerances, as computed by the reference implementation of the rule (same intervals, seeds as the
# example's). The non-FLOOR bias value is the mean of d over those cells (-1.50 / 14), as §7 defines bias and as the
# published entry gives it over all cells; delta_agree uses the intervals only. The verdict stays disagree_scatter.
WIDOWX_V0_4 = {
    "spec_version": "v0.4", "verdict_rule": "limits_of_agreement", "loa_method": "union_bound",
    "non_floor": {"n_cells": 14,
                  "bias": {"value": -0.10714285714285714, "ci95": [-0.14177219606773236, -0.06831183754571299]},
                  "scatter_net": {"value": 0.4788519633018395, "ci95": [0.4401165266801726, 0.5138002824633572]}},
    "delta_agree": 1.1488207496959124, "delta_disagree": 0.6945075165582807,
}
WIDOWX_V0_4_UNCALIBRATED = {"spec_version": "v0.4", "verdict_rule": "limits_of_agreement", "loa_method": "union_bound",
                            "non_floor": None, "delta_agree": None, "delta_disagree": None}


def as_v0_4(t, **fields):
    """A trust entry exported as v0.4 in memory: the v0.4 fields of the WidowX example (or null for a
    not_yet_calibrated entry), then `fields`; delta_agree and delta_disagree recomputed when `recompute` is true."""
    recompute = fields.pop("recompute", False)
    t.update(copy.deepcopy(WIDOWX_V0_4_UNCALIBRATED if t["verdict"] == "not_yet_calibrated" else WIDOWX_V0_4))
    t.update(fields)
    if recompute:
        t["delta_agree"], t["delta_disagree"] = demonstrated(t)
    return t


def complete_twin(t, simulator=None, embodiment=None):
    """Fill a twin calibration record so that every item is measured, complete and within tolerance. Values are
    invented to exercise the rules; the record exists only in the self-test's memory."""
    pin = lambda name: {"location": f"selftest/{name}", "sha256": hashlib.sha256(name.encode()).hexdigest()}
    names = t["joints"]["names"]
    pose = {"xyz_m": [0.3, 0.0, 0.5], "quat_wxyz": [1.0, 0.0, 0.0, 0.0]}
    t.update(status="calibrated", robot_unit="selftest arm", synthetic=False,
             sessions=[{"id": "cal", "date": "2026-11-24", "kind": "calibration"},
                       {"id": "rec", "date": "2026-11-24", "kind": "recording"}])
    if simulator is not None:
        t.update(simulator=copy.deepcopy(simulator), embodiment=embodiment)
    t["joints"].update(source="us", method="x", file=pin("arm.json"), file_format="x", reference_poses=[
        {"id": f"p{i}", "joints": dict.fromkeys(names, 0.0), "point_xyz_m": [0.2, 0.0, 0.1], "evidence": pin(f"p{i}"),
         "gripper_error_mm": 3.0} for i in range(MIN_REFERENCE_POSES)])
    t["control"].update(source="operator", method="x", software={"name": "x", "version": "1"},
                        gains={n: {"p": 16, "i": 0, "d": 32} for n in names}, control_hz=30, speed_limits="none",
                        image_preprocessing="none", twin_uses=True)
    t["actuators"].update(source="us", method="x", excitation=pin("excitation"), parameters=pin("parameters"),
                          excites=dict.fromkeys(t["actuators"]["excites"], True),
                          replay={"recording": pin("held out"), "rms_deg": dict.fromkeys(names, 0.4)})
    for c in t["cameras"]:
        c.update(source="us", method="x", board_images=pin(c["id"]), board="charuco", n_images=MIN_BOARD_IMAGES,
                 focus_locked=True, intrinsics={"model": "x", "width": 640, "height": 480, "fx": 500.0, "fy": 500.0,
                                                "cx": 320.0, "cy": 240.0, "distortion": [0.0] * 5},
                 reprojection_rms_px=0.3, pose=copy.deepcopy(pose), pose_method="x", pose_error_mm=3.0,
                 session_drift_px={"rec": 1.0})
    sc = t["scene"]
    sc.update(source="us", method="x")
    for o in sc["fixed_objects"]:
        o.update(size_m=[0.1, 0.1, 0.1], pose=copy.deepcopy(pose), pose_method="measured", touch_error_mm=6.0)
    for o in sc["task_objects"]:
        o.update(size_m=[0.03, 0.03, 0.08], mass_kg=0.05)
    sc["layouts"].update(method="measured", record=pin("layouts"), episodes_recorded=sc["layouts"]["episodes"])


def selftest(records):
    """Faults applied one at a time to a copy of the records; each must be rejected. Then valid variants that must be
    accepted. Returns failures and the two counts."""
    def first(kind, test=lambda r: True):
        return next(n for n, r in records.items() if r["record"] == kind and test(r))

    ref, card, plan, manifest = (first(k) for k in ("reference_set", "entry_card", "assessment_plan",
                                                     "calibration_manifest"))
    cell = first("cell_agreement")
    won = first("episode", lambda r: r["outcome"]["success"])
    lost = first("episode", lambda r: not r["outcome"]["success"])
    v1 = lambda r: r["spec_version"] == "v0.1"
    won1 = first("episode", lambda r: v1(r) and r["outcome"]["success"] and r["compute"]["inference_device"] == "cuda")
    lost1 = first("episode", lambda r: v1(r) and not r["outcome"]["success"])
    graded = first("trust_entry", lambda r: r["verdict"] != "not_yet_calibrated")
    uncalibrated = first("trust_entry", lambda r: r["verdict"] == "not_yet_calibrated")
    twin = first("twin_calibration")

    def setter(name, path, value):
        def apply(recs):
            obj = recs[name]
            for k in path[:-1]:
                obj = obj[k]
            if value is KeyError:
                del obj[path[-1]]
            else:
                obj[path[-1]] = value
        return name, apply

    def rank_entry(recs):   # the plan's rank KPI given a tolerance, and the graded entry pointed at it
        recs[plan]["kpis"][1]["tolerance"] = recs[graded]["tolerance"]
        for r in recs.values():
            if r["record"] == "trust_entry":
                r["plan_sha256"] = record_sha(recs[plan])
        recs[graded]["kpi"] = recs[plan]["kpis"][1]["id"]

    def disclose(recs):   # disclosed history listing the first cell; the plan and trust links follow the new hashes
        recs[manifest].update(disclosed=True, items=[{"data": "x", "cells": [[recs[cell]["cell"]["policy"],
                                                     recs[cell]["cell"]["task"]]], "parameters": None, "purpose": "x"}])
        recs[plan]["calibration_manifest"] = record_sha(recs[manifest])
        for r in recs.values():
            if r["record"] == "trust_entry":
                r["plan_sha256"] = record_sha(recs[plan])
                r["calibration_overlap"] = False

    def complete(fault=None):   # the twin made complete, then one fault applied to it
        def apply(recs):
            complete_twin(recs[twin])
            if fault:
                fault(recs[twin])
        return twin, apply

    def link_plan(status, twin_fault=None, label="calibrated", complete_it=True):
        """The plan given a status and linked to the twin (made complete for the plan's subject unless complete_it is
        false); trust entries follow the new plan hash and carry `label`."""
        def apply(recs):
            subject = recs[plan]["subject"]
            if complete_it:
                complete_twin(recs[twin], subject["simulator"], subject["embodiment"])
            if twin_fault:
                twin_fault(recs[twin])
            subject["twin_calibration"] = record_sha(recs[twin])
            recs[plan]["status"] = status
            for r in recs.values():
                if r["record"] == "trust_entry":
                    r.update(plan_sha256=record_sha(recs[plan]), twin_calibration=label)
        return apply

    def customer_uncalibrated(recs):   # a customer plan with no twin calibration; trust entries follow its hash
        recs[plan]["status"] = "customer_final"
        for r in recs.values():
            if r["record"] == "trust_entry":
                r["plan_sha256"] = record_sha(recs[plan])

    def link_card(ours=True, frozen=True, complete_it=True, simulator=None):
        def apply(recs):
            if complete_it:
                complete_twin(recs[twin], simulator or recs[card]["simulator"], recs[ref]["embodiment"])
            elif simulator is None:
                recs[twin].update(simulator=copy.deepcopy(recs[card]["simulator"]), embodiment=recs[ref]["embodiment"])
            recs[card].update(twin_calibration=record_sha(recs[twin]), ours=ours,
                              frozen_at="2026-11-24 12:00:00 UTC" if frozen else None)
        return apply

    def camera(**values):   # the twin made complete, then its first camera changed
        return complete(lambda t: t["cameras"][0].update(**values))

    def uncalibrate(t):   # one item inferred, so the twin is uncalibrated
        t["joints"]["source"] = "inferred"
        t["status"] = "uncalibrated"

    def drop(path):
        def apply(t):
            obj = t
            for k in path[:-1]:
                obj = obj[k]
            obj[path[-1]] = None
        return apply

    def event(name, recs):   # one applied stage-triggered event on the record's first factor (invented values)
        factor = next(iter(recs[name]["factors"]))
        return {"id": "light_change", "factor": factor, "trigger": "stage:lift", "t": 5.9, "block": 59,
                "stage": "lift", "v": 0.305142, "value": 0.929601, "applied": True, "reason": None, "chunk_phase": 1,
                "draw_seed": [20261127, 1, 2, 1, 1, 0]}

    def replay_record(recs):   # a branch record with every replay field, invented values
        recs[lost1].update(events=[event(lost1, recs)], fork=dict(FORK_EXAMPLE), scene_seeds=[20261127, 1, 2, 1, 0, 0],
                           trace_sha256="b66eb388ca0ba3f88e5b13f2d3fc44c863864690c8aa2f5b05fdce1a04efa086",
                           trace_method="per-block digest chain (example)",
                           operating_conditions={"id": "kitchen-v0", "sha256": "c" * 64, "time_of_day_h": 7.25})

    def v02(name, physics_sha="04b4cf885885d5bbd8cb6fdac56cc6d9efb2a00e2c8122ddd1b82df9a1b3e25b"):
        """A v0.1 record relabelled v0.2 in memory with the v0.2 fields (the hash is the option struct of a kitchen
        scene at noslip 4; an example value)."""
        def apply(recs):
            r = recs[name]
            r.update(spec_version="v0.2", simulated=True)
            r["simulator"]["physics_options_sha256"] = physics_sha
        return apply

    def v03(name, **generator):
        """A v0.1 record exported in memory as v0.3: the v0.2 fields (option hash not recorded) and the generator
        updated by `generator` (`seedless=True, seeds={}` gives a seedless generator)."""
        def apply(recs):
            v02(name, None)(recs)
            recs[name]["spec_version"] = "v0.3"
            recs[name]["generator"].update(generator)
        return apply

    def pnp(reached="lift", success=False, **outcome):
        """lost1 as a v0.2 failure (or success) scored by molmospaces_pnp_port_v1 (§8.4), with invented times."""
        def apply(recs):
            v02(lost1)(recs)
            stages = PNP_STAGES[:0 if reached == "none" else PNP_STAGES.index(reached) + 1]
            o = recs[lost1]["outcome"]
            o.update(checker=PNP, checker_version="0.1.0", success=success, goal_margin=None,
                     margin_components=None, constraint_margins={}, stage_reached=reached,
                     stage_times={s: 6.6 + i for i, s in enumerate(stages)})
            if success:
                o.update(episode_margin=1, stage_class="S", first_failed=None, terminal_class=None)
            else:
                cls, terms, first_stage = PNP_FAILURE.get(reached, ("P", ("goal_not_held",), "finish"))
                o.update(episode_margin=-(4 - len(stages)) / 4, stage_class=cls, terminal_class=terms[0],
                         first_failed={"stage": first_stage, "predicate": PNP_PREDICATES[terms[0]][0], "t": 39.996})
            o.update(outcome)
        return apply

    def v04(name=None, **fields):
        """Both trust entries exported as v0.4 (as_v0_4), then `fields` applied to entry `name` with the demonstrated
        tolerances recomputed from its own inputs unless `fields` gives them."""
        def apply(recs):
            for r in recs.values():
                if r["record"] == "trust_entry":
                    as_v0_4(r)
            if name is not None:
                as_v0_4(recs[name], recompute="delta_agree" not in fields and "delta_disagree" not in fields, **fields)
        return apply

    # Separate-rule AGREE: bias interval inside ±δ and scatter upper bound ≤ δ, but U = 0.1 + 1.96 × 0.2 = 0.492 > δ.
    v0_agree = dict(bias={"value": 0.0, "ci95": [-0.1, 0.1], "ci95_clustered": None},
                    scatter_net={"value": 0.1, "ci95": [0.0, 0.2]})
    v0_agree_nf = {"n_cells": 14, "bias": {"value": 0.0, "ci95": [-0.1, 0.1]},
                   "scatter_net": {"value": 0.1, "ci95": [0.0, 0.2]}}
    no_interval = dict(scatter_net={"value": 0.364, "ci95": None},
                       non_floor=dict(WIDOWX_V0_4["non_floor"], scatter_net={"value": 0.479, "ci95": None}))

    faults = {  # label: (name of the record that must be rejected, fault)
        "v0.4: a v0-style AGREE whose upper bound on the limits of agreement exceeds δ": (graded, v04(
            graded, verdict="agree", non_floor=v0_agree_nf, **v0_agree)),
        "v0.4: AGREE over all cells that fails over the non-FLOOR cells": (graded, v04(
            graded, verdict="agree", bias={"value": 0.0, "ci95": [-0.05, 0.05], "ci95_clustered": None},
            scatter_net={"value": 0.0, "ci95": [0.0, 0.05]})),
        "v0.4: AGREE with fewer than 2 non-FLOOR cells": (graded, v04(
            graded, verdict="agree", bias={"value": 0.0, "ci95": [-0.05, 0.05], "ci95_clustered": None},
            scatter_net={"value": 0.0, "ci95": [0.0, 0.05]},
            non_floor={"n_cells": 1, "bias": None, "scatter_net": None})),
        "v0.4: disagree_scatter where the cause is unresolved": (graded, v04(
            graded, verdict="disagree_scatter", bias={"value": 0.2, "ci95": [0.15, 0.25], "ci95_clustered": None},
            scatter_net={"value": 0.1, "ci95": [0.06, 0.2]})),
        "v0: disagree_unresolved": setter(graded, ["verdict"], "disagree_unresolved"),
        "v0: a v0.4 field": setter(graded, ["delta_agree"], 1.0),
        "v0.4: without the non-FLOOR inputs": (graded, lambda recs: (v04()(recs), recs[graded].pop("non_floor"))),
        "v0.4: without the rule's name": (graded, lambda recs: (v04()(recs), recs[graded].pop("verdict_rule"))),
        "v0.4: an unknown bound method": (graded, v04(graded, loa_method="direct")),
        "v0.4: delta_agree not the bound": (graded, v04(graded, delta_agree=1.0, delta_disagree=0.6945075165582807)),
        "v0.4: delta_agree without the padding check": (graded, v04(
            graded, delta_agree=loa_bounds(records[graded]["bias"]["ci95"], *records[graded]["scatter_net"]["ci95"])[1],
            delta_disagree=0.6945075165582807)),
        "v0.4: delta_disagree rounded": (graded, v04(graded, delta_agree=1.1488207496959124, delta_disagree=0.695)),
        "v0.4: delta_agree given with fewer than 2 non-FLOOR cells": (graded, v04(
            graded, verdict="disagree_scatter", non_floor={"n_cells": 1, "bias": None, "scatter_net": None},
            delta_agree=1.0, delta_disagree=0.6945075165582807)),
        "v0.4: non-FLOOR count not the cells'": (graded, v04(
            graded, non_floor=dict(WIDOWX_V0_4["non_floor"], n_cells=13))),
        "v0.4: non-FLOOR inputs with fewer than 2 non-FLOOR cells": (graded, v04(
            graded, non_floor=dict(WIDOWX_V0_4["non_floor"], n_cells=1))),
        "v0.4: floor with non-FLOOR cells": (graded, v04(graded, verdict="floor")),
        "v0.4: not_determined with the wrong possible verdicts": (graded, v04(
            graded, verdict="not_determined", verdict_possible=["disagree_scatter", "inconclusive"], **no_interval)),
        "v0.4: a determined verdict without a scatter interval": (graded, v04(
            graded, verdict="disagree_scatter", **no_interval)),
        "v0.4: not_yet_calibrated with non-FLOOR inputs": (uncalibrated, lambda recs: (
            v04()(recs), recs[uncalibrated].update(non_floor={"n_cells": 0, "bias": None, "scatter_net": None}))),
        "trust entry labelled v0.3": setter(graded, ["spec_version"], "v0.3"),
        "trust entry labelled v0.4 without the v0.4 fields": setter(graded, ["spec_version"], "v0.4"),
        "synthetic reference set": setter(ref, ["synthetic"], True),
        "unknown field": setter(ref, ["note"], "x"),
        "rank with too few policies": setter(ref, ["metrics"], ["level", "rank", "stage"]),
        "budget kind without a budget": setter(ref, ["termination_rule", "budget"], None),
        "budget key not a task": setter(ref, ["termination_rule", "budget"], {"oven": {"value": 1, "unit": "s"}}),
        "matching file hash": setter(ref, ["matching_file"], {"path": "spec/v0.md", "sha256": "0" * 64}),
        "edited reference set": (card, setter(ref, ["producer"], "someone else")[1]),
        "missing checkpoint": setter(card, ["checkpoints"], {"molmo": {"revision": None, "matches_reference": None}}),
        "blind without a rule": setter(card, ["information_used", "class"], "declared_blind"),
        "grader without same_as_reference": setter(card, ["grader", "same_as_reference"], KeyError),
        "bad timestamp": setter(card, ["frozen_at"], "2026-11-23"),
        "submitted entry below 100 episodes": setter(card, ["provenance"], "as_submitted"),
        "entry with one episode per cell": setter(card, ["episodes_per_cell"], 1),
        "baseline with one episode per cell": (card, lambda recs: recs[card].update(kind="baseline", provenance="computed",
                                                                                  simulator=None, episodes_per_cell=1)),
        "cell d differs from the counts": (cell, lambda recs: recs[cell].update(d=0.5, interval=[0.4, 0.6])),
        "cell k above n": setter(cell, ["sim", "k"], 51),
        "cell interval excludes d": setter(cell, ["interval"], [0.2, 0.3]),
        "cell KPI not in the plan": setter(cell, ["kpi"], "stage_T"),
        "cell task not in the plan": setter(cell, ["cell", "task"], "fold cloth"),
        "cell not marked in calibration": (cell, disclose),
        "plan stage KPI without a stage": setter(plan, ["kpis", 0], {"id": "s", "kind": "failure_stage", "target": "X",
                                                                    "statistic": "x", "tolerance": 0.1, "conditions": None}),
        "plan without its manifest": setter(plan, ["calibration_manifest"], "0" * 64),
        "plan referent grader kind": setter(plan, ["referent", "grader", "kind"], "panel"),
        "manifest undisclosed with items": setter(manifest, ["items"], [{"data": "x", "cells": "all",
                                                                         "parameters": None, "purpose": "x"}]),
        "edited plan": (graded, setter(plan, ["route"], "rerun")[1]),
        "trust not_determined without possible verdicts": (graded, lambda recs: recs[graded].update(
            verdict="not_determined", verdict_possible=None, scatter_net={"value": 0.364, "ci95": None})),
        "trust tolerance not the plan's": setter(graded, ["tolerance"], 0.1),
        "trust cell count": setter(graded, ["n_cells"], 23),
        "trust overlap false with undisclosed history": setter(graded, ["calibration_overlap"], False),
        "trust overlap true": setter(graded, ["calibration_overlap"], True),
        "trust interval excludes bias": setter(graded, ["bias", "ci95"], [0.1, 0.2]),
        "trust synthetic": setter(graded, ["synthetic"], True),
        "trust unknown failure type": setter(uncalibrated, ["target"], "lighting"),
        "uncalibrated trust with an estimate": setter(uncalibrated, ["bias", "value"], 0.1),
        "uncalibrated trust with a tolerance": setter(uncalibrated, ["tolerance"], 0.25),
        "uncalibrated trust with episodes": setter(uncalibrated, ["n_real_episodes"], 50),
        "uncalibrated trust with a fitted date": setter(uncalibrated, ["fitted"], "2026-11-22"),
        "not_determined with a scatter interval": (graded, lambda recs: recs[graded].update(
            verdict="not_determined", verdict_possible=["disagree_scatter", "inconclusive"])),
        "possible verdicts against the rule": (graded, lambda recs: recs[graded].update(
            verdict="not_determined", verdict_possible=["agree", "inconclusive"],
            scatter_net={"value": 0.364, "ci95": None})),
        "agree without a scatter interval": (graded, lambda recs: recs[graded].update(
            verdict="agree", scatter_net={"value": 0.1, "ci95": None})),
        "possible verdicts on a determined verdict": setter(graded, ["verdict_possible"], ["disagree_scatter"]),
        "floor with non-FLOOR cells": (graded, lambda recs: recs[graded].update(verdict="floor", verdict_possible=None)),
        "T_k without its interval": setter(graded, ["T_k"], 0.5),
        "PPV_k without its interval": setter(graded, ["ppv_k"], 0.5),
        "episode success with a violated constraint": setter(won, ["outcome", "constraint_margins",
                                                                   "distractors_undisturbed"], -0.2),
        "episode success with a first failed predicate": setter(won, ["outcome", "first_failed"],
                                                                {"stage": "grasp", "predicate": "x", "t": 1.0}),
        "episode success with stage class T": setter(won, ["outcome", "stage_class"], "T"),
        "episode failure with a positive failsearch margin": setter(lost, ["outcome", "episode_margin"], 0.3),
        "episode failure without its first failed predicate": setter(lost, ["outcome", "first_failed"], None),
        "episode perturbs an unknown factor": setter(lost, ["perturbed", 0, "name"], "gravity"),
        "episode unknown failure type": setter(lost, ["perturbed", 0, "failure_type"], "lighting"),
        "episode stage class outside G, T, P, S": setter(lost, ["outcome", "stage_class"], "X"),
        "episode truncated scenario hash": setter(lost, ["scenario_hash"], "1e6de6d1afd99f6d"),
        "episode unknown field": setter(lost, ["notes"], "x"),
        "episode without provenance": setter(lost, ["versions"], {"python": "3.14"}),
        "non-synthetic episode without a policy family": setter(lost, ["policy", "family"], None),
        "v0 episode carrying a v0.1 field": setter(lost, ["compute"], {"inference_device": "cpu", "device_name": "x",
                                                                       "toolkit": {}, "kernel_settings": {}}),
        "v0 episode labelled v0.1 without the v0.1 fields": setter(lost, ["spec_version"], "v0.1"),
        "episode with an unknown spec version": setter(lost, ["spec_version"], "v0.4"),
        "v0.1 episode carrying simulated": setter(lost1, ["simulated"], True),
        "v0.1 episode carrying a physics options hash": setter(lost1, ["simulator", "physics_options_sha256"], "a" * 64),
        "v0.1 episode with the v0.2 checker": setter(lost1, ["outcome", "checker"], PNP),
        "v0.1 episode labelled v0.2 without the v0.2 fields": setter(lost1, ["spec_version"], "v0.2"),
        "v0.2 episode without simulated": (lost1, lambda recs: (v02(lost1)(recs), recs[lost1].pop("simulated"))),
        "v0.2 episode with simulated as text": (lost1, lambda recs: (v02(lost1)(recs),
                                                                     recs[lost1].update(simulated="true"))),
        "v0.2 episode without a physics options hash key": (lost1, lambda recs: (
            v02(lost1)(recs), recs[lost1]["simulator"].pop("physics_options_sha256"))),
        "v0.2 truncated physics options hash": (lost1, v02(lost1, "04b4cf88")),
        "v0.2 simulated episode with a real rerun block": (lost1, lambda recs: (v02(lost1)(recs), recs[lost1].update(
            synthetic=False, real_rerun={"random_holdout": True, "setup_seconds": None, "initial_poses": None}))),
        "v0.2 real measurement without a real rerun block": (lost1, lambda recs: (
            v02(lost1, None)(recs), recs[lost1].update(simulated=False, synthetic=False))),
        "v0.2 real episode with a physics options hash": (lost1, lambda recs: (v02(lost1)(recs), recs[lost1].update(
            simulated=False, synthetic=False,
            real_rerun={"random_holdout": True, "setup_seconds": None, "initial_poses": None}))),
        "v0.1 episode carrying generator.seedless": setter(lost1, ["generator", "seedless"], False),
        "v0.2 episode with an empty generator.seeds": (lost1, lambda recs: (v02(lost1)(recs), recs[lost1][
            "generator"].update(seeds={}))),
        "v0.2 episode with a seedless generator": (lost1, lambda recs: (v02(lost1)(recs), recs[lost1][
            "generator"].update(seeds={}, seedless=True))),
        "v0.1 episode labelled v0.3 without the v0.2 fields": setter(lost1, ["spec_version"], "v0.3"),
        "v0.3 seedless generator that lists seeds": (lost1, v03(lost1, seedless=True)),
        "v0.3 empty seeds without seedless": (lost1, v03(lost1, seeds={})),
        "v0.3 empty seeds with seedless false": (lost1, v03(lost1, seeds={}, seedless=False)),
        "v0.3 seedless as text": (lost1, v03(lost1, seeds={}, seedless="true")),
        "v0.3 seedless null": (lost1, v03(lost1, seeds={}, seedless=None)),
        "pnp failure with a positive margin": (lost1, pnp(episode_margin=0.5)),
        "pnp failure with a margin off the stage rule": (lost1, pnp(episode_margin=-0.75)),
        "pnp failure after lift classed G": (lost1, pnp(stage_class="G")),
        "pnp failure after lift classed drop": (lost1, pnp(terminal_class="drop")),
        "pnp failure without contact classed not_lifted": (lost1, pnp("none", terminal_class="not_lifted")),
        "pnp failure after support classed T": (lost1, pnp("support", stage_class="T")),
        "pnp failure reaching finish": (lost1, pnp("finish", stage_class="S", terminal_class="goal_not_held",
                                                   episode_margin=0.0)),
        "pnp failure naming a later stage as first failed": (lost1, pnp(first_failed={
            "stage": "finish", "predicate": "supported", "t": 39.996})),
        "pnp goal_not_held naming support as its predicate": (lost1, pnp(
            "support", terminal_class="goal_not_held",
            first_failed={"stage": "finish", "predicate": "supported", "t": 39.996})),
        "pnp failure with an unknown stage": (lost1, pnp(stage_reached="grasp")),
        "pnp failure with times for stages not reached": (lost1, pnp(stage_times={"touch": 1.0, "lift": 2.0,
                                                                                  "support": 3.0})),
        "pnp success with a terminal class": (lost1, pnp("finish", success=True, terminal_class="goal_not_held")),
        "pnp success with a margin other than 1": (lost1, pnp("finish", success=True, episode_margin=0.5)),
        "pnp success that reached support": (lost1, pnp("support", success=True)),
        "pnp success with times for stages not reached": (lost1, pnp("touch", success=True, stage_times={
            "touch": 1.0, "lift": 2.0})),
        "pnp success without times for stages reached": (lost1, pnp("finish", success=True, stage_times={
            "touch": 1.0, "lift": 2.0, "support": 3.0})),
        "pnp failure with a goal margin": (lost1, pnp(goal_margin=-0.2)),
        "pnp success with a goal margin": (lost1, pnp("finish", success=True, goal_margin=0.3)),
        "pnp failure with a constraint margin": (lost1, pnp(constraint_margins={"receptacle_moved": 0.4})),
        "pnp stage times out of stage order": (lost1, pnp("support", stage_times={
            "touch": 5.0, "lift": 4.0, "support": 6.0})),
        "episode with a list as spec version": setter(lost, ["spec_version"], ["v0"]),
        "episode with an object as spec version": setter(lost1, ["spec_version"], {"v": "v0.1"}),
        "v0.1 episode without a checker release": setter(lost1, ["outcome", "checker_version"], KeyError),
        "v0.1 episode with an empty checker release": setter(lost1, ["outcome", "checker_version"], ""),
        "v0.1 episode with an unknown checker": setter(lost1, ["outcome", "checker"], "worktop"),
        "v0.1 worktop failure with a positive margin": setter(lost1, ["outcome", "episode_margin"], 0.3),
        "v0.1 episode without a generator field": setter(lost1, ["generator"], KeyError),
        "v0.1 generator without a release": setter(lost1, ["generator", "release"], None),
        "v0.1 generator with a truncated constraints hash": setter(lost1, ["generator", "constraints_sha256"],
                                                                   "000b2592"),
        "v0.1 generator without seeds": setter(lost1, ["generator", "seeds"], {}),
        "v0.1 episode without a device": setter(won1, ["compute"], KeyError),
        "v0.1 device outside the list": setter(won1, ["compute", "inference_device"], "gpu"),
        "v0.1 cuda record without CUBLAS_WORKSPACE_CONFIG": (won1, lambda recs: recs[won1]["compute"][
            "kernel_settings"].pop("CUBLAS_WORKSPACE_CONFIG")),
        "v0.1 cuda record without toolkit versions": setter(won1, ["compute", "toolkit"], {}),
        "v0.1 cuda record without a device name": setter(won1, ["compute", "device_name"], None),
        "v0.1 policy with weights and no device": setter(won1, ["compute"], {"inference_device": "none",
                                                                             "device_name": None, "toolkit": {},
                                                                             "kernel_settings": {}}),
        "v0.1 episode without events": setter(lost1, ["events"], KeyError),
        "v0.1 events without scene seeds": (lost1, lambda recs: recs[lost1].update(
            events=[event(lost1, recs)], scene_seeds=None)),
        "v0.1 fork without scene seeds": (lost1, lambda recs: recs[lost1].update(fork=FORK_EXAMPLE, scene_seeds=None)),
        "v0.1 event on a factor not in factors": (lost1, lambda recs: recs[lost1].update(
            events=[dict(event(lost1, recs), factor="gravity")])),
        "v0.1 event with a malformed trigger": (lost1, lambda recs: recs[lost1].update(
            events=[dict(event(lost1, recs), trigger="when lifted")])),
        "v0.1 stage trigger outside its stage": (lost1, lambda recs: recs[lost1].update(
            events=[dict(event(lost1, recs), stage="approach")])),
        "v0.1 event not applied without a reason": (lost1, lambda recs: recs[lost1].update(
            events=[dict(event(lost1, recs), applied=False)])),
        "v0.1 event without its draw seeds": (lost1, lambda recs: recs[lost1].update(
            events=[dict(event(lost1, recs), draw_seed=[])])),
        "v0.1 events out of time order": (lost1, lambda recs: recs[lost1].update(
            events=[event(lost1, recs), dict(event(lost1, recs), t=1.0, trigger="time:1.0", stage=None)])),
        "v0.1 trace hash without its method": setter(lost1, ["trace_sha256"], "a" * 64),
        "v0.1 trace method without a hash": setter(lost1, ["trace_method"], "x"),
        "v0.1 fork with a truncated snapshot hash": setter(lost1, ["fork"], dict(FORK_EXAMPLE, snapshot_sha256="0d0d")),
        "v0.1 fork with an unknown snapshot hash version": (lost1, lambda recs: (replay_record(recs), recs[lost1][
            "fork"].update(snapshot_hash_version=3))),
        "v0.1 fork with a snapshot hash version given as text": (lost1, lambda recs: (replay_record(recs), recs[lost1][
            "fork"].update(snapshot_hash_version="2"))),
        "v0.1 fork with a snapshot hash and a null hash version": (lost1, lambda recs: (replay_record(recs), recs[lost1][
            "fork"].update(snapshot_hash_version=None))),
        "v0.1 fork at the start naming a snapshot hash version": (lost1, lambda recs: recs[lost1].update(
            fork=dict(FORK_EXAMPLE, boundary="start", block=0, snapshot_sha256=None, snapshot_hash_version=2),
            scene_seeds=[20261127, 1, 2, 1, 0, 0])),
        "v0.1 operating conditions without their hash": setter(lost1, ["operating_conditions"], {
            "id": "x", "sha256": None, "time_of_day_h": 7.5}),
        "v0.1 operating conditions at hour 24": setter(lost1, ["operating_conditions"], {
            "id": "x", "sha256": "b" * 64, "time_of_day_h": 24}),
        "offset with scatter above δ and no interval called disagree_offset": (graded, lambda recs: recs[graded].update(
            bias={"value": -0.4, "ci95": [-0.45, -0.35], "ci95_clustered": None},
            scatter_net={"value": 0.364, "ci95": None}, verdict="disagree_offset", verdict_possible=None)),
        "verdict read from the clustered interval": (graded, lambda recs: recs[graded]["bias"].update(
            value=-0.31, ci95=[-0.40, -0.30], ci95_clustered=[-0.45, 0.10])),   # offset only in bias.ci95
        "trust entry on a rank KPI": (graded, rank_entry),
        "twin with inferred data marked calibrated": setter(twin, ["status"], "calibrated"),
        "complete twin marked uncalibrated": complete(lambda t: t.update(status="uncalibrated")),
        "calibrated twin with an inferred item": complete(lambda t: t["joints"].update(source="inferred")),
        "calibrated twin without a method": complete(lambda t: t["scene"].update(method=None)),
        "calibrated twin without the physical arm": complete(lambda t: t.update(robot_unit=None)),
        "calibrated twin without its joint file": complete(drop(["joints", "file"])),
        "calibrated twin with too few reference poses": complete(lambda t: t["joints"]["reference_poses"].pop()),
        "calibrated twin with gripper error above 5 mm": complete(
            lambda t: t["joints"]["reference_poses"][0].update(gripper_error_mm=5.1)),
        "calibrated twin without servo gains": complete(drop(["control", "gains"])),
        "calibrated twin with control settings the twin does not use": complete(
            lambda t: t["control"].update(twin_uses=False)),
        "calibrated twin without reversals in its excitation": complete(
            lambda t: t["actuators"]["excites"].update(reversals=None)),
        "calibrated twin replayed on its fitted recording": complete(lambda t: t["actuators"]["replay"].update(
            recording=dict(t["actuators"]["excitation"]))),
        "calibrated twin with replay error above 0.5 deg": complete(
            lambda t: t["actuators"]["replay"]["rms_deg"].update({t["joints"]["names"][0]: 0.6})),
        "calibrated twin with too few board images": camera(n_images=14),
        "calibrated twin with focus not locked": camera(focus_locked=False),
        "calibrated twin without a reprojection error": camera(reprojection_rms_px=None),
        "calibrated twin with camera pose error above 4 mm": camera(pose_error_mm=4.5),
        "calibrated twin with drift above 2.6 px": camera(session_drift_px={"rec": 3.0}),
        "calibrated twin with a recording session not checked for drift": camera(session_drift_px={}),
        "calibrated twin without a recording session": complete(lambda t: (
            t.update(sessions=[x for x in t["sessions"] if x["kind"] != "recording"]),
            [c.update(session_drift_px={}) for c in t["cameras"]])),
        "calibrated twin with touch error above 10 mm": complete(
            lambda t: t["scene"]["fixed_objects"][0].update(touch_error_mm=11.0)),
        "calibrated twin without a task object mass": complete(
            lambda t: t["scene"]["task_objects"][0].update(mass_kg=None)),
        "calibrated twin missing a starting layout": complete(lambda t: t["scene"]["layouts"].update(
            episodes_recorded=t["scene"]["layouts"]["episodes"] - 1)),
        "calibrated synthetic twin": complete(lambda t: t.update(synthetic=True)),
        "twin gains for unknown joints": setter(twin, ["control", "gains"], {"elbow": {"p": 1, "i": 0, "d": 0}}),
        "twin drift for a session not recorded": setter(twin, ["cameras", 0, "session_drift_px"], {"later": 1.0}),
        "twin quaternion not unit length": camera(pose={"xyz_m": [0.3, 0.0, 0.5], "quat_wxyz": [1.0, 1.0, 0.0, 0.0]}),
        "twin layouts recorded beyond episodes": setter(twin, ["scene", "layouts", "episodes_recorded"], 31),
        "plan linked to a twin of another simulator": (plan, link_plan("illustration", complete_it=False)),
        "plan linked to a twin not validated": setter(plan, ["subject", "twin_calibration"], "0" * 64),
        "trust entry calibrated without a twin calibration": setter(graded, ["twin_calibration"], "calibrated"),
        "trust entry uncalibrated under a calibrated twin": (graded, link_plan("illustration", label="uncalibrated")),
        "customer verdict on an uncalibrated twin": (graded, customer_uncalibrated),
        "customer verdict on a twin linked but uncalibrated": (
            graded, link_plan("customer_final", twin_fault=uncalibrate, label="uncalibrated")),
        "entry linked to a twin of another simulator": (card, link_card(simulator={"name": "MuJoCo", "version": None,
                                                                                    "config_hash": None})),
        "baseline entry with a twin calibration": (card, lambda recs: (link_card(frozen=False)(recs), recs[card].update(
            kind="baseline", provenance="computed", simulator=None))),
        "our frozen simulator entry without a twin calibration": (card, lambda recs: recs[card].update(
            ours=True, frozen_at="2026-11-24 12:00:00 UTC")),
        "our frozen simulator entry on an uncalibrated twin": (card, link_card(complete_it=False)),
    }
    def customer_not_reported(recs):   # a customer plan on an uncalibrated twin, its entry reporting no verdict
        customer_uncalibrated(recs)
        recs[graded].update(kpi=None, verdict="not_yet_calibrated", tolerance=None, fitted=None, n_cells=0,
                            n_real_episodes=0, bias={"value": None, "ci95": None, "ci95_clustered": None},
                            scatter_net={"value": None, "ci95": None})

    accepted = {  # label: valid variant; every record must pass
        "v0.4 export of the WidowX entries (disagree_scatter; not_yet_calibrated)": v04(),
        "v0: a separate-rule AGREE (bias interval and scatter each within δ)": lambda recs: recs[graded].update(
            verdict="agree", **copy.deepcopy(v0_agree)),
        "v0.4: the same inputs are inconclusive": v04(graded, verdict="inconclusive", non_floor=v0_agree_nf,
                                                     **copy.deepcopy(v0_agree)),
        "v0.4: AGREE over all cells and the non-FLOOR cells": v04(
            graded, verdict="agree", bias={"value": 0.0, "ci95": [-0.05, 0.05], "ci95_clustered": None},
            scatter_net={"value": 0.0, "ci95": [0.0, 0.05]},
            non_floor={"n_cells": 14, "bias": {"value": 0.0, "ci95": [-0.06, 0.06]},
                       "scatter_net": {"value": 0.0, "ci95": [0.0, 0.08]}}),
        "v0.4: disagree_unresolved": v04(graded, verdict="disagree_unresolved",
                                         bias={"value": 0.2, "ci95": [0.15, 0.25], "ci95_clustered": None},
                                         scatter_net={"value": 0.1, "ci95": [0.06, 0.2]}),
        "v0.4: not_determined without a scatter interval": v04(
            graded, verdict="not_determined",
            verdict_possible=["disagree_scatter", "disagree_unresolved", "inconclusive"], **no_interval),
        "complete twin calibration": complete()[1],
        "customer plan on a calibrated twin": link_plan("customer_final"),
        "customer plan on an uncalibrated twin, no verdict reported": customer_not_reported,
        "our frozen simulator entry on a calibrated twin": link_card(),
        "a published entry linked to an uncalibrated twin": link_card(ours=False, complete_it=False),
        "v0.1 replay record: events, fork, trace and operating conditions": replay_record,
        "v0.1 replay record with snapshot hash version 2": lambda recs: (replay_record(recs), recs[lost1][
            "fork"].update(snapshot_hash_version=2)),
        "v0.1 fork at the start with a null snapshot hash version": lambda recs: recs[lost1].update(
            fork=dict(FORK_EXAMPLE, boundary="start", block=0, snapshot_sha256=None, snapshot_hash_version=None),
            scene_seeds=[20261127, 1, 2, 1, 0, 0]),
        "v0.1 event not applied, with its reason": lambda recs: recs[lost1].update(
            events=[dict(event(lost1, recs), applied=False, reason="carton held: not resting")]),
        "v0.1 record from a stored scenario (no generator)": lambda recs: recs[lost1].update(generator=None),
        "v0.1 cpu record": lambda recs: recs[won1].update(compute={
            "inference_device": "cpu", "device_name": "AMD Ryzen 7 7700", "toolkit": {"torch": "2.11.0"},
            "kernel_settings": {"threads": 1}}),
        "v0.2 simulated record": v02(lost1),
        "v0.2 simulated record with the option hash not recorded": v02(lost1, None),
        "v0.2 simulated, synthetic record (stand-in or over-marked)": lambda recs: (
            v02(lost1)(recs), recs[lost1].update(synthetic=True)),
        "v0.2 synthetic stand-in for a real outcome (no rerun block)": lambda recs: (
            v02(lost1, None)(recs), recs[lost1].update(simulated=False)),
        "v0.2 real rerun": lambda recs: (v02(lost1, None)(recs), recs[lost1].update(
            simulated=False, synthetic=False,
            real_rerun={"random_holdout": True, "setup_seconds": 40.0, "initial_poses": None})),
        "v0.3 export with the example's seeds": v03(lost1),
        "v0.3 export with the example's seeds and seedless false": v03(lost1, seedless=False),
        "v0.3 seedless generator": v03(lost1, seeds={}, seedless=True, constraints_sha256=None),
        "v0.3 record from a stored scenario (no generator)": lambda recs: (v03(lost1)(recs), recs[lost1].update(
            generator=None)),
        "pnp failure with no contact": pnp("none"),
        "pnp failure after touch": pnp("touch"),
        "pnp failure after lift": pnp("lift"),
        "pnp failure after support: left support": pnp("support"),
        "pnp failure after support: goal not held (receptacle tilted)": pnp(
            "support", terminal_class="goal_not_held",
            first_failed={"stage": "finish", "predicate": "receptacle_tilt", "t": 31.2}),
        "pnp success": pnp("finish", success=True),
        "pnp push-in success (lift never reached)": pnp("touch", success=True),
        "pnp success with no robot contact (a push-in without a touch)": pnp("none", success=True),
        "pnp success through carry-forward with support only before the lift": pnp("lift", success=True),
        "pnp failure with equal stage times": pnp("support", stage_times={"touch": 5.0, "lift": 5.0, "support": 5.0}),
    }
    failures = []
    for label, (target, apply) in faults.items():
        recs = copy.deepcopy(records)
        apply(recs)
        if not validate(recs)[target]:
            failures.append(label)
    for label, apply in accepted.items():
        recs = copy.deepcopy(records)
        apply(recs)
        problems = [f"{n}: {m}" for n, ms in validate(recs).items() for m in ms]
        if problems:
            failures.append(f"{label} (rejected: {problems[0]})")
    return failures, len(faults), len(accepted)


def main():
    paths = [Path(p) for p in sys.argv[1:]] or (sorted(EXAMPLES.glob("*.json")) + sorted(EXAMPLES.glob("*.jsonl"))
                                                + sorted((EXAMPLES / "data" / "synthetic").glob("*.jsonl")))
    records, bad = {}, []
    for p in paths:
        try:
            text_ = p.read_text(encoding="utf-8")
            if p.suffix == ".jsonl":
                for i, line in enumerate(text_.splitlines(), 1):
                    if line.strip():
                        records[f"{p.name}:{i}"] = json.loads(line)
            else:
                records[p.name] = json.loads(text_)
        except (OSError, ValueError) as e:
            bad.append(f"{p}: cannot read JSON: {e}")
    for name, problems in validate(records).items():
        bad += [f"{name}: {m}" for m in problems]
    if bad:
        sys.exit("\n".join(bad))
    summary = f"{len(records)} records valid"
    if not sys.argv[1:]:
        failures, n, m = selftest(records)
        if failures:
            sys.exit(f"{summary}; self-test failed: {'; '.join(failures)}")
        summary += f"; self-test: {n} of {n} faults rejected, {m} of {m} valid variants accepted"
    print(summary)


if __name__ == "__main__":
    main()
