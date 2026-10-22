"""Portable evidence lookup. Copied into generated skills; only uses Python stdlib."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path


def folded(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


def search(root: Path, query: str, person: str = "", limit: int = 8, *, reviewed_only: bool = False,
           include_duplicates: bool = False):
    index = json.loads((root / "references/index.json").read_text(encoding="utf-8"))
    terms = folded(query).split()
    found = []
    for video in index:
        if person and folded(person) not in folded(video["person"]):
            continue
        review = video.get("review", {})
        if reviewed_only and (review.get("decision") != "selected" or review.get("status") in {"stale", "unreviewed"}):
            continue
        if video.get("duplicate_of") and not include_duplicates:
            # Preserve a named creator's own source when filtering by person.
            canonical = next((v for v in index if v["id"] == video["duplicate_of"]), None)
            if canonical and (not person or folded(person) in folded(canonical["person"])):
                continue
        path = root / video["reference"]
        body = path.read_text(encoding="utf-8")
        normalized = folded(body)
        if not all(term in normalized for term in terms):
            continue
        title = folded(video["title"])
        score = sum(10 * (term in title) + min(normalized.count(term), 20) for term in terms)
        if review.get("decision") == "selected" and review.get("status") != "stale":
            score += 20
        elif review.get("decision") == "excluded":
            score -= 30
        fragments = []
        for chunk in re.split(r"(?m)^### ", body)[1:]:
            heading, _, content = chunk.partition("\n")
            if not terms or any(term in folded(content) for term in terms):
                excerpt = content.split("[Ver fuente]", 1)[0].strip()
                url = re.search(r"\[Ver fuente\]\(([^)]+)\)", content)
                fragments.append({"segment": heading, "excerpt": excerpt[:700], "url": url.group(1) if url else video["url"]})
                if len(fragments) == 3:
                    break
        found.append((score, {**video, "fragments": fragments}))
    found.sort(key=lambda pair: (pair[0], pair[1].get("published_at") or ""), reverse=True)
    return {"total": len(found), "results": [item for _, item in found[:max(1, min(limit, 30))]],
            "note": "Coincidencias textuales; lee las referencias completas antes de interpretar. No valida recomendaciones."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Buscar fragmentos de evidencia sin cargar toda la biblioteca.")
    parser.add_argument("query", help="Términos que deben aparecer en el video; tolera tildes.")
    parser.add_argument("--person", default="")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--reviewed-only", action="store_true", help="Solo selección editorial vigente; no implica audio completo verificado.")
    parser.add_argument("--include-duplicates", action="store_true")
    args = parser.parse_args()
    print(json.dumps(search(Path(__file__).resolve().parents[1], args.query, args.person, args.limit,
        reviewed_only=args.reviewed_only, include_duplicates=args.include_duplicates), ensure_ascii=False, indent=2))
