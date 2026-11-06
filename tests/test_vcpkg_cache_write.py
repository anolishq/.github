"""Which reusable workflows may save the vcpkg binary cache.

Run: python3 -m unittest discover tests

setup-vcpkg keys the binary cache by os, arch, triplet, compiler, vcpkg
baseline, runner image and manifest, and saves it unless `cache-write` is
"false". Every job in a caller with the same triplet and compiler shares one
key, and a cache entry cannot be overwritten, so the first job to save it
keeps it. A reusable workflow that builds only part of the caller's
dependencies finishes early, saves a cache without the expensive packages, and
leaves the caller's full build unable to save ("Unable to reserve cache with
key ..."). Every later job then gets an exact hit on that partial cache and
builds the rest from source.

So the gcc workflows restore the cache but save it only when the caller passes
`cache-write: "true"`. fuzz.yml builds with Clang, so its key never matches a
gcc build's; it is usually the only job that can save its key, and keeps
saving by default.
"""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
ACTION = ROOT / ".github" / "actions" / "setup-vcpkg" / "action.yml"

# workflow -> the default of its cache-write input
CACHE_WRITE_DEFAULT = {
    "valgrind-leak.yml": "false",
    "dependency-scan.yml": "false",
    "clang-tidy-diff.yml": "false",
    "fuzz.yml": "true",
}


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers(doc):
    # PyYAML reads the bare key `on` as the boolean True.
    return doc.get("on", doc.get(True)) or {}


def setup_vcpkg_steps(doc):
    return [s for job in doc["jobs"].values() for s in job.get("steps", [])
            if "/actions/setup-vcpkg" in str(s.get("uses", ""))]


class CacheWriteInputTest(unittest.TestCase):
    def test_cache_write_input_and_its_default(self):
        for name, default in CACHE_WRITE_DEFAULT.items():
            with self.subTest(workflow=name):
                inputs = triggers(load(WORKFLOWS / name))["workflow_call"]["inputs"]
                self.assertIn("cache-write", inputs)
                spec = inputs["cache-write"]
                # A string, as setup-vcpkg's own input is, so the value passes
                # through unchanged; "false", not the YAML boolean false.
                self.assertEqual(spec.get("type"), "string")
                self.assertIs(spec.get("required", False), False)
                self.assertEqual(spec.get("default"), default)

    def test_setup_vcpkg_gets_the_cache_write_input(self):
        for name in CACHE_WRITE_DEFAULT:
            with self.subTest(workflow=name):
                steps = setup_vcpkg_steps(load(WORKFLOWS / name))
                self.assertEqual(len(steps), 1)
                self.assertEqual(steps[0].get("with", {}).get("cache-write"),
                                 "${{ inputs.cache-write }}")

    def test_fuzz_builds_with_clang(self):
        """fuzz.yml may keep saving only while its key carries a Clang compiler hash."""
        env = load(WORKFLOWS / "fuzz.yml").get("env", {})
        self.assertEqual((env.get("CC"), env.get("CXX")), ("clang", "clang++"))


class ReusableWorkflowsChooseTest(unittest.TestCase):
    def test_every_reusable_setup_vcpkg_step_sets_cache_write(self):
        """A reusable workflow states whether it saves, instead of inheriting "true"."""
        checked = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            doc = load(path)
            if "workflow_call" not in triggers(doc):
                continue
            for step in setup_vcpkg_steps(doc):
                checked.append(path.name)
                with self.subTest(workflow=path.name, step=step.get("name")):
                    self.assertIn("cache-write", step.get("with", {}))
        # The scan saw the workflows this module is about.
        self.assertTrue(set(CACHE_WRITE_DEFAULT) <= set(checked), checked)


class SetupVcpkgDefaultTest(unittest.TestCase):
    def test_action_still_writes_by_default(self):
        """Callers' main builds call the action directly and rely on it saving."""
        spec = load(ACTION)["inputs"]["cache-write"]
        self.assertEqual(spec.get("default"), "true")


if __name__ == "__main__":
    unittest.main()
