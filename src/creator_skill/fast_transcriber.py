from __future__ import annotations

import os
import threading
from pathlib import Path

_MODELS: dict[str, object] = {}
_MODEL_LOCK = threading.Lock()


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def _timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def transcribe_detailed(source: str, model_name: str, language: str, *, beam_size: int = 5) -> dict:
    """Keep original time boundaries and diagnostics; confidence is not accuracy."""
    from faster_whisper import WhisperModel

    threads = max(2, min(10, (os.cpu_count() or 4) - 2))
    with _MODEL_LOCK:
        model = _MODELS.get(model_name)
        if model is None:
            project_cache = Path(__file__).resolve().parents[2] / ".venv/quality-models"
            cache = os.environ.get("CREATOR_MD_MODEL_CACHE")
            if cache is None and (project_cache / f"models--Systran--faster-whisper-{model_name}").exists():
                cache = str(project_cache)
            model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=threads,
                num_workers=1,
                download_root=cache,
            )
            _MODELS[model_name] = model
        segments, info = model.transcribe(
            source,
            language=None if language == "auto" else language,
            beam_size=beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
            word_timestamps=True,
        )
        records = [{"start": s.start, "end": s.end, "text": s.text.strip(),
                    "avg_logprob": s.avg_logprob, "no_speech_prob": s.no_speech_prob,
                    "compression_ratio": s.compression_ratio,
                    "words": [{"start": w.start, "end": w.end, "word": w.word,
                               "probability": w.probability} for w in s.words or []]}
                   for s in segments if s.text.strip()]
        return {"segments": records,
                "transcript": "\n".join(f"{_timestamp(s['start'])} {s['text']}" for s in records),
                "recognition": {"engine": "faster_whisper", "model": model_name,
                    "beam_size": beam_size, "condition_on_previous_text": False,
                    "word_timestamps": True, "language": info.language,
                    "language_probability": info.language_probability,
                    "duration": info.duration, "duration_after_vad": info.duration_after_vad,
                    "reviewed": False}}


def transcribe(source: str, model_name: str, language: str) -> str:
    """Compatibility for callers that need the legacy timestamped text."""
    return transcribe_detailed(source, model_name, language)["transcript"]
