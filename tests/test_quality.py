import json
import math
import sys
from types import SimpleNamespace

import pytest

from creator_skill.quality import assess, fingerprint, review_for
from creator_skill.skill_ads_metrics import calculate
from creator_skill.visual import sample_times
from creator_skill.storage import atomic_json
from creator_skill.errors import ValidationError


def test_recognition_preserves_real_boundaries_and_uncertainty(monkeypatch):
    from creator_skill import fast_transcriber as module
    calls = {}
    class Model:
        def __init__(self, *a, **kw):
            pass
        def transcribe(self, source, **kwargs):
            calls.update(kwargs)
            return iter([SimpleNamespace(start=.35, end=1.78, text=" treinta por ciento ",
                avg_logprob=-1.3, no_speech_prob=.1, compression_ratio=1.2,
                words=[SimpleNamespace(start=.35, end=.7, word=" treinta", probability=.4)])]), SimpleNamespace(
                    language="es", language_probability=.99, duration=2, duration_after_vad=1.8)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    monkeypatch.setattr(module, "_MODELS", {})
    result = module.transcribe_detailed("sample.wav", "base", "es")
    assert result["segments"][0]["start"] == .35
    assert result["segments"][0]["end"] == 1.78
    assert result["segments"][0]["words"][0]["probability"] == .4
    assert calls["word_timestamps"] and calls["beam_size"] == 5
    assert result["recognition"]["reviewed"] is False
    flags = assess(result["segments"])["flags"]
    assert {f["code"] for f in flags} >= {"asr_uncertainty", "numbers_to_check"}


def test_quality_does_not_turn_silence_or_absence_of_warnings_into_verification():
    result = assess([{"start": 0, "end": 10, "text": "Palabras normales " * 20}])
    assert not result["audio_verified"] and not result["visual_verified"]
    assert result["status"] == "unreviewed"
    broken = assess([{"start": float("nan"), "end": 0, "text": "Número 50"}])
    assert broken["status"] == "needs_review"


def test_sample_covers_full_long_video_and_stays_inside_short_one():
    times = sample_times(1200)
    assert len(times) == 40 and times[0] == 0 and times[-1] >= 1160
    assert all(0 <= t < 1200 for t in times)
    assert sample_times(.5) == [0]


def test_exact_duplicates_and_stale_editorial_review():
    assert fingerprint([{"text": "¡MÉTRICAS, de ventas!"}]) == fingerprint([{"text": "metricas de ventas"}])
    assert fingerprint([{"text": "no escales"}]) != fingerprint([{"text": "escales"}])
    assert review_for({"id": "v", "source_hash": "new"}, {"v": {"source_hash": "old", "decision": "selected"}})["status"] == "stale"


@pytest.mark.parametrize("interval", [(1, 900), (-1, 3), (1, float("inf")), (float("nan"), 4), (5, 6)])
def test_curation_rejects_outside_and_nonfinite_times(tmp_path, interval):
    from creator_skill.curation import publish
    atomic_json(tmp_path / "knowledge.json", {"name": "Ads", "videos": [{"id": "v", "source_hash": "h",
        "segments": [{"start": 1, "end": 5}]}]})
    atomic_json(tmp_path / "curated.json", {"reviewed_at": "2026-10-05", "insights": [{
        "title": "Idea", "principle": "Principio", "when": "Contexto", "steps": ["Acción"], "limits": "Límite",
        "evidence": [{"video": "v", "start": interval[0], "end": interval[1]}]}]})
    with pytest.raises(ValidationError, match="intervalo"):
        publish(tmp_path)
    assert not (tmp_path / "skill/references/criterios-curados.md").exists()


def test_search_separates_selected_from_pending_and_crossposts(tmp_path):
    from creator_skill.skill_search import search
    index = []
    for key, person, duplicate, review in [("a", "Ana", None, {"decision": "selected", "status": "text_reviewed"}),
            ("b", "Beto", "a", {}), ("c", "Ceci", None, {"decision": "selected", "status": "stale"})]:
        path = tmp_path / f"references/videos/{key}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("### s0\n\nventas útiles\n\n[Ver fuente](https://example.com)", encoding="utf-8")
        index.append({"id": key, "title": "Ventas", "person": person, "url": "https://example.com", "reference": f"references/videos/{key}.md", "duplicate_of": duplicate, "review": review})
    atomic_json(tmp_path / "references/index.json", index)
    assert search(tmp_path, "ventas", reviewed_only=True)["total"] == 1
    assert search(tmp_path, "ventas")["total"] == 2
    assert search(tmp_path, "ventas", person="Beto")["total"] == 1
    assert search(tmp_path, "ventas", include_duplicates=True)["total"] == 3


def cohort(**kwargs):
    return {"same_cohort": True, "cohort_mature": True, "currency": "PEN", "period": "test",
            "spend": 300, "conversations": 100, "sales": 3, "net_revenue": 600, "variable_costs": 360} | kwargs


def test_cheaper_chats_can_have_worse_business_results():
    a = calculate(cohort())
    b = calculate(cohort(spend=300, conversations=50, sales=6, net_revenue=1200, variable_costs=720))
    assert a["cost_per_conversation"] == 3 < b["cost_per_conversation"]
    assert a["cost_per_sale"] == 100 > b["cost_per_sale"] == 50
    assert a["contribution_after_ads"] == -60 < b["contribution_after_ads"] == 180


def test_no_sales_or_spend_never_produce_a_fake_zero_cpa_or_roas():
    result = calculate(cohort(sales=0, net_revenue=0, variable_costs=0))
    assert result["cost_per_sale"] is None and result["conversation_to_sale_rate"] == 0
    assert result["contribution_after_ads"] == -300
    assert calculate(cohort(spend=0))["roas"] is None


@pytest.mark.parametrize("changes", [{"same_cohort": False}, {"sales": 1.5}, {"spend": math.nan},
    {"spend": -1}, {"spend": True}, {"sales": 101}, {"currency": ""}])
def test_cohort_calculator_rejects_incomparable_or_invalid_inputs(changes):
    with pytest.raises(ValueError):
        calculate(cohort(**changes))


def test_streamed_download_obeys_timeout():
    import subprocess
    from creator_skill.process import CommandRunner
    with pytest.raises(subprocess.TimeoutExpired):
        CommandRunner().run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=.2, on_output=lambda *a: None)


def test_backfill_stops_when_a_successful_job_does_not_advance(tmp_path, monkeypatch):
    from creator_skill import backfill
    source = {"id": "a", "project": "a", "category": "ads", "enabled": True}
    library = SimpleNamespace(root=tmp_path, load=lambda: {"sources": [source], "settings": {"enabled": True, "process_limit": 10}})
    status = {"pending": 50, "completed": 5}
    monkeypatch.setattr(backfill, "ContentProject", lambda *a, **k: SimpleNamespace(status=lambda: status))
    calls = []
    class Jobs:
        def __init__(self, root):
            pass
        def start(self, action, payload):
            calls.append(payload)
            return "job"
        def get(self, key):
            return {"status": "completed"}
    monkeypatch.setattr(backfill, "JobStore", Jobs)
    monkeypatch.setattr(backfill.shutil, "disk_usage", lambda p: SimpleNamespace(free=10*1024**3))
    result = backfill.run(library)
    assert result["status"] == "stopped_no_progress"
    assert len(calls) == 1 and calls[0]["count"] == 10


def test_sync_keeps_collection_results_when_export_is_busy(tmp_path, monkeypatch):
    from creator_skill.library import Library
    from creator_skill.knowledge import KnowledgeBuilder
    from creator_skill.errors import CreatorSkillError
    library = Library(tmp_path / "workspaces")
    def busy(*args):
        raise CreatorSkillError("Ya hay una tarea trabajando en este proyecto.")
    monkeypatch.setattr(KnowledgeBuilder, "build_all", busy)
    report = library.run()
    assert report["knowledge_status"] == "deferred"
    assert json.loads((library.root / ".creator-md/last-sync.json").read_text())["knowledge_status"] == "deferred"


def test_visual_context_does_not_replace_speech_and_preserves_failure(tmp_path, monkeypatch):
    from creator_skill import visual
    from creator_skill.video_runner import SummarizeAdapter
    from creator_skill.models import Video
    adapter = SummarizeAdapter(None)
    original = {"segments": [{"start": 1, "end": 3, "text": "Mira la tabla en pantalla"}], "method": "youtube_captions"}
    monkeypatch.setattr(visual, "extract_visual", lambda *a, **k: {"segments": [{"start": 2, "end": 2.04, "text": "OCR: 30%"}], "visual_coverage": {"kind": "sampled_frames"}})
    result = adapter._visual_context(dict(original), Video("a", "https://example.com"), tmp_path)
    assert result["segments"] == original["segments"] and result["method"] == "youtube_captions"
    assert result["visual_notes"][0]["text"] == "OCR: 30%"
    def unavailable(*args, **kwargs):
        raise RuntimeError("HTTP 403")
    monkeypatch.setattr(visual, "extract_visual", unavailable)
    result = adapter._visual_context(dict(original), Video("a", "https://example.com"), tmp_path)
    assert result["segments"] == original["segments"] and "403" in result["visual_error"]
    monkeypatch.setenv("CREATOR_MD_VISUAL_CONTEXT", "0")
    assert "visual_error" not in adapter._visual_context(dict(original), Video("a", "https://example.com"), tmp_path)


def test_changing_model_preserves_schedule_limits_and_spending_policy(tmp_path):
    from creator_skill.library import Library
    library = Library(tmp_path / "workspaces")
    library.update_settings({"enabled": True, "interval_hours": 12, "process_limit": 7, "allow_paid": False})
    settings = library.update_settings({"model": "small"})
    assert settings == {"enabled": True, "interval_hours": 12, "process_limit": 7, "allow_paid": False, "model": "small"}
    settings = library.update_settings({"enabled": False})
    assert settings["enabled"] is False and settings["model"] == "small"
