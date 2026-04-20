# anolishq/.github

Org-level shared workflows and configuration for all anolishq repositories.

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
|-------|---------|-------------|
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
