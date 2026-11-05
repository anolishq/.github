"""Tests for the "clang-tidy on changed lines" step of clang-tidy-diff.yml.

Run: python3 -m unittest discover tests

They check which commits the step diffs for each event, and that it fails
rather than passes when it cannot work that out. The step runs in a clone of
a throwaway origin, the way actions/checkout leaves it with fetch-depth: 0.
`clang-tidy-diff` is a stand-in that records the diff it was given and can
print a finding; it lints nothing, so these tests do not cover clang-tidy
itself, which the workflow pins and CI's test-setup-clang-tools job checks.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow_steps import run_step

WORKFLOW = "clang-tidy-diff.yml"
STEP = "clang-tidy on changed lines"
ZEROS = "0" * 40
PATHS = "*.c *.cc *.cpp *.cxx *.h *.hh *.hpp *.hxx"

STUB_DIFF = r'''#!/usr/bin/env python3
import os, sys
open(os.environ["STUB_DIFF_OUT"], "w").write(sys.stdin.read())
if os.environ.get("STUB_FINDING"):
    print(os.environ["STUB_FINDING"])
'''

GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


class ClangTidyDiffTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.env = {**GIT_ENV}
        origin, dev = self.root / "origin.git", self.root / "dev"
        self.git(self.root, "init", "-q", "--bare", "-b", "main", str(origin))
        self.git(self.root, "init", "-q", "-b", "main", str(dev))
        self.git(dev, "remote", "add", "origin", str(origin))
        self.base = self.commit(dev, "src/a.cpp", "int a() { return 1; }\n")
        self.main = self.commit(dev, "src/a.cpp", "int a() { return 1; }\nint a2() { return 2; }\n")
        self.git(dev, "push", "-q", "origin", "main")
        self.git(dev, "switch", "-q", "-c", "feature")
        self.feature = self.commit(dev, "src/b.cpp", "int b() { return 3; }\n")
        self.git(dev, "push", "-q", "origin", "feature")
        self.git(dev, "switch", "-q", "main")
        self.docs = self.commit(dev, "README.md", "docs\n")
        self.git(dev, "push", "-q", "origin", "main:docs")
        self.dev, self.origin = dev, origin

        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        for name, text in (("clang-tidy-diff", STUB_DIFF), ("clang-tidy", "#!/bin/sh\nexit 0\n")):
            (bin_dir / name).write_text(text)
            (bin_dir / name).chmod(0o755)
        self.diff_out = self.root / "linted.diff"
        self.env.update({"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                         "STUB_DIFF_OUT": str(self.diff_out)})

    def tearDown(self):
        self._tmp.cleanup()

    def git(self, cwd, *args):
        p = subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV},
                           capture_output=True, text=True, check=True)
        return p.stdout.strip()

    def commit(self, repo, path, text):
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
        self.git(repo, "add", path)
        self.git(repo, "commit", "-q", "-m", f"change {path}")
        return self.git(repo, "rev-parse", "HEAD")

    def lint(self, event, head, base_ref="", before="", default_branch="main", **env):
        """Check out `head` as actions/checkout does, then run the step."""
        work = self.root / "work"
        shutil.rmtree(work, ignore_errors=True)
        self.git(self.root, "clone", "-q", str(self.origin), str(work))
        self.git(work, "checkout", "-q", "--detach", head)
        (work / "build" / "ci").mkdir(parents=True)
        (work / "build" / "ci" / "compile_commands.json").write_text('[{"file": "x"}]\n')
        values = {"inputs.configure-preset": "ci", "inputs.paths": PATHS,
                  "inputs.blocking": "true", "github.event_name": event,
                  "github.base_ref": base_ref, "github.event.before": before,
                  "github.event.repository.default_branch": default_branch}
        return run_step(WORKFLOW, STEP, work, values, {},
                        {**self.env, "GITHUB_WORKSPACE": str(work), **env})

    def linted(self):
        return self.diff_out.read_text() if self.diff_out.exists() else None

    def test_push_lints_the_pushed_commits(self):
        res = self.lint("push", self.main, before=self.base)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIsNotNone(self.linted(), "clang-tidy-diff was not run")
        self.assertIn("+int a2() { return 2; }", self.linted())
        self.assertIn("No new findings", res.summary)

    def test_push_finding_fails_when_blocking(self):
        res = self.lint("push", self.main, before=self.base,
                        STUB_FINDING="src/a.cpp:2:5: warning: bad [some-check]")
        self.assertNotEqual(res.rc, 0, res.log)
        self.assertIn("1 finding(s)", res.summary)

    def test_push_with_unknown_before_fails(self):
        res = self.lint("push", self.main, before="1" * 40)
        self.assertNotEqual(res.rc, 0, res.log)
        self.assertIsNone(self.linted())
        self.assertIn("were not checked", res.summary)

    def test_push_of_a_new_branch_lints_against_the_default_branch(self):
        res = self.lint("push", self.feature, before=ZEROS)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIsNotNone(self.linted(), "clang-tidy-diff was not run")
        self.assertIn("+int b() { return 3; }", self.linted())
        self.assertNotIn("a2", self.linted())

    def test_push_without_cpp_changes_says_so(self):
        res = self.lint("push", self.docs, before=self.main)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIsNone(self.linted())
        self.assertIn(f"No C/C++ changes in {self.main}...HEAD", res.summary)

    def test_pull_request_lints_against_its_base(self):
        res = self.lint("pull_request", self.feature, base_ref="main")
        self.assertEqual(res.rc, 0, res.log)
        self.assertIsNotNone(self.linted(), "clang-tidy-diff was not run")
        self.assertIn("+int b() { return 3; }", self.linted())
        self.assertNotIn("a2", self.linted())

    def test_pull_request_without_base_fails(self):
        res = self.lint("pull_request", self.feature, base_ref="")
        self.assertNotEqual(res.rc, 0, res.log)
        self.assertIsNone(self.linted())
        self.assertIn("No base branch", res.summary)

    def test_event_without_a_change_range_says_nothing_was_linted(self):
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                res = self.lint(event, self.main)
                self.assertEqual(res.rc, 0, res.log)
                self.assertIsNone(self.linted())
                self.assertIn("nothing was linted", res.summary)
                self.assertNotIn("No C/C++ changes", res.summary)

    def test_unsupported_event_fails(self):
        # An event the step does not know must not pass with nothing linted.
        for event in ("merge_group", "pull_request_target", "workflow_call"):
            with self.subTest(event=event):
                res = self.lint(event, self.feature, base_ref="main", before=self.base)
                self.assertNotEqual(res.rc, 0, res.log)
                self.assertIsNone(self.linted())
                self.assertIn(f"does not support {event} runs", res.summary)

    def test_push_without_before_or_default_branch_fails(self):
        res = self.lint("push", self.feature, before=ZEROS, default_branch="")
        self.assertNotEqual(res.rc, 0, res.log)
        self.assertIsNone(self.linted())
        self.assertIn("No previous commit or default branch", res.summary)


if __name__ == "__main__":
    unittest.main()
