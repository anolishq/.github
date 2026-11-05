"""Tests for the "clang-tidy on changed lines" step of clang-tidy-diff.yml.

Run: python3 -m unittest discover tests

They check which commits the step diffs for each event, and that it fails
rather than passes when it cannot work that out.

The working copy is built the way actions/checkout builds it with
fetch-depth: 0 (as its logs show): `git init`, `remote add`, then a fetch of
`+refs/heads/*:refs/remotes/origin/*` and `+refs/tags/*:refs/tags/*`.
- pull_request also fetches GitHub's merge commit to refs/remotes/pull/1/merge
  and checks it out; main moves on after that merge commit was made, which is
  where `base...HEAD` and `base..HEAD` differ.
- push checks out `-B <branch> refs/remotes/origin/<branch>`, re-fetching the
  pushed commit into that ref when the branch has moved past it.
Nothing is copied from the origin by path, so a commit no ref reaches is not
in the working copy, as on a runner.

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
HEADS = ["+refs/heads/*:refs/remotes/origin/*", "+refs/tags/*:refs/tags/*"]

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
        self.dev, self.origin = dev, origin
        # main: c0 -> c1
        self.c0 = self.commit("src/a.cpp", "int a() { return 1; }\n")
        self.c1 = self.commit("src/a.cpp", "int a() { return 1; }\nint a1() { return 2; }\n")
        self.git(dev, "push", "-q", "origin", "main")
        # a PR branch off c1, and GitHub's merge commit of it into c1
        self.git(dev, "switch", "-q", "-c", "feature")
        self.feature = self.commit("src/b.cpp", "int b() { return 3; }\n")
        self.git(dev, "push", "-q", "origin", "feature")
        self.git(dev, "switch", "-q", "--detach", self.c1)
        self.git(dev, "merge", "-q", "--no-ff", "-m", "Merge feature into main", self.feature)
        self.merge = self.git(dev, "rev-parse", "HEAD")
        self.git(dev, "push", "-q", "origin", f"{self.merge}:refs/pull/1/merge")
        # main moves on (another PR, with C++) after the merge commit was made
        self.git(dev, "switch", "-q", "main")
        self.c2 = self.commit("src/a.cpp",
                              "int a() { return 1; }\nint a1() { return 2; }\nint a2() { return 4; }\n")
        self.git(dev, "push", "-q", "origin", "main")
        # a docs-only commit on its own branch
        self.git(dev, "switch", "-q", "-c", "docs")
        self.docs = self.commit("README.md", "docs\n")
        self.git(dev, "push", "-q", "origin", "docs")
        # a commit that was pushed and then rewritten away, so no ref reaches it
        self.git(dev, "switch", "-q", "-c", "gone", self.c2)
        self.gone = self.commit("src/gone.cpp", "int gone();\n")
        self.git(dev, "push", "-q", "origin", "gone")
        self.git(dev, "push", "-q", "origin", "--delete", "gone")
        self.git(origin, "reflog", "expire", "--expire=now", "--all")
        self.git(origin, "gc", "-q", "--prune=now")
        self.git(dev, "switch", "-q", "main")

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

    def commit(self, path, text):
        (self.dev / path).parent.mkdir(parents=True, exist_ok=True)
        (self.dev / path).write_text(text)
        self.git(self.dev, "add", path)
        self.git(self.dev, "commit", "-q", "-m", f"change {path}")
        return self.git(self.dev, "rev-parse", "HEAD")

    def checkout(self, head, branch=None, pr_merge=None):
        """Build the working copy as actions/checkout does (see the module docstring)."""
        work = self.root / "work"
        shutil.rmtree(work, ignore_errors=True)
        self.git(self.root, "init", "-q", str(work))
        self.git(work, "remote", "add", "origin", str(self.origin))
        fetch = ["fetch", "-q", "--no-tags", "--prune", "--no-recurse-submodules", "origin"]
        if pr_merge:
            self.git(work, *fetch, *HEADS, f"+{pr_merge}:refs/remotes/pull/1/merge")
            self.git(work, "checkout", "-q", "--force", "refs/remotes/pull/1/merge")
        else:
            self.git(work, *fetch, *HEADS)
            if self.git(work, "rev-parse", f"refs/remotes/origin/{branch}") != head:
                self.git(work, *fetch, f"+{head}:refs/remotes/origin/{branch}")
            self.git(work, "checkout", "-q", "--force", "-B", branch, f"refs/remotes/origin/{branch}")
        self.assertEqual(self.git(work, "rev-parse", "HEAD"), head)
        (work / "build" / "ci").mkdir(parents=True)
        (work / "build" / "ci" / "compile_commands.json").write_text('[{"file": "x"}]\n')
        return work

    def lint(self, event, head, branch="main", base_ref="", before="", default_branch="main",
             pr_merge=None, **env):
        work = self.checkout(head, branch, pr_merge)
        values = {"inputs.configure-preset": "ci", "inputs.paths": PATHS,
                  "inputs.blocking": "true", "github.event_name": event,
                  "github.base_ref": base_ref, "github.event.before": before,
                  "github.event.repository.default_branch": default_branch,
                  "github.ref_name": branch}
        return run_step(WORKFLOW, STEP, work, values, {},
                        {**self.env, "GITHUB_WORKSPACE": str(work), **env})

    def linted(self):
        return self.diff_out.read_text() if self.diff_out.exists() else None

    def test_push_lints_the_pushed_commits(self):
        res = self.lint("push", self.c2, before=self.c1)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIsNotNone(self.linted(), "clang-tidy-diff was not run")
        self.assertIn("+int a2() { return 4; }", self.linted())
        self.assertNotIn("+int a1", self.linted())
        self.assertIn("No new findings", res.summary)

    def test_push_of_several_commits_lints_them_all(self):
        res = self.lint("push", self.c2, before=self.c0)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIn("+int a1() { return 2; }", self.linted())
        self.assertIn("+int a2() { return 4; }", self.linted())

    def test_push_finding_fails_when_blocking(self):
        res = self.lint("push", self.c2, before=self.c1,
                        STUB_FINDING="src/a.cpp:3:5: warning: bad [some-check]")
        self.assertNotEqual(res.rc, 0, res.log)
        self.assertIn("1 finding(s)", res.summary)

    def test_push_whose_before_is_no_longer_reachable_fails(self):
        # As after a force-push: `before` is not in the fetched history.
        res = self.lint("push", self.c2, before=self.gone)
        self.assertNotEqual(res.rc, 0, res.log)
        self.assertIsNone(self.linted())
        self.assertIn("were not checked", res.summary)

    def test_push_of_a_new_branch_lints_against_the_default_branch(self):
        res = self.lint("push", self.feature, branch="feature", before=ZEROS)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIsNotNone(self.linted(), "clang-tidy-diff was not run")
        self.assertIn("+int b() { return 3; }", self.linted())
        self.assertNotIn("src/a.cpp", self.linted())

    def test_first_push_of_the_default_branch_says_nothing_was_linted(self):
        res = self.lint("push", self.c2, before=ZEROS)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIsNone(self.linted())
        self.assertIn("first push of main", res.summary)
        self.assertIn("nothing was linted", res.summary)
        self.assertNotIn("No C/C++ changes", res.summary)

    def test_push_without_cpp_changes_says_so(self):
        res = self.lint("push", self.docs, branch="docs", before=self.c2)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIsNone(self.linted())
        self.assertIn(f"No C/C++ changes in {self.c2}...HEAD", res.summary)

    def test_pull_request_lints_only_its_own_changes(self):
        # HEAD is the merge commit; main has moved on since. Only the PR's lines count.
        res = self.lint("pull_request", self.merge, base_ref="main", pr_merge=self.merge)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIsNotNone(self.linted(), "clang-tidy-diff was not run")
        self.assertIn("+int b() { return 3; }", self.linted())
        self.assertNotIn("src/a.cpp", self.linted())

    def test_pull_request_uses_its_base_not_the_default_branch(self):
        # A PR into main in a repo whose default branch is something else.
        res = self.lint("pull_request", self.merge, base_ref="main", default_branch="develop",
                        pr_merge=self.merge)
        self.assertEqual(res.rc, 0, res.log)
        self.assertIn("+int b() { return 3; }", self.linted())

    def test_pull_request_without_base_fails(self):
        res = self.lint("pull_request", self.merge, base_ref="", pr_merge=self.merge)
        self.assertNotEqual(res.rc, 0, res.log)
        self.assertIsNone(self.linted())
        self.assertIn("No base branch", res.summary)

    def test_event_without_a_change_range_says_nothing_was_linted(self):
        for event in ("schedule", "workflow_dispatch"):
            with self.subTest(event=event):
                res = self.lint(event, self.c2)
                self.assertEqual(res.rc, 0, res.log)
                self.assertIsNone(self.linted())
                self.assertIn("nothing was linted", res.summary)
                self.assertNotIn("No C/C++ changes", res.summary)

    def test_unsupported_event_fails(self):
        # An event the step does not know must not pass with nothing linted.
        for event in ("merge_group", "pull_request_target", "workflow_call"):
            with self.subTest(event=event):
                res = self.lint(event, self.c2, base_ref="main", before=self.c1)
                self.assertNotEqual(res.rc, 0, res.log)
                self.assertIsNone(self.linted())
                self.assertIn(f"does not support {event} runs", res.summary)

    def test_push_without_before_or_default_branch_fails(self):
        res = self.lint("push", self.feature, branch="feature", before=ZEROS, default_branch="")
        self.assertNotEqual(res.rc, 0, res.log)
        self.assertIsNone(self.linted())
        self.assertIn("No previous commit or default branch", res.summary)


if __name__ == "__main__":
    unittest.main()
