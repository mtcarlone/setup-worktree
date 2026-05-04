import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from click.testing import CliRunner

from setup_worktree.cli import load_plan, run


class LoadPlanTests(unittest.TestCase):
    def test_loads_example_shape(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            resolved_root = root.resolve()
            config = root / "tree-setup.yml"
            config.write_text(
                """
setup:
  source: "./source"
  destination: "./destination"
  directories:
    - "specs"
    - ".agents":
        - "skills"
  files:
    - ".gitignore"
  mappings:
    - ".agents/skills": "./shared/skills"
""",
                encoding="utf-8",
            )

            plan = load_plan(config)

            self.assertEqual(plan.source_root, resolved_root / "source")
            self.assertEqual(plan.destination_root, resolved_root / "destination")
            self.assertEqual(
                plan.directories,
                (Path("specs"), Path(".agents"), Path(".agents/skills")),
            )
            self.assertEqual(plan.files, (Path(".gitignore"),))
            self.assertEqual(
                plan.mappings,
                ((Path(".agents/skills"), resolved_root / "shared" / "skills"),),
            )


class RunTests(unittest.TestCase):
    def test_copies_configured_paths_and_mappings(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            destination = root / "destination"
            shared = root / "shared" / "skills"
            config = root / "tree-setup.yml"

            (source / "specs").mkdir(parents=True)
            (source / ".agents").mkdir()
            (source / "specs" / "note.md").write_text("spec", encoding="utf-8")
            (source / "AGENTS.md").write_text("agents", encoding="utf-8")
            shared.mkdir(parents=True)
            (shared / "skill.md").write_text("skill", encoding="utf-8")
            config.write_text(
                f"""
setup:
  source: "{source}"
  destination: "{destination}"
  directories:
    - "specs"
    - ".agents":
        - "skills"
  files:
    - "AGENTS.md"
  mappings:
    - ".agents/skills": "{shared}"
""",
                encoding="utf-8",
            )

            result = CliRunner().invoke(run, [str(config)])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(
                (destination / "specs" / "note.md").read_text(encoding="utf-8"),
                "spec",
            )
            self.assertEqual(
                (destination / "AGENTS.md").read_text(encoding="utf-8"),
                "agents",
            )
            self.assertEqual(
                (destination / ".agents" / "skills" / "skill.md").read_text(
                    encoding="utf-8"
                ),
                "skill",
            )

    def test_missing_source_skips_by_default_and_fails_in_strict_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            destination = root / "destination"
            config = root / "tree-setup.yml"

            source.mkdir()
            config.write_text(
                f"""
setup:
  source: "{source}"
  destination: "{destination}"
  files:
    - "missing.env"
""",
                encoding="utf-8",
            )

            default_result = CliRunner().invoke(run, [str(config)])

            self.assertEqual(default_result.exit_code, 0, default_result.output)
            self.assertIn("Skipping File not found:", default_result.output)

            strict_result = CliRunner().invoke(run, [str(config), "--strict"])

            self.assertNotEqual(strict_result.exit_code, 0)
            self.assertIn("Error: File not found:", strict_result.output)


if __name__ == "__main__":
    unittest.main()
