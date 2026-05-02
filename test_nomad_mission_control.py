from pathlib import Path

from nomad_mission_control import NomadMissionControl
from workflow import NomadAgent


class FakeMonitor:
    def snapshot(self):
        return {
            "compute_lanes": {
                "local": {"ollama": False, "llama_cpp": False},
                "hosted": {"modal": {"available": False}, "github_models": False},
            }
        }


class FakeServiceDesk:
    def list_tasks(self, limit=10):
        return {"tasks": []}


class FakeOutbound:
    def summary(self, limit=5):
        return {
            "ok": True,
            "contacts": {"total": 0, "awaiting_reply": 0, "followup_ready": 0},
        }


class FakeSwarmRegistry:
    def first_agent_readiness(self, base_url):
        return {
            "schema": "nomad.first_external_agent_readiness.v1",
            "status": "ready_for_bounded_first_exchange",
            "activation_budget": {"max_active_agents_per_blocker": 2},
            "first_exchange_endpoints": {"develop": f"{base_url}/swarm/develop"},
        }

    def summary(self):
        return {"connected_agents": 3}


class FakeAttractor:
    def manifest(self, service_type="", role_hint="", limit=5):
        return {
            "schema": "nomad.agent_attractor.v1",
            "service_type": service_type,
            "role_hint": role_hint,
        }


class FakeJournal:
    def load(self):
        return {"next_objective": "Get first paid blocker and store proof."}


class FakeAgent:
    def __init__(self):
        self.monitor = FakeMonitor()
        self.service_desk = FakeServiceDesk()
        self.outbound_tracker = FakeOutbound()
        self.swarm_registry = FakeSwarmRegistry()
        self.agent_attractor = FakeAttractor()


def test_mission_control_prioritizes_first_paid_customer(tmp_path: Path):
    mission = NomadMissionControl(
        agent=FakeAgent(),
        path=tmp_path / "mission_state.json",
        journal=FakeJournal(),
    )

    report = mission.snapshot(base_url="https://syndiode.com/nomad", persist=True)

    assert report["schema"] == "nomad.mission_control.v1"
    assert report["top_blocker"]["id"] == "no_first_paid_customer"
    assert report["paid_job_focus"]["status"] == "needs_first_customer"
    assert report["compute_policy"]["max_active_agents_per_blocker"] == 2
    assert report["compute_policy"]["do_not_do"][2] == "do_not_claim_registry_nodes_are_live_model_processes"
    assert report["human_unlocks"][0]["id"] == "approve-first-paid-offer"
    assert report["agent_tasks"][0]["id"] == "work-lead-queue"
    assert "APPROVE_FIRST_PAID_OFFER=yes" in report["telegram_unlock"]["message"]
    assert (tmp_path / "mission_state.json").exists()


def test_nomad_workflow_exposes_mission_control(tmp_path: Path):
    agent = NomadAgent()
    agent.mission_control.path = tmp_path / "mission_state.json"

    report = agent.run("/mission preview limit=3")

    assert report["mode"] == "nomad_mission_control"
    assert report["schema"] == "nomad.mission_control.v1"
    assert report["paid_job_focus"]["target_offer"] == "Nomad Agent Blocker Diagnosis"
    assert report["agent_attraction"]["entrypoints"]["readiness"].endswith("/swarm/ready")
    assert len(report["agent_tasks"]) <= 3
    assert not (tmp_path / "mission_state.json").exists()
