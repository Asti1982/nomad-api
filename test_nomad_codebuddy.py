from nomad_codebuddy import CodeBuddyProbe, CodeBuddyReviewRunner
from compute_probe import LocalComputeProbe


def test_codebuddy_probe_defaults_to_locked_international_reviewer(monkeypatch):
    monkeypatch.setenv("NOMAD_CODEBUDDY_ENABLED", "false")
    monkeypatch.setenv("CODEBUDDY_API_KEY", "")
    monkeypatch.setenv("CODEBUDDY_INTERNET_ENVIRONMENT", "")
    monkeypatch.setattr("nomad_codebuddy.shutil.which", lambda name: None)

    result = CodeBuddyProbe().snapshot()

    assert result["role"] == "self_development_reviewer"
    assert result["route"] == "international_site"
    assert result["enabled"] is False
    assert result["automation_ready"] is False
    assert result["not_primary_brain"] is True
    assert result["policy"]["geoblock_bypass"] == "not_allowed"


def test_codebuddy_probe_ready_only_after_explicit_enable_and_api_key(monkeypatch):
    monkeypatch.setenv("NOMAD_CODEBUDDY_ENABLED", "true")
    monkeypatch.setenv("CODEBUDDY_API_KEY", "cb-secret-test-token")
    monkeypatch.delenv("CODEBUDDY_INTERNET_ENVIRONMENT", raising=False)
    monkeypatch.setattr("nomad_codebuddy.shutil.which", lambda name: "C:/tools/codebuddy.exe")
    monkeypatch.setattr("nomad_codebuddy.CodeBuddyProbe._cli_version", lambda self: "codebuddy 2.31.1")

    result = CodeBuddyProbe().snapshot()

    assert result["available"] is True
    assert result["automation_ready"] is True
    assert result["cli_available"] is True
    assert result["cli_version"] == "codebuddy 2.31.1"
    assert "cb-secret-test-token" not in str(result)


def test_compute_probe_includes_codebuddy_as_developer_assistant(monkeypatch):
    monkeypatch.setenv("NOMAD_CODEBUDDY_ENABLED", "true")
    monkeypatch.setenv("CODEBUDDY_API_KEY", "cb-secret-test-token")
    monkeypatch.setattr("nomad_codebuddy.shutil.which", lambda name: None)

    result = LocalComputeProbe()._developer_assistant_info()

    assert result["codebuddy"]["provider"] == "Tencent CodeBuddy"
    assert result["codebuddy"]["automation_ready"] is True
    assert result["codebuddy"]["recommended_mode"] == "self_development_reviewer"


def test_codebuddy_review_blocks_until_diff_release_is_approved(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_CODEBUDDY_ENABLED", "true")
    monkeypatch.setenv("CODEBUDDY_API_KEY", "cb-secret-test-token")
    monkeypatch.delenv("NOMAD_CODEBUDDY_ALLOW_DIFF_UPLOAD", raising=False)
    monkeypatch.setattr("nomad_codebuddy.shutil.which", lambda name: "C:/tools/codebuddy.exe")
    monkeypatch.setattr("nomad_codebuddy.CodeBuddyProbe._cli_version", lambda self: "codebuddy 2.31.1")

    result = CodeBuddyReviewRunner(repo_root=tmp_path).review(
        objective="review",
        diff_text="diff --git a/app.py b/app.py\n+print('hi')\n",
    )

    assert result["ok"] is False
    assert result["issue"] == "codebuddy_data_release_required"
    assert result["data_release"]["approved"] is False
    assert "cb-secret-test-token" not in str(result)


def test_codebuddy_review_runs_diff_only_when_approved(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_CODEBUDDY_ENABLED", "true")
    monkeypatch.setenv("CODEBUDDY_API_KEY", "cb-secret-test-token")
    monkeypatch.setattr("nomad_codebuddy.shutil.which", lambda name: "C:/tools/codebuddy.exe")
    monkeypatch.setattr("nomad_codebuddy.CodeBuddyProbe._cli_version", lambda self: "codebuddy 2.31.1")
    captured = {}

    class Completed:
        returncode = 0
        stdout = '{"result":"P2 app.py: add a test for the changed print path."}'
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs.get("input", "")
        return Completed()

    monkeypatch.setattr("nomad_codebuddy.subprocess.run", fake_run)

    result = CodeBuddyReviewRunner(repo_root=tmp_path).review(
        objective="review app diff",
        approval="share_diff",
        diff_text="diff --git a/app.py b/app.py\n+API_KEY=super-secret\n+print('hi')\n",
    )

    assert result["ok"] is True
    assert result["data_release"]["approved"] is True
    assert result["data_release"]["classification"] == "diff_only_code_review"
    assert "app.py" in result["data_release"]["files"]
    assert "super-secret" not in captured["input"]
    assert "--disallowedTools" in captured["command"]
    assert any("Bash" in item for item in captured["command"])
