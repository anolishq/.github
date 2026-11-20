"""Tests for the Collect metrics step of metrics.yml.

Run: python3 -m unittest discover tests

tokei, cloc and tree are stand-ins that record their arguments, so the test
needs none of them installed; jq is the runner's.
"""
import os
import stat
import tempfile
import unittest
from pathlib import Path

from workflow_steps import run_step

WORKFLOW = "metrics.yml"
COLLECT = "Collect metrics"

RECORDER = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$ARGS_DIR/$(basename "$0").$$"
"""


class MetricsCollectTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.work = root / "work"
        self.work.mkdir()
        self.args = root / "args"
        self.args.mkdir()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        for tool in ("tokei", "cloc", "tree"):
            stub = bin_dir / tool
            stub.write_text(RECORDER)
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        self.env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "ARGS_DIR": str(self.args)}

    def tearDown(self):
        self._tmp.cleanup()

    def tokei_calls(self):
        return [p.read_text().splitlines() for p in sorted(self.args.glob("tokei.*"))]

    def run_collect(self, exclude_dirs):
        values = {"inputs.exclude-dirs": exclude_dirs, "github.repository": "anolishq/example",
                  "github.sha": "0" * 40}
        result = run_step(WORKFLOW, COLLECT, self.work, values, {}, self.env)
        self.assertEqual(result.rc, 0, result.log)
        return result

    def test_tokei_gets_one_exclude_per_listed_directory(self):
        # #145: tokei takes each --exclude as one pattern and does not split on
        # commas, so the whole list as one argument excluded nothing.
        self.run_collect(".git,node_modules,build,external")
        calls = self.tokei_calls()
        self.assertEqual(len(calls), 2)
        for args in calls:
            excluded = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "--exclude"]
            self.assertEqual(excluded, [".git", "node_modules", "build", "external", "package-lock.json"], args)

    def test_exclude_dirs_input_is_not_run_as_shell(self):
        # The input reaches the script through env:, so shell syntax in it is data.
        marker = Path(self._tmp.name) / "ran"
        self.run_collect(f"build,$(touch {marker})")
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
