## setup-worktree

`setup-worktree` copies files and directories that are commonly ignored by Git
from a source checkout into a new worktree.

Install it with uv from this repository:

```bash
uv tool install .
```

Install it directly from GitHub:

```bash
uv tool install git+https://github.com/<owner>/<repo>@v0.1.0
```

To install the latest commit from the default branch, omit the tag:

```bash
uv tool install git+https://github.com/<owner>/<repo>
```

Run it with a YAML configuration:

```bash
setup-worktree examples/tree-setup.yml
setup-worktree --config examples/tree-setup.yml
setup-worktree copy examples/tree-setup.yml
```

The command copies source-relative `directories` and `files` into the configured
destination. `mappings` let you copy a destination path from another source, such
as a shared skills directory.

Relative `source`, `destination`, and mapping source paths are resolved from the
directory containing the YAML file.

```yaml
setup:
  source: "/path/to/main/checkout"
  destination: "/path/to/new/worktree"

  directories:
    - "specs/feature-spec"
    - ".mcp-configs"
    - ".agents":
        - "skills"

  files:
    - "AGENTS.md"
    - ".gitignore"

  mappings:
    - ".agents/skills": "/path/to/shared/codex/skills"
```

Useful options:

```bash
setup-worktree tree-setup.yml --dry-run
setup-worktree tree-setup.yml --strict
```

Create a starter configuration:

```bash
setup-worktree init
setup-worktree init --agent codex
setup-worktree init --agent claude
setup-worktree init --agent codex --agent claude
setup-worktree init --agent all --output tree-setup.yml --force
```

Contributor checks:

```bash
uv sync --dev
uv run task check
```
