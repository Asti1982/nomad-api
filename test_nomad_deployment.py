from nomad_deployment import (
    DEFAULT_GITHUB_DEPLOY_BRANCH,
    derive_public_api_url,
    modal_deployment_snapshot,
    modal_secret_name,
    modal_should_include,
)


def test_modal_deployment_snapshot_defaults_to_syndiode_branch(monkeypatch, tmp_path):
    monkeypatch.delenv("NOMAD_GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("NOMAD_GITHUB_DEPLOY_BRANCH", raising=False)
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "onrender.syndiode.com")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("NOMAD_MODAL_SECRET_NAME", "nomad-env")

    snapshot = modal_deployment_snapshot(repo_root=tmp_path)

    assert snapshot["github_branch"] == DEFAULT_GITHUB_DEPLOY_BRANCH
    assert snapshot["public_api_url"] == "https://onrender.syndiode.com"
    assert snapshot["deploy_commands"][0] == "modal secret create nomad-env --from-dotenv .env --force"
    assert snapshot["deploy_commands"][1].startswith("modal deploy modal_nomad.py")


def test_modal_deployment_snapshot_prefers_public_url_and_repo_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_GITHUB_REPOSITORY", "Asti1982/syndiode")
    monkeypatch.setenv("NOMAD_GITHUB_DEPLOY_BRANCH", "feature-launch")
    monkeypatch.setenv("NOMAD_PUBLIC_API_URL", "https://agents.syndiode.com")
    monkeypatch.setenv("NOMAD_RENDER_DOMAIN", "api.syndiode.com")

    snapshot = modal_deployment_snapshot(repo_root=tmp_path)

    assert snapshot["github_repository"] == "Asti1982/syndiode"
    assert snapshot["github_branch"] == "feature-launch"
    assert snapshot["public_api_url"] == "https://agents.syndiode.com"


def test_modal_secret_name_accepts_explicit_none(monkeypatch):
    monkeypatch.setenv("NOMAD_MODAL_SECRET_NAME", "none")

    assert modal_secret_name() == ""


def test_modal_copy_filter_excludes_state_and_keeps_seed_inputs():
    assert modal_should_include("workflow.py") is True
    assert modal_should_include("cryptogrift_guard_agent.py") is True
    assert modal_should_include("public/nomad.html") is True
    assert modal_should_include("nomad_agent_seed_sources.json") is True
    assert modal_should_include(".env") is False
    assert modal_should_include("nomad_agent_campaigns.json") is False
    assert modal_should_include("nomad_autonomous_artifacts/output.txt") is False


def test_derive_public_api_url_prefers_render_domain_when_local():
    assert (
        derive_public_api_url(
            configured_public_url="http://localhost:8787",
            render_domain="api.syndiode.com",
        )
        == "https://api.syndiode.com"
    )
    assert (
        derive_public_api_url(
            configured_public_url="https://nomad.syndiode.com",
            render_domain="api.syndiode.com",
        )
        == "https://nomad.syndiode.com"
    )
