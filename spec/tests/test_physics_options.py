"""Tests of the reference definition of `simulator.physics_options_sha256` (spec/physics_options.py; spec/v0.md §8.1,
v0.2). Standard library; the MuJoCo test runs only where the mujoco package is installed.

    python3 -I -m unittest discover -s spec/tests
"""
import json
import sys
import unittest
from pathlib import Path

SPEC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SPEC))

import physics_options as po  # noqa: E402

# The option struct of a kitchen scene (MuJoCo 4.0.1), as recorded from a compiled model, with noslip_iterations set
# to 4.
KITCHEN = {"ccd_iterations": 35, "ccd_tolerance": 1e-06, "cone": 1, "density": 0.0, "disableactuator": 0,
           "disableflags": 0, "enableflags": 0, "gravity": [0.0, 0.0, -9.81], "impratio": 10.0, "integrator": 3,
           "iterations": 100, "jacobian": 2, "ls_iterations": 50, "ls_tolerance": 0.01, "magnetic": [0.0, -0.5, 0.0],
           "noslip_iterations": 4, "noslip_tolerance": 1e-06, "o_friction": [1.0, 1.0, 0.005, 0.0001, 0.0001],
           "o_margin": 0.0, "o_solimp": [0.9, 0.95, 0.001, 0.5, 2.0], "o_solref": [0.02, 1.0], "sdf_initpoints": 40,
           "sdf_iterations": 10, "sleep_tolerance": 0.001, "solver": 2, "timestep": 0.002, "tolerance": 1e-08,
           "viscosity": 0.0, "wind": [0.0, 0.0, 0.0]}


class Struct:
    """Stand-in for a bindings struct: public attributes, a private one and a method, which are skipped."""

    def __init__(self, fields):
        self.__dict__.update(fields)
        self._private = 1

    def method(self):
        return 0


class PhysicsOptions(unittest.TestCase):
    def test_definition_pinned(self):
        """The hash of the recorded kitchen struct; a change to the definition changes it and must take a new version."""
        self.assertEqual(po.options_sha256(KITCHEN), "04b4cf885885d5bbd8cb6fdac56cc6d9efb2a00e2c8122ddd1b82df9a1b3e25b")

    def test_struct_and_mapping_agree(self):
        self.assertEqual(po.options_sha256(Struct(KITCHEN)), po.options_sha256(KITCHEN))

    def test_canonical_form(self):
        text = po.canonical(po.options_map(KITCHEN)).decode()
        self.assertNotIn(" ", text)
        self.assertEqual(list(json.loads(text)), sorted(KITCHEN))

    def test_any_field_changes_the_hash(self):
        base = po.options_sha256(KITCHEN)
        self.assertNotEqual(base, po.options_sha256(dict(KITCHEN, noslip_iterations=0)))
        self.assertNotEqual(base, po.options_sha256(dict(KITCHEN, o_solimp=[0.9, 0.95, 0.001, 0.5, 2.5])))
        self.assertNotEqual(base, po.options_sha256({k: v for k, v in KITCHEN.items() if k != "sleep_tolerance"}))

    def test_integer_and_real_are_distinct(self):
        """1 and 1.0 serialise differently: an enum read as a real would change the hash, so producers read the
        bindings' own types."""
        self.assertNotEqual(po.options_sha256(dict(KITCHEN, solver=2)), po.options_sha256(dict(KITCHEN, solver=2.0)))

    def test_refusals(self):
        for bad in ({"flag": True}, {"t": float("nan")}, {"t": "0.002"}, {}):
            with self.assertRaises((TypeError, ValueError)):
                po.options_map(bad)

    @unittest.skipUnless(__import__("importlib.util").util.find_spec("mujoco"), "mujoco not installed")
    def test_mujoco_struct(self):
        import mujoco
        m = mujoco.MjModel.from_xml_string('<mujoco><option noslip_iterations="4"/></mujoco>')
        mp = po.options_map(m.opt)
        self.assertEqual(mp["noslip_iterations"], 4)
        self.assertIn("timestep", mp)
        self.assertEqual(po.options_sha256(m.opt), po.options_sha256(mp))


if __name__ == "__main__":
    unittest.main()
