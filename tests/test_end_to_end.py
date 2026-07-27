from __future__ import annotations

import json
from pathlib import Path

from creator_skill.project import CreatorProject

FIXTURES = Path(__file__).parent / "fixtures" / "videos"


class FixtureOpenKB:
    """Test double for OpenKB's public CLI contract."""

    def compile(self, kb_dir, source_dir, name, intent):
        (kb_dir / ".openkb").mkdir(parents=True, exist_ok=True)
        wiki = kb_dir / "wiki"
        wiki.mkdir(exist_ok=True)
        for source in source_dir.glob("*.md"):
            (wiki / source.name).write_text(source.read_text())
        skill = kb_dir / "output" / "skills" / name
        references = skill / "references"
        references.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            "description: Applies the creator's documented method when users ask "
            "for campaign analysis, scaling, testing, or creative decisions.\n"
            "---\n\n"
            "# Procedure\n\n"
            "Read references/methodology.md. Separate sourced claims from inference, "
            "cite the video and timestamp, show contradictions, and never speak on "
            "behalf of the creator.\n"
        )
        references.joinpath("methodology.md").write_text(
            "\n\n".join(path.read_text() for path in sorted(source_dir.glob("*.md")))
        )
        return skill

    def validate(self, kb_dir, name):
        assert (kb_dir / "output" / "skills" / name / "SKILL.md").exists()

    def evaluate(self, kb_dir, name):
        assert (kb_dir / "wiki").exists()


def test_three_local_video_results_complete_the_pipeline(tmp_path):
    project = CreatorProject(tmp_path / "workspaces", "meta-ads-expert")
    project.pipeline.openkb = FixtureOpenKB()
    project.pipeline.openai_validator = None
    report = project.build(
        "https://www.tiktok.com/@demo",
        "Aplicar la metodología documentada del creador",
        max_videos=3,
        batch_size=2,
        fixture_dir=FIXTURES,
    )
    assert report["videos_discovered"] == 3
    assert report["videos_processed"] == 3
    assert report["validation"]["agent_skills"] == "passed"
    assert len(list(project.paths.sources.glob("*.md"))) == 3
    assert len(list((project.paths.kb / "wiki").glob("*.md"))) == 3
    assert Path(report["exports"]["zip"]).exists()
    state = json.loads(project.paths.state.read_text())
    assert all(video["status"] == "completed" for video in state["videos"].values())

    project.pipeline.openkb = FixtureOpenKB()
    second = project.update(FIXTURES)
    assert second["videos_processed"] == 3
    assert project.state.load()["skill_version"] == 2

