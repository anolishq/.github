"""Tests for the require-needs-passed action, the check behind a repo's `ok` job.

Run: python3 -m unittest discover tests
"""
import os
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ACTION = ROOT / ".github" / "actions" / "require-needs-passed" / "action.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def run_action(results):
    step = yaml.safe_load(ACTION.read_text(encoding="utf-8"))["runs"]["steps"][0]
    env = dict(os.environ, RESULTS=results)
    return subprocess.run(["bash", "-e", "-c", step["run"]], env=env, capture_output=True, text=True, check=False)


class RequireNeedsPassedTest(unittest.TestCase):
    def test_passes_when_every_job_succeeded_or_was_skipped(self):
        for results in ("success", "skipped", "success skipped success"):
            with self.subTest(results):
                self.assertEqual(run_action(results).returncode, 0)

    def test_fails_on_any_other_result(self):
        # `abandoned` is what GitHub reported for jobs that never ran
        # (anolishq/.github#168); the unknown value stands for one added later.
        for bad in ("failure", "cancelled", "abandoned", "some_future_result"):
            with self.subTest(bad):
                result = run_action(f"success {bad} skipped")
                self.assertEqual(result.returncode, 1)
                self.assertIn(f"ended as '{bad}'", result.stdout)

    def test_fails_when_given_no_results(self):
        # An empty input means the caller's expression is wrong, not that all passed.
        for empty in ("", "   "):
            with self.subTest(repr(empty)):
                self.assertEqual(run_action(empty).returncode, 1)

    def test_this_repo_ok_job_uses_the_action(self):
        job = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["ok"]
        step = next(s for s in job["steps"] if s.get("uses") == "./.github/actions/require-needs-passed")
        self.assertEqual(step["with"]["results"], "${{ join(needs.*.result, ' ') }}")
        self.assertEqual(job["if"], "always()")


if __name__ == "__main__":
    unittest.main()
