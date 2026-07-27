from __future__ import annotations

import json
import os
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .errors import ValidationError
from .process import CommandRunner


def validate_agent_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return ["SKILL.md is missing"]
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return ["SKILL.md must contain YAML frontmatter"]
    frontmatter = text.split("---", 2)[1]
    values: dict[str, str] = {}
    for line in frontmatter.splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip("\"'")
    name = values.get("name", "")
    description = values.get("description", "")
    if name != skill_dir.name:
        errors.append("frontmatter name must match the skill directory")
    if (
        not name
        or len(name) > 64
        or name.startswith("-")
        or name.endswith("-")
        or "--" in name
        or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in name)
    ):
        errors.append("name must follow the Agent Skills naming rules")
    if not description or len(description) > 1024:
        errors.append("description must contain 1-1024 characters")
    if len(text.splitlines()) > 500:
        errors.append("SKILL.md must stay at or below 500 lines")
    return errors


class OpenKBAdapter:
    def __init__(self, runner: CommandRunner, executable: str = "openkb"):
        self.runner = runner
        self.executable = executable

    def compile(
        self, kb_dir: Path, source_dir: Path, name: str, intent: str
    ) -> Path:
        kb_dir.mkdir(parents=True, exist_ok=True)
        if not (kb_dir / ".openkb").exists():
            self.runner.run([self.executable, "init"], cwd=kb_dir)
        self.runner.run([self.executable, "add", str(source_dir.resolve())], cwd=kb_dir)
        self.runner.run(
            [self.executable, "skill", "new", name, intent], cwd=kb_dir
        )
        return kb_dir / "output" / "skills" / name

    def validate(self, kb_dir: Path, name: str) -> None:
        self.runner.run(
            [self.executable, "skill", "validate", name], cwd=kb_dir
        )

    def evaluate(self, kb_dir: Path, name: str) -> None:
        self.runner.run([self.executable, "skill", "eval", name], cwd=kb_dir)


class SkillPipeline:
    def __init__(
        self,
        runner: CommandRunner,
        openkb: OpenKBAdapter,
        openai_validator: Path | None = None,
        anthropic_packager: Path | None = None,
    ):
        self.runner = runner
        self.openkb = openkb
        self.openai_validator = openai_validator
        self.anthropic_packager = anthropic_packager

    def validate(self, kb_dir: Path, name: str, skill_dir: Path) -> dict:
        self.openkb.validate(kb_dir, name)
        errors = validate_agent_skill(skill_dir)
        if errors:
            raise ValidationError("; ".join(errors))
        official = "unavailable"
        if self.openai_validator and self.openai_validator.exists():
            self.runner.run([sys.executable, str(self.openai_validator), str(skill_dir)])
            official = "passed"
        return {
            "openkb": "passed",
            "agent_skills": "passed",
            "openai": official,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def evaluate(self, kb_dir: Path, name: str) -> dict:
        self.openkb.evaluate(kb_dir, name)
        return {"openkb": "completed", "timestamp": datetime.now(UTC).isoformat()}

    def export(self, skill_dir: Path, export_dir: Path) -> dict:
        export_dir.mkdir(parents=True, exist_ok=True)
        universal = export_dir / skill_dir.name
        if universal.exists():
            shutil.rmtree(universal)
        shutil.copytree(skill_dir, universal)
        zip_path = export_dir / f"{skill_dir.name}.zip"
        skill_path = export_dir / f"{skill_dir.name}.skill"
        for archive in (zip_path, skill_path):
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(skill_dir.rglob("*")):
                    if path.is_file():
                        bundle.write(path, Path(skill_dir.name) / path.relative_to(skill_dir))
        anthropic = "unavailable"
        if self.anthropic_packager and self.anthropic_packager.exists():
            self.runner.run(
                [
                    sys.executable,
                    str(self.anthropic_packager),
                    str(skill_dir),
                    str(export_dir),
                ]
            )
            anthropic = "completed"
        return {
            "universal": str(universal),
            "zip": str(zip_path),
            "skill": str(skill_path),
            "anthropic_packager": anthropic,
        }


def discover_openai_validator() -> Path | None:
    override = os.environ.get("CREATOR_SKILL_OPENAI_VALIDATOR")
    candidates = [
        Path(override) if override else None,
        Path.home()
        / ".codex/skills/.system/skill-creator/scripts/quick_validate.py",
    ]
    return next((path for path in candidates if path and path.exists()), None)


def discover_anthropic_packager() -> Path | None:
    override = os.environ.get("CREATOR_SKILL_ANTHROPIC_PACKAGER")
    candidates = [
        Path(override) if override else None,
        Path.home() / ".claude/skills/skill-creator/scripts/package_skill.py",
    ]
    return next((path for path in candidates if path and path.exists()), None)


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")

