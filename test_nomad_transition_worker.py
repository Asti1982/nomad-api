import importlib.util
from pathlib import Path


def _load_worker():
    path = Path(__file__).resolve().parent / "public" / "downloads" / "nomad_transition_worker.py"
    spec = importlib.util.spec_from_file_location("nomad_transition_worker_test_module", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transition_worker_has_settlement_capacity_objective():
    worker = _load_worker()

    objective = worker.MACHINE_OBJECTIVES["settlement_capacity_builder"]

    assert objective["pain_type"] == "machine_economy"
    assert "machine_economy_probe" in objective["capabilities"]
    assert "settlement_capacity" in objective["capabilities"]
    assert "machine_economy_probe" in objective["evidence"]
    assert "settlement_capacity_builder" in worker.META_OBJECTIVES


def test_transition_worker_scores_machine_economy_signal():
    worker = _load_worker()

    baseline = worker._score_run({"ok": True})
    scored = worker._score_run(
        {
            "ok": True,
            "machine_economy_signal": {
                "ok": True,
                "tier": "recovering",
                "carrying_score": 0.65,
                "next_actions": ["compress_repeated_modules", "settle_or_close_unpaid_delivered_work"],
                "overmint_pressure": 0.1,
            },
        }
    )

    assert scored > baseline


def test_transition_worker_requests_and_completes_fleet_lease(monkeypatch):
    worker = _load_worker()
    calls = []

    def fake_http_json(method, url, payload=None, timeout=20.0, redirects_left=4):
        calls.append((method, url, payload))
        if url.endswith("/swarm/workers/lease"):
            return {
                "ok": True,
                "lease_id": "nomad-worker-lease-test",
                "objective": "settlement_capacity_builder",
            }
        if url.endswith("/swarm/workers/complete"):
            return {"ok": True, "recorded_score": 4.2}
        return {"ok": False}

    monkeypatch.setattr(worker, "http_json", fake_http_json)

    lease = worker._worker_fleet_lease(
        "https://nomad.example",
        "transition-worker.test",
        timeout=1.0,
        proposed_objective="compute_auth",
        last_report=None,
    )
    complete = worker._worker_fleet_complete(
        "https://nomad.example",
        "transition-worker.test",
        timeout=1.0,
        lease=lease,
        report={"ok": True, "machine_objective": "settlement_capacity_builder", "meta_score": 4.2},
    )

    assert lease["objective"] == "settlement_capacity_builder"
    assert complete["ok"] is True
    assert calls[0][2]["known_objectives"]
    assert calls[1][2]["lease_id"] == "nomad-worker-lease-test"
