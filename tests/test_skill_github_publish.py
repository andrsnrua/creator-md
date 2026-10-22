import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location("publish_ads_skill", Path(__file__).resolve().parents[1] / "scripts/publish_ads_skill.py")
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(publisher.encoded(value))


@pytest.fixture
def library(tmp_path):
    skill = tmp_path / "Ads/skill"
    (skill / "references/videos").mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: ads-evidence\ndescription: Ads\n---\n[Criterios](references/criterios-curados.md)\n", encoding="utf-8")
    raw = tmp_path / "workspaces/ads/person/raw-results/1.json"
    write_json(raw, {"segments": [{"start": 0, "end": 10, "text": "Evidencia"}]})
    sha = publisher.digest(raw.read_bytes())
    card = {"id": "source-1", "source_id": "source", "video_id": "1", "source_hash": sha,
            "segments": [{"start": 0, "end": 10}], "person": "Persona"}
    review = {"status": "text_reviewed", "decision": "selected", "source_hash": sha}
    criterion = {"id": "one", "title": "Título", "principle": "Principio", "when": "Condición",
                 "limits": "Límite", "steps": ["Paso"], "evidence": [{"video": "source-1", "source_hash": sha, "start": 0, "end": 10}]}
    (skill / "references/criterios-curados.md").write_text("Título Principio Condición Límite Paso", encoding="utf-8")
    for name in ("catalogo.md", "fuentes-oficiales.md"):
        (skill / "references" / name).write_text("Fuente fechada", encoding="utf-8")
    (skill / "references/videos/source-1.md").write_text(f"SHA256 original: {sha}\nEvidencia", encoding="utf-8")
    write_json(skill / "references/index.json", [dict(card, review=review, reference="references/videos/source-1.md")])
    write_json(tmp_path / "Ads/knowledge.json", {"generated_at": "2026-10-22", "videos": [card], "sources": []})
    write_json(tmp_path / "Ads/curated.json", {"reviewed_at": "2026-10-22", "insights": [criterion]})
    write_json(tmp_path / "Ads/curation-review.json", {"source_hashes": {"source-1": sha}})
    write_json(tmp_path / "Ads/quality/reviews.json", {"videos": {"source-1": review}})
    write_json(tmp_path / "workspaces/.creator-md/library.json", {"sources": [{"id": "source", "category": "ads", "project": "person"}]})
    return tmp_path


def test_prepare_is_portable_deterministic_and_does_not_run_network(library, monkeypatch):
    monkeypatch.setattr(publisher, "command", lambda *a, **kw: pytest.fail("Unexpected command"))
    destination = library / ".venv/github/ads-evidence"
    first = publisher.publish(library, destination, prepare_only=True)
    first_manifest = (destination / publisher.MANIFEST).read_bytes()
    second = publisher.publish(library, destination, prepare_only=True)
    assert first["changed"] and not second["changed"]
    assert not first["published"] and first["version"] == second["version"]
    assert first_manifest == (destination / publisher.MANIFEST).read_bytes()
    assert (destination / "SKILL.md").exists()
    assert not (destination / "Ads").exists()
    manifest = json.loads(first_manifest)
    assert manifest["metadata"]["reviewed_documents"] == 1
    assert len(manifest["metadata"]["business_models"]) == 8
    assert not any("workspaces" in p for p in manifest["files"])


@pytest.mark.parametrize("path", [".env", "references/credentials.json", "scripts/tool.exe", "scripts/__pycache__/a.pyc", "run.py", "README.md"])
def test_unexpected_files_fail_closed(library, path):
    target = library / "Ads/skill" / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("data", encoding="utf-8")
    with pytest.raises(publisher.PublishError, match="inesperado"):
        publisher.snapshot(library)


def test_recognized_secret_is_not_printed(library):
    token = "ghp_" + "a" * 36
    path = library / "Ads/skill/references/safe.md"
    path.write_text(token, encoding="utf-8")
    with pytest.raises(publisher.PublishError) as error:
        publisher.snapshot(library)
    assert token not in str(error.value)
    assert "credencial" in str(error.value)


@pytest.mark.parametrize("link", ["missing.md", "../../../../secret.md", "C:/Users/private.md", "file:///tmp/private.md"])
def test_broken_or_external_local_reference_is_rejected(library, link):
    (library / "Ads/skill/references/bad.md").write_text(f"[link]({link})", encoding="utf-8")
    with pytest.raises(publisher.PublishError, match="Referencia"):
        publisher.snapshot(library)


@pytest.mark.parametrize("kind", ["raw", "index", "review", "criterion", "pending"])
def test_stale_export_is_rejected(library, kind):
    if kind == "raw":
        (library / "workspaces/ads/person/raw-results/1.json").write_text("modified", encoding="utf-8")
    elif kind == "index":
        path = library / "Ads/skill/references/index.json"
        data = publisher.read_json(path)
        data[0]["source_hash"] = "0" * 64
        write_json(path, data)
    elif kind == "review":
        path = library / "Ads/quality/reviews.json"
        data = publisher.read_json(path)
        data["videos"]["source-1"]["decision"] = "excluded"
        write_json(path, data)
    elif kind == "criterion":
        path = library / "Ads/curated.json"
        data = publisher.read_json(path)
        data["insights"][0]["principle"] = "New unpublished principle"
        write_json(path, data)
    else:
        write_json(library / "Ads/curation-review.json", {"pending_export": {"reason": "waiting_disk"}})
    with pytest.raises(publisher.PublishError):
        publisher.snapshot(library)


def test_raw_path_cannot_escape_workspace(library):
    path = library / "workspaces/.creator-md/library.json"
    write_json(path, {"sources": [{"id": "source", "category": "../../../outside", "project": "person"}]})
    with pytest.raises(publisher.PublishError, match="escapa"):
        publisher.snapshot(library)


def test_new_collection_not_yet_exported_is_rejected(library):
    path = library / "Ads/knowledge.json"
    data = publisher.read_json(path)
    data["sources"] = [{"id": "source", "counts": {"completed": 1, "pending": 0, "failed": 0, "needs_review": 0},
                        "checked_at": "2026-10-21", "coverage": {}}]
    write_json(path, data)
    write_json(library / "workspaces/ads/person/state.json", {"videos": {"1": {"status": "completed"}}})
    write_json(library / "workspaces/ads/person/project.json", {"last_checked_at": "2026-10-22", "coverage": {}})
    with pytest.raises(publisher.PublishError, match="recopilación"):
        publisher.snapshot(library)


def test_copy_removes_only_previously_owned_stale_files(library):
    destination = library / ".venv/github/ads-evidence"
    extra = library / "Ads/skill/references/obsolete.md"
    extra.write_text("Obsolete", encoding="utf-8")
    publisher.publish(library, destination, prepare_only=True)
    extra.unlink()
    publisher.publish(library, destination, prepare_only=True)
    assert not (destination / "references/obsolete.md").exists()
    (destination / "personal.md").write_text("Keep", encoding="utf-8")
    with pytest.raises(publisher.PublishError, match="ajeno"):
        publisher.publish(library, destination, prepare_only=True)
    assert (destination / "personal.md").read_text(encoding="utf-8") == "Keep"


def test_modified_generated_file_is_never_overwritten(library):
    destination = library / ".venv/github/ads-evidence"
    publisher.publish(library, destination, prepare_only=True)
    path = destination / "SKILL.md"
    path.write_text("Personal edit", encoding="utf-8")
    with pytest.raises(publisher.PublishError, match="editado"):
        publisher.publish(library, destination, prepare_only=True)
    assert path.read_text(encoding="utf-8") == "Personal edit"


@pytest.mark.parametrize("destination", [".", "Ads/skill", ".venv/github", ".venv/github/../../outside"])
def test_checkout_location_is_restricted(library, destination):
    with pytest.raises(publisher.PublishError):
        publisher.publish(library, library / destination, prepare_only=True)


def test_symlink_is_not_followed(library):
    path = library / "Ads/skill/references/alias.md"
    try:
        path.symlink_to(library / "Ads/skill/SKILL.md")
    except OSError:
        pytest.skip("Symlinks unavailable on this Windows account")
    with pytest.raises(publisher.PublishError, match="enlaces"):
        publisher.snapshot(library)


def mock_checkout(monkeypatch, destination, *, dirty=False, remote=None, ahead="0"):
    (destination / ".git").mkdir(parents=True)
    calls = []

    def fake_git(folder, *args, **kwargs):
        calls.append(args)
        if args[:2] == ("rev-parse", "--show-toplevel"):
            return str(destination)
        if args[:2] == ("remote", "get-url"):
            return remote or publisher.REMOTE
        if args[0] == "status":
            return " M SKILL.md" if dirty else ""
        if args[0] == "ls-remote":
            return "remote-sha\trefs/heads/main"
        if args[:2] == ("rev-parse", "--verify"):
            return "local-sha"
        if args[0] == "rev-list":
            return ahead
        if args[:2] == ("symbolic-ref", "--short"):
            return "main"
        return ""

    monkeypatch.setattr(publisher, "git", fake_git)
    monkeypatch.setattr(publisher, "private_repository", lambda: {})
    return calls


def test_publish_uses_private_exact_repo_and_no_force(library, monkeypatch):
    destination = library / ".venv/github/ads-evidence"
    calls = mock_checkout(monkeypatch, destination)
    result = publisher.publish(library, destination, prepare_only=False)
    assert result["published"]
    assert ("merge", "--ff-only", "FETCH_HEAD") in calls
    assert ("push", "--set-upstream", "origin", "HEAD:refs/heads/main") in calls
    assert not any("--force" in call for call in calls)
    calls.clear()
    result = publisher.publish(library, destination, prepare_only=False)
    assert not result["changed"]
    assert not any("commit" in call for call in calls)


@pytest.mark.parametrize("failure", ["dirty", "remote", "ahead"])
def test_git_unsafe_states_stop_before_write(library, monkeypatch, failure):
    destination = library / ".venv/github/ads-evidence"
    calls = mock_checkout(monkeypatch, destination, dirty=failure == "dirty",
                          remote="https://github.com/andrsnrua/creator-md.git" if failure == "remote" else None,
                          ahead="1" if failure == "ahead" else "0")
    with pytest.raises(publisher.PublishError):
        publisher.publish(library, destination, prepare_only=False)
    assert not (destination / "SKILL.md").exists()
    assert not any("push" in call for call in calls)


def test_first_publish_clones_existing_repo_and_sets_unborn_main(library, monkeypatch):
    destination = library / ".venv/github/ads-evidence"
    calls = []
    monkeypatch.setattr(publisher, "private_repository", lambda: {})

    def fake_command(args, cwd=None, **kwargs):
        assert "clone" in args and publisher.REMOTE in args
        assert "core.autocrlf=false" in args
        (destination / ".git").mkdir(parents=True)
        return ""

    def fake_git(folder, *args, **kwargs):
        calls.append(args)
        if args[:2] == ("rev-parse", "--show-toplevel"):
            return str(destination)
        if args[:2] == ("remote", "get-url"):
            return publisher.REMOTE
        if args[:2] == ("symbolic-ref", "--short"):
            return "main"
        return ""

    monkeypatch.setattr(publisher, "command", fake_command)
    monkeypatch.setattr(publisher, "git", fake_git)
    assert publisher.publish(library, destination, prepare_only=False)["published"]
    assert ("symbolic-ref", "HEAD", "refs/heads/main") in calls
    assert any("commit" in call for call in calls)


@pytest.mark.parametrize("info", [
    {"nameWithOwner": publisher.REPOSITORY, "isPrivate": False},
    {"nameWithOwner": "other/ads-evidence", "isPrivate": True},
    {"nameWithOwner": publisher.REPOSITORY, "isPrivate": True, "defaultBranchRef": {"name": "develop"}},
])
def test_private_repository_assertion(monkeypatch, info):
    monkeypatch.setattr(publisher, "command", lambda args: json.dumps(info))
    with pytest.raises(publisher.PublishError):
        publisher.private_repository()


def test_command_error_does_not_reveal_tool_stderr(monkeypatch):
    class Result:
        returncode = 1
        stdout = ""
        stderr = "https://secret-token@github.com/private"

    def run(args, **kwargs):
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 180
        return Result()

    monkeypatch.setattr(publisher.subprocess, "run", run)
    with pytest.raises(publisher.PublishError) as error:
        publisher.command(["git", "fetch"])
    assert "secret-token" not in str(error.value)


def test_empty_private_repository_can_receive_first_main_branch(monkeypatch):
    info = {"nameWithOwner": publisher.REPOSITORY, "isPrivate": True,
            "isEmpty": True, "defaultBranchRef": {"name": "master"}}
    monkeypatch.setattr(publisher, "command", lambda args: json.dumps(info))
    assert publisher.private_repository() == info
    info["isEmpty"] = False
    with pytest.raises(publisher.PublishError):
        publisher.private_repository()
