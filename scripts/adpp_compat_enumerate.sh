#!/usr/bin/env bash
#
# adpp_compat_enumerate.sh — emit the ADPP compatibility-matrix cell set as JSON.
#
# The org-level compatibility matrix (anolis-protocol#28) crosses RELEASED
# protocol harness versions with RELEASED provider versions and runs the
# conformance harness for each pair. This script discovers the eligible cells:
#
#   protocol axis : anolis-protocol releases >= the conformance floor (v1.3.0,
#                   the first release shipping the anolis_conformance harness).
#   provider axis : the latest MAX_PER_PROVIDER releases of each provider whose
#                   tag bundles config/conformance.toml (the harness manifest).
#                   Releases predating the manifest are skipped, so the matrix
#                   self-activates as conformant releases land.
#
# Output (stdout): a compact JSON array of
#   { protocol, protocol_ver, provider, version, ver }
# Requires: gh (authenticated), jq.
set -euo pipefail

ORG="anolishq"
FLOOR="1.3.0"
PROVIDERS=(anolis-provider-ezo anolis-provider-sim anolis-provider-bread)
MAX_PER_PROVIDER="${MAX_PER_PROVIDER:-5}"

# --- protocol axis: releases at or above the conformance floor ---
protocols=()
while IFS= read -r t; do
  v="${t#v}"
  if [ "$(printf '%s\n%s\n' "$FLOOR" "$v" | sort -V | head -1)" = "$FLOOR" ]; then
    protocols+=("$t")
  fi
done < <(gh release list -R "$ORG/anolis-protocol" --limit 50 --json tagName --jq '.[].tagName')

# --- provider axis x protocol axis: one cell per (eligible release, protocol) ---
cells='[]'
for repo in "${PROVIDERS[@]}"; do
  while IFS= read -r vt; do
    # eligible only if the tag bundles the conformance manifest
    if gh api "repos/$ORG/$repo/contents/config/conformance.toml?ref=$vt" >/dev/null 2>&1; then
      for pt in "${protocols[@]}"; do
        cells=$(jq -c \
          --arg protocol "$pt" --arg protocol_ver "${pt#v}" \
          --arg provider "$repo" --arg version "$vt" --arg ver "${vt#v}" \
          '. += [{protocol:$protocol, protocol_ver:$protocol_ver, provider:$provider, version:$version, ver:$ver}]' \
          <<<"$cells")
      done
    fi
  done < <(gh release list -R "$ORG/$repo" --limit "$MAX_PER_PROVIDER" --json tagName --jq '.[].tagName')
done

echo "$cells"
