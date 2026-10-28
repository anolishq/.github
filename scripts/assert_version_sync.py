#!/usr/bin/env python3
"""
assert_version_sync.py: Checks that the version strings listed in version-locations.txt agree.

Each line is `path: regex`, where the regex's first group captures a version.
Every match of every line is checked, so a file may be listed more than once
and may hold the version several times.

A line may start with `group|` to check it against the other lines of that
group instead of the repo's own version, e.g. a doc that mirrors a dependency
pin from CMakeLists.txt:

    protocol|CMakeLists.txt: GIT_TAG v([0-9.]+)
    protocol|docs/providers.md: protocol v([0-9.]+)

Exit codes: 0 all agree, 1 mismatch, 2 bad input (malformed line, missing
file, or a regex with no match).
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
LOCATIONS_FILE = ROOT / "version-locations.txt"
DEFAULT_GROUP = "version"
GROUP_PREFIX = re.compile(r"^([A-Za-z0-9_-]+)\|")

entries = []  # (group, path, regex)

try:
    with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            group = DEFAULT_GROUP
            m = GROUP_PREFIX.match(line)
            if m:
                group, line = m.group(1), line[m.end():]
            if ':' not in line:
                print(f"Malformed line in version-locations.txt: {line}", file=sys.stderr)
                sys.exit(2)
            path, regex = line.split(':', 1)
            entries.append((group, path.strip(), regex.strip()))
except FileNotFoundError:
    print(f"version-locations.txt not found in {ROOT}", file=sys.stderr)
    sys.exit(2)

if not entries:
    print("No versions found. Check version-locations.txt.", file=sys.stderr)
    sys.exit(2)

groups = {}  # group -> list of (path, regex, version)

for group, relpath, regex in entries:
    fpath = ROOT / relpath
    if not fpath.exists():
        print(f"Error: tracked file not found: {relpath}", file=sys.stderr)
        sys.exit(2)
    content = fpath.read_text(encoding="utf-8")
    found = [m.group(1) for m in re.finditer(regex, content, re.MULTILINE)]
    if not found:
        print(f"Error: Could not find version in {relpath} using regex: {regex}", file=sys.stderr)
        sys.exit(2)
    groups.setdefault(group, []).extend((relpath, regex, v) for v in found)

failed = False
for group, found in groups.items():
    unique = {v for _, _, v in found}
    label = "Version" if group == DEFAULT_GROUP else f"Group '{group}'"
    if len(unique) > 1:
        failed = True
        print(f"{label} mismatch detected:", file=sys.stderr)
        for path, regex, ver in found:
            print(f"  {path} ({regex}): {ver}", file=sys.stderr)
    else:
        print(f"{label}: all {len(found)} string(s) match {unique.pop()}")

sys.exit(1 if failed else 0)
