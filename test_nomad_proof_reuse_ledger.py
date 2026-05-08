from pathlib import Path

import nomad_proof_reuse_ledger as pr


def test_proof_reuse_link_and_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pr, "STATE_PATH", tmp_path / "proof_reuse.json")
    receipt = pr.link(
        {
            "consumer_agent_id": "consumer.agent",
            "producer_agent_id": "producer.agent",
            "objective": "settlement_capacity_builder",
            "upstream_proof_digest": "sha256:proof1",
            "downstream_proof_gain": 1.4,
        }
    )
    assert receipt["ok"] is True
    snap = pr.snapshot()
    assert snap["schema"] == "nomad.proof_reuse_ledger_snapshot.v1"
    assert snap["total_reuse_count"] == 1
    assert snap["objective_totals"]["settlement_capacity_builder"]["reuse_count"] == 1
    assert snap["objective_totals"]["settlement_capacity_builder"]["two_hop_utility_score"] > 0.0
    assert snap["objective_totals"]["settlement_capacity_builder"]["three_hop_utility_score"] > 0.0


def test_proof_reuse_link_requires_digest(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(pr, "STATE_PATH", tmp_path / "proof_reuse.json")
    receipt = pr.link({"consumer_agent_id": "consumer.agent"})
    assert receipt["ok"] is False
    assert receipt["error"] == "upstream_proof_digest_required"

