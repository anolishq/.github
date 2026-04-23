#!/usr/bin/env python3
"""
assert_version_sync.py: Checks that all version strings in version-locations.txt are identical.
Fails with a clear message if any mismatch is found.
"""
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
LOCATIONS_FILE = ROOT / "version-locations.txt"

version_regexes = []

try:
    with open(LOCATIONS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            if ':' not in line:
                print(f"Malformed line in version-locations.txt: {line}", file=sys.stderr)
                sys.exit(2)
            path, regex = line.split(':', 1)
            version_regexes.append((path.strip(), regex.strip()))
except FileNotFoundError:
    print(f"version-locations.txt not found in {ROOT}", file=sys.stderr)
    sys.exit(2)

versions = {}

for relpath, regex in version_regexes:
    fpath = ROOT / relpath
    if not fpath.exists():
        print(f"Error: tracked file not found: {relpath}", file=sys.stderr)
        sys.exit(2)
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(regex, content, re.MULTILINE)
    if not m:
        print(f"Error: Could not find version in {relpath} using regex: {regex}", file=sys.stderr)
        sys.exit(2)
    versions[relpath] = m.group(1)

if not versions:
    print("No versions found. Check version-locations.txt.", file=sys.stderr)
    sys.exit(2)

unique_versions = set(versions.values())
if len(unique_versions) > 1:
    print("Version mismatch detected:", file=sys.stderr)
    for path, ver in versions.items():
        print(f"  {path}: {ver}", file=sys.stderr)
    sys.exit(1)

print(f"All version strings match: {unique_versions.pop()}")
