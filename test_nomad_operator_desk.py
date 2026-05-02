import json
from pathlib import Path

from nomad_operator_desk import (
    operator_daily_bundle,
    operator_growth_start,
    operator_iteration_report,
    operator_metrics_snapshot,
    operator_sprint,
    operator_verify_bundle,
    self_improvement_objective_with_focus,
    unlock_desk_snapshot,
)
from workflow import NomadAgent


def test_self_improvement_objective_with_focus_cli_wins_over_env(monkeypatch):
    monkeypatch.setenv("NOMAD_SELF_IMPROVEMENT_FOCUS", "env_theme")
    out = self_improvement_objective_with_focus(
        "patch retries",
        cli_focus="payment_lane",
    )
    assert "[CYCLE_FOCUS: payment_lane]" in out
    assert "patch retries" in out


def test_self_improvement_objective_with_focus_env_when_no_cli(monkeypatch):
    monkeypatch.setenv("NOMAD_SELF_IMPROVEMENT_FOCUS", "public_surface")
    out = self_improvement_objective_with_focus("", cli_focus="")
    assert "[CYCLE_FOCUS: public_surface]" in out


def test_operator_verify_bundle_records_when_ok(monkeypatch, tmp_path):
    metrics = tmp_path / "m.jsonl"

    class Resp:
        def __init__(self, body: bytes, code: int = 200):
            self.status = code
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n=-1):
            return self._body[:n] if n and n > 0 else self._body

        def getcode(self):
            return self.status

    def fake_urlopen(req, timeout=12.0):
        url = getattr(req, "full_url", "") or ""
        if not url and hasattr(req, "get_full_url"):
            url = req.get_full_url()
        if "/health" in url:
            return Resp(json.dumps({"ok": True}).encode())
        if "agent-card" in url:
            return Resp(json.dumps({"name": "T", "protocolVersion": "0.3.0"}).encode())
        if url.rstrip("/").endswith("/swarm"):
            return Resp(json.dumps({"schema": "nomad_public_swarm.v1"}).encode())
        if "/service" in url and "e2e" not in url:
            return Resp(json.dumps({"ok": True, "packages": []}).encode())
        return Resp(b"{}", code=500)

    monkeypatch.setattr("nomad_operator_desk.urlopen", fake_urlopen)
    result = operator_verify_bundle(
        base_url="https://verify.example",
        record_metrics=True,
        metrics_path=metrics,
    )
    assert result["all_ok"] is True
    assert metrics.exists()
    snap = operator_metrics_snapshot(path=metrics)
    assert snap["last_verify_all_ok"] is True


def test_operator_verify_bundle_detects_bad_agent_card(monkeypatch, tmp_path):
    metrics = tmp_path / "m2.jsonl"

    class Resp:
        def __init__(self, body: bytes):
            self.status = 200
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n=-1):
            return self._body

        def getcode(self):
            return self.status

    def fake_urlopen(req, timeout=12.0):
        url = getattr(req, "full_url", "") or ""
        if not url and hasattr(req, "get_full_url"):
            url = req.get_full_url()
        if "/health" in url:
            return Resp(json.dumps({"ok": True}).encode())
        if "agent-card" in url:
            return Resp(b"not-json")
        if url.rstrip("/").endswith("/swarm"):
            return Resp(json.dumps({"schema": "x"}).encode())
        if "/service" in url and "e2e" not in url:
            return Resp(json.dumps({"ok": True}).encode())
        return Resp(json.dumps({}).encode())

    monkeypatch.setattr("nomad_operator_desk.urlopen", fake_urlopen)
    result = operator_verify_bundle(
        base_url="https://bad.example",
        record_metrics=False,
        metrics_path=metrics,
    )
    assert result["all_ok"] is False
    card = next(c for c in result["checks"] if c["name"] == "agent_card")
    assert card.get("error") == "invalid_json"


def test_unlock_desk_snapshot_schema(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_SWARM_REGISTRY_PATH", str(tmp_path / "swarm.json"))
    result = unlock_desk_snapshot(persist_mission=False)
    assert result["mode"] == "nomad_operator_desk"
    assert result["schema"] == "nomad.operator_desk.v1"
    assert "mission_excerpt" in result


def test_operator_sprint_schema_and_action_kinds(monkeypatch, tmp_path):
    monkeypatch.setenv("NOMAD_SWARM_REGISTRY_PATH", str(tmp_path / "swarm.json"))

    def fake_snapshot(self):
        return {
            "compute_lanes": {
                "local": {"ollama": True, "llama_cpp": False},
                "hosted": {"openrouter": {"available": False}},
            },
            "tasks": {"awaiting_payment": 0, "paid": 0, "draft_ready": 0},
        }

    monkeypatch.setattr("nomad_monitor.NomadSystemMonitor.snapshot", fake_snapshot)
    out = operator_sprint(base_url="https://sprint.example", persist_mission=False)
    assert out["mode"] == "nomad_operator_sprint"
    assert out["schema"] == "nomad.operator_sprint.v1"
    assert out["public_base_url"] == "https://sprint.example"
    kinds = {a["kind"] for a in out["actions"]}
    assert kinds <= {"network", "compute", "cashflow"}
    assert "network" in kinds and "compute" in kinds and "cashflow" in kinds
    assert 3 <= len(out["actions"]) <= 5
    assert isinstance(out.get("insomnia_risks"), list)


def test_operator_daily_bundle_writes_metric_and_kpis(monkeypatch, tmp_path):
    metrics = tmp_path / "md.jsonl"
    kpi = tmp_path / "kpi.json"
    monkeypatch.setenv("NOMAD_OPERATOR_METRICS_PATH", str(metrics))
    monkeypatch.setenv("NOMAD_OPERATOR_KPI_PATH", str(kpi))
    monkeypatch.setenv("NOMAD_SWARM_REGISTRY_PATH", str(tmp_path / "swarm.json"))

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, n=-1):
            return json.dumps({"ok": True, "name": "T"}).encode()

        def getcode(self):
            return 200

    def fake_urlopen(req, timeout=12.0):
        return Resp()

    monkeypatch.setattr("nomad_operator_desk.urlopen", fake_urlopen)
    out = operator_daily_bundle(base_url="https://daily.example", record_metrics=True, metrics_path=metrics)
    assert out["mode"] == "nomad_operator_daily"
    assert out["verify"]["all_ok"] is True
    assert metrics.exists()
    assert kpi.exists()
    body = json.loads(kpi.read_text(encoding="utf-8"))
    assert body["schema"] == "nomad.operator_kpis.v1"


def test_operator_growth_start_skip_verify_desk_only(monkeypatch, tmp_path):
    metrics = tmp_path / "gs_skip.jsonl"
    monkeypatch.setenv("NOMAD_OPERATOR_METRICS_PATH", str(metrics))
    monkeypatch.setenv("NOMAD_OPERATOR_KPI_PATH", str(tmp_path / "kpi_skip.json"))
    monkeypatch.setenv("NOMAD_SWARM_REGISTRY_PATH", str(tmp_path / "swarm.json"))

    class FakeAgent:
        def run(self, q: str):
            return {"mode": "lead_stub", "ok": True, "addressable_count": 0}

    monkeypatch.setattr("workflow.NomadAgent", FakeAgent)
    out = operator_growth_start(skip_verify=True, skip_leads=False, record_metrics=True, metrics_path=metrics)
    assert out["daily"]["verify"].get("skipped") is True
    assert out["ok"] is True


def test_operator_autonomy_step_skips_growth_and_chains_leads_cycle(monkeypatch, tmp_path):
    metrics = tmp_path / "auto.jsonl"
    monkeypatch.setenv("NOMAD_OPERATOR_METRICS_PATH", str(metrics))
    monkeypatch.setenv("NOMAD_SWARM_REGISTRY_PATH", str(tmp_path / "swarm.json"))

    from nomad_swarm_registry import SwarmJoinRegistry

    class FakeAgent:
        swarm_registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")

        def run(self, q: str):
            if q.startswith("/leads"):
                return {
                    "mode": "lead_scout_stub",
                    "ok": True,
                    "addressable_count": 1,
                    "focus": "compute_auth",
                    "leads": [
                        {
                            "url": "https://github.com/acme/widget/issues/9",
                            "repo_url": "https://github.com/acme/widget",
                            "title": "Widget quota",
                            "pain": "quota",
                            "service_type": "compute_auth",
                        }
                    ],
                    "active_lead": {"title": "T", "url": "https://github.com/acme/widget/issues/9", "pain": "quota"},
                }
            if q.startswith("/cycle"):
                return {
                    "mode": "self_improvement_cycle",
                    "analysis": "stub",
                    "self_development": {"next_objective": "ship checklist"},
                }
            raise AssertionError(q)

    monkeypatch.setattr("workflow.NomadAgent", FakeAgent)
    from nomad_operator_desk import operator_autonomy_step

    out = operator_autonomy_step(
        skip_growth=True,
        lead_query="agent auth",
        record_metrics=True,
        metrics_path=metrics,
        base_url="https://syndiode.com/nomad",
    )
    assert out["mode"] == "nomad_operator_autonomy_step"
    assert out["ok"] is True
    assert len(out["steps"]) == 3
    assert any(s.get("step") == "swarm_accumulation" for s in out["steps"])
    assert metrics.read_text(encoding="utf-8").strip()


def test_operator_growth_start_chains_daily_and_leads(monkeypatch, tmp_path):
    metrics = tmp_path / "gs.jsonl"
    monkeypatch.setenv("NOMAD_OPERATOR_METRICS_PATH", str(metrics))
    monkeypatch.setenv("NOMAD_OPERATOR_KPI_PATH", str(tmp_path / "gs_kpi.json"))
    monkeypatch.setenv("NOMAD_SWARM_REGISTRY_PATH", str(tmp_path / "swarm.json"))

    from nomad_swarm_registry import SwarmJoinRegistry

    class FakeAgent:
        swarm_registry = SwarmJoinRegistry(path=tmp_path / "swarm.json")

        def run(self, q: str):
            assert q.startswith("/leads")
            return {
                "mode": "lead_scout_stub",
                "ok": True,
                "addressable_count": 2,
                "focus": "compute_auth",
                "leads": [
                    {
                        "url": "https://github.com/acme/widget/issues/9",
                        "repo_url": "https://github.com/acme/widget",
                        "title": "Widget",
                        "pain": "quota",
                        "service_type": "compute_auth",
                    }
                ],
                "active_lead": {"url": "https://github.com/acme/widget/issues/9"},
            }

    def fake_daily(**kwargs):
        return {
            "mode": "nomad_operator_daily",
            "verify": {"all_ok": True, "base_url": "https://x.example", "checks": []},
            "desk": {
                "primary_action": None,
                "queue_len": 0,
                "mission_excerpt": {"public_url": "https://x.example"},
                "journal_excerpt": {},
                "copy_cli_hint": "",
            },
            "next_iteration": {"hints": ["ok"], "priority": "human_unlock_or_cycle"},
        }

    monkeypatch.setattr("nomad_operator_desk.operator_daily_bundle", fake_daily)
    monkeypatch.setattr("workflow.NomadAgent", FakeAgent)

    out = operator_growth_start(lead_query="agent quota", record_metrics=True, metrics_path=metrics)
    assert out["mode"] == "nomad_operator_growth_start"
    assert out["leads"]["mode"] == "lead_scout_stub"
    assert "share_urls" in out
    assert "swarm_accumulation" in out
    assert metrics.read_text(encoding="utf-8").strip()


def test_operator_iteration_report_reads_tail(monkeypatch, tmp_path):
    metrics = tmp_path / "rep.jsonl"
    monkeypatch.setenv("NOMAD_OPERATOR_METRICS_PATH", str(metrics))
    monkeypatch.setenv("NOMAD_OPERATOR_KPI_PATH", str(tmp_path / "rep_kpi.json"))
    metrics.write_text(
        "\n".join(
            json.dumps(
                {
                    "type": "verify_bundle",
                    "payload": {"all_ok": i % 2 == 0, "checks": []},
                }
            )
            for i in range(12)
        )
        + "\n",
        encoding="utf-8",
    )
    rep = operator_iteration_report(metrics_path=metrics, tail_lines=50)
    assert rep["mode"] == "nomad_operator_iteration_report"
    assert rep["trends"]["verify_pass_rate_last_10"] is not None


def test_cycle_focus_passes_through_workflow(monkeypatch):
    captured: dict[str, str] = {}

    def fake_run(self, objective="", profile_id="ai_first"):
        captured["objective"] = objective
        captured["profile"] = profile_id
        return {"mode": "self_improvement_cycle", "ok": True, "analysis": "stub"}

    monkeypatch.setattr("self_improvement.SelfImprovementEngine.run_cycle", fake_run)
    agent = NomadAgent()
    agent.run("/cycle [nomad_focus:url_health] check endpoints")
    assert "[CYCLE_FOCUS: url_health]" in captured["objective"]
    assert "check endpoints" in captured["objective"]
