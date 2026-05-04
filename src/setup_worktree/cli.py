from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import yaml

AGENT_ORDER = ("codex", "claude")
AGENT_CHOICES = (*AGENT_ORDER, "all")
COMMON_TEMPLATE_FILES = (".gitignore", ".python-version")


DirectoryTemplate = str | tuple[str, tuple[str, ...]]


@dataclass(frozen=True)
class CopyPlan:
    """Normalized copy instructions loaded from a YAML configuration file."""

    source_root: Path
    destination_root: Path
    directories: tuple[Path, ...]
    files: tuple[Path, ...]
    mappings: tuple[tuple[Path, Path], ...]


@dataclass(frozen=True)
class CopyOperation:
    """A resolved source and destination pair to copy."""

    source: Path
    destination: Path


@dataclass(frozen=True)
class AgentTemplate:
    """Starter YAML entries for one supported agent."""

    directories: tuple[DirectoryTemplate, ...]
    files: tuple[str, ...]
    mappings: tuple[tuple[str, str], ...]


AGENT_TEMPLATES = {
    "codex": AgentTemplate(
        directories=((".agents", ("skills",)), ".codex"),
        files=("AGENTS.md",),
        mappings=((".agents/skills", "../shared-skills/codex"),),
    ),
    "claude": AgentTemplate(
        directories=((".claude", ("skills",)),),
        files=("CLAUDE.md",),
        mappings=((".claude/skills", "../shared-skills/claude"),),
    ),
}


def _as_path(value: Any, field_name: str) -> Path:
    """Validate a YAML scalar as a path and expand a leading user home marker."""
    if not isinstance(value, str) or not value.strip():
        raise click.ClickException(f"`{field_name}` must be a non-empty string.")
    return Path(value).expanduser()


def _config_path(value: Any, field_name: str, config_dir: Path) -> Path:
    """Validate a YAML scalar as a path relative to the config file directory."""
    path = _as_path(value, field_name)
    if path.is_absolute():
        return path
    return (config_dir / path).resolve()


def _relative_path(value: Any, field_name: str) -> Path:
    """Validate a YAML scalar as a relative path."""
    path = _as_path(value, field_name)
    if path.is_absolute():
        raise click.ClickException(f"`{field_name}` must be relative: {value}")
    return path


def _flatten_directories(items: Any) -> tuple[Path, ...]:
    """Normalize directory entries into a deduplicated tuple of relative paths."""
    if items is None:
        return ()
    if not isinstance(items, list):
        raise click.ClickException("`setup.directories` must be a list.")

    directories: list[Path] = []
    for item in items:
        if isinstance(item, str):
            directories.append(_relative_path(item, "setup.directories[]"))
            continue

        if not isinstance(item, dict):
            raise click.ClickException(
                "`setup.directories` entries must be strings or mappings."
            )

        for parent, children in item.items():
            parent_path = _relative_path(parent, "setup.directories[]")
            directories.append(parent_path)
            if children is None:
                continue
            if not isinstance(children, list):
                raise click.ClickException(
                    f"`setup.directories.{parent}` must be a list."
                )
            for child in children:
                directories.append(
                    parent_path / _relative_path(child, f"setup.directories.{parent}[]")
                )

    return tuple(dict.fromkeys(directories))


def _flatten_files(items: Any) -> tuple[Path, ...]:
    """Normalize file entries into a tuple of relative paths."""
    if items is None:
        return ()
    if not isinstance(items, list):
        raise click.ClickException("`setup.files` must be a list.")
    return tuple(_relative_path(item, "setup.files[]") for item in items)


def _flatten_mappings(
    items: Any,
    config_dir: Path,
) -> tuple[tuple[Path, Path], ...]:
    """Normalize explicit destination-to-source mapping entries."""
    if items is None:
        return ()

    raw_mappings: list[tuple[Any, Any]]
    if isinstance(items, dict):
        raw_mappings = list(items.items())
    elif isinstance(items, list):
        raw_mappings = []
        for item in items:
            if not isinstance(item, dict):
                raise click.ClickException("`setup.mappings` entries must be mappings.")
            raw_mappings.extend(item.items())
    else:
        raise click.ClickException("`setup.mappings` must be a mapping or list.")

    mappings: list[tuple[Path, Path]] = []
    for destination, source in raw_mappings:
        mappings.append(
            (
                _relative_path(destination, "setup.mappings destination"),
                _config_path(source, "setup.mappings source", config_dir),
            )
        )
    return tuple(mappings)


def load_plan(config_path: Path) -> CopyPlan:
    """Load and validate a YAML configuration file as a copy plan."""
    config_path = config_path.expanduser().resolve()
    config_dir = config_path.parent

    try:
        with config_path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream) or {}
    except FileNotFoundError as exc:
        raise click.ClickException(f"Configuration file not found: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise click.ClickException(f"Invalid YAML in {config_path}: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("setup"), dict):
        raise click.ClickException("Configuration must contain a `setup` mapping.")

    setup = data["setup"]
    return CopyPlan(
        source_root=_config_path(setup.get("source"), "setup.source", config_dir),
        destination_root=_config_path(
            setup.get("destination"),
            "setup.destination",
            config_dir,
        ),
        directories=_flatten_directories(setup.get("directories")),
        files=_flatten_files(setup.get("files")),
        mappings=_flatten_mappings(setup.get("mappings"), config_dir),
    )


def _copy_directory(
    source: Path,
    destination: Path,
    *,
    dry_run: bool,
    strict: bool,
) -> None:
    """Copy a directory tree, optionally skipping or failing on missing sources."""
    if not source.is_dir():
        message = f"Directory not found: {source}"
        if strict:
            raise click.ClickException(message)
        click.echo(f"Skipping {message}")
        return

    click.echo(f"Copy directory {source} -> {destination}")
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True)


def _copy_file(
    source: Path,
    destination: Path,
    *,
    dry_run: bool,
    strict: bool,
) -> None:
    """Copy a single file, optionally skipping or failing on missing sources."""
    if not source.is_file():
        message = f"File not found: {source}"
        if strict:
            raise click.ClickException(message)
        click.echo(f"Skipping {message}")
        return

    click.echo(f"Copy file {source} -> {destination}")
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_path(
    source: Path,
    destination: Path,
    *,
    dry_run: bool,
    strict: bool,
) -> None:
    """Copy a source path as either a directory or file based on its type."""
    if source.is_dir():
        _copy_directory(source, destination, dry_run=dry_run, strict=strict)
    else:
        _copy_file(source, destination, dry_run=dry_run, strict=strict)


def _copy_operations(plan: CopyPlan) -> tuple[CopyOperation, ...]:
    """Resolve plan entries into ordered copy operations."""
    operations: list[CopyOperation] = []
    mapping_sources = dict(plan.mappings)
    copied_mappings: set[Path] = set()

    for directory in plan.directories:
        source = mapping_sources.get(directory, plan.source_root / directory)
        if directory in mapping_sources:
            copied_mappings.add(directory)
        operations.append(CopyOperation(source, plan.destination_root / directory))

    for file_path in plan.files:
        source = mapping_sources.get(file_path, plan.source_root / file_path)
        if file_path in mapping_sources:
            copied_mappings.add(file_path)
        operations.append(CopyOperation(source, plan.destination_root / file_path))

    for destination, source in plan.mappings:
        if destination not in copied_mappings:
            operations.append(CopyOperation(source, plan.destination_root / destination))

    return tuple(operations)


def execute_plan(plan: CopyPlan, *, dry_run: bool = False, strict: bool = False) -> None:
    """Copy all configured paths from a loaded plan into the destination root."""
    destination_root = plan.destination_root
    if dry_run:
        click.echo("Dry run: no files will be changed.")
    else:
        destination_root.mkdir(parents=True, exist_ok=True)

    for operation in _copy_operations(plan):
        _copy_path(
            operation.source,
            operation.destination,
            dry_run=dry_run,
            strict=strict,
        )


class SetupWorktreeGroup(click.Group):
    """Route unknown top-level arguments to the copy command for compatibility."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Treat `setup-worktree config.yml` as `setup-worktree copy config.yml`."""
        if args:
            first_arg = args[0]
            if first_arg not in self.commands and first_arg not in ("-h", "--help"):
                args = ["copy", *args]
        return super().parse_args(ctx, args)


def _resolve_config_path(
    config_path: Path | None,
    config_option: Path | None,
    path_option: Path | None,
) -> Path:
    """Resolve positional and option-style config inputs into one path."""
    configured_paths = [
        path for path in (config_path, config_option, path_option) if path is not None
    ]
    if len(configured_paths) > 1:
        raise click.ClickException("Provide only one config path.")

    return configured_paths[0] if configured_paths else Path("tree-setup.yml")


def _selected_agents(agents: tuple[str, ...]) -> tuple[str, ...]:
    """Normalize requested template agents into a stable, deduplicated tuple."""
    if not agents or "all" in agents:
        return AGENT_ORDER

    selected = tuple(agent for agent in AGENT_ORDER if agent in agents)
    if not selected:
        raise click.ClickException("Select at least one supported agent.")
    return selected


def _template_spec(agents: tuple[str, ...]) -> AgentTemplate:
    """Merge selected agent templates into one renderable template."""
    directories: list[DirectoryTemplate] = []
    files: list[str] = []
    mappings: list[tuple[str, str]] = []

    for agent in agents:
        template = AGENT_TEMPLATES[agent]
        directories.extend(template.directories)
        files.extend(template.files)
        mappings.extend(template.mappings)

    files.extend(COMMON_TEMPLATE_FILES)
    return AgentTemplate(
        directories=tuple(dict.fromkeys(directories)),
        files=tuple(dict.fromkeys(files)),
        mappings=tuple(dict.fromkeys(mappings)),
    )


def _render_template(agents: tuple[str, ...]) -> str:
    """Render a starter YAML configuration for the selected agents."""
    template = _template_spec(agents)
    lines = [
        "setup:",
        '  source: "../main-checkout"',
        '  destination: "../new-worktree"',
        "",
        "  directories:",
    ]

    for directory in template.directories:
        if isinstance(directory, str):
            lines.append(f'    - "{directory}"')
            continue

        parent, children = directory
        lines.append(f'    - "{parent}":')
        for child in children:
            lines.append(f'        - "{child}"')

    lines.extend(["", "  files:"])
    for file_path in template.files:
        lines.append(f'    - "{file_path}"')

    lines.extend(["", "  mappings:"])
    for destination, source in template.mappings:
        lines.append(f'    - "{destination}": "{source}"')

    return "\n".join(lines) + "\n"


def write_template(output: Path, agents: tuple[str, ...], *, force: bool) -> None:
    """Write a starter YAML configuration file for the selected agents."""
    output = output.expanduser()
    if output.exists() and not force:
        raise click.ClickException(f"Template already exists: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_render_template(agents), encoding="utf-8")
    click.echo(f"Wrote template {output}")


@click.group(
    cls=SetupWorktreeGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
)
def run() -> None:
    """Copy worktree setup files and create starter configuration templates."""


@run.command()
@click.argument(
    "config_path",
    type=click.Path(path_type=Path, dir_okay=False, exists=False),
    required=False,
)
@click.option(
    "-c",
    "--config",
    "config_option",
    type=click.Path(path_type=Path, dir_okay=False, exists=False),
    help="Path to the YAML configuration file.",
)
@click.option(
    "--path",
    "path_option",
    type=click.Path(path_type=Path, dir_okay=False, exists=False),
    help="Alias for --config.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print planned copies without changing the destination.",
)
@click.option(
    "--strict",
    is_flag=True,
    help="Fail when a configured source path is missing instead of skipping it.",
)
def copy(
    config_path: Path | None,
    config_option: Path | None,
    path_option: Path | None,
    dry_run: bool,
    strict: bool,
) -> None:
    """Copy configured files and directories into a worktree."""
    plan = load_plan(_resolve_config_path(config_path, config_option, path_option))
    execute_plan(plan, dry_run=dry_run, strict=strict)


@run.command()
@click.option(
    "--agent",
    "agents",
    multiple=True,
    type=click.Choice(AGENT_CHOICES, case_sensitive=False),
    help="Agent config to include. Repeat for multiple agents.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    default=Path("tree-setup.yml"),
    show_default=True,
    help="Path to write the starter YAML file.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite the output file if it already exists.",
)
def init(agents: tuple[str, ...], output: Path, force: bool) -> None:
    """Create a starter YAML configuration file."""
    write_template(output, _selected_agents(agents), force=force)


if __name__ == "__main__":
    run()
