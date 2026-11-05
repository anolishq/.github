"""Tests for tests/workflow_steps.py, the helper the workflow tests run steps with.

Run: python3 -m unittest discover tests
"""
import unittest

from workflow_steps import render


class RenderTest(unittest.TestCase):
    def test_known_values_are_filled_in(self):
        self.assertEqual(render("a=${{ inputs.a }} b=${{inputs.b}}", {"inputs.a": "1", "inputs.b": 2}, {}),
                         "a=1 b=2")

    def test_unknown_expression_raises(self):
        # An expression the helper cannot evaluate must fail the test, not become "".
        with self.assertRaises(KeyError):
            render("${{ inputs.missing }}", {}, {})
        with self.assertRaises(KeyError):
            render("${{ inputs.a || 'x' }}", {"inputs.a": "1"}, {})

    def test_missing_output_of_a_known_step_renders_empty(self):
        self.assertEqual(render("[${{ steps.vg.outputs.ran }}]", {}, {"vg": {}}), "[]")
        self.assertEqual(render("${{ steps.vg.outputs.ran }}", {}, {"vg": {"ran": "true"}}), "true")

    def test_output_of_an_unknown_step_raises(self):
        with self.assertRaises(KeyError):
            render("${{ steps.other.outputs.ran }}", {}, {"vg": {}})

    def test_booleans_render_as_actions_does(self):
        self.assertEqual(render("${{ inputs.on }} ${{ inputs.off }}",
                                {"inputs.on": True, "inputs.off": False}, {}), "true false")
        self.assertEqual(render("${{ steps.s.outputs.b }}", {}, {"s": {"b": False}}), "false")


if __name__ == "__main__":
    unittest.main()
