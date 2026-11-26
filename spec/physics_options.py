"""Reference definition of `simulator.physics_options_sha256` (spec/v0.md §8.1, episode record v0.2). Standard library.

The hash covers the simulator's global physics option struct as compiled into the model the episode ran, read at the
first step: every field of the struct, by its name in the simulator's bindings, with its value. For MuJoCo that is
every public field of `mjOption` (`model.opt`): integers (enums and flags included) as JSON integers, reals as JSON
numbers, arrays as lists of numbers. The map is serialised as canonical JSON (keys sorted, no whitespace, UTF-8,
Python's shortest round-trip float text; the `canonical` function of `spec/validate.py`) and hashed
with SHA-256.

What it covers and what it does not: the option struct only (timestep, integrator, solver, iterations, tolerances,
cone, impratio, noslip and CCD settings, global contact overrides, gravity, wind, density, viscosity, flags). Per-geom
friction, masses, solver parameters set on bodies or geoms, and the model's contents are not in it; a friction band
that scales a geom's friction leaves the hash unchanged. The field set is the bindings' own, so a MuJoCo release that
adds a field changes the hash of equal values: two hashes are compared only between
records with equal `simulator.name` and `simulator.version`.

    from physics_options import options_map, options_sha256
    options_sha256(model.opt)          # MuJoCo: the compiled model's option struct
    python3 -I spec/physics_options.py <model.xml>   # needs the mujoco package; prints the map's hash
"""
from __future__ import annotations

import hashlib
import json
import math
import sys

DEFINITION = "spec/physics_options.py v1"


def _value(v):
    """A field value as JSON: bool refused, integers kept, reals as float, arrays (anything with `tolist`, or a
    sequence) as lists."""
    if hasattr(v, "tolist"):
        v = v.tolist()
    if isinstance(v, bool):
        raise TypeError("an option field is a number or an array of numbers, not a bool")
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if not math.isfinite(v):
            raise ValueError("an option field is finite")
        return v
    if isinstance(v, (list, tuple)):
        return [_value(x) for x in v]
    raise TypeError(f"an option field is a number or an array of numbers, not {type(v).__name__}")


def options_map(opt) -> dict:
    """Every public, non-callable field of the option struct (or the items of a mapping), name → JSON value."""
    if isinstance(opt, dict):
        items = opt.items()
    else:
        items = ((k, getattr(opt, k)) for k in dir(opt) if not k.startswith("_"))
    out = {}
    for k, v in items:
        if callable(v):
            continue
        out[k] = _value(v)
    if not out:
        raise ValueError("the option struct has no fields")
    return out


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def options_sha256(opt) -> str:
    return hashlib.sha256(canonical(options_map(opt))).hexdigest()


def main():
    import mujoco   # only for the command line; the definition itself needs no simulator

    model = mujoco.MjModel.from_xml_path(sys.argv[1])
    print(options_sha256(model.opt), f"(MuJoCo {mujoco.__version__}, {DEFINITION})")


if __name__ == "__main__":
    main()
