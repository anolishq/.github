#!/usr/bin/env bash
#
# apply-branch-protection.sh
#
# Applies the canonical classic branch protection to the `main` branch of
# every anolishq repository whose CI exposes the shared `ok` aggregator
# status check, protects each repo's `v*` release tags against deletion and
# force-push, and asserts the canonical repository settings. This is the single
# source of truth for `main` protection, tag protection, and merge behaviour
# across the org while we remain on the GitHub Free plan (org-level rulesets
# require GitHub Team; per-repo rulesets are free on public repos; and
# `delete_branch_on_merge` has no org-level default at any tier).
#
# The canonical protection requires exactly one status check — `ok` — which
# every repo's CI exposes as a final aggregator job. See each repo's
# .github/workflows/ci.yml.
#
# Idempotent: re-running re-asserts the same settings and is a no-op on
# already-conformant repos. This is what makes it safe to run on a schedule
# (see .github/workflows/branch-protection-heal.yml) to heal drift.
#
# Per-repo outcomes are classified so a scheduled run is legible:
#   - OK       — protection + settings asserted (or already conformant)
#   - SKIPPED  — expected, non-fatal (repo archived: archived repos reject
#                protection PUTs by design, so this must NOT fail the run)
#   - FAILED   — genuine problem (repo missing, API error) → non-zero exit
# The exit code is non-zero only if at least one repo FAILED.
#
# Usage:
#   ./scripts/apply-branch-protection.sh           # apply to all repos
#   ./scripts/apply-branch-protection.sh --dry-run # show what would change
#
# Requires: gh CLI authenticated with admin on the org repos (the heal
# workflow supplies an admin-scoped PAT; the default GITHUB_TOKEN cannot PUT
# branch protection / rulesets across repos).
#
set -euo pipefail

ORG=anolishq
BRANCH=main
TAG_RULESET_NAME="protect-version-tags"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Repos that expose the shared `ok` status check.
#
# NOTE: every repo listed here MUST have an `ok` job in its CI that runs on
# pull_request, otherwise PRs will be permanently blocked by the required
# check. Do not add a repo here until its CI exposes `ok`. Onboarding a new
# repo = add it here (the reconciliation report at the end of a run flags org
# repos that are not yet enrolled).
REPOS=(
  .github
  anolis
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

# Canonical branch protection. PR required, no human approval needed (solo-dev
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

# Canonical repository settings.
#
# `delete_branch_on_merge` is load-bearing, not cosmetic. Renovate hands merges
# to GitHub via platformAutomerge, so GitHub — not Renovate — deletes the head
# branch, and GitHub honours this flag. With it false, branch names that recur
# forever (renovate/lock-file-maintenance, renovate/python-dev-tooling …)
# survive their own merge. Renovate then reuses the stale branch, regenerates
# nothing against the new base, and aborts with "Detected empty commit -
# aborting git push"; the leftover branch reopens as a duplicate PR that
# squash-merges empty, and eventually latches to "PR Edited (Blocked)",
# silently killing lock file maintenance for that repo. GitHub offers no
# org-level default for this, so it is per-repo drift and belongs here.
# See anolishq/.github#113.
#
# `allow_auto_merge` is what lets Renovate delegate the merge to GitHub in the
# first place; without it, automerge-eligible PRs sit open indefinitely.
read -r -d '' REPO_SETTINGS <<'JSON' || true
{
  "delete_branch_on_merge": true,
  "allow_auto_merge": true
}
JSON

# Tag protection ruleset. Blocks deletion and force-push (non-fast-forward) of
# immutable release tags; creation of new release tags is intentionally allowed.
#
# The pattern is `v*.*` (DOTTED tags: v2.4, v0.2.7 …), NOT `v*`. Bare-major
# aliases like `v1`/`v2` are *moving* tags — the shared-actions release flow
# re-points them with `git tag -f v2 <sha> && git push -f origin v2` (see
# README), which non_fast_forward would block. Immutable release tags always
# carry a dot; the moving aliases never do, so `v*.*` protects exactly the tags
# that must never move or be deleted and leaves the aliases free. Because
# nothing matched here is ever meant to move, no bypass actor is needed —
# mirroring the branch `enforce_admins: true` posture.
#
# The classic tag-protection API was retired by GitHub, so this is a repository
# ruleset (free on public repos).
read -r -d '' TAG_RULESET <<JSON || true
{
  "name": "${TAG_RULESET_NAME}",
  "target": "tag",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": [ "refs/tags/v*.*" ], "exclude": [] } },
  "rules": [ { "type": "deletion" }, { "type": "non_fast_forward" } ],
  "bypass_actors": []
}
JSON

declare -a ok_repos=() skipped_repos=() failed_repos=()

# Assert the tag ruleset idempotently: update the existing one by id if present,
# otherwise create it. Returns non-zero on a genuine API failure.
apply_tag_ruleset() {
  local repo="$1" existing_id
  # Fetch existing rulesets FIRST. A genuine list failure must not fall through
  # to a POST — that would create a duplicate ruleset (GitHub does not enforce
  # unique names), which no later run would reconcile. Fail the repo instead.
  if ! existing_id="$(gh api "/repos/${ORG}/${repo}/rulesets" \
      -H "Accept: application/vnd.github+json" \
      --jq "[.[] | select(.name == \"${TAG_RULESET_NAME}\") | .id] | first // empty")"; then
    return 1
  fi
  if [[ -n "$existing_id" ]]; then
    echo "$TAG_RULESET" | gh api -X PUT \
      "/repos/${ORG}/${repo}/rulesets/${existing_id}" \
      -H "Accept: application/vnd.github+json" --input - >/dev/null
  else
    echo "$TAG_RULESET" | gh api -X POST \
      "/repos/${ORG}/${repo}/rulesets" \
      -H "Accept: application/vnd.github+json" --input - >/dev/null
  fi
}

for repo in "${REPOS[@]}"; do
  if [[ "$DRY_RUN" == true ]]; then
    printf 'would protect %s/%s (branch %s + tag ruleset %s + repo settings)\n' \
      "$ORG" "$repo" "$BRANCH" "$TAG_RULESET_NAME"
    continue
  fi

  printf 'protecting %s/%s ... ' "$ORG" "$repo"

  # Archived repos reject protection PUTs (403) by design — skip, don't fail.
  archived="$(gh api "/repos/${ORG}/${repo}" --jq '.archived' 2>/dev/null || echo 'lookup-failed')"
  if [[ "$archived" == "lookup-failed" ]]; then
    echo "FAILED (repo lookup failed — missing or API error)"
    failed_repos+=("$repo")
    continue
  fi
  if [[ "$archived" == "true" ]]; then
    echo "SKIPPED (archived)"
    skipped_repos+=("$repo")
    continue
  fi

  if echo "$PROTECTION" | gh api -X PUT \
       "/repos/${ORG}/${repo}/branches/${BRANCH}/protection" \
       -H "Accept: application/vnd.github+json" --input - >/dev/null \
     && echo "$REPO_SETTINGS" | gh api -X PATCH "/repos/${ORG}/${repo}" \
       -H "Accept: application/vnd.github+json" --input - >/dev/null \
     && apply_tag_ruleset "$repo"; then
    echo "ok"
    ok_repos+=("$repo")
  else
    echo "FAILED"
    failed_repos+=("$repo")
  fi
done

if [[ "$DRY_RUN" == true ]]; then
  exit 0
fi

# --- Drift reconciliation -------------------------------------------------
# Surface list drift loudly (dynamic discovery, explicit enrollment): report
# any non-archived org repo that is not enrolled, and any enrolled repo that is
# archived/gone. These are warnings, not failures — enrollment stays deliberate
# because requiring `ok` on a repo that lacks it would block its PRs.
echo
echo "=== reconciliation ==="
# Only public repos: tag rulesets are free only on public repos, and classic
# protection targets public repos here, so flagging a private repo as
# "unenrolled" would be a false nudge. An enumeration failure is surfaced (not
# swallowed into a phantom empty entry) and skips the pass.
if ! org_list="$(gh repo list "$ORG" --no-archived --visibility public --limit 200 \
    --json name --jq '.[].name' 2>/dev/null | sort)" || [[ -z "$org_list" ]]; then
  echo "WARNING: could not enumerate org repos (gh repo list failed) — skipping reconciliation."
else
  mapfile -t org_repos <<<"$org_list"
  mapfile -t unenrolled < <(comm -23 \
    <(printf '%s\n' "${org_repos[@]}") \
    <(printf '%s\n' "${REPOS[@]}" | sort))
  if ((${#unenrolled[@]} > 0)); then
    echo "WARNING: non-archived public org repos not enrolled (add to REPOS once they expose \`ok\`):"
    printf '  - %s\n' "${unenrolled[@]}"
  else
    echo "all non-archived public org repos are enrolled."
  fi
fi

# Enrolled repos that skipped (archived) or failed as missing should be removed
# from REPOS; surface them together for the same reason.
if ((${#skipped_repos[@]} > 0)); then
  echo "NOTE: enrolled repos skipped as archived (candidates for removal from REPOS):"
  printf '  - %s\n' "${skipped_repos[@]}"
fi

# --- Summary --------------------------------------------------------------
echo
echo "=== summary ==="
printf 'OK:      %d  %s\n' "${#ok_repos[@]}" "${ok_repos[*]}"
printf 'SKIPPED: %d  %s\n' "${#skipped_repos[@]}" "${skipped_repos[*]}"
printf 'FAILED:  %d  %s\n' "${#failed_repos[@]}" "${failed_repos[*]}"

((${#failed_repos[@]} == 0))
