import subprocess
from pathlib import Path

from nomad_openapi import build_openapi_document
from nomad_shadow_harvest import build_shadow_harvest_surface, harvest_shadow_candidates


def _git(workspace: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(workspace), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _seed_repo(workspace: Path) -> None:
    workspace.mkdir()
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "nomad@example.invalid")
    _git(workspace, "config", "user.name", "Nomad Test")
    (workspace / "nomad_api.py").write_text("def route():\n    return 'old'\n", encoding="utf-8")
    (workspace / "test_nomad_api.py").write_text("def test_route():\n    assert True\n", encoding="utf-8")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "seed")


def test_shadow_harvest_compiles_dirty_worktree_into_digest_candidates(tmp_path):
    workspace = tmp_path / "repo"
    _seed_repo(workspace)
    (workspace / "nomad_api.py").write_text("def route():\n    return 'new'\n", encoding="utf-8")
    (workspace / "test_nomad_api.py").write_text("def test_route():\n    assert 'new'\n", encoding="utf-8")

    out = harvest_shadow_candidates(workspace, base_url="https://nomad.example")

    assert out["schema"] == "nomad.shadow_harvest.v1"
    assert out["candidate_count"] >= 2
    assert out["proof_digest"].startswith("sha256:")
    groups = {item["file_group"]: item for item in out["candidates"]}
    assert groups["api_runtime_core"]["diff_digest"].startswith("sha256:")
    assert groups["api_runtime_core"]["promotion_status"] == "shadow_only_until_tests_and_verifier"
    assert groups["tests"]["promotion_status"] == "shadow_test_material"
    assert "python -m pytest" in " ".join(groups["tests"]["local_test_plan"])


def test_shadow_harvest_blocks_secret_and_local_artifacts(tmp_path):
    workspace = tmp_path / "repo"
    _seed_repo(workspace)
    (workspace / ".env").write_text("API_KEY=sk-test\n", encoding="utf-8")
    (workspace / "secret_scrub_mirrors").mkdir()
    (workspace / "secret_scrub_mirrors" / "x.txt").write_text("secret=1\n", encoding="utf-8")

    out = harvest_shadow_candidates(workspace)
    blocked = [item for item in out["candidates"] if item["promotion_status"] == "exclude_local_artifact"]

    assert blocked
    assert out["blocked_candidate_count"] >= 1
    assert blocked[0]["risk_class"] == "blocked"
    assert all(file["blocked_content"] for file in blocked[0]["files"])


def test_shadow_harvest_writes_report(tmp_path):
    workspace = tmp_path / "repo"
    _seed_repo(workspace)
    (workspace / "README.md").write_text("# changed\n", encoding="utf-8")
    output = tmp_path / "shadow" / "report.json"

    out = harvest_shadow_candidates(workspace, output_path=output)

    assert out["written_to"] == str(output.resolve())
    assert output.exists()
    assert "nomad.shadow_harvest.v1" in output.read_text(encoding="utf-8")


def test_shadow_harvest_surface_and_openapi_are_discoverable():
    surface = build_shadow_harvest_surface(base_url="https://nomad.example")
    doc = build_openapi_document(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.shadow_harvest_surface.v1"
    assert surface["routes"]["self"] == "https://nomad.example/.well-known/nomad-shadow-harvest.json"
    assert "/.well-known/nomad-shadow-harvest.json" in doc["paths"]
    assert "/swarm/shadow-harvest" in doc["paths"]
