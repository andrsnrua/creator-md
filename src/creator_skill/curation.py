"""Publish human/agent-reviewed insight records only when their evidence is present."""
from __future__ import annotations
import json
import math
import hashlib
from pathlib import Path
from .errors import ValidationError
from .knowledge import stamp, evidence_url
from .storage import atomic_json, atomic_text, file_lock
from .quality import read_reviews, review_for


def publish(output: Path) -> dict:
    with file_lock(output / ".build.lock"):
        return _publish(output)


def _publish(output: Path) -> dict:
    knowledge = json.loads((output / "knowledge.json").read_text(encoding="utf-8"))
    curated = json.loads((output / "curated.json").read_text(encoding="utf-8"))
    videos = {c["id"]: c for c in knowledge["videos"]}
    reviews = read_reviews(output)
    library_root = output.parent / "workspaces"
    library_path = library_root / ".creator-md/library.json"
    sources = {s["id"]: s for s in json.loads(library_path.read_text(encoding="utf-8"))["sources"]} if library_path.exists() else {}
    lines = [f"# Criterios revisados · {knowledge['name']}", "", f"Revisión: {curated['reviewed_at']}", "",
             "Síntesis editorial de evidencia. No demuestra causalidad ni garantiza resultados. Las propuestas de aplicación son de esta biblioteca, no citas literales del creador.", ""]
    for insight in curated["insights"]:
        for key in ("title", "principle", "when", "steps", "limits", "evidence"):
            if not insight.get(key):
                raise ValidationError(f"Falta {key} en el criterio {insight.get('id')}.")
        lines += [f"## {insight['title']}", "", insight["principle"], "", "**Cuándo aplica:** " + insight["when"], "", "**Aplicación propuesta:**", ""]
        lines += [f"{i+1}. {step}" for i, step in enumerate(insight["steps"])]
        lines += ["", "**Límites y contraejemplos:** " + insight["limits"], "", "**Evidencia:**", ""]
        for evidence in insight["evidence"]:
            video = videos.get(evidence["video"])
            if not video:
                raise ValidationError("La evidencia del criterio no existe en la biblioteca.")
            start, end = evidence["start"], evidence["end"]
            intervals = [s for s in video["segments"] if isinstance(s.get("start"), (int, float))
                         and isinstance(s.get("end"), (int, float))
                         and math.isfinite(s["start"]) and math.isfinite(s["end"]) and s["start"] < s["end"]]
            if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                    or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end
                    or not intervals or start < min(s["start"] for s in intervals)
                    or end > max(s["end"] for s in intervals)
                    or not any(s["start"] < end and s["end"] > start for s in intervals)):
                raise ValidationError("El intervalo citado no existe en la transcripción.")
            previous_hash = evidence.get("source_hash")
            if previous_hash and previous_hash != video["source_hash"]:
                raise ValidationError("Cambió una transcripción citada: revisar el criterio antes de volver a publicarlo.")
            source = sources.get(video.get("source_id"))
            if source:
                raw = library_root / source["category"] / source["project"] / "raw-results" / f"{video['video_id']}.json"
                if not raw.resolve().is_relative_to(library_root.resolve()) or not raw.exists() or hashlib.sha256(raw.read_bytes()).hexdigest() != video["source_hash"]:
                    raise ValidationError("Cambió o falta el original citado; reconstruir y revisar antes de publicar.")
            review = review_for(video, reviews)
            if review.get("status") == "stale" or review.get("decision") == "excluded":
                raise ValidationError("Una evidencia fue excluida o su revisión quedó obsoleta: revisar el criterio.")
            evidence["segments"] = [s.get("id", f"s{i}") for i, s in enumerate(video["segments"])
                                    if s["start"] < end and s["end"] > start]
            evidence["review_scope"] = review.get("scope", "editorial_text_only")
            evidence["source_hash"] = video["source_hash"]
            evidence["url"] = evidence_url(video["url"], start)
            evidence["person"] = video["person"]
            lines += [f"- [{video['person']} · {stamp(start)}–{stamp(end)}]({evidence['url']}) · [transcripción](videos/{video['id']}.md)."]
        if insight.get("contradictions"):
            lines += ["", "**Diferencias y condiciones:** " + insight["contradictions"], ""]
        for official in insight.get("official", []):
            # Never turn a later editorial edit into a claim of a new web check.
            checked = official.get("checked_at")
            lines += [f"- Contraste oficial: [{official['title']}]({official['url']}) (consulta: {checked or 'sin fecha registrada; verificar vigencia'})."]
        lines.append("")
    atomic_text(output / "skill/references/criterios-curados.md", "\n".join(lines))
    atomic_json(output / "curated.json", curated)
    return {"insights": len(curated["insights"]), "reviewed_at": curated["reviewed_at"]}
