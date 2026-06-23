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

### valgrind-leak.yml

Reusable memory-leak check for the C/C++ repos: builds a target (vcpkg + a
CMake preset) and runs a chosen command under `valgrind --leak-check=full`,
applying a repo-provided suppressions file. **Advisory by default** (the job
succeeds, surfacing the leak summary + a `valgrind-log` artifact); set
`enforce: true` to fail on "definitely lost".

```yaml
jobs:
  leak-check:
    uses: anolishq/.github/.github/workflows/valgrind-leak.yml@<sha> # v2
    with:
      build-preset: ci-linux-release
      build-target: anolis-runtime          # optional, faster than building all
      run: "build/ci-linux-release/core/anolis-runtime --check-config test.yaml"
      # duration: "30s"                      # for long-running binaries (sends SIGINT, then leak-checks)
      # suppressions: valgrind.supp          # applied when present
      # enforce: true                        # fail on definitely-lost
```

vcpkg / gRPC / protobuf / abseil produce well-documented valgrind false
positives, so each consumer checks in its own **`valgrind.supp`**; the first run
per repo is a triage pass — the workflow runs with `--gen-suppressions=all`, so
the artifact contains ready-to-paste suppression blocks. Only **"definitely
lost"** is treated as a failure; "possibly lost" / "still reachable" (library
static/TLS allocations) are reported but ignored.

### fuzz.yml

Reusable [libFuzzer](https://llvm.org/docs/LibFuzzer.html) runner for the C/C++
repos. Builds a repo's fuzz targets with **Clang**
(`-fsanitize=fuzzer,address`) and runs each for a bounded time against
its checked-in corpus. This is a short **regression** run, not a soak — keep
`max-total-time` small. Advisory by default (crashes surface in the summary + a
`fuzz-crashes` artifact); `enforce: true` fails on a crash.

Two pieces:

1. **`templates/AddFuzzTarget.cmake`** — copy into the consumer repo (e.g.
   `cmake/AddFuzzTarget.cmake`), gate behind `option(ENABLE_FUZZING ...)`, and
   declare targets with `anolis_add_fuzz_target(NAME ... SOURCES ... LINK ...)`.
   A harness only defines `LLVMFuzzerTestOneInput`; libFuzzer provides `main()`.
2. **A `ci-fuzz` CMake preset** (Clang + `ENABLE_FUZZING=ON`) the workflow configures.

```yaml
jobs:
  fuzz:
    uses: anolishq/.github/.github/workflows/fuzz.yml@<sha> # v2
    with:
      build-preset: ci-fuzz
      fuzz-binaries: "build/ci-fuzz/fuzz/fuzz_config build/ci-fuzz/fuzz/fuzz_frame"
      corpus-root: fuzz/corpus      # per-target subdir by binary basename
      max-total-time: "60"          # seconds per target
      # enforce: true               # fail on crash
```

## Shared Configuration

### .markdownlint.json

Shared markdownlint configuration fetched by `docs-check.yml`:

- Line length: 140 (relaxed for technical docs)
- MD033 disabled (allows inline HTML for VitePress components)

### Provider lint/format templates

Shared C++ formatting/lint config for the device providers (ezo/sim/bread), kept
consistent with the anolis runtime. Copy each into the consumer repo root:

| Template | Copy to | Purpose |
| --- | --- | --- |
| `templates/clang-format` | `.clang-format` | clang-format 18 style (Google base, 120 cols, 4-space indent). Gate in CI with `clang-format --dry-run --Werror`. |
| `templates/clang-tidy` | `.clang-tidy` | High-signal checks (diagnostic/analyzer/bugprone/performance; readability off). Adjust `HeaderFilterRegex` to the repo's source roots. |
| `templates/editorconfig` | `.editorconfig` | Editor defaults aligned with `.clang-format` (4-space C++, LF, trim trailing). |
| `templates/pre-commit-config.yaml` | `.pre-commit-config.yaml` | **Pinned formatter source of truth.** `mirrors-clang-format@v18.1.8` — the same PyPI wheel, run identically by devs (`pre-commit install`) and CI (`pre-commit run --all-files`). |
| `templates/provider.justfile` | `justfile` | Task runner (`setup`, `hooks`, `fmt`, `fmt-check`, `lint`, `check`, `test`). `fmt`/`fmt-check` delegate to pre-commit. Set `preset` to the repo's primary CMake preset. |

The formatter is pinned **in-repo** via pre-commit (`.pre-commit-config.yaml`),
so the exact clang-format version is consumed identically at commit time and in
CI — the CI gate is a `pre-commit` job running `pre-commit run --all-files`. Pin
the wheel rather than an apt package: `apt` versions drift by distro/image
(unversioned `clang-format` on `ubuntu-24.04` is an experimental 18.0 snapshot;
`clang-format-18` is 18.1.3 there but 18.1.8 on Debian), and 18.1.3 vs 18.1.8
wrap long operator chains differently — so an apt-based gate is non-deterministic.
The `mirrors-clang-format` hook uses the byte-identical PyPI wheel everywhere.
This supersedes the interim CI-only `pipx run clang-format==18.1.8` gate.

> This per-repo inline gate is an interim measure. The planned org-wide source of
> truth is a shared **pre-commit** config (pinned hooks, enforced locally and in
> CI) — see [#69](https://github.com/anolishq/.github/issues/69).

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
