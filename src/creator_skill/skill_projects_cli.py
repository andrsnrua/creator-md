"""Manage portable skill projects without starting the web server."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import CreatorSkillError
from .library import Library
from .skill_projects import SkillProjects


def main(root: Path, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Skills por persona o grupo de personas.")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="Listar perfiles guardados.")
    for action in ("create", "update", "import-curation"):
        command = actions.add_parser(action)
        command.add_argument("--file", type=Path, required=True, help="Archivo JSON UTF-8.")
        if action != "create":
            command.add_argument("--id", required=True)
    for action in ("preview", "export"):
        actions.add_parser(action).add_argument("--id", required=True)
    build = actions.add_parser("build", help="Reconstruir sin consultar plataformas.")
    target = build.add_mutually_exclusive_group(required=True)
    target.add_argument("--id")
    target.add_argument("--all", action="store_true", help="Actualizar sólo proyectos automáticos con cambios.")
    args = parser.parse_args(argv)
    try:
        projects = SkillProjects(Library(root / "workspaces"))
        if args.action == "list":
            result = projects.list()
        elif args.action == "build":
            result = projects.build(args.id) if args.id else projects.build_all(auto_only=True)
        elif args.action == "preview":
            result = projects.preview(args.id)
        elif args.action == "export":
            result = {"zip": str(projects.export(args.id))}
        else:
            if args.file.stat().st_size > 2_000_000:
                raise ValueError("El JSON excede el límite de 2 MB.")
            payload = json.loads(args.file.read_text(encoding="utf-8-sig"))
            if args.action == "create":
                result = projects.create(payload)
            elif args.action == "update":
                result = projects.update(args.id, payload)
            else:
                result = projects.import_curation(args.id, payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, list) and any(isinstance(item, dict) and item.get("error") for item in result):
            return 1
        return 0
    except (CreatorSkillError, OSError, ValueError) as exc:
        print(f"No se pudo completar: {exc}", file=sys.stderr)
        return 2
