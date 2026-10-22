from creator_skill.web_ui import JobStore, _library, _project_from_source


def test_project_name_is_derived_and_normalized():
    assert (
        _project_from_source("https://www.tiktok.com/@nico_financial.ads")
        == "nico-financial-ads"
    )


def test_empty_library(tmp_path):
    assert _library(tmp_path / "workspaces") == {
        "categories": [],
        "projects": [],
    }


def test_tiktok_webpage_error_has_actionable_message(tmp_path):
    message = JobStore(tmp_path)._friendly_error(
        Exception("ERROR: [TikTok] Unexpected response from webpage request")
    )

    assert "canal público oficial" in message
