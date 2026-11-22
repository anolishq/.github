"""The reusable workflows' setup-vcpkg steps (#174).

Run: python3 -m unittest discover tests

Each reusable workflow that installs vcpkg dependencies uses setup-vcpkg v3,
which keeps packages in the org's R2 bucket and picks read or write from the
event. A called workflow sees only the secrets its caller passes, so callers
add `secrets: inherit`; without it the job builds without the remote cache.
The `cache-write` input, and `triplet` where it only named the old cache key,
stay accepted so existing callers keep working, and are ignored.
"""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
V3_PIN = "anolishq/.github/.github/actions/setup-vcpkg@655d35b035ac85416e33be70d810b7e8b17b15cb"

R2_INPUTS = {
    "r2-endpoint": "${{ vars.VCPKG_R2_ENDPOINT }}",
    "r2-bucket": "${{ vars.VCPKG_R2_BUCKET }}",
    "r2-read-access-key-id": "${{ secrets.VCPKG_R2_READ_ACCESS_KEY_ID }}",
    "r2-read-secret-access-key": "${{ secrets.VCPKG_R2_READ_SECRET_ACCESS_KEY }}",
    "r2-write-access-key-id": "${{ secrets.VCPKG_R2_WRITE_ACCESS_KEY_ID }}",
    "r2-write-secret-access-key": "${{ secrets.VCPKG_R2_WRITE_SECRET_ACCESS_KEY }}",
}

# The workflows this module is about; the scan below must find each of them.
EXPECTED = {"fuzz.yml", "valgrind-leak.yml", "clang-tidy-diff.yml", "dependency-scan.yml"}


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers(doc):
    # PyYAML reads the bare key `on` as the boolean True.
    return doc.get("on", doc.get(True)) or {}


def setup_vcpkg_steps(doc):
    return [s for job in doc["jobs"].values() for s in job.get("steps", [])
            if "/actions/setup-vcpkg" in str(s.get("uses", ""))]


def reusable_steps():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc = load(path)
        if "workflow_call" in triggers(doc):
            for step in setup_vcpkg_steps(doc):
                yield path.name, doc, step


class ReusableWorkflowsUseV3Test(unittest.TestCase):
    def test_the_scan_sees_every_workflow(self):
        self.assertEqual({name for name, _, _ in reusable_steps()}, EXPECTED)

    def test_each_step_pins_v3_and_passes_the_r2_inputs(self):
        for name, _, step in reusable_steps():
            with self.subTest(workflow=name):
                self.assertEqual(step["uses"], V3_PIN)
                self.assertEqual(step.get("with"), R2_INPUTS)

    def test_old_inputs_stay_accepted(self):
        """Removing a workflow_call input fails every caller that still passes it."""
        for name, doc, _ in reusable_steps():
            inputs = triggers(doc)["workflow_call"]["inputs"]
            for old in ("triplet", "cache-write"):
                with self.subTest(workflow=name, input=old):
                    self.assertIn(old, inputs)
                    self.assertIs(inputs[old].get("required", False), False)

    # A cold cache makes clang-tidy-diff build every dependency from source,
    # which takes longer than 30 minutes for a caller with protobuf. The caller
    # sets the limit; the default keeps every existing caller at 30.
    def test_clang_tidy_diff_timeout_is_an_input_defaulting_to_30(self):
        doc = load(WORKFLOWS / "clang-tidy-diff.yml")
        spec = triggers(doc)["workflow_call"]["inputs"].get("timeout-minutes")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.get("type"), "number")
        self.assertIs(spec.get("required", False), False)
        self.assertEqual(spec.get("default"), 30)
        self.assertEqual(doc["jobs"]["clang-tidy-diff"]["timeout-minutes"], "${{ inputs.timeout-minutes }}")


if __name__ == "__main__":
    unittest.main()
