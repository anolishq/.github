"""setup-vcpkg's binary cache mode, by event (#176).

Run: python3 -m unittest discover tests

Runs the action's binary-source.sh with a GitHub event's values and reads
what it exports. A run writes to the R2 cache only on the default branch
(a push, a workflow_dispatch, or a schedule) and only with the write token;
every other run reads with the read token; a run with no token for its mode,
such as a fork pull request, builds without the remote cache.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".github" / "actions" / "setup-vcpkg" / "binary-source.sh"

TOKENS = {
    "READ_ID": "read-id",
    "READ_SECRET": "read-secret",
    "WRITE_ID": "write-id",
    "WRITE_SECRET": "write-secret",
}


def run(event, ref="refs/heads/main", default_branch="main", **overrides):
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp, "env")
        out_file = Path(tmp, "out")
        env = {
            "PATH": os.environ["PATH"],
            "EVENT": event,
            "REF": ref,
            "DEFAULT_BRANCH": default_branch,
            "ENDPOINT": "https://account.r2.cloudflarestorage.com",
            "BUCKET": "bucket",
            **TOKENS,
            "RUNNER_TEMP": tmp,
            "GITHUB_ENV": str(env_file),
            "GITHUB_OUTPUT": str(out_file),
            **overrides,
        }
        subprocess.run(["bash", str(SCRIPT)], env=env, check=True, capture_output=True)
        exported = dict(line.split("=", 1) for line in env_file.read_text().splitlines())
        mode = out_file.read_text().strip().removeprefix("mode=")
        config = Path(tmp, "vcpkg-aws-config")
        exported["_config"] = config.read_text() if config.exists() else None
        return mode, exported


class EventToModeTest(unittest.TestCase):
    TABLE = [
        # (event, ref, expected mode, token used)
        ("push", "refs/heads/main", "readwrite", "write-id"),
        ("workflow_dispatch", "refs/heads/main", "readwrite", "write-id"),
        ("schedule", "refs/heads/main", "readwrite", "write-id"),
        ("pull_request", "refs/pull/7/merge", "read", "read-id"),
        ("push", "refs/heads/feature", "read", "read-id"),
        ("workflow_dispatch", "refs/heads/feature", "read", "read-id"),
        ("push", "refs/tags/v1.0.0", "read", "read-id"),
        ("merge_group", "refs/heads/gh-readonly-queue/main/pr-7", "read", "read-id"),
    ]

    def test_table(self):
        for event, ref, mode, key_id in self.TABLE:
            with self.subTest(event=event, ref=ref):
                got, env = run(event, ref)
                self.assertEqual(got, mode)
                self.assertEqual(env["AWS_ACCESS_KEY_ID"], key_id)
                self.assertEqual(env["AWS_SECRET_ACCESS_KEY"], key_id.replace("-id", "-secret"))
                self.assertEqual(
                    env["VCPKG_BINARY_SOURCES"],
                    f"clear;default,readwrite;x-aws,s3://bucket/vcpkg/,{mode}",
                )

    def test_a_fork_pull_request_gets_no_remote_cache(self):
        empty = {k: "" for k in TOKENS}
        mode, env = run("pull_request", "refs/pull/7/merge", **empty)
        self.assertEqual(mode, "none")
        self.assertEqual(env["VCPKG_BINARY_SOURCES"], "clear;default,readwrite")
        self.assertNotIn("AWS_ACCESS_KEY_ID", env)

    def test_a_pull_request_never_uses_the_write_token(self):
        mode, env = run("pull_request", "refs/pull/7/merge", READ_ID="", READ_SECRET="")
        self.assertEqual(mode, "none")
        self.assertNotIn("AWS_ACCESS_KEY_ID", env)

    def test_a_writer_without_the_write_token_reads(self):
        mode, env = run("push", WRITE_ID="", WRITE_SECRET="")
        self.assertEqual(mode, "read")
        self.assertEqual(env["AWS_ACCESS_KEY_ID"], "read-id")

    def test_an_unknown_default_branch_does_not_write(self):
        mode, _ = run("push", default_branch="")
        self.assertEqual(mode, "read")

    def test_no_endpoint_or_bucket_means_no_remote_cache(self):
        for missing in ("ENDPOINT", "BUCKET"):
            with self.subTest(missing=missing):
                mode, env = run("push", **{missing: ""})
                self.assertEqual(mode, "none")
                self.assertNotIn("AWS_ACCESS_KEY_ID", env)


class AwsSettingsTest(unittest.TestCase):
    def test_r2_endpoint_region_and_single_put_uploads(self):
        _, env = run("push")
        self.assertEqual(env["AWS_ENDPOINT_URL_S3"], "https://account.r2.cloudflarestorage.com")
        self.assertEqual(env["AWS_DEFAULT_REGION"], "auto")
        self.assertTrue(env["AWS_CONFIG_FILE"].endswith("vcpkg-aws-config"))
        # A multipart upload of grpc failed in the #175 spike; packages go up
        # in one PUT (R2's limit for one is 5 GiB).
        self.assertIn("multipart_threshold = 4GB", env["_config"])


if __name__ == "__main__":
    unittest.main()
