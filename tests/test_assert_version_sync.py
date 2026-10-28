"""Tests for scripts/assert_version_sync.py. Run: python3 -m unittest discover tests"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "assert_version_sync.py"


def run(files, locations):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        (root / "version-locations.txt").write_text(locations, encoding="utf-8")
        p = subprocess.run([sys.executable, str(SCRIPT)], cwd=root, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


class VersionSyncTest(unittest.TestCase):
    def test_matching_versions_pass(self):
        rc, out = run({"a.txt": "version 1.2.3\n", "b.json": '"version": "1.2.3"\n'},
                      'a.txt: version ([0-9.]+)\nb.json: "version": "([0-9.]+)"\n')
        self.assertEqual(rc, 0, out)
        self.assertIn("1.2.3", out)

    def test_mismatch_across_files_fails(self):
        rc, out = run({"a.txt": "version 1.2.3\n", "b.txt": "version 1.2.4\n"},
                      "a.txt: version ([0-9.]+)\nb.txt: version ([0-9.]+)\n")
        self.assertEqual(rc, 1, out)

    def test_two_regexes_on_one_file_are_both_checked(self):
        rc, out = run({"README.md": "A=1.0.0\nB=2.0.0\n", "c.txt": "v 2.0.0\n"},
                      "README.md: ^A=([0-9.]+)\nREADME.md: ^B=([0-9.]+)\nc.txt: v ([0-9.]+)\n")
        self.assertEqual(rc, 1, out)
        self.assertIn("1.0.0", out)

    def test_every_match_of_a_regex_is_checked(self):
        rc, out = run({"README.md": "download/v2.0.0/x and download/v9.9.9/y\n", "c.txt": "v 2.0.0\n"},
                      "README.md: download/v([0-9.]+)/\nc.txt: v ([0-9.]+)\n")
        self.assertEqual(rc, 1, out)
        self.assertIn("9.9.9", out)

    def test_regex_with_no_match_fails(self):
        rc, out = run({"a.txt": "version 1.2.3\n"}, "a.txt: version ([0-9.]+)\na.txt: nothing ([0-9.]+)\n")
        self.assertEqual(rc, 2, out)

    def test_regex_without_a_capture_group_is_bad_input(self):
        rc, out = run({"a.txt": "version 1.2.3\n"}, "a.txt: version [0-9.]+\n")
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)

    def test_invalid_regex_is_bad_input(self):
        rc, out = run({"a.txt": "version 1.2.3\n"}, "a.txt: version ([0-9.]+\n")
        self.assertEqual(rc, 2, out)
        self.assertNotIn("Traceback", out)

    def test_missing_file_fails(self):
        rc, out = run({"a.txt": "version 1.2.3\n"}, "a.txt: version ([0-9.]+)\ngone.txt: v ([0-9.]+)\n")
        self.assertEqual(rc, 2, out)

    def test_groups_are_checked_separately(self):
        files = {"CMakeLists.txt": "project(x VERSION 0.4.0)\nGIT_TAG v1.2.0\n",
                 "vcpkg.json": '"version": "0.4.0"\n', "docs/deps.md": "protocol v1.2.0\n"}
        rc, out = run(files, "CMakeLists.txt: VERSION ([0-9.]+)\nvcpkg.json: \"version\": \"([0-9.]+)\"\n"
                             "protocol|CMakeLists.txt: GIT_TAG v([0-9.]+)\nprotocol|docs/deps.md: protocol v([0-9.]+)\n")
        self.assertEqual(rc, 0, out)

    def test_mismatch_inside_a_group_fails(self):
        files = {"CMakeLists.txt": "GIT_TAG v1.3.0\n", "docs/deps.md": "protocol v1.2.0\n"}
        rc, out = run(files, "protocol|CMakeLists.txt: GIT_TAG v([0-9.]+)\nprotocol|docs/deps.md: protocol v([0-9.]+)\n")
        self.assertEqual(rc, 1, out)
        self.assertIn("protocol", out)

    def test_regex_containing_a_pipe_is_not_a_group(self):
        rc, out = run({"a.txt": "version 1.2.3\n", "b.txt": "ver 1.2.3\n"},
                      "a.txt: (?:version|ver) ([0-9.]+)\nb.txt: (?:version|ver) ([0-9.]+)\n")
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
