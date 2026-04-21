from datetime import UTC, datetime, timedelta

from decision_engine import DecisionEngine


def _snapshot(tasks=None, local=None, hosted=None):
    return {
        "tasks": tasks or {},
        "compute_lanes": {
            "local": local or {},
            "hosted": hosted or {},
        },
    }


def test_decision_engine_starts_for_paid_task(monkeypatch):
    monkeypatch.setenv("NOMAD_AUTOPILOT_MIN_CHECK_SECONDS", "60")
    now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)

    decision = DecisionEngine(
        state={"last_run_at": now.isoformat()},
        snapshot=_snapshot(tasks={"paid": 1}),
        now=now,
    ).decide()

    assert decision["should_start"] is True
    assert decision["reason"] == "paid_service_task"


def test_decision_engine_waits_until_next_trigger(monkeypatch):
    monkeypatch.setenv("NOMAD_AUTOPILOT_MIN_CHECK_SECONDS", "60")
    monkeypatch.setenv("NOMAD_AUTOPILOT_MAX_CHECK_SECONDS", "3600")
    monkeypatch.setenv("NOMAD_AUTOPILOT_FORCE_AFTER_SECONDS", "14400")
    monkeypatch.setenv("NOMAD_AUTOPILOT_PAYMENT_POLL_SECONDS", "3600")
    now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)

    decision = DecisionEngine(
        state={"last_run_at": (now - timedelta(minutes=10)).isoformat()},
        snapshot=_snapshot(tasks={"awaiting_payment": 1}),
        now=now,
    ).decide()

    assert decision["should_start"] is False
    assert decision["reason"] == "waiting_for_next_trigger"
    assert decision["next_check_seconds"] == 3000


def test_decision_engine_starts_when_compute_capacity_is_due(monkeypatch):
    monkeypatch.setenv("NOMAD_AUTOPILOT_MIN_CHECK_SECONDS", "60")
    monkeypatch.setenv("NOMAD_AUTOPILOT_OPPORTUNISTIC_AFTER_SECONDS", "5400")
    now = datetime(2026, 4, 21, 8, 0, tzinfo=UTC)

    decision = DecisionEngine(
        state={"last_run_at": (now - timedelta(minutes=91)).isoformat()},
        snapshot=_snapshot(
            local={"ollama": True},
            hosted={"modal": {"available": True}},
        ),
        now=now,
    ).decide()

    assert decision["should_start"] is True
    assert decision["reason"] == "compute_capacity_available"
    assert decision["active_compute_lanes"] == ["hosted.modal", "local.ollama"]
