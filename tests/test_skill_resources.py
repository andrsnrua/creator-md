import pytest

from creator_skill import knowledge
from creator_skill.errors import ValidationError
from creator_skill.knowledge import KnowledgeBuilder
from creator_skill.library import Library


def maintained_resources(tmp_path, monkeypatch):
    resource_root = tmp_path / "maintained"
    ads = resource_root / "ads"
    (ads / "references/negocios").mkdir(parents=True)
    (ads / "agents").mkdir()
    (ads / "scripts").mkdir()
    (ads / "SKILL.md").write_text("---\nname: ads-evidence\ndescription: Ads con contexto\n---\n", encoding="utf-8")
    (ads / "references/negocios/locales.md").write_text("Medir citas atendidas.", encoding="utf-8")
    (ads / "agents/openai.yaml").write_text("interface:\n  display_name: Ads\n", encoding="utf-8")
    (ads / "scripts/brief.py").write_text("print('brief')\n", encoding="utf-8")
    monkeypatch.setattr(knowledge, "SKILL_RESOURCES", resource_root)
    return ads


def test_ads_build_keeps_maintained_resources_and_editorial_evidence(tmp_path, monkeypatch):
    maintained = maintained_resources(tmp_path, monkeypatch)
    lib = Library(tmp_path / "workspaces")
    lib.add_area({"name": "Ads"})
    builder = KnowledgeBuilder(lib)
    output = builder.output("ads")
    (output / "skill/references").mkdir(parents=True)
    curated = output / "skill/references/criterios-curados.md"
    curated.write_text("Criterio revisado por la biblioteca", encoding="utf-8")
    curation = output / "curated.json"
    curation.write_text('{"insights": []}\n', encoding="utf-8")
    before_curation = curation.read_bytes()

    for _ in range(2):
        builder.build("ads")
        assert (output / "skill/SKILL.md").read_bytes() == (maintained / "SKILL.md").read_bytes()
        assert (output / "skill/references/negocios/locales.md").read_text(encoding="utf-8") == "Medir citas atendidas."
        assert (output / "skill/agents/openai.yaml").exists()
        assert (output / "skill/scripts/brief.py").exists()
        assert (output / "skill/scripts/search_evidence.py").exists()
        assert (output / "skill/scripts/ads_metrics.py").exists()
        assert (output / "skill/references/procedimientos-ads.md").exists()
        assert curated.read_text(encoding="utf-8") == "Criterio revisado por la biblioteca"
        assert curation.read_bytes() == before_curation
        (output / "skill/SKILL.md").write_text("Edición derivada accidental", encoding="utf-8")


def test_ads_resources_do_not_change_other_areas(tmp_path, monkeypatch):
    maintained_resources(tmp_path, monkeypatch)
    lib = Library(tmp_path / "workspaces")
    area = lib.add_area({"name": "Diseño"})["id"]
    builder = KnowledgeBuilder(lib)
    builder.build(area)
    output = builder.output(area) / "skill"
    assert "name: diseno-evidence" in (output / "SKILL.md").read_text(encoding="utf-8")
    assert not (output / "agents/openai.yaml").exists()
    assert not (output / "references/negocios/locales.md").exists()
    assert not (output / "scripts/ads_metrics.py").exists()


@pytest.mark.parametrize("relative", [
    "references/criterios-curados.md", "references/index.json", "references/catalogo.md",
    "references/videos/video.md", "references/quality/frame.md", "scripts/search_evidence.py",
    "scripts/ads_metrics.py", "references/CRITERIOS-CURADOS.md",
])
def test_resources_cannot_overwrite_generated_evidence(tmp_path, monkeypatch, relative):
    maintained = maintained_resources(tmp_path, monkeypatch)
    forbidden = maintained / relative
    forbidden.parent.mkdir(parents=True, exist_ok=True)
    forbidden.write_text("No debe publicarse", encoding="utf-8")
    output = tmp_path / "Ads"
    (output / "skill").mkdir(parents=True)
    entrypoint = output / "skill/SKILL.md"
    entrypoint.write_text("Versión anterior", encoding="utf-8")
    with pytest.raises(ValidationError, match="reservado"):
        knowledge._copy_ads_resources(output)
    assert entrypoint.read_text(encoding="utf-8") == "Versión anterior"
    assert not (output / "skill" / relative).exists()


def test_resource_copy_ignores_runtime_files(tmp_path, monkeypatch):
    maintained = maintained_resources(tmp_path, monkeypatch)
    (maintained / "scripts/__pycache__").mkdir()
    for relative in ("scripts/__pycache__/brief.pyc", "references/draft.tmp", ".build.lock"):
        (maintained / relative).write_bytes(b"\xff")
    copied = knowledge._copy_ads_resources(tmp_path / "Ads")
    assert "SKILL.md" in copied
    assert not any("__pycache__" in p or p.endswith((".tmp", ".lock")) for p in copied)
