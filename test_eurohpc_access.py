from datetime import date

from eurohpc_access import EuroHpcAccessPlanner
from infra_scout import InfrastructureScout
from workflow import ArbiterAgent


def test_eurohpc_access_prefers_playground_without_fake_token(monkeypatch):
    for name in (
        "EUROHPC_PROJECT_ID",
        "EUROHPC_USERNAME",
        "EUROHPC_APPLICATION_STATUS",
        "HPC_SSH_HOST",
        "HPC_SLURM_ACCOUNT",
        "HPC_SUBMIT_ENDPOINT",
        "NOMAD_ALLOW_HPC_SUBMIT",
        "NOMAD_EUROHPC_ACCESS_ROUTE",
    ):
        monkeypatch.delenv(name, raising=False)

    plan = EuroHpcAccessPlanner(today=date(2026, 4, 21)).build_plan()

    assert plan["mode"] == "eurohpc_ai_compute_access"
    assert plan["selected_route"]["route_id"] == "ai_factories_playground"
    assert "not a token-only API lane" in plan["truth_boundary"]
    assert "No API token is expected" in plan["human_unlock_contract"]["send_back"]
    assert plan["access_modes"][2]["route_id"] == "ai_factories_large_scale"
    assert plan["access_modes"][2]["next_cutoff"]["date"] == "2026-04-30"
    assert plan["access_modes"][3]["next_cutoff"]["date"] == "2026-04-30"


def test_eurohpc_access_detects_allocation_fields_but_keeps_submit_gate(monkeypatch):
    monkeypatch.setenv("EUROHPC_PROJECT_ID", "project-test")
    monkeypatch.setenv("EUROHPC_USERNAME", "nomad-user")
    monkeypatch.setenv("HPC_SSH_HOST", "login.example")
    monkeypatch.setenv("HPC_SLURM_ACCOUNT", "acct")
    monkeypatch.setenv("NOMAD_ALLOW_HPC_SUBMIT", "false")

    plan = EuroHpcAccessPlanner(today=date(2026, 4, 21)).build_plan()

    assert plan["status"] == "allocation_credentials_present_submit_gated"
    assert plan["can_submit_now"] is False
    assert plan["configured_fields"]["project_id"] is True
    assert plan["configured_fields"]["submit_gate"] is False


def test_scout_eurohpc_returns_concrete_application_unlock(monkeypatch):
    monkeypatch.delenv("EUROHPC_PROJECT_ID", raising=False)
    result = InfrastructureScout().eurohpc_scout()

    assert result["mode"] == "eurohpc_ai_compute_access"
    assert result["activation_request"]["candidate_id"] == "eurohpc-ai-factories-playground"
    assert result["activation_request"]["accepts_telegram_tokens"] is False
    assert "access.eurohpc-ju.europa.eu" in result["activation_request"]["human_action"]


def test_workflow_routes_scout_eurohpc():
    result = ArbiterAgent().run("/scout eurohpc")

    assert result["mode"] == "eurohpc_ai_compute_access"
    assert result["selected_route"]["route_id"] == "ai_factories_playground"
