# Robotense home robot test standard

The Robotense test standard defines how a home-robot test is written, how each trial is recorded and scored, and how far a simulated result can be relied on for a real robot. `spec/v0.md` defines the scenario document (one per test: the task, the scene and its named objects, the factors that may vary, the goal with its margins, the constraints and the stages), the episode record (one per trial), the trust entry, the benchmark records (reference set and entry card), the credibility assessment records (cell agreement, assessment plan and calibration manifest) and the twin calibration record. `spec/variance-v0.md` defines the home variance classification, a shared vocabulary for the conditions a home robot operates in, and the variance card, the record format for one condition, which compiles into scene edits and the factors of a scenario document.

## Status

Version v0, draft. Robotense publishes and maintains the standard. The episode record is at v0.2; the other records are at v0. `spec/variance-v0.md` is draft v0 with draft v0.1 additions. Versioning rules are in `spec/v0.md` §14.

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
| `spec/tests/` | Tests of episode record versions and of the physics-options hash |
| `spec/examples/scenarios/` | Scenario documents: the three worked examples of `spec/v0.md` §10, and two tasks from our failure-search pilot |
| `spec/examples/pilot-episodes-mug-in-bowl.jsonl` | Episode records from a simulated run |
| `spec/examples/data/synthetic/` | Synthetic episode records in the v0.1 format |
| `spec/examples/sim-agreement-r2-*.json` | A benchmark reference set and entry card, both drafts |
| `spec/examples/ca-widowx-*` | Credibility assessment records built from published counts, marked `illustration` (`spec/v0.md` §12) |
| `spec/examples/twin-calibration-so101-armnetbench.json` | A twin calibration record with status `uncalibrated` (`spec/v0.md` §13) |
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
- `spec/validate.py` and the tests use the standard library only. One test runs only when the `mujoco` package is installed and is skipped otherwise.
- `spec/checker.py` needs NumPy, and PyYAML to read YAML scenario files. Usage and the state trace format are in its docstring.
- `spec/rubric.py` uses the standard library, and PyYAML to read YAML scenario files.
- The command line of `spec/physics_options.py` needs the `mujoco` package.

## Licences

- Text (`README.md`, `spec/v0.md`, `spec/variance-v0.md`): CC BY 4.0, in `LICENSE-docs`.
- Code and examples (the Python files, `spec/tests/`, `spec/examples/`): Apache-2.0, in `LICENSE`.

To credit the text: "Robotense home robot test standard v0, https://github.com/robotense/home-robot-test-standard, CC BY 4.0", and state any changes you made. When you redistribute the code or examples, include `LICENSE` and meet its redistribution terms (section 4).

## Contact

https://robotense.com

research@robotense.com
