#!/usr/bin/env bash
#
# adpp_compat_summary.sh <results.json>
#
# Render the ADPP compatibility-matrix results (from adpp_compat_run.sh) as a
# GitHub-flavored markdown table on stdout (intended for $GITHUB_STEP_SUMMARY).
# Report-only: prints a status table, never exits non-zero on conformance fails.
set -euo pipefail

R="${1:?usage: adpp_compat_summary.sh <results.json>}"

echo "## ADPP Compatibility Matrix"
echo
echo "Released protocol harness × released provider — conformance harness run per"
echo "cell. Non-gating; report-only (anolis-protocol#28)."
echo

if [ ! -s "$R" ] || [ "$(jq 'length' "$R")" = "0" ]; then
  echo "_No eligible (protocol × provider) cells yet — no released provider bundles"
  echo "\`config/conformance.toml\` against a protocol harness ≥ v1.3.0._"
  exit 0
fi

total="$(jq 'length' "$R")"
passed="$(jq '[.[]|select(.status=="pass")]|length' "$R")"
failed="$(jq '[.[]|select(.status=="fail")]|length' "$R")"
errored="$(jq '[.[]|select(.status=="error")]|length' "$R")"

line="**$passed/$total passed.**"
[ "$failed" -gt 0 ] && line="$line ❌ $failed failed."
[ "$errored" -gt 0 ] && line="$line ⚠️ $errored no-verdict."
echo "$line"
echo
echo "Legend: ✅ pass · ❌ provider violates the contract for that protocol ·"
echo "⚠️ harness produced no verdict (version incompatibility, e.g. an older"
echo "harness erroring against a newer provider) — _not_ a provider failure · – not run."
echo

# Columns = protocol versions; rows = provider @ version.
mapfile -t protos < <(jq -r '[.[].protocol]|unique|sort|.[]' "$R")

header="| provider @ version |"
divider="|---|"
for p in "${protos[@]}"; do
  header+=" $p |"
  divider+="---|"
done
echo "$header"
echo "$divider"

while IFS= read -r pv; do
  prov="${pv%% *}"
  ver="${pv##* }"
  row="| \`$prov\` $ver |"
  for p in "${protos[@]}"; do
    st="$(jq -r --arg prov "$prov" --arg ver "$ver" --arg p "$p" \
      'map(select(.provider==$prov and .version==$ver and .protocol==$p))|.[0].status // "na"' "$R")"
    case "$st" in
      pass) row+=" ✅ |" ;;
      fail) row+=" ❌ |" ;;
      error) row+=" ⚠️ |" ;;
      *) row+=" – |" ;;
    esac
  done
  echo "$row"
done < <(jq -r '[.[]|.provider+" "+.version]|unique|.[]' "$R" | sort)

echo
echo "<details><summary>Per-cell harness summary</summary>"
echo
jq -r '.[]|"- \({pass:"✅",fail:"❌",error:"⚠️"}[.status] // "–") `\(.protocol)` × `\(.provider)` \(.version) — \(.summary) (rc=\(.rc))"' "$R"
echo
echo "</details>"
