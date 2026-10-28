#!/usr/bin/env python3
"""
validate_doc_snippets.py: Validates YAML and JSON code blocks in published docs against JSON Schemas.

Opt-in: a repo lists its schemas in doc-schemas.json at its root; without that
file there is nothing to do. Each entry is a local `path` or a `url`, with an
optional `pointer` to the schema inside the file (e.g. "/schema" for a
provider's --config-schema envelope):

    {"schemas": {"runtime-config": {"path": "schemas/runtime/runtime-config.schema.json"}}}

Published docs are README.md and docs/**/*.md, minus the names listed in
docs/.indexignore (same rules as the docs site). Every ```yaml, ```yml or
```json block in them needs an HTML comment as the nearest non-blank line
above it:

    <!-- validate: runtime-config -->               a complete document
    <!-- validate: runtime-config fragment -->      top-level keys only: the root `required` is dropped
    <!-- validate: runtime-config pointer=/properties/providers -->   validate against a subschema
    <!-- validate: none -->                         not a config example

Exit codes: 0 all valid, 1 a block failed or has no annotation, 2 bad input
(unknown schema name, unreadable schema, malformed annotation).
"""
import copy
import json
import re
import sys
import urllib.request
from pathlib import Path

import jsonschema
import yaml

ROOT = Path.cwd()
REGISTRY = ROOT / "doc-schemas.json"
DOCS = ROOT / "docs"
LANGS = {"yaml": "yaml", "yml": "yaml", "json": "json"}
FENCE_OPEN = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})[ \t]*(?P<lang>[A-Za-z0-9_+-]*)")
ANNOTATION = re.compile(r"^\s*<!--\s*validate:\s*(?P<spec>.*?)\s*-->\s*$")


def fail_input(msg):
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(2)


def read_indexignore():
    try:
        lines = (DOCS / ".indexignore").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    rules = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rules.append((line.removeprefix("**/").rstrip("/"), line.endswith("/"), line.startswith("**/")))
    return rules


def ignored(rules, rel, is_dir):
    base = rel.rsplit("/", 1)[-1]
    return any((not dir_only or is_dir) and (base == pat if anywhere else rel == pat)
               for pat, dir_only, anywhere in rules)


def published_files():
    files = [ROOT / "README.md"] if (ROOT / "README.md").is_file() else []
    if not DOCS.is_dir():
        return files
    rules = read_indexignore()

    def walk(d):
        for entry in sorted(d.iterdir()):
            rel = entry.relative_to(DOCS).as_posix()
            if entry.is_dir():
                if not ignored(rules, rel, True):
                    walk(entry)
            elif entry.suffix == ".md" and not ignored(rules, rel, False):
                files.append(entry)

    walk(DOCS)
    return files


def code_blocks(text):
    """Yield (line_no, lang, body, annotation_or_None) for each fenced block."""
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = FENCE_OPEN.match(lines[i])
        if not m:
            i += 1
            continue
        fence, lang = m.group("fence"), m.group("lang").lower()
        start = i
        body = []
        i += 1
        while i < len(lines) and not lines[i].strip().startswith(fence):
            body.append(lines[i])  # a fence's uniform indent parses the same in YAML and JSON
            i += 1
        i += 1
        annotation = None
        j = start - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j >= 0:
            a = ANNOTATION.match(lines[j])
            if a:
                annotation = a.group("spec")
        yield start + 1, lang, "\n".join(body) + "\n", annotation


_schemas = {}


def load_schema(name, entries):
    if name in _schemas:
        return _schemas[name]
    entry = entries.get(name)
    if entry is None:
        fail_input(f"unknown schema '{name}'; doc-schemas.json lists: {', '.join(sorted(entries)) or 'none'}")
    try:
        if "path" in entry:
            data = json.loads((ROOT / entry["path"]).read_text(encoding="utf-8"))
        elif "url" in entry:
            with urllib.request.urlopen(entry["url"], timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        else:
            fail_input(f"schema '{name}' needs a path or a url")
    except (OSError, ValueError) as exc:
        fail_input(f"cannot read schema '{name}': {exc}")
    pointer = entry.get("pointer")
    if pointer:
        data = resolve_pointer(data, pointer, f"schema '{name}'")
    _schemas[name] = data
    return data


def resolve_pointer(doc, pointer, what):
    node = doc
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            fail_input(f"{what} has no {pointer}")
        node = node[part]
    return node


def build_schema(spec, entries):
    """Turn an annotation spec into (schema, label), or None for `none`."""
    words = spec.split()
    if not words:
        fail_input("empty validate annotation")
    if words == ["none"]:
        return None
    root = load_schema(words[0], entries)
    schema = root
    for word in words[1:]:
        if word == "fragment":
            schema = copy.deepcopy(schema)
            schema.pop("required", None)
        elif word.startswith("pointer="):
            pointer = word.split("=", 1)[1]
            sub = copy.deepcopy(resolve_pointer(root, pointer, f"schema '{words[0]}'"))
            # Keep the root's definitions so the subschema's local $refs resolve.
            for key in ("$schema", "$defs", "definitions"):
                if key in root and key not in sub:
                    sub[key] = root[key]
            schema = sub
        else:
            fail_input(f"unknown validate option '{word}' in '{spec}'")
    return schema


def main():
    if not REGISTRY.is_file():
        print("No doc-schemas.json; nothing to validate.")
        return 0
    try:
        entries = json.loads(REGISTRY.read_text(encoding="utf-8")).get("schemas", {})
    except ValueError as exc:
        fail_input(f"doc-schemas.json: {exc}")

    problems = []
    checked = 0
    for path in published_files():
        rel = path.relative_to(ROOT).as_posix()
        for line, lang, body, spec in code_blocks(path.read_text(encoding="utf-8")):
            if lang not in LANGS:
                continue
            where = f"{rel}:{line}"
            if spec is None:
                problems.append(f"{where}: ```{lang} block has no validate annotation")
                continue
            schema = build_schema(spec, entries)
            if schema is None:
                continue
            try:
                instance = yaml.safe_load(body) if LANGS[lang] == "yaml" else json.loads(body)
            except (yaml.YAMLError, ValueError) as exc:
                problems.append(f"{where}: does not parse as {LANGS[lang]}: {exc}")
                continue
            validator = jsonschema.validators.validator_for(schema)(schema)
            errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
            for err in errors:
                at = "/".join(str(p) for p in err.path) or "(root)"
                problems.append(f"{where}: [{spec}] at {at}: {err.message}")
            checked += 1

    for p in problems:
        print(p, file=sys.stderr)
    print(f"Validated {checked} block(s); {len(problems)} problem(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
