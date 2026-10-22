"""Portable entry point for the project-local runtime, including isolated Python."""
import runpy
import site
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGES = str(ROOT / ".venv" / "runtime-packages")
site.addsitedir(PACKAGES)
# Prefer the versions installed for this project over an older global package.
if PACKAGES in sys.path:
    sys.path.remove(PACKAGES)
sys.path.insert(0, PACKAGES)
sys.path.insert(0, str(ROOT / "src"))
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ytdlp":
        sys.argv.pop(1)
        runpy.run_module("yt_dlp", run_name="__main__")
    elif len(sys.argv) > 1 and sys.argv[1] == "free-discovery":
        sys.argv.pop(1)
        runpy.run_module("creator_skill.free_discovery_worker", run_name="__main__")
    elif len(sys.argv) > 1 and sys.argv[1] == "sync":
        from creator_skill.library import Library
        library = Library(ROOT / "workspaces")
        library.migrate()
        print(library.run(due_only="--due" in sys.argv))
    elif len(sys.argv) > 1 and sys.argv[1] == "build":
        from creator_skill.library import Library
        from creator_skill.knowledge import KnowledgeBuilder
        library = Library(ROOT / "workspaces")
        library.migrate()
        print(KnowledgeBuilder(library).build_all())
        from creator_skill.skill_projects import SkillProjects
        print(SkillProjects(library).build_all(auto_only=True))
    elif len(sys.argv) > 1 and sys.argv[1] == "skills":
        from creator_skill.skill_projects_cli import main
        raise SystemExit(main(ROOT, sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "audit":
        from creator_skill.quality_audit import main
        main(ROOT, sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "backfill":
        import argparse
        from creator_skill.library import Library
        from creator_skill.backfill import run
        parser = argparse.ArgumentParser()
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--max-batches", type=int)
        args = parser.parse_args(sys.argv[2:])
        print(run(Library(ROOT / "workspaces"), once=args.once, max_batches=args.max_batches))
    elif len(sys.argv) > 1 and sys.argv[1] == "serve":
        from creator_skill.web_ui import serve
        serve(ROOT / "workspaces", "127.0.0.1", 8770)
    else:
        from creator_skill.launcher import main
        main()
