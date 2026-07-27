from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import CreatorSkillError
from .project import CreatorProject, doctor_data


def _common(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--workspace-root", type=Path, default=Path("workspaces"))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="creator-skill",
        description="Orchestrate creator videos into portable Agent Skills.",
    )
    commands = root.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor")
    _common(doctor)

    discover = commands.add_parser("discover")
    _common(discover)
    discover.add_argument("--profile", required=True)
    discover.add_argument("--project", default="discovery")
    discover.add_argument("--max-videos", type=int)

    build = commands.add_parser("build")
    _common(build)
    build.add_argument("--profile", required=True)
    build.add_argument("--name", required=True)
    build.add_argument("--intent", required=True)
    build.add_argument("--max-videos", type=int)
    build.add_argument("--batch-size", type=int, default=10)
    build.add_argument("--fixture-dir", type=Path)

    for name in ("resume", "update"):
        command = commands.add_parser(name)
        _common(command)
        command.add_argument("--project", required=True)
        command.add_argument("--fixture-dir", type=Path)

    for name in ("validate", "eval", "export", "status"):
        command = commands.add_parser(name)
        _common(command)
        command.add_argument("--project", required=True)
    return root


def _print(data: dict | list) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def run(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        data = doctor_data()
        _print(data)
        return 0 if all(item["available"] for item in data.values()) else 1
    project_name = getattr(args, "project", None) or getattr(args, "name", None)
    project = CreatorProject(args.workspace_root, project_name)
    if args.command == "discover":
        videos = project.discover(args.profile, args.max_videos)
        _print({"count": len(videos), "profile_json": str(project.paths.profile)})
    elif args.command == "build":
        _print(
            project.build(
                args.profile,
                args.intent,
                args.max_videos,
                args.batch_size,
                args.fixture_dir,
            )
        )
    elif args.command == "resume":
        _print(project.resume(args.fixture_dir))
    elif args.command == "update":
        _print(project.update(args.fixture_dir))
    elif args.command == "status":
        _print(project.state.load())
    elif args.command == "validate":
        config = project.load_config()
        skill_dir = project.paths.kb / "output" / "skills" / project.name
        _print(project.pipeline.validate(project.paths.kb, project.name, skill_dir))
    elif args.command == "eval":
        _print(project.pipeline.evaluate(project.paths.kb, project.name))
    elif args.command == "export":
        skill_dir = project.paths.kb / "output" / "skills" / project.name
        _print(project.pipeline.export(skill_dir, project.paths.exports))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parser().parse_args(argv))
    except (CreatorSkillError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

