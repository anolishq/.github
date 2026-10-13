# AGENTS.md — <REPO NAME>

> Per-repo conventions for coding agents (Claude Code, OpenCode, …). The
> canonical cross-repo rules — Conventional Commits, minimal-first/YAGNI, no
> secrets, run checks before asserting success — live in the user's **global**
> `AGENTS.md` and are not repeated here. This file records only what is
> **specific to this repo**: the commands, the gate, and the non-obvious things
> agents get wrong here. Keep it short; delete sections that don't apply.

## Build / test

<!-- The actual commands. Replace with this repo's real flow. -->
- _Setup / build / test commands here._
- The required CI status check is the **`ok`** job (it aggregates the lanes);
  never bypass it, and never merge red.

## Tooling

<!-- Keep only the lines true for this repo. -->
- **C++ repos:** clang-format / clang-tidy are pinned to **18.1.8** via the
  shared `setup-clang-tools` action (install the same pinned binary on dev boxes) —
  do NOT use pip/apt/pre-commit/container versions. Run `clang-format -i` before
  **every** commit (CI fails otherwise). vcpkg comes from the shared
  `setup-vcpkg` action.
- Shared `.github` actions/workflows are SHA-pinned with a `# <tag>` comment so
  Renovate can track them — keep that comment when bumping.

## C++ conventions

<!-- The org-wide C++ conventions. Keep for C++ repos; delete otherwise. -->
- **C++20**, and `std::format` for diagnostic and error messages.
- **Headers live beside their `.cpp` under `src/`**, included full-path with
  `-I src` (`#include "<pkg>/x.hpp"`). fluxgraph, the library the providers
  consume, keeps its headers under `include/fluxgraph/` instead. Before adding a
  directory of headers with no `.cpp`, read the `clang-tidy-diff.yml` section of
  the anolishq/.github README: the gate lints a changed header with a borrowed
  compile command.
- **Test-only clang-tidy relaxations go in `tests/.clang-tidy`** with
  `InheritParentConfig: true`, not in per-line `NOLINT`s or an org-wide disable.
- **A genuine false positive gets one `// NOLINTNEXTLINE(<check>) <reason>`
  line**, short enough for the 120-column limit. clang-format wraps a longer
  one onto a second line, and the suppression then applies to that comment line
  instead of the code. Run clang-tidy after clang-format.
- **The PR clang-tidy gate is diff-only.** Leave existing findings on lines the
  PR does not touch.

## Repo-specific gotchas

<!-- The highest-value section. ONLY non-obvious things agents get wrong here:
     selection mechanisms, generated-file locations, language/standard quirks,
     contracts that must stay in sync, etc. If there are none, say "None." -->
- _List the real gotchas, or "None."_
