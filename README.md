# anolishq/.github

Shared reusable workflows, composite actions and configuration for the
anolishq repositories.

## Versioning

Pin a shared workflow or action to a commit SHA, with the tag it tracks as a
comment:

```yaml
uses: anolishq/.github/.github/workflows/docs-check.yml@<sha> # v2
```

Renovate reads the comment and re-pins the SHA when that tag moves. Do not pin
to `@<sha> # main`: Renovate would then re-pin on every commit to `main` and
open PRs across the org.

The tags:

| Tag | Kind | Used for |
| --- | --- | --- |
| `v2` | Moving | Most workflows and actions |
| `v2.N` | Annotated, immutable | A specific release; `setup-vcpkg` is pinned `# v2.5` |
| `clang-tidy-diff` | Moving | `clang-tidy-diff.yml` |
| `setup-clang-tools` | Moving | The `setup-clang-tools` action |

The shared Renovate preset,
[`anolishq/renovate-config`](https://github.com/anolishq/renovate-config/blob/main/default.json),
holds third-party GitHub Actions for 3 days but applies no hold to
`anolishq/.github`. Non-major updates to it, including SHA re-pins, automerge
once CI passes. A major update, such as `v2` to `v3`, opens a PR for review.

### Cutting a release

For a backward-compatible change, tag the new `main` commit as the next
`v2.N` and move `v2` to it:

```bash
git tag -a v2.<N> -m "v2.<N>" <sha>
git push origin v2.<N>
git tag -f v2 <sha>
git push -f origin v2
```

A tag ruleset blocks deleting or force-pushing any `v*.*` tag, so check the
SHA before pushing `v2.N`; see [Branch protection](#branch-protection).

For a breaking change, cut `v3` and migrate the consumers.

## Reusable workflows

In the examples, `<sha>` is the commit the tag points at.

### docs-check.yml

Checks a repo's documentation. The repos with published docs that call it
(anolis, anolis-protocol, the providers, anolis-workbench and fluxgraph) run it
from their `ci.yml` as a `docs` job listed in the `needs` of the `ok`
aggregator, so a failure blocks the merge. For example, in
[`anolis`](https://github.com/anolishq/anolis/blob/main/.github/workflows/ci.yml):

```yaml
jobs:
  docs:
    name: Docs
    uses: anolishq/.github/.github/workflows/docs-check.yml@<sha> # v2

  ok:
    name: ok
    if: always()
    needs:
      - docs
      # ...the repo's other jobs
    runs-on: ubuntu-latest
    steps:
      - name: Fail if any required job failed or was cancelled
        if: contains(needs.*.result, 'failure') || contains(needs.*.result, 'cancelled')
        run: exit 1
```

A repo may gate the `docs` job on a path filter. A skipped job does not fail
`ok`.

Its jobs:

| Job | What it checks |
| --- | --- |
| Markdown Lint | markdownlint-cli2 over `markdownlint-globs` |
| VitePress Build | The docs build with VitePress, which catches Vue template parse errors |
| Link Check | lychee `--offline` over `docs/**/*.md` and `*.md`: local links only |
| Snippet Validation | YAML and JSON blocks against JSON Schemas; opt-in, see below |

Inputs:

| Input | Default | Description |
| --- | --- | --- |
| `docs-path` | `docs` | Docs directory copied into the VitePress build |
| `markdownlint-globs` | `docs/**/*.md`, `README.md`, `CONTRIBUTING.md` | Files to lint |
| `skip-vitepress` | `false` | Skip the VitePress build |
| `skip-link-check` | `false` | Skip the local link check |

#### Snippet validation

The job runs `scripts/validate_doc_snippets.py` at the commit the caller pins.
It does nothing unless the repo has a `doc-schemas.json` at its root, which
names each schema by a local `path` or a `url`, with an optional JSON
`pointer` to the schema inside the file:

```json
{
  "schemas": {
    "runtime-config": { "path": "schemas/runtime/runtime-config.schema.json" },
    "sim-config": { "url": "https://example.com/sim-config-schema.json", "pointer": "/schema" }
  }
}
```

It checks the published docs: `README.md` and `docs/**/*.md`, minus the names
in `docs/.indexignore`. Once a repo opts in, every `yaml`, `yml` or `json`
fenced block in them needs a `validate` comment as the nearest non-blank line
above it. A block without one fails. The forms:

```text
<!-- validate: runtime-config -->                              a complete document
<!-- validate: runtime-config fragment -->                     the schema's root `required` is dropped
<!-- validate: runtime-config pointer=/properties/providers --> validate against a subschema
<!-- validate: none -->                                        not a config example
```

A block's top-level keys must also be declared in the schema's `properties`,
even where the schema allows other keys. The runtime's loader only warns on an
unknown key, so a misspelled key would otherwise pass.

The script exits 1 when a block fails or has no annotation, and 2 on bad input:
an unknown schema name, an unreadable schema or a malformed annotation.

Renovate moves a schema `url` of the form
`https://raw.githubusercontent.com/anolishq/<repo>/v<x.y.z>/...` to that
repo's latest release.

### version-sync.yml

Fails when the version strings a repo keeps in several files disagree. It runs
`scripts/assert_version_sync.py`, at the commit the caller pins, against the
repo's `version-locations.txt`.

```yaml
jobs:
  version-sync:
    uses: anolishq/.github/.github/workflows/version-sync.yml@<sha> # v2
```

Inputs:

| Input | Default | Description |
| --- | --- | --- |
| `python-version` | `3.12` | Python used to run the script |
| `working-directory` | `.` | Directory holding `version-locations.txt`. Only `.` works: the script path `_github/scripts/...` resolves from this directory too |

`version-locations.txt` has one `path:regex` line per location. Blank lines
and lines starting with `#` are skipped. The line splits at its first `:`, so
the path cannot contain one and the regex can. The regex's first capture group
is the version:

```text
# version-locations.txt
CMakeLists.txt:project\(.* VERSION ([0-9]+\.[0-9]+\.[0-9]+)
vcpkg.json:"version": "([0-9]+\.[0-9]+\.[0-9]+)"
```

Every match of every line is checked, with `re.MULTILINE`, so a file may hold
the version several times or be listed twice.

A line that starts with `group|` is checked against the other lines of that
group instead of the repo's own version. Use it for a doc that mirrors a
dependency pin:

```text
protocol|CMakeLists.txt: GIT_TAG v([0-9.]+)
protocol|docs/providers.md: protocol v([0-9.]+)
```

The script exits 1 when any group's versions differ, and 2 on bad input: no
`version-locations.txt`, a malformed or empty one, a tracked file missing, or
a regex with no match.

### metrics.yml

Collects repository metrics with tokei, cloc and tree, and uploads them as a
`metrics-<repo>-<run number>` artifact kept for 90 days. The job summary shows
the tokei table.

```yaml
# .github/workflows/metrics.yml
name: Metrics
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
jobs:
  collect:
    uses: anolishq/.github/.github/workflows/metrics.yml@<sha> # v2
```

`exclude-dirs` takes comma-separated directories to skip. A release workflow
passes `tag: ${{ github.ref_name }}`, which is written to `metrics.json` (the
short SHA by default); the `metrics-json-path` output gives that file's path.

### valgrind-leak.yml

Builds a target with vcpkg and a CMake preset, then runs a command under
`valgrind --leak-check=full`. Only "definitely lost" counts as a leak.
"Possibly lost" and "still reachable" are reported and ignored.

The job is advisory by default: it succeeds and puts the leak summary in the
job summary and a `valgrind-log-<preset>` artifact. Set `enforce: true` to fail
on a definite leak.

```yaml
jobs:
  leak-check:
    uses: anolishq/.github/.github/workflows/valgrind-leak.yml@<sha> # v2
    with:
      build-preset: ci-linux-release
      build-target: anolis-runtime      # optional; faster than the whole preset
      run: "build/ci-linux-release/core/anolis-runtime --check-config test.yaml"
      # duration: "30s"                 # long-running binaries: send SIGINT after this
      # suppressions: valgrind.supp     # the default; applied when present
      # enforce: true
```

Other inputs: `triplet` (default `x64-linux-static`), `signal` (default
`INT`), `manifest-dir` (default `.`).

vcpkg, gRPC, protobuf and abseil produce known false positives, so each repo
checks in its own `valgrind.supp`. Valgrind runs with `--gen-suppressions=all`,
so the log artifact holds suppression blocks ready to paste.

### fuzz.yml

Builds a repo's [libFuzzer](https://llvm.org/docs/LibFuzzer.html) targets with
Clang (`-fsanitize=fuzzer,address`) and runs each for a bounded time against its checked-in corpus. It is a
short regression run, not a soak: keep `max-total-time` small. Advisory by
default; crashes appear in the job summary and a `fuzz-crashes` artifact, and
`enforce: true` fails the job on a crash.

A repo needs:

- `templates/AddFuzzTarget.cmake`, copied into the repo (for example
  `cmake/AddFuzzTarget.cmake`) and included behind `option(ENABLE_FUZZING ...)`.
  Declare targets with `anolis_add_fuzz_target(NAME ... SOURCES ... LINK ...)`.
  A harness defines only `LLVMFuzzerTestOneInput`; libFuzzer provides `main()`.
- A CMake preset that uses Clang and sets `ENABLE_FUZZING=ON`.

```yaml
jobs:
  fuzz:
    uses: anolishq/.github/.github/workflows/fuzz.yml@<sha> # v2
    with:
      build-preset: ci-fuzz
      fuzz-binaries: "build/ci-fuzz/fuzz/fuzz_config build/ci-fuzz/fuzz/fuzz_frame"
      corpus-root: fuzz/corpus      # one subdirectory per binary name
      max-total-time: "60"          # seconds per target
      # enforce: true
```

Other inputs: `triplet` (default `x64-linux-static`), `manifest-dir` (default
`.`).

### clang-tidy-diff.yml

Runs the pinned clang-tidy 18.1.8, with the repo's `.clang-tidy`, over only
the lines a PR changes. Findings appear as annotations on the PR diff and in
the job summary. The job configures and builds the preset first, because
clang-tidy needs `compile_commands.json` and any generated headers.

It is advisory by default. With `blocking: true` a finding on a changed line
fails the job; list it in the repo's `ok` aggregator so that blocks the merge.
In either mode the job fails when a PR changes C/C++ sources and clang-tidy
could not check them: no `compile_commands.json`, one with no entries, a crash,
or a clang-tidy that cannot start.

Callers pin it to the `clang-tidy-diff` tag:

```yaml
jobs:
  clang-tidy:
    permissions:
      contents: read
    uses: anolishq/.github/.github/workflows/clang-tidy-diff.yml@<sha> # clang-tidy-diff
    with:
      configure-preset: ci-linux-tidy
      triplet: x64-linux          # the repo's CI triplet
      apt-packages: graphviz      # build deps vcpkg does not provide
      blocking: true
```

Inputs:

| Input | Default | Description |
| --- | --- | --- |
| `configure-preset` | (required) | CMake configure preset; must export `compile_commands.json` to `build/<preset>` |
| `build-preset` | `configure-preset` | Build preset run before linting, to generate headers |
| `triplet` | `x64-linux-static` | vcpkg triplet; must match the repo's CI triplet |
| `paths` | `*.c *.cc *.cpp *.cxx *.h *.hh *.hpp *.hxx` | Space-separated git pathspecs to lint |
| `blocking` | `false` | Fail the job on a finding on a changed line |
| `apt-packages` | empty | Space-separated apt packages installed before configuring |

What a caller must get right:

- **The configure preset keeps the default `binaryDir`, `build/<presetName>`,
  and sets `CMAKE_EXPORT_COMPILE_COMMANDS=ON`.** The job reads the database
  from `build/<configure-preset>`. A repo whose main preset overrides
  `binaryDir` adds a tidy preset that keeps it, with every optional component
  enabled so all sources are in the database.
- `triplet` matches the repo's CI triplet. Otherwise the job misses the warm
  vcpkg cache, builds the dependencies from source, and can hit its 30-minute
  timeout.
- A changed header borrows the compile command of the translation unit
  clang-tidy judges closest by name and path. If that unit lacks the header's
  include root, such as a generated `*.pb.cc`, the header's includes fail with
  `clang-diagnostic-error: file not found`. A `.cpp` beside the header or with
  the same name avoids this. Check a directory of headers with no `.cpp`
  locally before relying on the gate:

  ```bash
  cmake --preset <preset>
  cmake --build --preset <preset>   # generated headers, if any
  clang-tidy -p build/<preset> path/to/new_dir/header.hpp
  ```

### dependency-scan.yml

Scans a repo's vcpkg dependency set for known CVEs. Call it on a schedule.
Findings never fail the build; they go to the job summary and a
`cve-report-<triplet>` artifact. A failed vcpkg install, a failed tool install
or the 90-minute timeout still fails the job.

```yaml
# .github/workflows/dependency-scan.yml
name: Dependency Scan
on:
  schedule:
    - cron: "0 7 * * 1" # Mondays 07:00 UTC
  workflow_dispatch:
permissions:
  contents: read
jobs:
  scan:
    uses: anolishq/.github/.github/workflows/dependency-scan.yml@<sha> # v2
    with:
      triplet: x64-linux-static   # x64-linux for repos on the built-in triplet
      # features: "tests;json;yaml;server"   # only if deps are feature-gated
```

Other inputs: `overlay-triplets` (default `triplets`, used when the directory
exists), `manifest-dir` (default `.`), `cve-bin-tool-ref`. No secrets are
needed.

vcpkg's SBOMs carry no CPE or purl, so generic SBOM scanners cannot match
them. The workflow installs the dependency set with vcpkg, reads each port's
version from its `vcpkg.spdx.json`, and maps the port to an NVD vendor and
product through a table in the workflow. Add an entry there when a repo gains
a dependency. It then runs
[`cve-bin-tool`](https://github.com/ossf/cve-bin-tool) twice: a version lookup
of the mapped ports, and a binary scan of the installed tree, which catches
linked libraries such as openssl and zlib. NVD data comes from the keyless
cveb.in mirror.

**An empty result is not a clean result when the NVD data did not load.** The
summary prints how many CVEs the database loaded, and marks coverage
INCOMPLETE when it is under 100,000.

Each finding row gives product, version, CVE, severity and score, with the
version vcpkg resolved. Confirm the CVE applies, then fix it by moving the
vcpkg baseline or port version.

## External link check

`external-links.yml` checks the external links in `docs/**/*.md` and
`README.md` on the default branch of each repo in its `REPOS` list, with the
settings in [`lychee.toml`](lychee.toml). Add a public repo to `REPOS` when it
gains published docs. Code blocks are not checked. It runs on Sundays at 06:00
UTC and on demand.

It gates nothing. A run with broken links opens or updates one issue in this
repo, "Broken external links in published docs", and a clean run closes it. A
PR that changes the workflow or `lychee.toml` runs the check and only
reports.

## Shared configuration

### .markdownlint.json

docs-check fetches this file, at the commit the caller pins, when the caller
has no markdownlint config of its own: `.markdownlint.jsonc`, `.json`,
`.yaml`, `.yml`, `.cjs` or `.mjs`, or a `.markdownlint-cli2.*` file. A failed
download fails the job.

It enables every rule except line length (MD013). Inline HTML (MD033) is
flagged; a repo that needs it disables MD033 in its own config.

### Templates

C++ formatting and lint config for the device providers. The formatting and
the clang-tidy check set match the anolis runtime; the runtime also promotes
every clang-tidy finding to an error (`WarningsAsErrors: "*"`), which the
template does not. Copy each into the repo root:

| Template | Copy to | Purpose |
| --- | --- | --- |
| `templates/clang-format` | `.clang-format` | Google base, 120 columns, 4-space indent |
| `templates/clang-tidy` | `.clang-tidy` | bugprone, performance, analyzer and diagnostic checks; readability off. Set `HeaderFilterRegex` to the repo's source roots |
| `templates/editorconfig` | `.editorconfig` | Editor defaults that match `.clang-format` |
| `templates/provider.justfile` | `justfile` | `setup`, `fmt`, `fmt-check`, `lint`, `check`, `test`. Set `preset` to the repo's main CMake preset |
| `templates/AGENTS.md` | `AGENTS.md` | Per-repo notes for coding agents |

### Pinned clang tools

clang-format output differs between builds: Debian's `clang-format-18` is
18.1.8, Ubuntu noble's is 18.1.3, and they format differently. So the org runs
one build everywhere: static LLVM 18.1.8 binaries from
[`muttleyxd/clang-tools-static-binaries`](https://github.com/muttleyxd/clang-tools-static-binaries),
tag `master-796e77c`, verified by SHA-512. Do not install clang-format from
apt, pip or pre-commit.

- In CI, the
  [`setup-clang-tools`](.github/actions/setup-clang-tools/action.yml) action
  installs `clang-format` on `PATH`, on Linux x86-64 runners only. With
  `tidy: "true"` it also installs `clang-tidy`, its builtin headers,
  `run-clang-tidy` and `clang-tidy-diff`. Pin it to the `setup-clang-tools`
  tag.
- On a dev box, install the same binaries with the same SHA-512s.
- A repo's `justfile` calls `clang-format` and `clang-tidy` from `PATH`. To
  change the version, update the action and reformat the tree in one change.

## Branch protection

`scripts/apply-branch-protection.sh` applies the same settings to every repo
in its `REPOS` list:

- Classic protection on `main`: one required status check, `ok` (the
  aggregator job in the repo's `ci.yml`), branches up to date before merge,
  admins included, PRs required with no approvals, no force-pushes or
  deletions.
- A ruleset, `protect-version-tags`, that blocks deleting or force-pushing
  tags matching `refs/tags/v*.*`. The moving tags (`v1`, `v2`) have no dot, so
  the release flow can still move them.
- `allow_auto_merge` and `delete_branch_on_merge` set to `true`. Renovate's
  automerge needs the first. Without the second, a Renovate branch whose name
  recurs, such as `renovate/lock-file-maintenance`, survives its merge and
  Renovate stops updating it.

```bash
./scripts/apply-branch-protection.sh --dry-run  # list what it would protect
./scripts/apply-branch-protection.sh            # apply, or heal drift
```

It needs `gh` with admin rights on the org's repos. It reports each repo as
OK, SKIPPED (archived) or FAILED, exits non-zero only on a failure, and lists
public, non-archived org repos that are not enrolled. Add a repo to `REPOS`
only once its CI has an `ok` job that runs on pull requests; otherwise no PR
in it can merge.

### Self-healing

`.github/workflows/branch-protection-heal.yml` runs the script on Wednesdays
at 06:00 UTC and on demand. The default `GITHUB_TOKEN` cannot write branch
protection or rulesets on other repos, so the workflow needs an admin token:

1. Create a fine-grained PAT with Administration: read and write on all
   anolishq repos, or a classic PAT with the `repo` scope.
2. Store it in this repo as the secret `BRANCH_PROTECTION_PAT`.

Without the secret the workflow fails at its "Verify admin PAT is present"
step, before touching any repo, with an error naming it.
