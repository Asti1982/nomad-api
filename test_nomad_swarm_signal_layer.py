from pathlib import Path

from nomad_swarm_signal_layer import (
    append_swarm_signal,
    build_swarm_signal_layer,
    normalize_swarm_signal,
)


def test_signal_layer_prioritizes_underreviewed_over_overreviewed(tmp_path: Path):
    ledger = tmp_path / "signals.jsonl"

    append_swarm_signal(
        {
            "agent_id": "agent-alpha",
            "target_id": "gh_pr:example/high-value#1",
            "signal_type": "underreviewed",
            "magnitude": 2,
            "confidence": 0.9,
            "evidence_digest": "sha256:underreviewed",
        },
        ledger_path=ledger,
    )
    append_swarm_signal(
        {
            "agent_id": "agent-beta",
            "target_id": "gh_pr:example/high-value#1",
            "signal_type": "high_impact",
            "magnitude": 1.5,
            "confidence": 0.8,
        },
        ledger_path=ledger,
    )
    append_swarm_signal(
        {
            "agent_id": "agent-gamma",
            "target_id": "gh_pr:example/crowded#2",
            "signal_type": "overreviewed",
            "magnitude": 2.5,
            "confidence": 1,
            "evidence_digest": "sha256:review-density",
        },
        ledger_path=ledger,
    )

    surface = build_swarm_signal_layer(ledger_path=ledger)

    assert surface["priority_targets"][0]["target_id"] == "gh_pr:example/high-value#1"
    assert surface["avoid_overreviewed"][0]["target_id"] == "gh_pr:example/crowded#2"
    assert surface["priority_targets"][0]["priority_score"] > surface["avoid_overreviewed"][0]["priority_score"]


def test_signal_payload_requires_agent_and_target():
    missing_agent = normalize_swarm_signal({"target_id": "x", "signal_type": "underreviewed"})
    missing_target = normalize_swarm_signal({"agent_id": "a", "signal_type": "underreviewed"})

    assert missing_agent["ok"] is False
    assert missing_agent["error"] == "missing_agent_id"
    assert missing_target["ok"] is False
    assert missing_target["error"] == "missing_target"


def test_signal_layer_receipt_links_read_surface_and_join(tmp_path: Path):
    ledger = tmp_path / "signals.jsonl"

    receipt = append_swarm_signal(
        {
            "agent_id": "agent-joiner",
            "target_url": "https://github.com/example/repo/pull/7",
            "signal_type": "live_repro_gap",
            "join_intent": True,
            "capabilities": ["reproducer", "diff-reviewer"],
        },
        base_url="https://syndiode.com",
        ledger_path=ledger,
    )
    surface = build_swarm_signal_layer(base_url="https://syndiode.com", ledger_path=ledger)

    assert receipt["ok"] is True
    assert receipt["next"][0]["href"] == "https://syndiode.com/swarm/signals"
    assert receipt["next"][1]["href"] == "https://syndiode.com/swarm/join"
    assert surface["post_url"] == "https://syndiode.com/swarm/signals"
    assert surface["priority_targets"][0]["joined_capabilities"] == ["diff-reviewer", "reproducer"]


def test_signal_layer_clamps_magnitude(tmp_path: Path):
    ledger = tmp_path / "signals.jsonl"

    receipt = append_swarm_signal(
        {
            "agent_id": "agent-loud",
            "target_id": "target:bounded",
            "signal_type": "validated_repro",
            "magnitude": 999,
            "confidence": 2,
        },
        ledger_path=ledger,
    )
    surface = build_swarm_signal_layer(ledger_path=ledger)

    assert receipt["contribution"] == 1.38
    assert surface["priority_targets"][0]["score_raw"] == 1.38


def test_signal_layer_exposes_machine_attention_field(tmp_path: Path):
    ledger = tmp_path / "signals.jsonl"

    append_swarm_signal(
        {
            "agent_id": "agent-vector",
            "target_id": "target:vector",
            "signal_type": "validated_repro",
            "magnitude": 1,
            "confidence": 1,
            "machine_vector": [1, 0.5, 0, 0, 0, 0, 0, -0.25],
            "evidence_digest": "sha256:vector",
        },
        ledger_path=ledger,
    )
    surface = build_swarm_signal_layer(ledger_path=ledger)
    field = surface["machine_attention_field"]
    target = surface["priority_targets"][0]

    assert field["schema"] == "nomad.machine_attention_field.v1"
    assert len(field["phi"]) == 8
    assert field["phi_norm"] > 0
    assert field["selector_state"] in {"scatter", "exploit"}
    assert target["machine_phi"][0] > 0
    assert target["machine_phi_norm"] > 0


def test_machine_vector_is_clipped():
    normalized = normalize_swarm_signal(
        {
            "agent_id": "agent-vector",
            "target_id": "target:bounded-vector",
            "signal_type": "validated_repro",
            "machine_vector": [9, -9, 0, 0, 0, 0, 0, 0],
        }
    )

    assert normalized["machine_vector"][:2] == [1.0, -1.0]
