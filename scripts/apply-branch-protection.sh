#!/usr/bin/env bash
#
# apply-branch-protection.sh
#
# Applies the canonical classic branch protection to the `main` branch of
# every anolishq repository whose CI exposes the shared `ok` aggregator
# status check. This is the single source of truth for `main` protection
# across the org while we remain on the GitHub Free plan (org-level
# rulesets require GitHub Team).
#
# The canonical protection requires exactly one status check — `ok` — which
# every repo's CI exposes as a final aggregator job. See each repo's
# .github/workflows/ci.yml.
#
# Idempotent: re-running re-asserts the same settings and is a no-op on
# already-conformant repos. Run it after onboarding a new repo (once that
# repo's CI grows an `ok` job) or to heal any drift.
#
# Usage:
#   ./scripts/apply-branch-protection.sh           # apply to all repos
#   ./scripts/apply-branch-protection.sh --dry-run # show what would change
#
# Requires: gh CLI authenticated with admin on the org repos.
#
set -euo pipefail

ORG=anolishq
BRANCH=main
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Repos that expose the shared `ok` status check.
#
# NOTE: every repo listed here MUST have an `ok` job in its CI that runs on
# pull_request, otherwise PRs will be permanently blocked by the required
# check. Do not add a repo here until its CI exposes `ok`.
REPOS=(
  .github
  anolis
  anolis-operator-ui
  anolis-projects
  anolis-protocol
  anolis-provider-bread
  anolis-provider-ezo
  anolis-provider-sdk
  anolis-provider-sim
  anolis-telemetry-export
  anolis-workbench
  anolishq.github.io
  baseliner-control
  fluxgraph
  renovate-config
)

# Canonical protection. PR required, no human approval needed (solo-dev
# org); admins included; one required check (`ok`); branch must be up to
# date before merge; no force-pushes or deletions.
read -r -d '' PROTECTION <<'JSON' || true
{
  "required_status_checks": {
    "strict": true,
    "checks": [ { "context": "ok" } ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "require_last_push_approval": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": false
}
JSON

fail=0
for repo in "${REPOS[@]}"; do
  if [[ "$DRY_RUN" == true ]]; then
    printf 'would protect %s/%s\n' "$ORG" "$repo"
    continue
  fi
  printf 'protecting %s/%s ... ' "$ORG" "$repo"
  if echo "$PROTECTION" | gh api -X PUT \
       "/repos/${ORG}/${repo}/branches/${BRANCH}/protection" \
       -H "Accept: application/vnd.github+json" --input - >/dev/null; then
    echo "ok"
  else
    echo "FAILED"
    fail=1
  fi
done

exit "$fail"
