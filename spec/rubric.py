#!/usr/bin/env python3
"""Document parser and item rules of spec v0 (spec/v0.md §3-§5, §9), used by spec/checker.py. Standard library only;
reading a YAML scenario needs PyYAML (`yaml.safe_load`), a JSON scenario needs nothing else.

- `parse()`: the §3 grammar. Only the grammar parses, plus the §5 derived predicate `lifted` inside stages; the draft
  predicates listed under "Proposed predicates" in §3 raise `CompileError` until they join the grammar. `seq` parses
  only as the whole top-level goal; a `seq` inside `all`, `any` or another `seq`, or in a stage or constraint, raises
  `CompileError`.
- `compile_items()`: a scenario document as numbered items, in this order:
  - **Stages** (S1, S2, ...): the §5 stages in their declared order, each reached at or after the stage before.
    `for_each` stages expand to one unit per object (S1[plate], S1[cube], ...), listed in `stage_units`.
  - **Goal** (G1, G2, ...): the §3 goal. A goal made of `all` and `any` is split into its leaf predicates, evaluated at
    the end and combined by `goal_tree`. A top-level `seq` gives one item per step, in order.
  - **Never** (C1, C2, ...): the §4 constraints, each evaluated over every step after `after`.
- `seq_holds()`: the reference evaluator of §3 ordered steps (first-time-true steps, window margins) on per-step
  margin traces.
- `decide()`: the verdict from item values `true`, `false` or `cannot_tell`, by the checker's rules (§3 min/max as
  three-valued and/or, §4 constraint failure with the goal met, §5 stage class). spec/checker.py computes the item
  values from a state trace, and `decide()` on them reproduces its verdict.
- `scenario_hash()`: the §1 hash, SHA-256 of the canonical JSON of the document without `trust`, as in
  `spec/validate.py`.

The checker's items and the rules that combine them come from the same goal, stage and constraint expressions as its
margins, so a verdict can be traced to one item, one predicate and one tolerance.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

RUBRIC_VERSION = "0.2.0"   # version of the item numbering and rules

# §3 default tolerances.
DEFAULT_INSIDE_TOL = 0.07      # m
DEFAULT_ON_TOL = 0.03          # m
DEFAULT_ON_GAP = 0.01          # m, contact_gap_max
DEFAULT_UPRIGHT_DEG = 30.0     # degrees
RELEASE_CLEARANCE = 0.005      # m, gripper_released

GRAMMAR_PREDICATES = ("inside", "on", "upright", "gripper_released", "joint_above")
STAGE_ONLY_PREDICATES = ("lifted",)   # §5 derived predicate, an event over the whole history
DRAFT_PREDICATES = ("base_stalled", "any_tipped", "opened", "grasping", "close_to", "collides", "wedged",
                    "limit_force_above", "reported_unable")
ANSWERS = ("true", "false", "cannot_tell")


class CompileError(ValueError):
    """The document is not a spec v0 scenario this parser can read."""


# ---------------------------------------------------------------- hashing, as spec/validate.py
def canonical(record) -> bytes:
    return json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def scenario_hash(doc: dict) -> str:
    """§1: SHA-256 over the canonical JSON of the document, excluding `trust`."""
    return hashlib.sha256(canonical({k: v for k, v in doc.items() if k != "trust"})).hexdigest()


# ---------------------------------------------------------------- expression parser (§3 grammar)
TOKEN = re.compile(r"\s*(?:(?P<num>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|(?P<name>\$?[A-Za-z_][A-Za-z0-9_.]*)|(?P<p>[(),]))")


def tokenize(text: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise CompileError(f"cannot parse expression at {text[pos:]!r} in {text!r}")
        kind = m.lastgroup
        out.append((kind, m.group(kind)))
        pos = m.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return out


def parse(text: str, allow_stage: bool = False, allow_seq: bool = False):
    """Parse a §3 expression into a tree: ("all"|"any"|"seq", [children]), ("not", child) or
    ("pred", name, [args]) with args as str or float. `seq` is accepted only as the whole expression and only when
    allow_seq (the top-level goal, §3); anywhere else, nested or in a stage or constraint, it is refused."""
    if not isinstance(text, str):
        raise CompileError(f"expression must be a string, got {text!r}")
    toks = tokenize(text)
    i = 0

    def peek():
        return toks[i] if i < len(toks) else (None, None)

    def take(kind=None, value=None):
        nonlocal i
        k, v = peek()
        if k is None or (kind and k != kind) or (value and v != value):
            raise CompileError(f"expected {value or kind} in {text!r}")
        i += 1
        return v

    def args():
        take("p", "(")
        out = []
        while True:
            k, v = peek()
            if k == "num":
                out.append(float(take("num")))
            elif k == "name":
                out.append(take("name"))
            else:
                raise CompileError(f"bad argument in {text!r}")
            if peek() == ("p", ","):
                take("p", ",")
                continue
            take("p", ")")
            return out

    def node(depth=0):
        name = take("name")
        if name == "seq" and not (allow_seq and depth == 0):
            raise CompileError(f"'seq' is allowed only as the whole top-level goal (§3): {text!r}")
        if name in ("all", "any", "seq"):
            take("p", "(")
            kids = [node(depth + 1)]
            while peek() == ("p", ","):
                take("p", ",")
                kids.append(node(depth + 1))
            take("p", ")")
            return (name, kids)
        if name == "not":
            child = node(depth + 1)
            if child[0] in ("all", "any", "seq"):
                raise CompileError(f"'not' applies to a predicate only (§3 grammar): {text!r}")
            return ("not", child)
        if name in DRAFT_PREDICATES:
            raise CompileError(f"predicate {name!r} is proposed in spec v0 §3 and is outside the grammar: {text!r}")
        if name not in GRAMMAR_PREDICATES and not (allow_stage and name in STAGE_ONLY_PREDICATES):
            raise CompileError(f"unknown predicate {name!r} in {text!r}")
        return ("pred", name, check_args(name, args(), text))

    tree = node()
    if i != len(toks):
        raise CompileError(f"trailing text in {text!r}")
    return tree


def check_args(name, a, text):
    def objs(n):
        return all(isinstance(x, str) for x in a[:n])

    def nums(start):
        return all(isinstance(x, float) for x in a[start:])

    ok = {
        "inside": len(a) in (2, 3) and objs(2) and nums(2),
        "on": len(a) in (2, 3) and objs(2) and nums(2),
        "upright": len(a) in (1, 2) and objs(1) and nums(1),
        "gripper_released": len(a) == 1 and objs(1),
        "joint_above": len(a) == 3 and objs(2) and nums(2),
        "lifted": len(a) == 2 and objs(1) and nums(1),
    }[name]
    if not ok:
        raise CompileError(f"wrong arguments for {name} in {text!r}")
    for x in a:
        if isinstance(x, float) and name != "joint_above" and x <= 0:
            raise CompileError(f"tolerance must be positive in {text!r}")
    return a


def substitute(text: str, obj: str) -> str:
    return re.sub(r"\$o\b", obj, text)


# ---------------------------------------------------------------- numbers
def num(x: float, digits: int = 1) -> str:
    s = f"{x:.{digits}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def leaf_source(node) -> str:
    if node[0] == "not":
        return "not " + leaf_source(node[1])
    if node[0] == "pred":
        return f"{node[1]}(" + ", ".join(num(x, 4) if isinstance(x, float) else x for x in node[2]) + ")"
    return f"{node[0]}(" + ", ".join(leaf_source(k) for k in node[1]) + ")"


# ---------------------------------------------------------------- loading
def load_document(path: Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:  # pragma: no cover
            raise CompileError("reading a YAML scenario needs PyYAML; give the document as JSON instead") from e
        doc = yaml.safe_load(text)
    else:
        doc = json.loads(text)
    if not isinstance(doc, dict):
        raise CompileError(f"{path}: not a mapping")
    return doc


# ---------------------------------------------------------------- items
def compile_items(doc: dict, feasibility: str | None = None) -> tuple[dict, dict]:
    """Spec v0 scenario document -> ({items, stage_units, goal_tree}, {item id: parsed expression}). Each item has
    `id`, `section` (stage, goal, never) and `source`; a stage item also `stage`, `unit`, `class_if_not_reached` and
    `skill`; a never item `constraint`, `after` and `failure_type`."""
    if doc.get("spec_version") != "v0":
        raise CompileError("spec_version must be 'v0'")
    if not isinstance(doc.get("id"), str) or not doc["id"]:
        raise CompileError("scenario needs an 'id'")

    # goal, with the draft feasibility block (§1)
    goal = doc.get("goal")
    if isinstance(goal, dict):
        if feasibility is None:
            raise CompileError(f"goal depends on feasibility status ({', '.join(sorted(goal))}); choose one")
        if feasibility not in goal:
            raise CompileError(f"no goal for feasibility status {feasibility!r}")
        goal = goal[feasibility]
    elif feasibility is not None:
        raise CompileError("feasibility given but the goal does not depend on it")
    if goal is None:
        raise CompileError("scenario needs a 'goal'")

    items, nodes = [], {}

    # stages (§5)
    units: dict[str, list] = {}
    for st in doc.get("stages") or []:
        if not isinstance(st, dict) or not {"id", "holds", "class_if_last_failed"} <= set(st):
            raise CompileError(f"stage needs id, holds and class_if_last_failed: {st!r}")
        if st["class_if_last_failed"] not in ("G", "T", "P"):
            raise CompileError(f"stage {st['id']}: class_if_last_failed must be G, T or P")
        objs = st.get("for_each")
        if objs is None:
            units.setdefault("", []).append((st, st["holds"]))
        else:
            for o in objs:
                units.setdefault(o, []).append((st, substitute(st["holds"], o)))
    stage_units = []
    for unit, rows in units.items():
        ids = []
        for n_, (st, holds) in enumerate(rows, 1):
            iid = f"S{n_}" + (f"[{unit}]" if unit else "")
            nodes[iid] = parse(holds, allow_stage=True)
            items.append({"id": iid, "section": "stage", "stage": st["id"], "unit": unit or None,
                          "class_if_not_reached": st["class_if_last_failed"], "skill": st.get("skill"),
                          "source": holds})
            ids.append(iid)
        stage_units.append({"unit": unit or None, "items": ids})

    # goal (§3)
    tree = parse(goal, allow_seq=True)
    leaves = []

    def goal_items(node, top=False):
        if top and node[0] == "seq":
            ids = []
            for k, step in enumerate(node[1], 1):
                iid = f"G{k}"
                nodes[iid] = step
                leaves.append({"id": iid, "section": "goal", "source": leaf_source(step)})
                ids.append(iid)
            return {"op": "seq", "args": ids}
        if node[0] in ("all", "any"):
            return {"op": node[0], "args": [goal_items(k) for k in node[1]]}
        iid = f"G{len(leaves) + 1}"
        nodes[iid] = node
        leaves.append({"id": iid, "section": "goal", "source": leaf_source(node)})
        return iid

    goal_tree = goal_items(tree, top=True)
    items.extend(leaves)

    # constraints (§4)
    for n_, c in enumerate(doc.get("constraints") or [], 1):
        if not isinstance(c, dict) or not {"id", "never"} <= set(c):
            raise CompileError(f"constraint needs id and never: {c!r}")
        after = c.get("after", "start")
        stage_ids = {st["id"] for st in doc.get("stages") or []}
        if not (after == "start" or (isinstance(after, str) and after.startswith("stage:") and after[6:] in stage_ids)):
            raise CompileError(f"constraint {c['id']}: after must be 'start' or stage:<id> of a declared stage")
        iid = f"C{n_}"
        nodes[iid] = parse(c["never"])
        items.append({"id": iid, "section": "never", "constraint": c["id"], "after": after,
                      "failure_type": c.get("failure_type"), "source": c["never"]})

    return {"items": items, "stage_units": stage_units, "goal_tree": goal_tree}, nodes


# ---------------------------------------------------------------- §3 ordered steps, reference evaluator
def seq_holds(margins) -> dict:
    """§3 `seq` with first-time-true steps, on per-step margin traces (margins[i][t] = rho_gi(s_t); true when > 0).

    t1 is the first t with g1 true; for i > 1, ti is the first t >= t(i-1) at which gi becomes true (true at t, false
    at t-1 or t = 0). The seq holds when every ti exists and the last step is true at T. Margins as §3 (window
    rule): a timed step i < n gives its largest margin over its window [ti, t(i+1)], or [ti, T] when
    t(i+1) does not exist; the last step, when timed, gives rho_gn(s_T). The first untimed step gives -rho_gi(s_t(i-1))
    when it was already true at t(i-1) (out of order), else its largest margin over [t(i-1), T], which is <= 0.
    rho is the min over the steps up to and including the first untimed step. Returns holds, rho, step_margins (one
    per step, None after the first untimed step), times (None for untimed steps) and first_failed (0-based step index
    or None)."""
    if not margins or len({len(m) for m in margins}) != 1 or not margins[0]:
        raise ValueError("need one non-empty margin trace per step, all the same length")
    n_t, n = len(margins[0]), len(margins)
    times, first_failed, prev = [], None, 0
    for i, m in enumerate(margins):
        if i == 0:
            t_i = next((t for t in range(n_t) if m[t] > 0), None)
        else:
            t_i = next((t for t in range(prev, n_t) if m[t] > 0 and (t == 0 or m[t - 1] <= 0)), None)
        if t_i is None:
            first_failed = i
            break
        times.append(t_i)
        prev = t_i
    step_margins = [None] * n
    for i, t_i in enumerate(times):
        m = margins[i]
        if i == n - 1:
            step_margins[i] = m[-1]
        else:
            end = times[i + 1] if i + 1 < len(times) else n_t - 1
            step_margins[i] = max(m[t_i:end + 1])
    if first_failed is not None:
        m, tp = margins[first_failed], (times[-1] if times else 0)
        step_margins[first_failed] = -m[tp] if first_failed > 0 and m[tp] > 0 else max(m[tp:])
    elif margins[-1][-1] <= 0:
        first_failed = n - 1
    times += [None] * (n - len(times))
    rho = min(v for v in step_margins if v is not None)
    return {"holds": first_failed is None, "rho": rho, "step_margins": step_margins, "times": times,
            "first_failed": first_failed}


# ---------------------------------------------------------------- verdict from item values
def _and(vals):
    return False if False in vals else (None if None in vals else True)


def _or(vals):
    return True if True in vals else (None if None in vals else False)


def decide(rubric: dict, answers: dict) -> dict:
    """Combine item values ('true', 'false', 'cannot_tell') with the checker's rules. `rubric` is a record with the
    `items`, `stage_units` and `goal_tree` of compile_items(); `answers` maps every item id to its value.

    success: goal true and no constraint violated (None when undetermined). constraint_failure: goal true and some
    constraint true (§4). Per stage unit: stage_reached is the last stage of the unbroken run of true answers from S1
    (§5, in order); stage_class is S when the goal holds or every stage of the unit was reached, otherwise the class of
    the first stage not reached (None when an answer before it is cannot_tell). first_failed: the first goal item
    answered false, for a failed goal."""
    ids = [it["id"] for it in rubric["items"]]
    missing = [i for i in ids if i not in answers]
    extra = [k for k in answers if k not in ids]
    bad = [k for k, v in answers.items() if v not in ANSWERS]
    if missing or extra or bad:
        raise ValueError(f"answers: missing {missing}, unknown {extra}, invalid values for {bad}")
    val = {k: {"true": True, "false": False, "cannot_tell": None}[v] for k, v in answers.items()}

    def ev(t):
        if isinstance(t, str):
            return val[t]
        vs = [ev(a) for a in t["args"]]
        return _or(vs) if t["op"] == "any" else _and(vs)

    goal = ev(rubric["goal_tree"])
    never = [val[it["id"]] for it in rubric["items"] if it["section"] == "never"]
    violated = _or(never) if never else False
    success = _and([goal, None if violated is None else not violated])
    by_id = {it["id"]: it for it in rubric["items"]}
    units = []
    for u in rubric["stage_units"]:
        reached, cls = None, None
        for iid in u["items"]:
            v = val[iid]
            if v is True:
                reached = by_id[iid]["stage"]
                continue
            cls = None if v is None else by_id[iid]["class_if_not_reached"]
            break
        else:
            cls = "S"
        if goal is True:
            cls = "S"
        units.append({"unit": u["unit"], "stage_reached": reached, "stage_class": cls})
    first_failed = None
    if goal is False:
        first_failed = next(it["id"] for it in rubric["items"] if it["section"] == "goal" and val[it["id"]] is False)
    return {"success": success, "goal_met": goal, "constraint_failure": (goal is True and violated is True),
            "violated": [it["constraint"] for it in rubric["items"] if it["section"] == "never" and val[it["id"]]],
            "stage_units": units, "first_failed": first_failed}
