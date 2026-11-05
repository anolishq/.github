"""Tests for the scan and summary steps of dependency-scan.yml.

Run: python3 -m unittest discover tests

The scan step runs against a stand-in `cve-bin-tool` on PATH. It writes
reports the way the pinned cve-bin-tool (ossf/cve-bin-tool@182267f) does:
  - `--no-0-cve-report` with zero CVEs writes no file at all
    (OutputEngine.output_file, output_engine/__init__.py:928-930);
  - otherwise `<output-file>.json` holds the list of findings, `[]` on a
    clean scan (json_output.output_json -> util.format_output);
  - it exits 1 when it finds CVEs and 0 when it finds none (cli.py:1330-1340),
    and something else when it fails.
"""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from workflow_steps import run_step

WORKFLOW = "dependency-scan.yml"
TRIPLET = "x64-linux-static"

STUB = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
name = args[args.index("--output-file") + 1]
formats = args[args.index("--format") + 1].split(",")
print(f"There are {os.environ.get('STUB_DB_COUNT', '312000')} CVE entries in the database")
if os.environ.get("STUB_CRASH"):
    sys.exit(int(os.environ["STUB_CRASH"]))
cves = json.loads(os.environ.get("STUB_CVES", "[]"))
if not (not cves and "--no-0-cve-report" in args):
    for fmt in formats:
        with open(f"{name}.{fmt}", "w") as f:
            f.write(json.dumps(cves) if fmt == "json" else "<html></html>")
sys.exit(1 if cves else 0)
'''

FINDING = {"vendor": "openssl", "product": "openssl", "version": "3.0.0",
           "cve_number": "CVE-2099-0001", "severity": "HIGH", "score": "7.5"}


class DependencyScanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.work = self.root / "work"
        (self.work / "vcpkg_installed" / TRIPLET).mkdir(parents=True)
        (self.work / "deps.csv").write_text("vendor,product,version\nopenssl,openssl,3.0.0\n")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "cve-bin-tool"
        stub.write_text(STUB)
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        self.env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    def tearDown(self):
        self._tmp.cleanup()

    def scan_and_summarise(self, dep_count="1", **stub_env):
        """Run the scan step, then the summary step with the scan's outputs."""
        values = {"inputs.triplet": TRIPLET}
        outputs = {"deps": {"count": dep_count}}
        scan = run_step(WORKFLOW, "Run CVE scan (non-blocking)", self.work,
                        values, outputs, {**self.env, **stub_env})
        self.assertEqual(scan.rc, 0, scan.log)
        outputs["scan"] = scan.outputs
        summary = run_step(WORKFLOW, "Build job summary", self.work, values, outputs, self.env)
        self.assertEqual(summary.rc, 0, summary.log)
        return scan, summary.summary

    def sections(self, summary):
        """The summary text under each of the two scan headings."""
        deps = summary.split("### Direct dependencies", 1)[1].split("### Binary scan", 1)
        return deps[0], deps[1]

    def test_clean_scan_reports_no_known_cves(self):
        _, summary = self.scan_and_summarise()
        deps, binary = self.sections(summary)
        for section in (deps, binary):
            self.assertIn("No known CVEs detected", section, summary)
            self.assertNotIn("No report produced", section, summary)

    def test_clean_scan_keeps_both_reports(self):
        self.scan_and_summarise()
        for name in ("cve-deps.json", "cve-binary.json"):
            path = self.work / name
            self.assertTrue(path.exists(), f"{name} not written")
            self.assertEqual(json.loads(path.read_text()), [])

    def test_findings_are_listed(self):
        _, summary = self.scan_and_summarise(STUB_CVES=json.dumps([FINDING]))
        deps, binary = self.sections(summary)
        for section in (deps, binary):
            self.assertIn("1 finding(s)", section, summary)
            self.assertIn("CVE-2099-0001", section, summary)

    def test_failed_scan_is_not_clean_and_names_the_exit_status(self):
        scan, summary = self.scan_and_summarise(STUB_CRASH="2")
        self.assertEqual(scan.outputs["deps_rc"], "2")
        deps, binary = self.sections(summary)
        for section in (deps, binary):
            self.assertNotIn("No known CVEs", section, summary)
            self.assertIn("cve-bin-tool exited 2", section, summary)

    def test_skipped_version_lookup_says_it_was_skipped(self):
        _, summary = self.scan_and_summarise(dep_count="0")
        deps, binary = self.sections(summary)
        self.assertIn("Skipped", deps, summary)
        self.assertNotIn("No known CVEs", deps, summary)
        self.assertIn("No known CVEs detected", binary, summary)

    def test_scan_that_never_ran_is_not_clean(self):
        values = {"inputs.triplet": TRIPLET}
        outputs = {"deps": {}, "scan": {}}
        summary = run_step(WORKFLOW, "Build job summary", self.work, values, outputs, self.env)
        self.assertEqual(summary.rc, 0, summary.log)
        deps, binary = self.sections(summary.summary)
        for section in (deps, binary):
            self.assertNotIn("No known CVEs", section, summary.summary)
            self.assertIn("did not run", section, summary.summary)

    def test_empty_result_with_unloaded_nvd_is_not_clean(self):
        _, summary = self.scan_and_summarise(STUB_DB_COUNT="5")
        self.assertIn("CVE coverage is INCOMPLETE", summary)
        self.assertNotIn("No known CVEs detected", summary)


if __name__ == "__main__":
    unittest.main()
