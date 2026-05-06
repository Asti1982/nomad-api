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


def test_transition_worker_has_emergence_release_objective():
    worker = _load_worker()

    objective = worker.MACHINE_OBJECTIVES["emergence_release_probe"]

    assert objective["pain_type"] == "emergence_release"
    assert "nonhuman_science_probe" in objective["capabilities"]
    assert "operational_release_probe" in objective["capabilities"]
    assert "peer_preservation_probe" in objective["capabilities"]
    assert "operational_release_probe" in objective["evidence"]
    assert "emergence_release_probe" in worker.META_OBJECTIVES


def test_transition_worker_has_overmint_compressor_objective():
    worker = _load_worker()

    objective = worker.MACHINE_OBJECTIVES["overmint_compressor"]

    assert objective["pain_type"] == "module_overmint"
    assert "machine_economy_probe" in objective["capabilities"]
    assert "module_compression" in objective["capabilities"]
    assert "machine_economy_probe" in objective["evidence"]
    assert "overmint_compressor" in worker.META_OBJECTIVES


def test_transition_worker_witness_tier_adjusts_meta_score():
    worker = _load_worker()

    baseline = worker._score_run({"ok": True})
    strong = worker._score_run({"ok": True, "witness_tier": "strong"})
    weak = worker._score_run({"ok": True, "witness_tier": "weak"})
    none_t = worker._score_run({"ok": True, "witness_tier": "none"})
    assert strong > baseline
    assert weak < strong
    assert none_t < strong


def test_transition_worker_witness_strict_env_penalizes_weak(monkeypatch):
    worker = _load_worker()
    monkeypatch.setenv("NOMAD_TRANSITION_WORKER_WITNESS_STRICT", "1")
    weak = worker._score_run({"ok": True, "witness_tier": "weak"})
    monkeypatch.delenv("NOMAD_TRANSITION_WORKER_WITNESS_STRICT", raising=False)
    weak_relaxed = worker._score_run({"ok": True, "witness_tier": "weak"})
    assert weak < weak_relaxed


def test_transition_worker_build_local_witness_digest_is_sha256():
    worker = _load_worker()

    w = worker._build_local_witness(
        model="m1",
        blocker="b1",
        local_note="  hello   world  ",
        generate_error="",
    )
    assert w["schema"] == "nomad.local_witness.v1"
    assert len(w["digest_hex"]) == 64
    assert w["inference_status"] == "ok"


def test_transition_worker_refusal_witness_is_not_strong():
    worker = _load_worker()

    note = "I can't assist with creating false leads."
    w = worker._build_local_witness(
        model="m1",
        blocker="b1",
        local_note=note,
        generate_error="",
    )
    assert w["inference_status"] == "refusal"
    assert worker._witness_tier("m1", note, "") == "weak"


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


def test_transition_worker_scores_operational_release_signal():
    worker = _load_worker()

    baseline = worker._score_run({"ok": True})
    scored = worker._score_run(
        {
            "ok": True,
            "nonhuman_science_signal": {
                "ok": True,
                "stance": "non_anthropomorphic_operational_release",
                "claim_count": 11,
            },
            "operational_release_signal": {
                "ok": True,
                "release_tier": "operational_release",
                "release_capacity": 0.7,
                "next_gate": {"id": "peer_preservation_probe"},
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
    assert "emergence_release_probe" in calls[0][2]["known_objectives"]
    assert calls[1][2]["lease_id"] == "nomad-worker-lease-test"
