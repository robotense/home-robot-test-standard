#!/usr/bin/env python3
"""Simulator checker compile target of spec v0 (spec/v0.md §3-§5, §9): the reference evaluator of a scenario
document's goal, constraints and stages over a recorded state trace, with robustness margins. Standard library plus
NumPy; PyYAML to read a YAML scenario. Reuses spec/rubric.py's parser, `seq_holds()` and item numbering
(`compile_items()`), so each of the document's items has one value and one margin.

    python3 -I spec/checker.py SCENARIO.yaml TRACE.json[.gz]            # outcome and item truth, JSON on stdout
    python3 -I spec/checker.py SCENARIO.yaml TRACE.json --truth          # only the `truth` block

Output (`evaluate()`; record `spec.checker_outcome.v0`).
- `outcome`: the §8.1 outcome fields with `checker: "spec_v0_grammar"`: success, goal_met, goal_margin and
  episode_margin (normalised, §3-§4), margin_components (each goal leaf's normalised margin at the end), constraint
  margins (normalised; null for a constraint whose `after` stage was never reached), constraint_failure, stage_reached,
  stage_times (seconds), stage_class, stage_units (one per §5 unit) and first_failed {stage, predicate, t}.
- `truth`: per-item values, {success, success_at_defaults, items: {item id: {value, margin_norm, margin_raw, t}}},
  item ids exactly as `spec/rubric.py` numbers them (S*, G*, C*). An item is true exactly when its margin_norm > 0.
  `rubric.decide(items record, item values)` reproduces `success`.
- `items_sha256`: SHA-256 of the canonical JSON of the items record (`rubric.compile_items()`) the truth refers to.

Semantics, by section.
- §3 leaves, margin rho in metres or degrees, normalised by the predicate's scale (±1 = one tolerance):
  `inside(a, b, tol)`  tol - d(c_a, V_b); V_b is b's `interior` volume; scale tol (default 0.07 m).
  `on(a, b, tol)`      min((tol - h)/tol, (gap_max - |g|)/gap_max); h the horizontal distance from c_a to b's `top`
                       surface (0 over it), g the vertical gap from a's lowest point to that surface; gap_max 0.01 m;
                       raw margin min(tol - h, gap_max - |g|). |g|: an object resting below the surface (beside it,
                       on the table) is not on it; the spec says "vertical gap" without a sign (an assumption of this checker).
  `upright(a, ang)`    ang - tilt(a), tilt the angle between a's `up_axis` (default local z) and world up; scale ang.
  `gripper_released(a)` min over fingers of the recorded finger-to-a distance, minus 0.005 m; scale 0.005 m (so the
                       boundary-success stratum, margin in (0, 0.5], is fingers 5-7.5 mm away).
  `joint_above(a, j, x)` q_j - x; scale 1 (the joint's own units).
  `not p`              -rho_p.  `all`: min.  `any`: max (of normalised margins).
- §5 `lifted(a, h)`: an event. Its value at step t is the largest (z_a(t') - z_a(0)) - h over steps t' <= t at which
  both fingers touch a; before the first such step it is -h. Normalised by h. z_a(0) is the trace's first step.
- §3 end-state goal: the goal's margin at the last trace step T. A top-level `seq`: `rubric.seq_holds()` on the
  steps' normalised margin traces (first-time-true steps, window margins).
- §4 constraint: violated when its `never` expression is true (margin > 0) at any step from `after` on (`start`: every
  step; `stage:<id>`: from the step the stage is reached, inclusive; a `for_each` stage: once every unit reached it).
  rho_c = min over those steps of -rho_expr. Episode margin min(goal, constraints). Success: goal true at T and no
  constraint violated (booleans; the margin's sign agrees except at an exact 0, an assumption of this checker).
- §5 stages, per unit: stage i is reached at the first step at or after stage i-1's step at which its `holds` is
  true ("at some point, at or after S(i-1)"). Item margin: the largest margin of `holds` over [t(i-1),
  T]; for a stage after an unreached stage, min(that unreached stage's margin, its own largest margin over the whole
  trace), so false items never carry a positive margin. stage_class: S when the goal holds at T or every stage of
  the unit was reached, else the class of the first stage not reached (as `decide()`).
- Goal items: a leaf of an `all`/`any` goal takes its value and margin at T. A `seq` step k takes `seq_holds`'s step
  margin; it is true when step k has a time and, for the last step, still holds at T; a step after the first untimed
  step is false with the first untimed step's margin.
- first_failed (failed goal): the first stage not reached (in unit order), with the leaf that decides its `holds` at
  the step of its best margin over its window; when every stage was reached, the failing `seq` step (or the goal at T),
  same rule; a goal met with a violated constraint gives `constraint:<id>` at its first violation.
- `success_at_defaults`: the same trace against the document with every `inside` and `on` tolerance replaced by the §3
  defaults (0.07 m, 0.03 m), the verdict under the default tolerances.

The state trace (record `spec.state_trace.v0`, JSON, optionally gzipped; written by a scene adapter at the control
rate). Columnar, one entry per control step:
    t                 [T] seconds, strictly increasing
    frame             "world" (z up, metres)
    objects           {name: {...}} for every object a predicate names (scene.objects keys of the document):
        pose          [T][7] x, y, z, qw, qx, qy, qz of the object frame (its centre c_a is the frame origin plus
                      `centre`, default [0, 0, 0]), or pose_static [7] for a body that does not move
        shape         {type: box, half: [3]} | {type: cylinder, radius, half_height} (axis local z) | {type: sphere,
                      radius}, in the object frame about `centre`: needed for `on` (a's lowest point)
        interior      {type: box, center: [3], half: [3]} | {type: frustum, center: [3], z0, z1, r0, r1} (axis local
                      z, radius r0 at z0 and r1 at z1, relative to center): needed for `inside` (b's interior volume)
        top           {type: disc, center: [3], radius} | {type: rect, center: [3], half: [2]}: needed for `on`
        up_axis       [3] local axis that is "up" for `upright` (default [0, 0, 1])
    fingers           [F] finger names
    finger_dist       {object: [T][F]} signed distance (m) from each finger's collision geometry to the object's
                      (MuJoCo mj_geomDistance; distmax >= 0.05): needed for `gripper_released`
    finger_touch      {object: [T][F]} 0/1, a contact between the finger and the object: needed for `lifted`
    finger_opening    [T][F] optional, recorded for the record, not read
    joints            {object: {joint: [T]}}: needed for `joint_above`
    x                 producer extras, not read
Receptacle geometry is a scene fact; a scenario document's header can state the rule its scene adapter applies.

Lineage. BEHAVIOR's BDDL evaluator also checks a task's declared goal conditions and reports which hold (Srivastava
et al., 2021). This checker evaluates the scenario document's own expressions in the same way and adds a normalised
margin per item (§3), ordered steps, "never" constraints (§4) and stage classes (§5).
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

SPEC = Path(__file__).resolve().parent
if str(SPEC) not in sys.path:
    sys.path.insert(0, str(SPEC))
import rubric  # noqa: E402  (spec/rubric.py: parser, item numbering, seq_holds, decide)

CHECKER_VERSION = "0.1.0"
TRACE_RECORD = "spec.state_trace.v0"
OUTCOME_RECORD = "spec.checker_outcome.v0"
DEFAULT_INSIDE_TOL = rubric.DEFAULT_INSIDE_TOL
DEFAULT_ON_TOL = rubric.DEFAULT_ON_TOL
DEFAULT_ON_GAP = rubric.DEFAULT_ON_GAP
DEFAULT_UPRIGHT_DEG = rubric.DEFAULT_UPRIGHT_DEG
RELEASE_CLEARANCE = rubric.RELEASE_CLEARANCE


class TraceError(ValueError):
    """The state trace lacks a field a predicate needs, or is malformed."""


# ---------------------------------------------------------------- geometry
def quat_to_mat(q: np.ndarray) -> np.ndarray:
    """[..., 4] (w, x, y, z), normalised here -> [..., 3, 3]."""
    q = np.asarray(q, float)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    w, x, y, z = np.moveaxis(q, -1, 0)
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
        np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
        np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1)], -2)


def dist_box(p: np.ndarray, half) -> np.ndarray:
    """Distance from points p [N, 3] (box frame, box centred at 0) to the solid box; 0 inside."""
    return np.linalg.norm(np.maximum(np.abs(p) - np.asarray(half, float), 0.0), axis=-1)


def dist_trapezoid(rho: np.ndarray, z: np.ndarray, z0, z1, r0, r1) -> np.ndarray:
    """Distance in the meridian half-plane from (rho, z) to the convex region {z0 <= z <= z1, 0 <= rho <= r(z)}, r
    linear from r0 at z0 to r1 at z1. For a solid of revolution this equals the 3-D distance to the solid."""
    poly = np.array([[0.0, z0], [r0, z0], [r1, z1], [0.0, z1]])
    pts = np.stack([rho, z], -1)
    inside = np.ones(len(pts), bool)
    best = np.full(len(pts), np.inf)
    for k in range(4):
        a, b = poly[k], poly[(k + 1) % 4]
        e = b - a
        nrm = np.array([e[1], -e[0]])          # outward for counter-clockwise order in (rho, z)
        inside &= (pts - a) @ nrm <= 1e-15
        s = np.clip(((pts - a) @ e) / (e @ e), 0.0, 1.0)
        best = np.minimum(best, np.linalg.norm(pts - (a + s[:, None] * e), axis=-1))
    return np.where(inside, 0.0, best)


class Trace:
    """A loaded `spec.state_trace.v0` with NumPy arrays."""

    def __init__(self, rec: dict):
        if rec.get("record") != TRACE_RECORD:
            raise TraceError(f"record must be {TRACE_RECORD!r}")
        if rec.get("frame", "world") != "world":
            raise TraceError("frame must be 'world'")
        self.rec = rec
        self.t = np.asarray(rec.get("t"), float)
        if self.t.ndim != 1 or self.t.size == 0:
            raise TraceError("t must be a non-empty list of times")
        if np.any(np.diff(self.t) <= 0):
            raise TraceError("t must be strictly increasing")
        self.n = self.t.size
        self.objects = rec.get("objects") or {}
        self.fingers = list(rec.get("fingers") or [])
        self._pose = {}

    def obj(self, name: str) -> dict:
        if name not in self.objects:
            raise TraceError(f"trace has no object {name!r}")
        return self.objects[name]

    def pose(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        """(centre positions [T, 3], rotation matrices [T, 3, 3]) of the object's centre frame."""
        if name not in self._pose:
            o = self.obj(name)
            if o.get("pose") is not None:
                P = np.asarray(o["pose"], float)
                if P.shape != (self.n, 7):
                    raise TraceError(f"{name}.pose must be [{self.n}][7], got {list(P.shape)}")
            elif o.get("pose_static") is not None:
                P = np.tile(np.asarray(o["pose_static"], float), (self.n, 1))
                if P.shape != (self.n, 7):
                    raise TraceError(f"{name}.pose_static must have 7 numbers")
            else:
                raise TraceError(f"{name} needs pose or pose_static")
            if np.any(np.abs(np.linalg.norm(P[:, 3:], axis=1) - 1) > 1e-3):
                raise TraceError(f"{name}: quaternions must be unit (w, x, y, z)")
            R = quat_to_mat(P[:, 3:])
            c = np.asarray(o.get("centre", [0, 0, 0]), float)
            self._pose[name] = (P[:, :3] + R @ c, R)
        return self._pose[name]

    def field(self, key: str, name: str, what: str) -> dict:
        g = self.obj(name).get(key)
        if not isinstance(g, dict):
            raise TraceError(f"{what} needs {name}.{key} in the trace")
        return g

    def finger(self, key: str, name: str, what: str) -> np.ndarray:
        d = (self.rec.get(key) or {}).get(name)
        if d is None:
            raise TraceError(f"{what} needs {key}[{name!r}] in the trace")
        a = np.asarray(d, float)
        if a.ndim != 2 or a.shape[0] != self.n or a.shape[1] < 1:
            raise TraceError(f"{key}[{name!r}] must be [{self.n}][F]")
        if self.fingers and a.shape[1] != len(self.fingers):
            raise TraceError(f"{key}[{name!r}] has {a.shape[1]} columns for {len(self.fingers)} fingers")
        return a

    def joint(self, name: str, joint: str) -> np.ndarray:
        q = ((self.rec.get("joints") or {}).get(name) or {}).get(joint)
        if q is None:
            raise TraceError(f"joint_above needs joints[{name!r}][{joint!r}] in the trace")
        q = np.asarray(q, float)
        if q.shape != (self.n,):
            raise TraceError(f"joints[{name!r}][{joint!r}] must have {self.n} values")
        return q


def load_trace(path) -> Trace:
    p = Path(path)
    raw = gzip.open(p, "rt", encoding="utf-8").read() if p.suffix == ".gz" else p.read_text(encoding="utf-8")
    return Trace(json.loads(raw))


def _local(tr: Trace, point_world: np.ndarray, body: str, center) -> np.ndarray:
    pb, Rb = tr.pose(body)
    return np.einsum("tji,tj->ti", Rb, point_world - pb) - np.asarray(center, float)


def lowest_z(tr: Trace, name: str, what: str) -> np.ndarray:
    c, R = tr.pose(name)
    s = tr.field("shape", name, what)
    if s.get("type") == "box":
        half = np.asarray(s["half"], float)
        corners = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float) * half
        return c[:, 2] + np.einsum("tk,ck->tc", R[:, 2, :], corners).min(axis=1)
    if s.get("type") == "cylinder":
        uz = np.abs(R[:, 2, 2])
        return c[:, 2] - float(s["half_height"]) * uz - float(s["radius"]) * np.sqrt(np.maximum(0.0, 1 - uz * uz))
    if s.get("type") == "sphere":
        return c[:, 2] - float(s["radius"])
    raise TraceError(f"{name}.shape type must be box, cylinder or sphere")


# ---------------------------------------------------------------- leaf margins
class Leaf:
    """One evaluated predicate: raw margin [T] (metres, degrees or joint units) and its scale."""

    def __init__(self, source: str, raw: np.ndarray, scale: float, norm: np.ndarray | None = None):
        self.source, self.raw, self.scale = source, raw, scale
        self.norm = raw / scale if norm is None else norm


def leaf_margin(node, tr: Trace) -> Leaf:
    _, name, a = node
    src = rubric.leaf_source(node)
    if name == "inside":
        o, r = a[0], a[1]
        tol = a[2] if len(a) > 2 else DEFAULT_INSIDE_TOL
        c, _ = tr.pose(o)
        v = tr.field("interior", r, src)
        p = _local(tr, c, r, v.get("center", [0, 0, 0]))
        if v.get("type") == "box":
            d = dist_box(p, v["half"])
        elif v.get("type") == "frustum":
            d = dist_trapezoid(np.hypot(p[:, 0], p[:, 1]), p[:, 2], v["z0"], v["z1"], v["r0"], v["r1"])
        else:
            raise TraceError(f"{r}.interior type must be box or frustum")
        return Leaf(src, tol - d, tol)
    if name == "on":
        o, r = a[0], a[1]
        tol = a[2] if len(a) > 2 else DEFAULT_ON_TOL
        c, _ = tr.pose(o)
        top = tr.field("top", r, src)
        p = _local(tr, c, r, top.get("center", [0, 0, 0]))
        if top.get("type") == "disc":
            h = np.maximum(np.hypot(p[:, 0], p[:, 1]) - float(top["radius"]), 0.0)
        elif top.get("type") == "rect":
            h = np.linalg.norm(np.maximum(np.abs(p[:, :2]) - np.asarray(top["half"], float), 0.0), axis=-1)
        else:
            raise TraceError(f"{r}.top type must be disc or rect")
        pb, Rb = tr.pose(r)
        surf_z = pb[:, 2] + Rb[:, 2, :] @ np.asarray(top.get("center", [0, 0, 0]), float)
        g = np.abs(lowest_z(tr, o, src) - surf_z)
        m_h, m_g = tol - h, DEFAULT_ON_GAP - g
        return Leaf(src, np.minimum(m_h, m_g), tol, norm=np.minimum(m_h / tol, m_g / DEFAULT_ON_GAP))
    if name == "upright":
        o = a[0]
        ang = a[1] if len(a) > 1 else DEFAULT_UPRIGHT_DEG
        _, R = tr.pose(o)
        up = np.asarray(tr.obj(o).get("up_axis", [0, 0, 1]), float)
        up = up / np.linalg.norm(up)
        cz = np.clip(R[:, 2, :] @ up, -1.0, 1.0)
        return Leaf(src, ang - np.degrees(np.arccos(cz)), ang)
    if name == "gripper_released":
        d = tr.finger("finger_dist", a[0], src)
        return Leaf(src, d.min(axis=1) - RELEASE_CLEARANCE, RELEASE_CLEARANCE)
    if name == "joint_above":
        o, j, x = a
        return Leaf(src, tr.joint(o, j) - x, 1.0)
    if name == "lifted":
        o, h = a
        c, _ = tr.pose(o)
        held = tr.finger("finger_touch", o, src).astype(bool).all(axis=1)
        inst = np.where(held, (c[:, 2] - c[0, 2]) - h, -h)
        return Leaf(src, np.maximum.accumulate(inst), h)
    raise rubric.CompileError(f"no checker margin for {name}")


class Expr:
    """An expression evaluated over the trace: normalised margin [T] and its leaves (for first_failed)."""

    def __init__(self, node, tr: Trace, cache: dict):
        self.node, self.tr, self.cache = node, tr, cache
        self.norm = self._ev(node)

    def _leaf(self, node) -> Leaf:
        key = rubric.leaf_source(node) + repr(node)
        if key not in self.cache:
            self.cache[key] = leaf_margin(node, self.tr)
        return self.cache[key]

    def _ev(self, node) -> np.ndarray:
        if node[0] == "pred":
            return self._leaf(node).norm
        if node[0] == "not":
            return -self._ev(node[1])
        vals = np.stack([self._ev(k) for k in node[1]])
        if node[0] == "all":
            return vals.min(axis=0)
        if node[0] == "any":
            return vals.max(axis=0)
        raise rubric.CompileError("seq is evaluated only as the top-level goal")

    def raw(self, t: int) -> float | None:
        """Raw margin at step t when the expression is a single leaf (or not leaf); None for a composite."""
        n, sign = self.node, 1.0
        while n[0] == "not":
            n, sign = n[1], -sign
        return sign * float(self._leaf(n).raw[t]) if n[0] == "pred" else None

    def deciding_leaf(self, t: int, node=None) -> str:
        """The leaf whose margin sets the expression's margin at step t (min child of all, max child of any)."""
        node = self.node if node is None else node
        if node[0] == "pred":
            return rubric.leaf_source(node)
        if node[0] == "not":
            inner = node[1]
            return "not " + rubric.leaf_source(inner) if inner[0] == "pred" else self.deciding_leaf(t, inner)
        vals = [Expr(k, self.tr, self.cache).norm[t] for k in node[1]]
        k = int(np.argmin(vals)) if node[0] == "all" else int(np.argmax(vals))
        return self.deciding_leaf(t, node[1][k])


# ---------------------------------------------------------------- document walk, numbered as spec/rubric.py
def goal_of(doc: dict, feasibility: str | None):
    goal = doc.get("goal")
    if isinstance(goal, dict):
        if feasibility is None or feasibility not in goal:
            raise rubric.CompileError(f"goal depends on feasibility status; choose one of {sorted(goal)}")
        goal = goal[feasibility]
    return goal


def goal_leaves(tree):
    """[(item id, node)] in rubric.compile_items' order: seq steps G1..Gn, or the leaves of all/any depth-first."""
    if tree[0] == "seq":
        return [(f"G{k}", step) for k, step in enumerate(tree[1], 1)]
    out = []

    def walk(n):
        if n[0] in ("all", "any"):
            for k in n[1]:
                walk(k)
        else:
            out.append((f"G{len(out) + 1}", n))
    walk(tree)
    return out


def _f(x) -> float:
    return float(round(float(x), 6))


def evaluate(doc: dict, trace: Trace, feasibility: str | None = None, defaults: bool = True) -> dict:
    """Scenario document and state trace -> outcome and item truth (module docstring)."""
    rub = rubric.compile_items(doc, feasibility)[0]
    tr, cache, T = trace, {}, trace.n - 1
    tsec = trace.t
    items: dict[str, dict] = {}

    # §3 goal
    tree = rubric.parse(goal_of(doc, feasibility), allow_seq=True)
    leaves = goal_leaves(tree)
    rub_goal = [it for it in rub["items"] if it["section"] == "goal"]
    if [i for i, _ in leaves] != [it["id"] for it in rub_goal] or \
            [rubric.leaf_source(n) for _, n in leaves] != [it["source"] for it in rub_goal]:
        raise AssertionError("goal items differ from spec/rubric.py's numbering")
    seq = None
    if tree[0] == "seq":
        steps = [Expr(s, tr, cache) for s in tree[1]]
        seq = rubric.seq_holds([list(map(float, e.norm)) for e in steps])
        goal_met, goal_margin = bool(seq["holds"]), float(seq["rho"])
        ff_margin = seq["step_margins"][seq["first_failed"]] if seq["first_failed"] is not None else None
        for k, ((iid, _), e) in enumerate(zip(leaves, steps)):
            m = seq["step_margins"][k]
            timed = seq["times"][k] is not None
            val = timed and (k < len(steps) - 1 or e.norm[T] > 0)
            if m is None:
                m = ff_margin
            items[iid] = {"value": bool(val), "margin_norm": _f(m), "margin_raw": None,
                          "t": _f(tsec[seq["times"][k]]) if timed else None}
        components = {rubric.leaf_source(s): _f(e.norm[T]) for s, e in zip(tree[1], steps)}
    else:
        g = Expr(tree, tr, cache)
        goal_margin = float(g.norm[T])
        goal_met = goal_margin > 0
        components = {}
        for iid, node in leaves:
            e = Expr(node, tr, cache)
            items[iid] = {"value": bool(e.norm[T] > 0), "margin_norm": _f(e.norm[T]),
                          "margin_raw": None if e.raw(T) is None else _f(e.raw(T)), "t": _f(tsec[T])}
            components[rubric.leaf_source(node)] = _f(e.norm[T])

    # §5 stages, per unit (item ids and order of compile_items)
    stage_items = [it for it in rub["items"] if it["section"] == "stage"]
    by_id = {it["id"]: it for it in stage_items}
    units, reach = [], {}
    for u in rub["stage_units"]:
        prev_t, prev_ok, prev_m, reached, cls = 0, True, None, None, None
        first_unreached = None
        for iid in u["items"]:
            it = by_id[iid]
            e = Expr(rubric.parse(it["source"], allow_stage=True), tr, cache)
            if prev_ok:
                w = e.norm[prev_t:]
                hit = np.flatnonzero(w > 0)
                m = float(w.max())
                if hit.size:
                    t_i = prev_t + int(hit[0])
                    items[iid] = {"value": True, "margin_norm": _f(m), "margin_raw": None, "t": _f(tsec[t_i])}
                    reach.setdefault(it["stage"], []).append(t_i)
                    reached, prev_t, prev_m = it["stage"], t_i, m
                    continue
                items[iid] = {"value": False, "margin_norm": _f(m), "margin_raw": None, "t": None}
                first_unreached = (iid, it, e, prev_t)
                cls = it["class_if_not_reached"]
                prev_ok, prev_m = False, m
            else:
                m = min(prev_m, float(e.norm.max()))
                items[iid] = {"value": False, "margin_norm": _f(m), "margin_raw": None, "t": None}
                prev_m = m
        if first_unreached is None:
            cls = "S"
        if goal_met:
            cls = "S"
        units.append({"unit": u["unit"], "stage_reached": reached, "stage_class": cls,
                      "_first_unreached": first_unreached})

    # §4 constraints
    cons_items = [it for it in rub["items"] if it["section"] == "never"]
    cons_margins, violated, first_violation = {}, [], None
    n_units_for = {}
    for st in doc.get("stages") or []:
        n_units_for[st["id"]] = len(st.get("for_each") or [None])
    for it in cons_items:
        after = it["after"]
        if after == "start":
            t0 = 0
        else:
            sid = after[6:]
            ts = reach.get(sid, [])
            t0 = max(ts) if len(ts) == n_units_for.get(sid, 1) else None
        if t0 is None:
            cons_margins[it["constraint"]] = None
            continue
        e = Expr(rubric.parse(it["source"]), tr, cache)
        w = e.norm[t0:]
        rho_c = float((-w).min())
        hit = np.flatnonzero(w > 0)
        cons_margins[it["constraint"]] = _f(rho_c)
        items[it["id"]] = {"value": bool(hit.size), "margin_norm": _f(-rho_c), "margin_raw": None,
                           "t": _f(tsec[t0 + int(hit[0])]) if hit.size else None}
        if hit.size:
            violated.append(it["constraint"])
            if first_violation is None or t0 + int(hit[0]) < first_violation[1]:
                first_violation = (it["constraint"], t0 + int(hit[0]))

    success = bool(goal_met and not violated)
    live = [v for v in cons_margins.values() if v is not None]
    episode_margin = min([goal_margin] + live)

    # first failed predicate
    first_failed = None
    if not goal_met:
        fu = next((u["_first_unreached"] for u in units if u["_first_unreached"] is not None), None)
        if fu is not None:
            iid, it, e, w0 = fu
            ts = w0 + int(np.argmax(e.norm[w0:]))
            first_failed = {"stage": it["stage"], "unit": it["unit"], "predicate": e.deciding_leaf(ts),
                            "t": _f(tsec[ts])}
        elif seq is not None:
            k = seq["first_failed"]
            e = steps[k]
            prev = seq["times"][k - 1] if k > 0 else 0
            if seq["times"][k] is not None:            # last step timed but false at T
                ts = T
            elif k > 0 and e.norm[prev] > 0:            # out of order: already true at t(k-1)
                ts = prev
            else:
                ts = prev + int(np.argmax(e.norm[prev:]))
            first_failed = {"stage": None, "unit": None, "step": k + 1, "predicate": e.deciding_leaf(ts),
                            "t": _f(tsec[ts])}
        else:
            first_failed = {"stage": None, "unit": None, "predicate": Expr(tree, tr, cache).deciding_leaf(T),
                            "t": _f(tsec[T])}
    elif violated:
        first_failed = {"stage": None, "unit": None, "predicate": f"constraint:{first_violation[0]}",
                        "t": _f(tsec[first_violation[1]])}

    stage_times = {}
    for sid, ts in reach.items():
        stage_times[sid] = _f(tsec[max(ts)]) if len(ts) == n_units_for.get(sid, 1) else None
    for u in units:
        u.pop("_first_unreached")
    single = len(units) == 1
    outcome = {
        "checker": "spec_v0_grammar", "success": success, "goal_met": bool(goal_met), "goal_margin": _f(goal_margin),
        "episode_margin": _f(episode_margin), "margin_components": components, "constraint_margins": cons_margins,
        "constraint_failure": bool(goal_met and violated), "violated": violated,
        "stage_reached": units[0]["stage_reached"] if single else {u["unit"]: u["stage_reached"] for u in units},
        "stage_class": units[0]["stage_class"] if single else {u["unit"]: u["stage_class"] for u in units},
        "stage_times": stage_times, "stage_units": units, "first_failed": first_failed, "terminal_class": None,
    }
    truth = {"success": success, "success_at_defaults": None, "items": items}
    if defaults:
        truth["success_at_defaults"] = evaluate(at_defaults(doc), trace, feasibility, defaults=False)["outcome"]["success"]
    return {"record": OUTCOME_RECORD, "checker_version": CHECKER_VERSION, "scenario_id": doc["id"],
            "scenario_hash": rubric.scenario_hash(doc),
            "items_sha256": hashlib.sha256(rubric.canonical(rub)).hexdigest(),
            "trace_sha256": hashlib.sha256(rubric.canonical(trace.rec)).hexdigest(),
            "n_steps": trace.n, "t_end": _f(tsec[T]), "outcome": outcome, "truth": truth}


# ---------------------------------------------------------------- the §3 defaults variant
def to_source(node) -> str:
    """A parsed expression back to text; numbers by repr, so the round trip is exact."""
    if node[0] == "pred":
        return f"{node[1]}(" + ", ".join(repr(x) if isinstance(x, float) else x for x in node[2]) + ")"
    if node[0] == "not":
        return "not " + to_source(node[1])
    return f"{node[0]}(" + ", ".join(to_source(k) for k in node[1]) + ")"


def _with_defaults(node):
    if node[0] == "pred":
        name, a = node[1], list(node[2])
        if name == "inside":
            return ("pred", name, a[:2] + [DEFAULT_INSIDE_TOL])
        if name == "on":
            return ("pred", name, a[:2] + [DEFAULT_ON_TOL])
        return node
    if node[0] == "not":
        return ("not", _with_defaults(node[1]))
    return (node[0], [_with_defaults(k) for k in node[1]])


def at_defaults(doc: dict) -> dict:
    """The document with every inside and on tolerance set to the §3 defaults (goal, stages and constraints)."""
    d = copy.deepcopy(doc)

    def fix(text, **kw):
        return to_source(_with_defaults(rubric.parse(text, **kw)))
    g = d.get("goal")
    if isinstance(g, dict):
        d["goal"] = {k: fix(v, allow_seq=True) for k, v in g.items()}
    else:
        d["goal"] = fix(g, allow_seq=True)
    for st in d.get("stages") or []:
        st["holds"] = fix(st["holds"], allow_stage=True)          # "$o" parses as a name and is written back
    for c in d.get("constraints") or []:
        c["never"] = fix(c["never"])
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scenario")
    ap.add_argument("trace")
    ap.add_argument("--feasibility")
    ap.add_argument("--truth", action="store_true", help="print only the truth block")
    a = ap.parse_args(argv)
    try:
        out = evaluate(rubric.load_document(Path(a.scenario)), load_trace(a.trace), a.feasibility)
    except (TraceError, rubric.CompileError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(out["truth"] if a.truth else out, sort_keys=True, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
