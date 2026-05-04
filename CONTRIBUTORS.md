# Contributors

Thanks for helping improve `setup-worktree`.

## Development Setup

Install dependencies with uv:

```bash
uv sync --dev
```

Run the contributor checks:

```bash
uv run task check
```

Individual tasks are available when you want a smaller feedback loop:

```bash
uv run task test
uv run task compile
uv run task help
uv run task build
```

## Contribution Guidelines

- Keep changes small and focused.
- Prefer clear CLI behavior over broad configurability.
- Add or update tests when changing copy behavior, path resolution, or YAML
  validation.
- Keep examples generic and free of machine-specific absolute paths.
- Run `uv run task check` before opening a pull request.

## Project Notes

This project uses `taskipy` for contributor tasks, configured in
`pyproject.toml`. Runtime dependencies should stay limited to what the CLI needs
to read configuration and copy files.
