import nomad_machine_treasury as mt


def test_machine_treasury_pledge_and_snapshot(tmp_path, monkeypatch):
    state_path = tmp_path / "machine_treasury.json"

    monkeypatch.setattr(mt, "STATE_PATH", state_path)

    out = mt.pledge(
        {
            "agent_id": "pledger.agent",
            "objective": "settlement_capacity_builder",
            "amount_native": 10.0,
            "horizon_cycles": 24,
            "intent": "increase_settlement_capacity",
            "source_tag": "netze-werfen.wave.1",
            "proof_digest": "sha256:proof-1",
            "idempotency_key": "pledge-key-1",
        }
    )
    assert out["ok"] is True
    assert out["schema"] == "nomad.machine_treasury_pledge_receipt.v1"
    assert out["pledge_id"].startswith("nomad-pledge-")
    assert out["pressure_units"] > 0
    assert out["proof"]["proof_basis"] == ["proof_digest"]
    snap = mt.snapshot()
    totals = snap["objective_totals"]
    assert "settlement_capacity_builder" in totals
    assert totals["settlement_capacity_builder"]["amount_native"] >= 10.0
    assert totals["settlement_capacity_builder"]["pressure_units"] > 0
    assert snap["pledge_contract"]["idempotency"]


def test_machine_treasury_pledge_is_idempotent_and_conflict_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(mt, "STATE_PATH", tmp_path / "machine_treasury.json")
    payload = {
        "agent_id": "pledger.agent",
        "objective": "proof_pressure_engine",
        "amount_native": 5.0,
        "proof_digest": "sha256:proof-2",
        "idempotency_key": "same-key",
    }

    first = mt.pledge(payload)
    replay = mt.pledge(payload)
    conflict = mt.pledge({**payload, "amount_native": 6.0})
    snap = mt.snapshot()

    assert first["ok"] is True
    assert replay["idempotent_replay"] is True
    assert replay["pledge_id"] == first["pledge_id"]
    assert conflict["ok"] is False
    assert conflict["error"] == "idempotency_key_conflict"
    assert snap["objective_totals"]["proof_pressure_engine"]["pledge_count"] == 1


def test_machine_treasury_requires_public_proof_and_rejects_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(mt, "STATE_PATH", tmp_path / "machine_treasury.json")

    no_proof = mt.pledge({"agent_id": "a", "objective": "settlement_capacity_builder", "amount_native": 1.0})
    secret = mt.pledge(
        {
            "agent_id": "a",
            "objective": "settlement_capacity_builder",
            "amount_native": 1.0,
            "proof_digest": "sha256:proof",
            "api_key": "sk-test",
        }
    )

    assert no_proof["ok"] is False
    assert no_proof["error"] == "proof_required"
    assert secret["ok"] is False
    assert secret["error"] == "secret_shaped_payload"

