# Robotense home robot test standard

[![validate](https://github.com/robotense/home-robot-test-standard/actions/workflows/validate.yml/badge.svg)](https://github.com/robotense/home-robot-test-standard/actions/workflows/validate.yml)

The Robotense test standard defines how a home-robot test is written, how each trial is recorded and scored, and how far a simulated result can be relied on for a real robot. `spec/v0.md` defines the scenario document (one per test: the task, the scene and its named objects, the factors that may vary, the goal with its margins, the constraints and the stages), the episode record (one per trial), the trust entry, the benchmark records (reference set and entry card), the credibility assessment records (cell agreement, assessment plan and calibration manifest) and the twin calibration record. `spec/variance-v0.md` defines the home variance classification, a shared vocabulary for the conditions a home robot operates in, and the variance card, the record format for one condition, which compiles into scene edits and the factors of a scenario document.

## Status

Version v0, draft. Robotense publishes and maintains the standard. The episode record is at v0.3 and the trust entry at v0.4; the other records are at v0. `spec/variance-v0.md` is draft v0 with draft v0.1 additions. Versioning rules are in `spec/v0.md` §14.

## What it builds on

Goal conditions build on BDDL's declarative goal predicates (Srivastava et al., 2021). Margins follow signal temporal logic, and ordered steps and "never" constraints follow temporal logic over finite traces. The classification takes its split into fixed scenery, ambient conditions and moving agents from ISO 34503:2023. The lineage of each part is stated at the top of each text.

## Contents

| Path | Contents |
|---|---|
| `spec/v0.md` | The scenario spec: scenario documents, episode records, trust entries, benchmark records, credibility assessment records, twin calibration records, versions |
| `spec/variance-v0.md` | The home variance classification and the variance card |
| `spec/validate.py` | Validator for episode records, trust entries, benchmark records, credibility assessment records and twin calibration records |
| `spec/checker.py` | Reference evaluator of a scenario document's goal, constraints and stages over a recorded state trace, with margins |
| `spec/rubric.py` | Parser of the goal grammar, item numbering, and the rules that combine item values into a verdict; used by `checker.py` |
| `spec/physics_options.py` | Reference definition of the physics-options hash in the episode record (`simulator.physics_options_sha256`) |
| `spec/tests/` | Tests of episode record and trust entry versions, of the physics-options hash and of the checker on the example traces |
| `spec/examples/scenarios/` | Scenario documents: the three worked examples of `spec/v0.md` §10, and two tasks from our failure-search pilot |
| `spec/examples/pilot-episodes-mug-in-bowl.jsonl` | Episode records from a simulated run |
| `spec/examples/data/synthetic/` | Synthetic episode records in the v0.1 format, and two state traces for worked example 1 |
| `spec/examples/sim-agreement-r2-*.json` | A benchmark reference set and entry card, both drafts |
| `spec/examples/ca-widowx-*` | Credibility assessment records built from published counts, marked `illustration` (`spec/v0.md` §12) |
| `spec/examples/twin-calibration-so101-armnetbench.json` | A twin calibration record with status `uncalibrated` (`spec/v0.md` §13) |
| `.github/workflows/validate.yml` | Runs the validator and the tests on Python 3.11 and 3.13 for every push and pull request |
| `LICENSE` | Apache License 2.0, for code and examples |
| `LICENSE-docs` | Creative Commons Attribution 4.0 International, for the text |

Records under `spec/examples/data/synthetic/` carry `"synthetic": true`. They show the record format and are never evidence.

## Running the validator and tests

Run from the repository root with Python 3.9 or later.

```
python3 -I spec/validate.py                          # every record in spec/examples/, then the rejection self-test
python3 -I spec/validate.py FILE ...                 # the named records
python3 -I -B -m unittest discover -s spec/tests
```

The validator checks each record's fields, values and links to the records it cites. Its self-test applies known faults to the examples and fails unless each is rejected. It exits with status 1 on any problem.

Requirements:
- `spec/validate.py` and the tests use the standard library only, with two exceptions that are skipped when the package is missing: the checker tests need NumPy and PyYAML, and one physics-options test needs the `mujoco` package.
- `spec/checker.py` needs NumPy, and PyYAML to read YAML scenario files. Usage and the state trace format are in its docstring.
- `spec/rubric.py` uses the standard library, and PyYAML to read YAML scenario files.
- The command line of `spec/physics_options.py` needs the `mujoco` package.

## Score a trial

`spec/checker.py` scores one trial. It evaluates a scenario document's goal, constraints and stages over the trial's recorded state trace (record `spec.state_trace.v0`; the format is in the checker's docstring) and prints the outcome as JSON. It needs NumPy and PyYAML. From the repository root, in a virtual environment:

```
python3 -m venv .venv
.venv/bin/python -m pip install numpy pyyaml
.venv/bin/python -I spec/checker.py spec/examples/scenarios/worked-example-1-mug-in-bowl.yaml \
    spec/examples/data/synthetic/worked-example-1-mug-in-bowl.success.trace.json
```

The trial succeeds: `"success": true`, stage class `S` (every stage reached), and every item of the document (stages `S1`-`S3`, goal leaves `G1`-`G3`) true with a positive margin. A normalised margin of 1 is one tolerance of clearance (`spec/v0.md` §3).

<details>
<summary>Expected output</summary>

```
{
 "checker_version": "0.1.0",
 "items_sha256": "9dcf1680382ad1a5d388df5e569ce0609da452d3bee25c13fbe864aa63e2b72c",
 "n_steps": 426,
 "outcome": {
  "checker": "spec_v0_grammar",
  "constraint_failure": false,
  "constraint_margins": {},
  "episode_margin": 0.998991,
  "first_failed": null,
  "goal_margin": 0.998991,
  "goal_met": true,
  "margin_components": {
   "gripper_released(mug)": 1.2554,
   "inside(mug, bowl, 0.07)": 1.0,
   "upright(mug, 30)": 0.998991
  },
  "stage_class": "S",
  "stage_reached": "finish",
  "stage_times": {
   "acquire": 3.3,
   "finish": 8.02,
   "transport": 5.14
  },
  "stage_units": [
   {
    "stage_class": "S",
    "stage_reached": "finish",
    "unit": null
   }
  ],
  "success": true,
  "terminal_class": null,
  "violated": []
 },
 "record": "spec.checker_outcome.v0",
 "scenario_hash": "6f65f5175e1680d2cbc02726d0282041d34d7e9ca2e26639acb30532a9f3a03b",
 "scenario_id": "kitchen_mug_in_bowl_001",
 "t_end": 8.5,
 "trace_sha256": "029aa4bbeaabd29120310dc14d63683b6341da5308dd1b42173946a11c1f4093",
 "truth": {
  "items": {
   "G1": {
    "margin_norm": 1.0,
    "margin_raw": 0.07,
    "t": 8.5,
    "value": true
   },
   "G2": {
    "margin_norm": 0.998991,
    "margin_raw": 29.969742,
    "t": 8.5,
    "value": true
   },
   "G3": {
    "margin_norm": 1.2554,
    "margin_raw": 0.006277,
    "t": 8.5,
    "value": true
   },
   "S1": {
    "margin_norm": 2.427,
    "margin_raw": null,
    "t": 3.3,
    "value": true
   },
   "S2": {
    "margin_norm": 1.0,
    "margin_raw": null,
    "t": 5.14,
    "value": true
   },
   "S3": {
    "margin_norm": 0.99938,
    "margin_raw": null,
    "t": 8.02,
    "value": true
   }
  },
  "success": true,
  "success_at_defaults": true
 }
}
```

</details>

The second trace, `worked-example-1-mug-in-bowl.failure.trace.json`, gives `"success": false`, stage class `T` and `first_failed` at stage `transport` on `inside(mug, bowl, 0.07)`: the mug was lifted but ended outside the bowl, on its side. The exit status is 0 whenever the trial is scored, whatever the verdict, and 2 when the document or trace is invalid.

Both traces were recorded in MuJoCo in a stand-in scene, our failure-search pilot's mug-in-bowl scene with a scripted Franka Panda policy, and not in the scene the document names. They are marked `"synthetic": true` and show the format; they are never evidence. Each file states this in `x.about`.

## Licences

- Text (`README.md`, `spec/v0.md`, `spec/variance-v0.md`): CC BY 4.0, in `LICENSE-docs`.
- Code and examples (the Python files, `spec/tests/`, `spec/examples/`): Apache-2.0, in `LICENSE`.

To credit the text: "Robotense home robot test standard v0, https://github.com/robotense/home-robot-test-standard, CC BY 4.0", and state any changes you made. When you redistribute the code or examples, include `LICENSE` and meet its redistribution terms (section 4).

## Contact

https://robotense.com

contact@robotense.com
