"""Transparent review signals, not an invented transcription accuracy score."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from .skill_search import folded
from .storage import atomic_json, atomic_text

NUMBERS = re.compile(r"\d|\b(?:cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|veinte|treinta|cien|ciento|mil|millones|por ciento)\b", re.I)
VISUAL = re.compile(r"\b(?:pantalla|grafico|grafica|tabla|columna|aqui ves|como puedes ver|este boton)\b")
PROMOTION = re.compile(r"\b(?:comenta|escribeme|link de mi|enlace de mi|mi curso|mi mentoria|agenda una|suscribete)\b")


def fingerprint(segments: list[dict]) -> str:
    normalized = " ".join(re.findall(r"\w+", folded(" ".join(s["text"] for s in segments))))
    return hashlib.sha256(normalized.encode()).hexdigest()


def assess(segments: list[dict], *, method: str = "automatic", duration=None) -> dict:
    flags = []
    def add(code, severity, ids, message):
        if ids:
            flags.append({"code": code, "severity": severity, "segments": ids, "message": message})
    invalid, dense, uncertain, numbers, screens, promotion = [], [], [], [], [], []
    texts = []
    for i, s in enumerate(segments):
        sid = s.get("id", f"s{i}")
        text = s.get("text", "").strip()
        texts.append(folded(text))
        start, end = s.get("start", 0), s.get("end", 0)
        valid = (isinstance(start, (int, float)) and isinstance(end, (int, float))
                 and math.isfinite(start) and math.isfinite(end) and 0 <= start < end)
        if not valid or (duration and end > duration + .5):
            invalid.append(sid)
        if valid and method != "visual_ocr" and len(text.split()) >= 8 and len(text.split()) / (end-start) > 5:
            dense.append(sid)
        # These are inspection thresholds, not calibrated correctness probabilities.
        if (s.get("avg_logprob", 0) < -1 or s.get("no_speech_prob", 0) > .6
                or s.get("compression_ratio", 0) > 2.4
                or any(w.get("probability", 1) < .5 for w in s.get("words", []))):
            uncertain.append(sid)
        if NUMBERS.search(text):
            numbers.append(sid)
        if VISUAL.search(folded(text)):
            screens.append(sid)
        if PROMOTION.search(folded(text)):
            promotion.append(sid)
    add("timing_unverified", "review", invalid, "Sin intervalo válido: no citar segundos como verificados.")
    add("dense_speech", "review", dense, "Muchas palabras por segundo: contrastar tiempos y audio; puede ser habla rápida.")
    add("asr_uncertainty", "review", uncertain, "El motor señala incertidumbre; contrastar con audio. No demuestra un error.")
    add("numbers_to_check", "context", numbers, "Comprobar cifras, unidad y condición antes de convertirlas en reglas.")
    add("screen_context", "context", screens, "La explicación puede depender de pantalla; consultar el fotograma.")
    add("promotion", "context", promotion, "Contiene invitaciones comerciales: separar promoción de explicación útil.")
    occurrences = Counter(texts)
    repeats = [str(i) for i, t in enumerate(texts) if t and len(t.split()) >= 4 and occurrences[t] >= 3]
    add("repetition", "review", [f"s{i}" for i in repeats], "Fragmentos repetidos: pueden ser énfasis o un fallo del reconocimiento.")
    if sum(len(t.split()) for t in texts) < 25:
        flags.append({"code": "short_text", "severity": "review", "segments": [], "message": "Texto muy corto: comprobar si falta contenido."})
    return {"version": 1, "status": "needs_review" if any(f["severity"] == "review" for f in flags) else "unreviewed",
            "flags": flags, "confidence_available": any("avg_logprob" in s for s in segments),
            "audio_verified": False, "visual_verified": False,
            "note": "Señales automáticas para priorizar lectura; no miden exactitud ni valor del consejo."}


def read_reviews(output: Path) -> dict:
    path = output / "quality/reviews.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("videos", {})


def review_for(card: dict, reviews: dict) -> dict:
    review = reviews.get(card["id"])
    if not review:
        return {"status": "unreviewed", "decision": "pending"}
    if review.get("source_hash") != card["source_hash"]:
        return {"status": "stale", "decision": "pending", "reason": "Cambió el original desde la revisión."}
    return review


def write_report(output: Path, cards: list[dict], generated_at: str) -> dict:
    counts = Counter(f["code"] for c in cards for f in c.get("quality", {}).get("flags", []))
    reviews = Counter(c.get("review", {}).get("decision", "pending") for c in cards)
    duplicated = sum(bool(c.get("duplicate_of")) for c in cards)
    queue = sorted(cards, key=lambda c: (
        c.get("review", {}).get("status") == "stale",
        c.get("review", {}).get("decision") == "pending",
        not bool(c.get("duplicate_of")),
        sum(f["severity"] == "review" for f in c.get("quality", {}).get("flags", [])),
        c.get("published_at") or ""), reverse=True)
    report = {"generated_at": generated_at, "videos": len(cards), "exact_text_duplicates": duplicated,
              "signals": dict(counts), "editorial_decisions": dict(reviews),
              "confidence_metadata_available": sum(c.get("quality", {}).get("confidence_available", False) for c in cards),
              "next_review": [{"video": c["id"], "person": c["person"], "title": c["title"],
                  "source_hash": c["source_hash"], "flags": c.get("quality", {}).get("flags", []),
                  "review": c.get("review", {}), "duplicate_of": c.get("duplicate_of")} for c in queue[:100]],
              "note": "No son tasas de error. Un texto sin alertas sigue sin estar verificado. Duplicados exactos no cubren paráfrasis ni todos los crossposts."}
    atomic_json(output / "quality/report.json", report)
    atomic_text(output / "quality/LEEME.md", "\n".join([
        "# Calidad de la biblioteca", "", f"Actualizado: {generated_at}. Documentos: {len(cards)}.", "",
        f"Duplicados de texto normalizado: {duplicated}. Se conservan los originales y sus autores.",
        f"Selección editorial: {dict(reviews)}.", "", report["note"], "",
        "## Señales para revisar", "", *[f"- {code}: {n} documentos." for code, n in sorted(counts.items())], "",
        "`report.json` contiene la cola priorizada. `reviews.json` conserva decisiones, motivos, alcance y hash.",
        "`audits/` conserva segundas transcripciones y OCR: comparaciones automáticas, no escuchas humanas.",
        "Las notas revisadas se exportan junto a las referencias del skill. Si cambia el hash, dejan de aplicarse.",
    ]) + "\n")
    return {k: v for k, v in report.items() if k != "next_review"}
