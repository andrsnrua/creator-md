import json
import sys
import zipfile
from pathlib import Path

import pytest

from creator_skill.errors import ExternalCommandError, ValidationError
from creator_skill.process import CommandRunner
from creator_skill.skill_pipeline import SkillPipeline, validate_agent_skill


class FakeOpenKB:
    def validate(self, kb_dir, name):
        return None

    def evaluate(self, kb_dir, name):
        return None


def create_skill(root: Path, name: str = "demo-skill") -> Path:
    skill = root / name
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: Applies cited creator knowledge when users ask for its method.\n"
        "---\n\n"
        "# Workflow\n\n"
        "Read references/methodology.md and cite the source URL and timestamp.\n"
    )
    (skill / "references" / "methodology.md").write_text("# Method\n")
    return skill


def test_command_runner_audits_and_raises(tmp_path):
    audit = tmp_path / "commands.jsonl"
    runner = CommandRunner(audit)
    result = runner.run([sys.executable, "-c", "print('ok')"])
    assert result.stdout.strip() == "ok"
    record = json.loads(audit.read_text().splitlines()[0])
    assert record["returncode"] == 0
    with pytest.raises(ExternalCommandError):
        runner.run([sys.executable, "-c", "raise SystemExit(3)"])


def test_agent_skill_validation(tmp_path):
    skill = create_skill(tmp_path)
    assert validate_agent_skill(skill) == []
    (skill / "SKILL.md").write_text("---\nname: Wrong\n---\n")
    assert len(validate_agent_skill(skill)) >= 2


def test_export_zip_and_skill_packages(tmp_path):
    skill = create_skill(tmp_path)
    pipeline = SkillPipeline(CommandRunner(), FakeOpenKB())
    exports = pipeline.export(skill, tmp_path / "exports")
    for key in ("zip", "skill"):
        path = Path(exports[key])
        assert path.exists()
        with zipfile.ZipFile(path) as archive:
            assert "demo-skill/SKILL.md" in archive.namelist()


def test_validation_failure_is_reported(tmp_path):
    skill = tmp_path / "bad"
    skill.mkdir()
    pipeline = SkillPipeline(CommandRunner(), FakeOpenKB())
    with pytest.raises(ValidationError):
        pipeline.validate(tmp_path, "bad", skill)

