"""Publish the portable Ads skill to its own private repository."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from creator_skill.storage import file_lock

REPOSITORY = "andrsnrua/ads-evidence"
REMOTE = f"https://github.com/{REPOSITORY}.git"
MANIFEST = "skill-manifest.json"
GENERATOR = "creator-md/publish_ads_skill/v1"
RESERVED = {"README.md", MANIFEST, ".gitignore", ".gitattributes"}
IGNORED = "__pycache__/\n*.py[cod]\n*.tmp\n*.lock\n.env*\n.venv/\n.DS_Store\nThumbs.db\n"
SECRET = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
LINK = re.compile(r"!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+\"[^\"]*\")?\)")
BUSINESSES = ["Ecommerce", "Negocios locales con citas", "Servicios profesionales o de alto ticket",
              "B2B consultivo", "Educación y formación", "Restaurantes y delivery",
              "SaaS y suscripciones", "Mayoristas y distribuidores"]


class PublishError(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def relative_name(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or "\\" in value or ":" in value or path.is_absolute()
            or any(p in {".", "..", ".git"} for p in path.parts) or str(path) != value):
        raise PublishError("Ruta no portable o fuera del paquete.")
    return value


def no_links(path: Path, boundary: Path, checked: set[Path] | None = None) -> None:
    path, boundary = Path(os.path.abspath(path)), Path(os.path.abspath(boundary))
    if not path.is_relative_to(boundary):
        raise PublishError("La ruta escapa de la carpeta autorizada.")
    for part in [path, *path.parents]:
        if checked is not None and part in checked:
            break
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise PublishError("No se admiten enlaces simbólicos ni junctions.")
        if checked is not None and stat.S_ISDIR(info.st_mode):
            checked.add(part)
        if part == boundary:
            break


def validate_destination(workspace: Path, destination: Path) -> Path:
    base = workspace.absolute() / ".venv" / "github"
    destination = destination.absolute()
    no_links(destination, workspace.absolute())
    destination = destination.resolve()
    base = base.resolve()
    if destination == base or not destination.is_relative_to(base):
        raise PublishError("--repo-dir debe ser una subcarpeta de .venv/github.")
    if destination == workspace.absolute() or destination.is_relative_to(workspace / "Ads"):
        raise PublishError("El checkout debe estar separado de la aplicación y del skill fuente.")
    return destination


def portable_files(skill: Path) -> dict[str, bytes]:
    no_links(skill, skill.parent.parent)
    payload = {}
    folded = set()
    checked: set[Path] = set()
    for folder, directories, files in os.walk(skill, followlinks=False):
        for name in directories + files:
            no_links(Path(folder) / name, skill, checked)
        for name in files:
            path = Path(folder) / name
            key = relative_name(path.relative_to(skill).as_posix())
            parts = PurePosixPath(key).parts
            if (key in RESERVED or any(p.startswith(".") or p == "__pycache__" for p in parts)
                    or any(word in path.stem.lower() for word in ("credential", "secret", "cookie", "password", "token"))
                    or (key != "SKILL.md" and parts[0] not in {"references", "scripts", "assets", "agents"})
                    or path.suffix.lower() not in {".md", ".json", ".py", ".yaml", ".png", ".jpg", ".jpeg", ".webp"}):
                raise PublishError(f"Archivo inesperado en el skill: {key}")
            if key.casefold() in folded:
                raise PublishError("El paquete contiene rutas duplicadas según Windows.")
            folded.add(key.casefold())
            data = path.read_bytes()
            if len(data) > 50 * 1024 * 1024:
                raise PublishError(f"Archivo demasiado grande para esta publicación: {key}")
            if path.suffix.lower() in {".md", ".json", ".py", ".yaml"}:
                text = data.decode("utf-8-sig")
                if SECRET.search(text):
                    raise PublishError(f"Posible credencial en {key}; no se muestra su contenido.")
            payload[key] = data
    for required in ("SKILL.md", "references/index.json", "references/criterios-curados.md"):
        if required not in payload:
            raise PublishError(f"Falta {required}.")
    if not re.search(r"(?m)^name: ads-evidence\s*$", payload["SKILL.md"].decode("utf-8-sig")):
        raise PublishError("El nombre del skill debe ser ads-evidence.")
    for key, data in payload.items():
        if not key.endswith(".md"):
            continue
        for match in LINK.finditer(data.decode("utf-8-sig")):
            link = unquote(match[1].strip("<>"))
            if link.startswith(("https://", "http://", "mailto:", "#")):
                continue
            parsed = urlsplit(link)
            if parsed.scheme in {"http", "https", "mailto"} or link.startswith("#"):
                continue
            if parsed.scheme or parsed.netloc or link.startswith(("/", "\\")):
                raise PublishError(f"Referencia local no portable en {key}.")
            target = (skill / key).parent / parsed.path
            resolved = target.resolve()
            if not resolved.is_relative_to(skill.resolve()) or not resolved.exists():
                raise PublishError(f"Referencia local ausente o fuera del skill en {key}: {link}")
    return payload


def snapshot(workspace: Path) -> dict[str, bytes]:
    """Keep collection/build locks only while reading a consistent local snapshot."""
    output = workspace / "Ads"
    with file_lock(workspace / "workspaces/.creator-md/sync.lock"), file_lock(output / ".build.lock"):
        payload = portable_files(output / "skill")
        knowledge = read_json(output / "knowledge.json")
        curated = read_json(output / "curated.json")
        review_log = read_json(output / "curation-review.json")
        reviews = read_json(output / "quality/reviews.json")["videos"]
        if review_log.get("pending_export"):
            raise PublishError("Hay una exportación pendiente; reconstruye y verifica antes de publicar.")
        index = json.loads(payload["references/index.json"])
        cards = {c["id"]: c for c in knowledge["videos"]}
        exported = {c["id"]: c for c in index}
        if len(cards) != len(knowledge["videos"]) or len(exported) != len(index) or cards.keys() != exported.keys():
            raise PublishError("El índice no corresponde al catálogo actual.")
        library = read_json(workspace / "workspaces/.creator-md/library.json")
        sources = {s["id"]: s for s in library["sources"]}
        checked: set[Path] = set()
        for exported_source in knowledge.get("sources", []):
            source = sources.get(exported_source["id"])
            if not source:
                raise PublishError("El catálogo incluye una fuente retirada de la biblioteca.")
            folder = workspace / "workspaces" / source["category"] / source["project"]
            no_links(folder, workspace / "workspaces", checked)
            no_links(folder / "state.json", workspace / "workspaces", checked)
            no_links(folder / "project.json", workspace / "workspaces", checked)
            records = read_json(folder / "state.json")["videos"]
            config = read_json(folder / "project.json")
            counts = {name: sum(v["status"] == name for v in records.values())
                      for name in ("completed", "pending", "failed", "needs_review")}
            if (counts != exported_source.get("counts")
                    or config.get("last_checked_at") != exported_source.get("checked_at")
                    or config.get("coverage", {}) != exported_source.get("coverage", {})):
                raise PublishError("Hay cambios de recopilación aún no exportados; reconstruye el skill.")
        for key, card in cards.items():
            entry = exported[key]
            if entry.get("source_hash") != card["source_hash"]:
                raise PublishError(f"Índice obsoleto: {key}")
            ref = relative_name(entry["reference"])
            if ref not in payload or card["source_hash"].encode() not in payload[ref]:
                raise PublishError(f"Transcripción exportada ausente u obsoleta: {key}")
            source = sources.get(card["source_id"])
            if not source:
                raise PublishError(f"Fuente local ausente: {key}")
            raw = workspace / "workspaces" / source["category"] / source["project"] / "raw-results" / f"{card['video_id']}.json"
            no_links(raw, workspace / "workspaces", checked)
            if not raw.is_file() or digest(raw.read_bytes()) != card["source_hash"]:
                raise PublishError(f"Original modificado o ausente: {key}")
            expected = reviews.get(key, {"status": "unreviewed", "decision": "pending"})
            if key in reviews and expected.get("source_hash") != card["source_hash"]:
                raise PublishError(f"Revisión obsoleta: {key}")
            if entry.get("review") != expected:
                raise PublishError(f"Revisión no exportada: {key}")
        for key, sha in review_log.get("source_hashes", {}).items():
            if key not in cards or cards[key]["source_hash"] != sha:
                raise PublishError(f"Registro editorial obsoleto: {key}")
        rendered = payload["references/criterios-curados.md"].decode("utf-8-sig")
        for criterion in curated["insights"]:
            for value in [criterion["title"], criterion["principle"], criterion["when"], criterion["limits"], *criterion["steps"]]:
                if value not in rendered:
                    raise PublishError("Los criterios editados no se han publicado al skill.")
            for citation in criterion["evidence"]:
                card = cards.get(citation["video"])
                if not card or citation.get("source_hash") != card["source_hash"]:
                    raise PublishError("Una cita tiene un hash distinto del original.")
                if exported[card["id"]]["review"].get("decision") != "selected":
                    raise PublishError("Una cita no tiene selección editorial vigente.")
                start, end = citation["start"], citation["end"]
                intervals = card["segments"]
                if (not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end))
                        or not intervals or not 0 <= start < end
                        or start < min(s["start"] for s in intervals) or end > max(s["end"] for s in intervals)):
                    raise PublishError("Una cita está fuera de la transcripción.")
        valid_reviews = [r for k, r in reviews.items() if k in cards and r.get("source_hash") == cards[k]["source_hash"]]
        coverage = [{k: s.get(k) for k in ("id", "person", "url", "checked_at", "coverage", "counts", "pending", "error")}
                    for s in knowledge.get("sources", [])]
        metadata = {"documents": len(cards), "reviewed_documents": len(valid_reviews),
                    "selected_documents": sum(r.get("decision") == "selected" for r in valid_reviews),
                    "full_text_reviews": sum(r.get("status") == "text_reviewed" for r in valid_reviews),
                    "criteria": [{"id": c["id"], "title": c["title"]} for c in curated["insights"]],
                    "curation_reviewed_at": curated.get("reviewed_at"), "coverage": coverage,
                    "source_hashes": {k: cards[k]["source_hash"] for k in sorted(cards)},
                    "business_models": BUSINESSES}
    version = digest(encoded({"files": {k: digest(v) for k, v in sorted(payload.items())}, "metadata": metadata}))
    payload["README.md"] = readme(metadata, version).encode("utf-8")
    payload[".gitignore"] = IGNORED.encode()
    payload[".gitattributes"] = b"* -text\n"
    payload[MANIFEST] = encoded({"schema_version": 1, "generator": GENERATOR, "repository": REPOSITORY,
                                 "version": version, "metadata": metadata,
                                 "files": {k: digest(v) for k, v in sorted(payload.items())}})
    return payload


def readme(metadata: dict, version: str) -> str:
    models = ", ".join(BUSINESSES)
    return f"""# Ads con Sebastián y evidencia

Skill independiente de Creator MD, centrado en Sebastián Boggiano y contrastado con Jesús Vargas, Nico Donovan y Martín Etcheb. La entrada es [SKILL.md](SKILL.md).

Versión de contenido: `{version[:16]}`. Revisión editorial: {metadata['curation_reviewed_at']}.
Incluye {metadata['documents']} documentos, {metadata['reviewed_documents']} revisiones editoriales de alcance indicado y {len(metadata['criteria'])} criterios. Recopilar un documento no equivale a validarlo.

## Instalar y usar

Clona este repositorio privado con una cuenta autorizada: `gh repo clone {REPOSITORY}`. Copia la carpeta completa, con nombre `ads-evidence`, al directorio de skills de tu agente. Abre una sesión nueva y pide: «Usa ads-evidence para diagnosticar mi negocio y proponer una prueba con economía, creativos, fuentes y métricas». También puedes pedir a una IA con acceso a archivos que lea SKILL.md.

No necesita una API de pago propia. Python 3.11+ es opcional para búsqueda y calculadoras. Un skill aporta instrucciones y evidencia; no entrena un modelo ni ejecuta campañas por sí mismo.

## Negocios y contenido

Ocho rutas: {models}. Incluye diagnóstico, creativos, WhatsApp, economía, experimentos, escalado, plantillas y referencias con tiempos. Los procedimientos adicionales son síntesis operativa, no citas atribuidas automáticamente a los creadores.

## Actualizaciones y límites

Creator MD recopila únicamente por vías gratuitas, revisa lo nuevo y publica un cambio cuando el paquete validado cambia. El mantenimiento depende del equipo disponible, acceso a fuentes y revisión editorial; GitHub no ejecuta esa recopilación por sí solo. Para actualizar una copia limpia usa `git pull --ff-only` y reemplaza la copia instalada. Conserva tus personalizaciones fuera de los archivos generados.

Consulta [catálogo y cobertura](references/catalogo.md), [criterios revisados](references/criterios-curados.md) y [fuentes oficiales fechadas](references/fuentes-oficiales.md). Hay fuentes con cobertura parcial, pendientes y bloqueos. No se acredita cobertura completa, revisión audiovisual total ni resultados garantizados. Las funciones de Meta requieren comprobar vigencia y disponibilidad en la cuenta.

`{MANIFEST}` registra hashes, criterios, revisión y cobertura de esta versión. Los originales y archivos privados de la aplicación permanecen fuera de este repositorio. El acceso del repositorio sigue siendo privado; publicar este paquete no concede derechos de redistribución del contenido de terceros.
"""


def command(args: list[str], cwd: Path | None = None, *, acceptable=(0,)) -> str:
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1")
    try:
        result = subprocess.run(args, cwd=cwd, env=environment, text=True, encoding="utf-8",
                                errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                shell=False, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublishError(f"No se pudo completar {args[0]}; comprueba instalación, acceso y conexión.") from exc
    if result.returncode not in acceptable:
        # Tool stderr can contain authenticated remote URLs; never echo it or the command.
        raise PublishError(f"{args[0]} terminó con código {result.returncode}; no se publicó una nueva versión.")
    return result.stdout.strip()


def git(destination: Path, *args: str, acceptable=(0,)) -> str:
    return command(["git", "-c", "core.hooksPath=" + os.devnull, "-c", "core.autocrlf=false", *args], destination,
                   acceptable=acceptable)


def check_checkout(destination: Path) -> bool:
    if not (destination / ".git").exists():
        return False
    no_links(destination / ".git", destination)
    if not (destination / ".git").is_dir():
        raise PublishError("Se requiere un checkout independiente, no un worktree enlazado.")
    top = Path(git(destination, "rev-parse", "--show-toplevel")).resolve()
    if top != destination.resolve():
        raise PublishError("El checkout no pertenece a la carpeta aislada.")
    allowed = {REMOTE, f"https://github.com/{REPOSITORY}", f"git@github.com:{REPOSITORY}.git"}
    for extra in ([], ["--push"]):
        urls = git(destination, "remote", "get-url", "--all", *extra, "origin").splitlines()
        if not urls or any(url not in allowed for url in urls):
            raise PublishError("origin no apunta exclusivamente al repositorio de skill autorizado.")
    if git(destination, "status", "--porcelain", "--untracked-files=all"):
        raise PublishError("El checkout tiene cambios locales. Revísalos antes de publicar.")
    return True


def owned_files(destination: Path) -> dict[str, str]:
    manifest_path = destination / MANIFEST
    if not manifest_path.exists():
        owned = {}
    else:
        old = read_json(manifest_path)
        if old.get("generator") != GENERATOR or old.get("repository") != REPOSITORY or old.get("schema_version") != 1:
            raise PublishError("El manifiesto no corresponde a este publicador.")
        owned = old["files"]
        if not isinstance(owned, dict):
            raise PublishError("Manifiesto de archivos inválido.")
        for key, sha in owned.items():
            relative_name(key)
            no_links(destination / key, destination)
            if not (destination / key).is_file() or digest((destination / key).read_bytes()) != sha:
                raise PublishError(f"Archivo generado editado fuera del publicador: {key}")
        owned = dict(owned, **{MANIFEST: digest(manifest_path.read_bytes())})
    for folder, dirs, files in os.walk(destination, followlinks=False):
        if Path(folder) == destination:
            dirs[:] = [d for d in dirs if d != ".git"]
        for name in dirs + files:
            no_links(Path(folder) / name, destination)
        for name in files:
            key = (Path(folder) / name).relative_to(destination).as_posix()
            if key not in owned:
                raise PublishError(f"Archivo ajeno al publicador; no se sobrescribe: {key}")
    return owned


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_snapshot(destination: Path, payload: dict[str, bytes]) -> bool:
    previous = owned_files(destination)
    hashes = {k: digest(v) for k, v in payload.items()}
    if previous == hashes:
        return False
    destination.mkdir(parents=True, exist_ok=True)
    for key, data in payload.items():
        if key != MANIFEST and previous.get(key) != hashes[key]:
            atomic_bytes(destination / key, data)
    for key in previous.keys() - payload.keys():
        (destination / key).unlink()
    atomic_bytes(destination / MANIFEST, payload[MANIFEST])
    return True


def private_repository() -> dict:
    info = json.loads(command(["gh", "repo", "view", REPOSITORY, "--json", "nameWithOwner,isPrivate,defaultBranchRef,isEmpty"]))
    if info.get("nameWithOwner") != REPOSITORY or info.get("isPrivate") is not True:
        raise PublishError("La publicación requiere el repositorio privado exacto andrsnrua/ads-evidence.")
    if info.get("isEmpty") is not True and info.get("defaultBranchRef") and info["defaultBranchRef"]["name"] != "main":
        raise PublishError("La rama principal remota debe ser main.")
    return info


def publish(workspace: Path, destination: Path, *, prepare_only: bool) -> dict:
    destination = validate_destination(workspace, destination)
    with file_lock(workspace / ".venv/github/.ads-evidence-publish.lock"):
        if not prepare_only:
            private_repository()
            if not destination.exists() or not any(destination.iterdir()):
                destination.parent.mkdir(parents=True, exist_ok=True)
                command(["git", "-c", "core.autocrlf=false", "clone", "--origin", "origin", "--", REMOTE, str(destination)], workspace)
        checkout = check_checkout(destination)
        if not prepare_only and not checkout:
            raise PublishError("Falta un checkout Git. Clona el repo privado vacío o inicializa el paquete preparado y su origin.")
        owned_files(destination)
        if not prepare_only:
            remote_head = git(destination, "ls-remote", "--heads", "origin", "refs/heads/main")
            head = git(destination, "rev-parse", "--verify", "HEAD", acceptable=(0, 128))
            if head and git(destination, "symbolic-ref", "--short", "HEAD") != "main":
                raise PublishError("La publicación solo admite la rama main.")
            if remote_head:
                if not head:
                    raise PublishError("El remoto tiene historia y el checkout local no. Usa un clon limpio.")
                git(destination, "fetch", "--no-tags", "origin", "main")
                # Fast-forward only; ahead/diverged local commits require explicit review.
                local_extra = git(destination, "rev-list", "--count", "FETCH_HEAD..HEAD")
                if local_extra != "0":
                    raise PublishError("Hay commits locales sin publicar o divergencia; revisar antes de continuar.")
                git(destination, "merge", "--ff-only", "FETCH_HEAD")
            elif not head:
                git(destination, "symbolic-ref", "HEAD", "refs/heads/main")
            if git(destination, "symbolic-ref", "--short", "HEAD") != "main":
                raise PublishError("La publicación solo admite la rama main.")
            owned_files(destination)
        payload = snapshot(workspace)
        changed = apply_snapshot(destination, payload)
        manifest = json.loads(payload[MANIFEST])
        result = {"repository": REPOSITORY, "directory": str(destination), "version": manifest["version"],
                  "files": len(payload), "changed": changed, "published": False, "prepare_only": prepare_only}
        if not prepare_only:
            if changed:
                # The full directory has already passed the strict generated-file allowlist.
                git(destination, "add", "--all", "--", ".")
                git(destination, "-c", "commit.gpgsign=false", "commit", "-m", f"Actualizar skill Ads {manifest['version'][:16]}")
            private_repository()
            # Push rejection is retained for review; no force, reset, stash or automatic retry.
            git(destination, "push", "--set-upstream", "origin", "HEAD:refs/heads/main")
            result["published"] = True
        return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare-only", action="store_true", help="Validar y copiar sin acceso de red, commit ni push.")
    mode.add_argument("--publish", action="store_true", help=f"Publicar en {REPOSITORY}, que ya debe existir y ser privado.")
    parser.add_argument("--repo-dir", type=Path, default=ROOT / ".venv/github/ads-evidence")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(publish(ROOT, args.repo_dir, prepare_only=args.prepare_only), ensure_ascii=False))
        return 0
    except (PublishError, OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"Publicación detenida: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
