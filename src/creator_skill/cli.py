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
    discover.add_argument("--profile", required=True)
    discover.add_argument("--project", default="discovery")
    discover.add_argument("--max-videos", type=int)

    extract = commands.add_parser("extract")
    _common(extract)
    extract.add_argument("--profile", required=True)
    extract.add_argument("--project", required=True)
    extract.add_argument("--count", required=True, type=int)

    continuation = commands.add_parser("continue")
    _common(continuation)
    continuation.add_argument("--project", required=True)
    continuation.add_argument("--count", required=True, type=int)

    status = commands.add_parser("status")
    _common(status)
    status.add_argument("--project", required=True)

    export = commands.add_parser("export")
    _common(export)
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
        return 0 if all(item["available"] for item in data.values()) else 1
    if args.command == "discover":
        project = CreatorProject(args.workspace_root, args.project)
        videos = project.discover(args.profile, args.max_videos)
        _print({"count": len(videos), "profile_json": str(project.paths.profile)})
    elif args.command == "extract":
        _print(
            ContentProject(args.workspace_root, args.project).start(
                args.profile, args.count
            )
        )
    elif args.command == "continue":
        _print(
            ContentProject(args.workspace_root, args.project).continue_from_history(
                args.count
            )
        )
    elif args.command == "status":
        _print(ContentProject(args.workspace_root, args.project).status())
    elif args.command == "export":
        _print(ContentProject(args.workspace_root, args.project).export())
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
