#!/usr/bin/env bash
#
# adpp_compat_run.sh <cells.json> <results.json>
#
# Runs the ADPP conformance harness for every (protocol, provider, version) cell
# produced by adpp_compat_enumerate.sh and writes a results array:
#   { protocol, provider, version, status: pass|fail, rc, summary }
#
# Per cell: install the protocol's conformance harness wheel (cached per
# protocol), download the provider's released linux-x86_64 binary + source
# tarball (cached per provider@version), then run the harness against the
# released binary using the released manifest + mock config. Never fails the
# job on a conformance failure — the result is recorded, not gated.
#
# Requires: gh (authenticated), jq, python3.
set -euo pipefail

CELLS="${1:?usage: adpp_compat_run.sh <cells.json> <results.json>}"
OUT="${2:?usage: adpp_compat_run.sh <cells.json> <results.json>}"
ORG="anolishq"

WORK="$(mktemp -d)"
VENVS="$WORK/venvs"
ART="$WORK/art"
mkdir -p "$VENVS" "$ART"
trap 'rm -rf "$WORK"' EXIT

# Install (once per protocol) the conformance harness from its release wheel;
# echo the path to the cell's anolis-adpp-conformance entry point.
ensure_harness() {
  local tag="$1" ver="${1#v}" venv="$VENVS/$1"
  if [ ! -x "$venv/bin/anolis-adpp-conformance" ]; then
    python3 -m venv "$venv" >&2
    "$venv/bin/pip" install --quiet --upgrade pip >&2
    "$venv/bin/pip" install --quiet \
      "anolis-protocol[conformance] @ https://github.com/$ORG/anolis-protocol/releases/download/$tag/anolis_protocol-$ver-py3-none-any.whl" >&2
  fi
  echo "$venv/bin/anolis-adpp-conformance"
}

# Download + unpack (once per provider@version) the released binary and source
# tarball; echo "<binary path>|<config dir>".
ensure_provider() {
  local repo="$1" ver="$2" d="$ART/$1@$2"
  if [ ! -d "$d" ]; then
    mkdir -p "$d/bin" "$d/cfg"
    gh release download "$ver" -R "$ORG/$repo" --pattern '*linux-x86_64.tar.gz' --dir "$d" >&2
    gh release download "$ver" -R "$ORG/$repo" --pattern '*source.tar.gz' --dir "$d" >&2
    tar xzf "$d"/*linux-x86_64.tar.gz -C "$d/bin"
    tar xzf "$d"/*source.tar.gz -C "$d/cfg" --strip-components=1
  fi
  local bin
  bin="$(find "$d/bin" -type f -name "$repo")"
  echo "$bin|$d/cfg"
}

results='[]'
n="$(jq 'length' "$CELLS")"
for i in $(seq 0 $((n - 1))); do
  cell="$(jq -c ".[$i]" "$CELLS")"
  protocol="$(jq -r '.protocol' <<<"$cell")"
  repo="$(jq -r '.provider' <<<"$cell")"
  version="$(jq -r '.version' <<<"$cell")"

  harness="$(ensure_harness "$protocol")"
  IFS='|' read -r bin cfg < <(ensure_provider "$repo" "$version")

  set +e
  out="$("$harness" \
    --provider-bin "$bin" \
    --provider-config "$cfg/config/conformance.yaml" \
    --provider-profile "$cfg/config/conformance.toml" \
    -ra 2>&1)"
  rc=$?
  set -e

  # Three outcomes, distinguished so a harness-side incompatibility is never
  # mislabeled as a provider conformance failure:
  #   pass  - harness ran and every selected assertion passed (rc 0).
  #   fail  - harness ran and reported failing/erroring assertions: the provider
  #           genuinely violates the contract for that protocol version.
  #   error - harness could not produce a verdict (e.g. a pytest INTERNALERROR,
  #           or every test deselected) - a harness/version-compat problem, not a
  #           provider defect. Older harnesses error out against newer providers.
  if [ "$rc" -eq 0 ]; then
    status="pass"
  elif grep -qE '[1-9][0-9]* (failed|error)' <<<"$out"; then
    status="fail"
  else
    status="error"
  fi
  line="$(grep -hoE '[0-9]+ (passed|failed|skipped|error|deselected|xfailed)[^=]*' <<<"$out" | tail -1 | sed -E 's/ +$//')"
  [ -n "$line" ] || line="(no harness summary; rc=$rc)"

  results="$(jq -c \
    --arg p "$protocol" --arg r "$repo" --arg v "$version" \
    --arg s "$status" --arg l "$line" --argjson rc "$rc" \
    '. += [{protocol:$p, provider:$r, version:$v, status:$s, rc:$rc, summary:$l}]' \
    <<<"$results")"
  echo "[$status] $protocol x $repo $version :: $line" >&2
done

echo "$results" >"$OUT"
