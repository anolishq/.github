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

## Repo-specific gotchas

<!-- The highest-value section. ONLY non-obvious things agents get wrong here:
     selection mechanisms, generated-file locations, language/standard quirks,
     contracts that must stay in sync, etc. If there are none, say "None." -->
- _List the real gotchas, or "None."_
