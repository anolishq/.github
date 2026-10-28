"""Tests for scripts/validate_doc_snippets.py. Run: python3 -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "validate_doc_snippets.py"

SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["providers"],
    "additionalProperties": False,
    "properties": {
        "providers": {"type": "array", "items": {"$ref": "#/$defs/provider"}},
        "http": {"type": "object", "properties": {"port": {"type": "integer"}}},
    },
    "$defs": {
        "provider": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}},
    },
}

FENCE = "```"


def run(files, registry=None):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "schemas").mkdir()
        (root / "schemas" / "cfg.json").write_text(json.dumps(SCHEMA), encoding="utf-8")
        (root / "schemas" / "env.json").write_text(json.dumps({"provider": "x", "schema": SCHEMA}), encoding="utf-8")
        reg = registry if registry is not None else {
            "schemas": {"cfg": {"path": "schemas/cfg.json"}, "env": {"path": "schemas/env.json", "pointer": "/schema"}}}
        (root / "doc-schemas.json").write_text(json.dumps(reg), encoding="utf-8")
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        p = subprocess.run([sys.executable, str(SCRIPT)], cwd=root, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


def doc(annotation, lang, body):
    ann = f"<!-- validate: {annotation} -->\n\n" if annotation else ""
    return f"# Page\n\n{ann}{FENCE}{lang}\n{body}{FENCE}\n"


class SnippetTest(unittest.TestCase):
    def test_valid_document_passes(self):
        rc, out = run({"docs/a.md": doc("cfg", "yaml", "providers:\n  - id: sim0\n")})
        self.assertEqual(rc, 0, out)

    def test_invalid_document_fails_with_location(self):
        rc, out = run({"docs/a.md": doc("cfg", "yaml", "providers:\n  - command: x\n")})
        self.assertEqual(rc, 1, out)
        self.assertIn("docs/a.md:5", out)
        self.assertIn("'id' is a required property", out)

    def test_unannotated_fence_fails(self):
        rc, out = run({"docs/a.md": doc(None, "yaml", "providers: []\n")})
        self.assertEqual(rc, 1, out)
        self.assertIn("no validate annotation", out)

    def test_none_skips(self):
        rc, out = run({"docs/a.md": doc("none", "yaml", "not: [valid\n")})
        self.assertEqual(rc, 0, out)

    def test_non_config_languages_are_ignored(self):
        rc, out = run({"docs/a.md": doc(None, "bash", "echo hi\n")})
        self.assertEqual(rc, 0, out)

    def test_fragment_drops_root_required_only(self):
        rc, out = run({"docs/a.md": doc("cfg fragment", "yaml", "http:\n  port: 8080\n")})
        self.assertEqual(rc, 0, out)
        rc, out = run({"docs/a.md": doc("cfg fragment", "yaml", "http:\n  port: eighty\n")})
        self.assertEqual(rc, 1, out)

    def test_fragment_still_refuses_unknown_top_level_keys(self):
        rc, out = run({"docs/a.md": doc("cfg fragment", "yaml", "htttp:\n  port: 8080\n")})
        self.assertEqual(rc, 1, out)

    def test_undeclared_top_level_key_fails_even_when_the_schema_allows_it(self):
        lax = dict(SCHEMA, additionalProperties=True)
        reg = {"schemas": {"lax": {"path": "schemas/lax.json"}}}
        files = {"schemas/lax.json": json.dumps(lax),
                 "docs/a.md": doc("lax fragment", "yaml", "htttp:\n  port: 8080\n")}
        rc, out = run(files, reg)
        self.assertEqual(rc, 1, out)
        self.assertIn("htttp", out)
        files["docs/a.md"] = doc("lax fragment", "yaml", "http:\n  port: 8080\n")
        rc, out = run(files, reg)
        self.assertEqual(rc, 0, out)

    def test_pointer_validates_a_subschema_with_refs(self):
        rc, out = run({"docs/a.md": doc("cfg pointer=/properties/providers", "yaml", "- id: sim0\n")})
        self.assertEqual(rc, 0, out)
        rc, out = run({"docs/a.md": doc("cfg pointer=/properties/providers", "yaml", "- command: x\n")})
        self.assertEqual(rc, 1, out)

    def test_registry_pointer_unwraps_an_envelope(self):
        rc, out = run({"docs/a.md": doc("env", "json", '{"providers": [{"id": "a"}]}\n')})
        self.assertEqual(rc, 0, out)
        rc, out = run({"docs/a.md": doc("env", "json", '{"providers": [{"command": "a"}]}\n')})
        self.assertEqual(rc, 1, out)

    def test_unparseable_snippet_fails(self):
        rc, out = run({"docs/a.md": doc("cfg", "yaml", "providers: [\n")})
        self.assertEqual(rc, 1, out)

    def test_unknown_schema_name_is_an_input_error(self):
        rc, out = run({"docs/a.md": doc("nope", "yaml", "providers: []\n")})
        self.assertEqual(rc, 2, out)

    def test_readme_is_checked(self):
        rc, out = run({"README.md": doc(None, "json", "{}\n")})
        self.assertEqual(rc, 1, out)

    def test_indexignored_pages_are_skipped(self):
        rc, out = run({"docs/.indexignore": "internal/\nTODO.md\n",
                       "docs/internal/x.md": doc(None, "yaml", "a: 1\n"),
                       "docs/TODO.md": doc(None, "yaml", "a: 1\n"),
                       "docs/ok.md": doc("cfg", "yaml", "providers: []\n")})
        self.assertEqual(rc, 0, out)

    def test_indented_fence_in_a_list_item(self):
        text = ("1. Step\n\n   <!-- validate: cfg -->\n\n   ```yaml\n   providers:\n     - id: a\n   ```\n")
        rc, out = run({"docs/a.md": text})
        self.assertEqual(rc, 0, out)

    def test_no_registry_means_nothing_to_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "README.md").write_text(doc(None, "yaml", "a: 1\n"), encoding="utf-8")
            p = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
