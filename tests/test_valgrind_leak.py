"""Tests for the run, summary and enforce steps of valgrind-leak.yml.

Run: python3 -m unittest discover tests

Most cases run real valgrind on small C programs, so they need valgrind and a
C compiler. They are skipped without them, except under GitHub Actions, where
CI installs valgrind and a missing tool must fail the run instead. The
empty-log and no-summary cases use a stand-in valgrind that writes a given
log, since real valgrind does not produce those on demand.
"""
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from workflow_steps import find_step, run_step

WORKFLOW = "valgrind-leak.yml"
RUN, SUMMARY, ENFORCE = "Run valgrind (non-blocking)", "Build job summary", "Enforce (optional)"
CC = shutil.which("cc") or shutil.which("gcc")
HAVE_TOOLS = bool(shutil.which("valgrind") and CC)
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"

PROGRAMS = {
    "clean": "#include <stdlib.h>\nint main(void) { free(malloc(16)); return 0; }\n",
    "leak": "#include <stdio.h>\n#include <stdlib.h>\n"
            "int main(void) { void *p = malloc(64); printf(\"%p\\n\", p); p = 0; return 0; }\n",
    # Runs until a signal stops it, and allocates nothing. The host's `sleep` is
    # not a neutral stand-in: uutils' sleep, the default on Ubuntu 26.04, leaves
    # 8 bytes definitely lost when SIGINT stops it under valgrind.
    "wait": "#include <unistd.h>\nint main(void) { for (;;) pause(); }\n",
}

STUB_VALGRIND = r'''#!/usr/bin/env bash
for a in "$@"; do
  case "$a" in --log-file=*) printf '%s' "$STUB_LOG" > "${a#--log-file=}" ;; esac
done
exit "${STUB_RC:-0}"
'''

HEADER_ONLY_LOG = ("==1== Memcheck, a memory error detector\n"
                   "==1== Command: build/app\n==1==\n")


class ValgrindLeakTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.env = {}

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, name):
        src = self.work / f"{name}.c"
        src.write_text(PROGRAMS[name])
        subprocess.run([CC, "-g", "-O0", "-o", str(self.work / name), str(src)], check=True)
        return f"./{name}"

    def use_stub_valgrind(self, log, rc):
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "valgrind"
        stub.write_text(STUB_VALGRIND)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        self.env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                    "STUB_LOG": log, "STUB_RC": str(rc)}

    def check(self, command, duration="", signal="INT"):
        """Run the run, summary and Enforce steps as the workflow wires them.

        The helper does not evaluate `if:`, so the Enforce step always runs here;
        test_enforce_step_runs_only_with_enforce checks its condition.
        """
        values = {"inputs.run": command, "inputs.suppressions": "valgrind.supp",
                  "inputs.duration": duration, "inputs.signal": signal}
        run = run_step(WORKFLOW, RUN, self.work, values, {}, self.env)
        self.assertEqual(run.rc, 0, run.log)
        outputs = {"vg": run.outputs}
        summary = run_step(WORKFLOW, SUMMARY, self.work, values, outputs, self.env)
        self.assertEqual(summary.rc, 0, summary.log)
        enforce = run_step(WORKFLOW, ENFORCE, self.work, values, outputs, self.env)
        return run, summary.summary, enforce

    def assert_not_checked(self, summary, enforce):
        self.assertNotEqual(enforce.rc, 0, enforce.log)
        self.assertIn("no leak summary", enforce.log)
        self.assertNotIn("valgrind clean", enforce.log)
        self.assertNotIn("No 'definitely lost' leaks", summary)
        self.assertIn("no leak summary", summary)

    def test_summary_when_the_run_step_did_not_run(self):
        # A failed build skips the run step, so it wrote no outputs and no log.
        summary = run_step(WORKFLOW, SUMMARY, self.work, {}, {"vg": {}}, self.env)
        self.assertEqual(summary.rc, 0, summary.log)
        self.assertIn("Valgrind did not run to the end of its step", summary.summary)
        self.assertNotIn("no leak summary", summary.summary)
        self.assertNotIn("No 'definitely lost' leaks", summary.summary)

    def test_enforce_step_runs_only_with_enforce(self):
        self.assertEqual(find_step(WORKFLOW, ENFORCE).get("if"), "${{ inputs.enforce }}")

    @unittest.skipUnless(HAVE_TOOLS or IN_CI, "needs valgrind and a C compiler")
    def test_missing_binary_fails_enforce(self):
        run, summary, enforce = self.check("./build/missing-bin")
        self.assert_not_checked(summary, enforce)
        self.assertEqual(run.outputs["rc"], "127")

    @unittest.skipUnless(HAVE_TOOLS or IN_CI, "needs valgrind and a C compiler")
    def test_old_log_does_not_count_as_this_run(self):
        # A valgrind.log left in the directory (committed, or from the build) must not
        # stand in for a run where valgrind could not start the target.
        (self.work / "valgrind.log").write_text(
            "==1== LEAK SUMMARY:\n==1==    definitely lost: 0 bytes in 0 blocks\n")
        run, summary, enforce = self.check("./build/missing-bin")
        self.assert_not_checked(summary, enforce)
        self.assertEqual(run.outputs["rc"], "127")

    @unittest.skipUnless(HAVE_TOOLS or IN_CI, "needs valgrind and a C compiler")
    def test_target_killed_by_duration_signal_kill_fails_enforce(self):
        # SIGKILL stops valgrind itself, so it writes no leak summary.
        run, summary, enforce = self.check(self.build("wait"), duration="2s", signal="KILL")
        self.assert_not_checked(summary, enforce)
        # GNU timeout exits 137 (128+9) after sending KILL. uutils' timeout 0.10,
        # the default on Ubuntu 26.04, exits 124; uutils changed it to 137 in
        # a185142 ("timeout: exit with 128+9 when the timeout signal is KILL").
        # The workflow only reports this code, so either means the run was stopped.
        self.assertIn(run.outputs["rc"], ("124", "137"))

    @unittest.skipUnless(HAVE_TOOLS or IN_CI, "needs valgrind and a C compiler")
    def test_non_executable_target_fails_enforce(self):
        (self.work / "app").write_text("not a program\n")
        run, summary, enforce = self.check("./app")
        self.assert_not_checked(summary, enforce)
        self.assertEqual(run.outputs["rc"], "126")

    def test_empty_log_fails_enforce(self):
        self.use_stub_valgrind("", 0)
        run, summary, enforce = self.check("build/app")
        self.assert_not_checked(summary, enforce)

    def test_log_without_leak_summary_fails_enforce(self):
        self.use_stub_valgrind(HEADER_ONLY_LOG, 137)
        run, summary, enforce = self.check("build/app")
        self.assert_not_checked(summary, enforce)

    @unittest.skipUnless(HAVE_TOOLS or IN_CI, "needs valgrind and a C compiler")
    def test_clean_program_passes_enforce(self):
        run, summary, enforce = self.check(self.build("clean"))
        self.assertEqual(run.outputs["definitely_lost"], "0")
        self.assertEqual(enforce.rc, 0, enforce.log)
        self.assertIn("No 'definitely lost' leaks", summary)

    @unittest.skipUnless(HAVE_TOOLS or IN_CI, "needs valgrind and a C compiler")
    def test_leaking_program_fails_enforce(self):
        run, summary, enforce = self.check(self.build("leak"))
        self.assertEqual(run.outputs["definitely_lost"], "64")
        self.assertNotEqual(enforce.rc, 0, enforce.log)
        self.assertIn("64 bytes definitely lost", enforce.log)
        self.assertIn("64 bytes definitely lost", summary)

    @unittest.skipUnless(HAVE_TOOLS or IN_CI, "needs valgrind and a C compiler")
    def test_target_stopped_by_duration_signal_still_counts_as_run(self):
        # `duration` stops a long-running target with SIGINT on purpose.
        _, summary, enforce = self.check(self.build("wait"), duration="2s")
        self.assertEqual(enforce.rc, 0, enforce.log)
        self.assertIn("No 'definitely lost' leaks", summary)


if __name__ == "__main__":
    unittest.main()
