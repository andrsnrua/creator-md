from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .content_project import ContentProject
from .errors import CreatorSkillError
from .project import CreatorProject, doctor_data
from .web_ui import serve


def _common(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--workspace-root", type=Path, default=Path("workspaces"))


def _category(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--category",
        default="sin-categoria",
        help="Rubro o categoría que agrupa a los creadores.",
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="creator-md",
        description="Extract resumable creator video transcripts into one Markdown file.",
    )
    commands = root.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor")
    _common(doctor)

    discover = commands.add_parser("discover")
    _common(discover)
    _category(discover)
    discover.add_argument("--profile", required=True)
    discover.add_argument("--project", default="discovery")
    discover.add_argument("--max-videos", type=int)

    extract = commands.add_parser("extract")
    _common(extract)
    _category(extract)
    extract.add_argument("--profile", required=True)
    extract.add_argument("--project", required=True)
    extract.add_argument("--count", required=True, type=int)

    continuation = commands.add_parser("continue")
    _common(continuation)
    _category(continuation)
    continuation.add_argument("--project", required=True)
    continuation.add_argument("--count", required=True, type=int)

    retry = commands.add_parser("retry")
    _common(retry)
    _category(retry)
    retry.add_argument("--project", required=True)
    retry.add_argument("--count", required=True, type=int)

    for action in ("sync", "pending", "history", "verify"):
        command = commands.add_parser(action)
        _common(command)
        _category(command)
        command.add_argument("--project", required=True)
        if action == "sync":
            command.add_argument("--scan-limit", type=int, default=100)
        elif action == "verify":
            command.add_argument("--repair", action="store_true",
                                 help="Reclasifica resultados vacíos con copia de seguridad previa.")
        else:
            command.add_argument("--count", type=int, default=20)

    status = commands.add_parser("status")
    _common(status)
    _category(status)
    status.add_argument("--project", required=True)

    export = commands.add_parser("export")
    _common(export)
    _category(export)
    export.add_argument("--project", required=True)

    web = commands.add_parser("serve")
    _common(web)
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", default=8765, type=int)
    return root


def _print(data: dict | list) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def run(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        data = doctor_data()
        _print(data)
        return 0 if all(item["available"] for item in data.values() if not item.get("optional")) else 1
    if args.command == "discover":
        project = CreatorProject(args.workspace_root, args.project, args.category)
        videos = project.discover(args.profile, args.max_videos)
        _print({"count": len(videos), "profile_json": str(project.paths.profile)})
    elif args.command == "extract":
        _print(
            ContentProject(args.workspace_root, args.project, category=args.category).start(
                args.profile, args.count
            )
        )
    elif args.command == "continue":
        _print(
            ContentProject(args.workspace_root, args.project, category=args.category).continue_from_history(
                args.count
            )
        )
    elif args.command == "retry":
        _print(
            ContentProject(args.workspace_root, args.project, category=args.category).retry_failed(args.count)
        )
    elif args.command == "status":
        _print(ContentProject(args.workspace_root, args.project, category=args.category).status())
    elif args.command in {"sync", "pending", "history", "verify"}:
        content = ContentProject(args.workspace_root, args.project, category=args.category)
        if args.command == "sync":
            result = content.sync_new(args.scan_limit)
        elif args.command == "pending":
            result = content.process_pending(args.count)
        elif args.command == "history":
            result = content.continue_from_history(args.count)
        else:
            result = content.audit_transcripts(repair=args.repair)
        _print(result)
    elif args.command == "export":
        _print(ContentProject(args.workspace_root, args.project, category=args.category).export())
    elif args.command == "serve":
        serve(args.workspace_root, args.host, args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parser().parse_args(argv))
    except (CreatorSkillError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
