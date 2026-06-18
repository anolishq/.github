# anolishq/.github

Org-level shared workflows and configuration for all anolishq repositories.

## Versioning

Consumers pin these shared workflows/actions to a commit SHA tagged **`v2`**:

```yaml
uses: anolishq/.github/.github/actions/setup-vcpkg@<sha> # v2
```

The `# v2` comment tells Renovate to track the **`v2` tag** — so a pin only
moves when `v2` is deliberately re-tagged (a release), **not** on every push to
`main`. Do **not** pin internal refs to `@<sha> # main`: that makes Renovate
re-pin on every `.github` commit, which churns PRs across the org.

**Cutting a release:** for a backward-compatible change, move the `v2` tag to
the new `main` SHA (`git tag -f v2 <sha> && git push -f origin v2`); for a
breaking change, cut `v3` and migrate consumers. Renovate then bumps the
SHA-pins to the new tag SHA (held 3 days by the supply-chain soak).

## Reusable Workflows

### docs-check.yml

Validates documentation on PRs and pushes:

- **Markdown lint** — style and formatting checks
- **VitePress build** — catches Vue template parsing errors before they break the docs site

```yaml
# .github/workflows/docs.yml
name: Docs
on: [push, pull_request]
jobs:
  check:
    uses: anolishq/.github/.github/workflows/docs-check.yml@main
```

Inputs:

| Input | Default | Description |
| ----- | ------- | ----------- |
| `docs-path` | `docs` | Path to docs directory |
| `markdownlint-globs` | `docs/**/*.md`, `README.md`, `CONTRIBUTING.md` | Files to lint |
| `skip-vitepress` | `false` | Skip VitePress build check |

### metrics.yml

Collects repository metrics (runs on main, not PRs):

- tokei (lines of code by language)
- cloc (detailed code statistics)
- tree (directory structure)

```yaml
# .github/workflows/metrics.yml
name: Metrics
on:
  push:
    branches: [main]
jobs:
  collect:
    uses: anolishq/.github/.github/workflows/metrics.yml@main
```

## Shared Configuration

### .markdownlint.json

Shared markdownlint configuration fetched by `docs-check.yml`:

- Line length: 140 (relaxed for technical docs)
- MD033 disabled (allows inline HTML for VitePress components)

## Dependency scanning

`dependency-scan.yml` is a reusable workflow that scans a repo's **vcpkg**
C/C++ dependency set for known CVEs. It runs on a schedule (and manual
dispatch), is **non-blocking** (never fails a build), and surfaces findings as
a job summary plus an uploaded report artifact.

```yaml
# .github/workflows/dependency-scan.yml in a consuming repo
name: Dependency Scan
on:
  schedule: [{ cron: "0 7 * * 1" }] # Mondays 07:00 UTC
  workflow_dispatch:
permissions: { contents: read }
jobs:
  scan:
    uses: anolishq/.github/.github/workflows/dependency-scan.yml@<sha> # main
    with:
      triplet: x64-linux-static   # x64-linux for repos using the built-in triplet
      # features: "tests;json;yaml;server"   # only if deps are feature-gated
```

No secrets or API keys are required.

### NVD data source (keyless)

The scan matches dependency versions against the **National Vulnerability
Database**, pulled from the keyless **cveb.in mirror** (FCIX-backed: no API key,
no rate limit, refreshed several times daily). NVD's own API returns `503` to
GitHub-hosted runner IPs even with a key, so the mirror is the reliable source
from CI. `cve-bin-tool` is pinned to a `main` commit because the fix to read the
live NVD **2.0** feed (the released 3.4 uses the retired, empty 1.1 feed) is not
in any release yet. The job summary reports the loaded CVE count and **flags
INCOMPLETE if the mirror ever fails to populate** — so an empty result is never
mistaken for a clean bill of health.

### How it works

vcpkg pins dependency versions via the registry baseline (not `vcpkg.json`),
and its SPDX SBOMs carry no CPE/purl, so generic SBOM scanners
(OSV-Scanner/Trivy/Grype) can't match them. Instead the workflow:

1. installs the resolved dependency set with vcpkg;
2. reads exact versions from the per-port `vcpkg.spdx.json` SBOMs and maps each
   vcpkg port to its NVD `vendor,product` via a small curated table in the
   reusable workflow (extend it when a new dependency is introduced);
3. runs [`cve-bin-tool`](https://github.com/intel/cve-bin-tool) two ways — a
   **version lookup** (`--input-file`, matches resolved versions against the
   *full* NVD database, covering C++ libs with no binary checker) and a
   **binary scan** (fingerprints compiled libraries, catching linked/transitive
   libs like openssl, zlib, c-ares).

### Reading and triaging findings

- Open the run → **Summary** for the two finding tables, or download the
  **`cve-report-*`** artifact for the full JSON/HTML.
- Each row is `product · version · CVE · severity · score`. The version is the
  vcpkg-resolved one actually shipped; confirm the CVE's applicability.
- **Remediate** by bumping the vcpkg baseline / port version (Renovate proposes
  these) so the fixed version is pulled.
- **False positives** can be suppressed with a cve-bin-tool triage file checked
  into the repo (see cve-bin-tool's `--triage-input-file`).

## Branch protection

Every repo's `main` is protected with one canonical classic ruleset: a
single required status check named `ok` (the final aggregator job each
repo's `ci.yml` exposes), `strict` up-to-date merges, admins included, no
force-pushes or deletions, and PRs required (0 approvals).

Org-level rulesets would let us define this once, but they require GitHub
Team; on the Free plan the equivalent is `scripts/apply-branch-protection.sh`,
which holds the canonical config and applies it to every `ok`-bearing repo.

```bash
./scripts/apply-branch-protection.sh --dry-run  # preview
./scripts/apply-branch-protection.sh            # apply / heal drift
```

Run it after onboarding a new repo — once that repo's CI exposes an `ok`
job, add it to the `REPOS` list in the script and re-run.
