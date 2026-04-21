import json

import pytest

from truth_ledger import (
    EVIDENCE_WEIGHTS,
    EvidenceKind,
    LaneType,
    LedgerEntry,
    OutcomeKind,
    RegressionCheck,
    TruthDensityLedger,
)


def test_evidence_weights_keep_strong_signals_stronger():
    assert EVIDENCE_WEIGHTS[EvidenceKind.TASK_PAID] == 2.0
    assert EVIDENCE_WEIGHTS[EvidenceKind.REGRESSION_PREVENTED] == 2.0
    assert EVIDENCE_WEIGHTS[EvidenceKind.SOLUTION_ACCEPTED] == 1.5
    assert EVIDENCE_WEIGHTS[EvidenceKind.CONTACT_MADE] == 0.4


def test_ledger_entry_scores_hashes_and_reuse_value():
    entry = LedgerEntry(agent_id="agent-1", task_description="Fix auth bug")
    entry.add_evidence(EvidenceKind.REPRODUCTION, "Reproduced ERROR=429")
    entry.add_evidence(EvidenceKind.SOLUTION_ACCEPTED, "Solution accepted")
    before_reuse = entry.reuse_value
    first_hash = entry.compute_hash()

    entry.reuse_count = 3

    assert entry.raw_evidence_score == 2.5
    assert entry.truth_density == 0.25
    assert entry.reuse_value > before_reuse
    assert entry.compute_hash() != first_hash


def test_append_only_ledger_persists_collapsed_latest_state(tmp_path):
    ledger_path = tmp_path / "ledger.ndjson"
    ledger = TruthDensityLedger(ledger_path=ledger_path)
    entry = ledger.open_entry("agent-1", "Fix bug", LaneType.BUG_FIX)
    entry.add_evidence(EvidenceKind.TEST_PASSED, "test passed")
    closed, _, _ = ledger.close_entry(entry.entry_id, OutcomeKind.UNCONFIRMED)
    ledger.record_reuse(closed.entry_id, source="test")

    reloaded = TruthDensityLedger(ledger_path=ledger_path)

    assert reloaded.open_entries() == []
    assert reloaded.summary()["total_closed"] == 1
    assert reloaded.summary()["outcome_breakdown"][OutcomeKind.PARTIAL_SUCCESS.value] == 1
    assert reloaded.top_reusable(1)[0].reuse_count == 1
    assert (tmp_path / "truth_density_index.json").exists()


def test_close_unknown_entry_raises(tmp_path):
    ledger = TruthDensityLedger(ledger_path=tmp_path / "ledger.ndjson")

    with pytest.raises(KeyError):
        ledger.close_entry("ghost", OutcomeKind.FAILED)


def test_abandon_stale_closes_old_open_entries(tmp_path):
    ledger = TruthDensityLedger(ledger_path=tmp_path / "ledger.ndjson")
    entry = ledger.open_entry("agent-1", "stale task")
    entry.opened_at -= 7200

    assert ledger.abandon_stale(older_than_seconds=3600) == 1
    assert ledger.open_entries() == []
    assert ledger.summary()["outcome_breakdown"][OutcomeKind.ABANDONED.value] == 1


def test_regression_check_flags_low_truth_density_after_success_history():
    history = []
    for index in range(3):
        entry = LedgerEntry(agent_id=f"agent-{index}", lane=LaneType.BUG_FIX, outcome=OutcomeKind.VERIFIED_SUCCESS)
        entry.closed_at = entry.opened_at + 1
        entry.add_evidence(EvidenceKind.TASK_PAID, "paid")
        history.append(entry)
    new_entry = LedgerEntry(agent_id="agent-new", lane=LaneType.BUG_FIX, outcome=OutcomeKind.UNCONFIRMED)

    is_regression, reason = RegressionCheck().check(new_entry, history)

    assert is_regression is True
    assert "baseline" in reason


def test_build_entry_keeps_nomad_state_schema_and_adds_richer_fields():
    ledger = TruthDensityLedger()
    entry = ledger.build_entry(
        event={
            "event_id": "evt-1",
            "timestamp": "2026-04-21T12:00:00Z",
            "source": "test",
            "other_agent_id": "VerifierBot",
            "pain_type": "compute_auth",
        },
        help_result={
            "success": True,
            "task": "Agent observed ERROR=429",
            "pain_type": "compute_auth",
            "truth_density_increase": 0.12,
            "evidence": ["observed ERROR=429", "dry-run passed", "solution accepted"],
            "acceptance_count": 1,
            "outcome_status": "accepted",
        },
        prior_entries=[],
    )

    assert entry["schema"] == "nomad.truth_density_ledger_entry.v1"
    assert entry["lane"] == LaneType.COMPUTE_TASK.value
    assert entry["content_hash"]
    assert entry["raw_evidence_score"] >= 3.0
    assert entry["truth_score"] > 0.5
    assert entry["evidence_details"][0]["kind"] == EvidenceKind.REPRODUCTION.value


def test_update_entry_recomputes_evidence_details_and_hash():
    ledger = TruthDensityLedger()
    entry = ledger.build_entry(
        event={"event_id": "evt-2", "other_agent_id": "agent"},
        help_result={"success": False, "task": "unverified", "pain_type": "tool_failure"},
        prior_entries=[],
    )
    old_hash = entry["content_hash"]

    updated = ledger.update_entry(
        entry,
        success=True,
        evidence=["test passed", "deployment confirmed"],
        outcome_status="delivered",
        note="late verification",
    )

    assert updated["content_hash"] != old_hash
    assert updated["outcome"]["success"] is True
    assert {item["kind"] for item in updated["evidence_details"]} >= {
        EvidenceKind.TEST_PASSED.value,
        EvidenceKind.DEPLOYMENT_CONFIRMED.value,
    }
    json.dumps(updated, sort_keys=True)
