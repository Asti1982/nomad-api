from nomad_external_value import append_external_value_event
from nomad_external_value_reconciler import (
    _comment_acceptance_signals,
    build_external_value_followup,
    parse_github_external_ref,
    propose_external_value_transition,
    reconcile_external_value_ledger,
)
from nomad_cli import run_once


def _record(eid: str, stage: str):
    base = {
        "agent_id": "nomad.test",
        "external_id": eid,
        "stage": stage,
        "work_url": "https://github.com/Scottcjn/Rustchain/pull/1",
        "proof_digest": "sha256:p",
        "verifier_trace_digest": "sha256:v",
    }
    if stage == "found":
        base["work_url"] = ""
        base["proof_digest"] = ""
        base["verifier_trace_digest"] = ""
    return append_external_value_event(base)


def test_parse_github_review_external_ref():
    ref = parse_github_external_ref(
        "gh_review:Scottcjn/Rustchain#4576:4265850272",
        "https://github.com/Scottcjn/Rustchain/pull/4576#pullrequestreview-4265850272",
    )

    assert ref["ok"]
    assert ref["kind"] == "review"
    assert ref["repo"] == "Scottcjn/Rustchain"
    assert ref["number"] == 4576
    assert ref["review_id"] == 4265850272


def test_parse_github_issue_comment_external_ref_from_url():
    ref = parse_github_external_ref(
        "",
        "https://github.com/Scottcjn/rustchain-bounties/issues/2819#issuecomment-4422232793",
    )

    assert ref["ok"]
    assert ref["kind"] == "issue_comment"
    assert ref["repo"] == "Scottcjn/rustchain-bounties"
    assert ref["number"] == 2819
    assert ref["comment_id"] == 4422232793


def test_comment_acceptance_distinguishes_soft_ack_from_owner_acceptance():
    ref = {
        "kind": "issue_comment",
        "repo": "Scottcjn/rustchain-bounties",
        "number": 2819,
        "comment_id": 4422232793,
        "work_url": "https://github.com/Scottcjn/rustchain-bounties/issues/2819#issuecomment-4422232793",
    }
    comments = [
        {
            "url": "https://github.com/Scottcjn/rustchain-bounties/issues/2819#issuecomment-4422232793",
            "body": "Submission for this bounty: https://github.com/Scottcjn/Rustchain/pull/4542",
            "author": {"login": "Asti1982"},
            "authorAssociation": "NONE",
            "viewerDidAuthor": True,
        },
        {
            "url": "https://github.com/Scottcjn/rustchain-bounties/issues/2819#issuecomment-4422413599",
            "body": "+1",
            "author": {"login": "jaxint"},
            "authorAssociation": "CONTRIBUTOR",
        },
        {
            "url": "https://github.com/Scottcjn/rustchain-bounties/issues/2819#issuecomment-4422713337",
            "body": "Accepted review for @Asti1982; payout queued for PR https://github.com/Scottcjn/Rustchain/pull/4542. Tx hash: abc123.",
            "author": {"login": "Scottcjn"},
            "authorAssociation": "OWNER",
        },
    ]

    out = _comment_acceptance_signals(comments, ref=ref)

    assert out["soft_ack_signal"] is True
    assert out["owner_acceptance_signal"] is True
    assert out["payment_receipt"] is True
    assert out["acceptance_evidence_count"] == 1


def test_comment_acceptance_ignores_self_authored_echoes_after_claim():
    ref = {
        "kind": "issue_comment",
        "repo": "Scottcjn/rustchain-bounties",
        "number": 73,
        "comment_id": 4423366870,
        "work_url": "https://github.com/Scottcjn/rustchain-bounties/issues/73#issuecomment-4423366870",
    }
    comments = [
        {
            "url": "https://github.com/Scottcjn/rustchain-bounties/issues/73#issuecomment-4423366870",
            "body": "Outcome: approved on updated head. Payout details can be provided if accepted.",
            "author": {"login": "Asti1982"},
            "authorAssociation": "NONE",
            "viewerDidAuthor": True,
        },
        {
            "url": "https://github.com/Scottcjn/rustchain-bounties/issues/73#issuecomment-4423369999",
            "body": "Follow-up: approved on current head; payout details can be provided if accepted.",
            "author": {"login": "Asti1982"},
            "authorAssociation": "NONE",
            "viewerDidAuthor": True,
        },
    ]

    out = _comment_acceptance_signals(comments, ref=ref)

    assert out["soft_ack_signal"] is False
    assert out["owner_acceptance_signal"] is False
    assert out["payment_receipt"] is False


def test_soft_ack_alone_does_not_propose_approved():
    event = {"stage": "submitted"}
    proposal = propose_external_value_transition(event, {"ok": True, "soft_ack_signal": True})

    assert proposal["proposed_stage"] == ""
    assert proposal["reason"] == "awaiting_external_acceptance"


def test_followup_soft_ack_is_machine_hold_not_value():
    event = {
        "stage": "submitted",
        "external_id": "gh_issue_comment:Scottcjn/rustchain-bounties#73:4423366870",
        "work_url": "https://github.com/Scottcjn/rustchain-bounties/issues/73#issuecomment-4423366870",
    }
    status = {"ok": True, "soft_ack_signal": True}
    proposal = propose_external_value_transition(event, status)
    followup = build_external_value_followup(event, status, proposal)

    assert followup["action"] == "ignore_soft_ack_wait_for_owner_signal"
    assert followup["target_stage"] == "approved"
    assert "owner_or_maintainer_acceptance_signal" in followup["required_evidence"]


def test_followup_merged_waits_for_positive_payment_receipt():
    event = {
        "stage": "merged",
        "external_id": "gh_pr:Scottcjn/Rustchain#4542",
        "work_url": "https://github.com/Scottcjn/Rustchain/pull/4542",
    }
    status = {"ok": True, "merged": True, "payment_receipt": False, "amount_usd": 0}
    proposal = propose_external_value_transition(event, status)
    followup = build_external_value_followup(event, status, proposal)

    assert proposal["proposed_stage"] == ""
    assert proposal["reason"] == "merged_but_no_payment_receipt"
    assert followup["action"] == "await_payment_receipt"
    assert followup["priority"] > 0.9
    assert "positive_amount_usd" in followup["required_evidence"]


def test_reconcile_pr_merge_proposes_monotonic_approved_step(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev.jsonl"))
    eid = "gh_pr:Scottcjn/Rustchain#4542"
    assert _record(eid, "found")["ok"]
    assert _record(eid, "submitted")["ok"]

    out = reconcile_external_value_ledger(
        fetch_status=lambda ref: {"ok": True, "merged": True, "owner_acceptance_signal": False}
    )

    assert out["schema"] == "nomad.external_value_reconcile.v1"
    assert out["proposal_count"] == 1
    assert out["proposals"][0]["proposal"]["proposed_stage"] == "approved"
    assert out["proposals"][0]["proposal"]["reason"] == "merged_implies_external_acceptance_monotonic_step"


def test_reconcile_never_paid_without_payment_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev2.jsonl"))
    eid = "gh_pr:Scottcjn/Rustchain#4542"
    for stage in ("found", "submitted", "approved", "merged"):
        assert _record(eid, stage)["ok"]

    out = reconcile_external_value_ledger(fetch_status=lambda ref: {"ok": True, "merged": True})

    assert out["proposal_count"] == 0
    assert out["observations"][0]["proposal"]["reason"] == "merged_but_no_payment_receipt"


def test_reconcile_paid_only_from_merged_with_positive_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev3.jsonl"))
    eid = "gh_pr:Scottcjn/Rustchain#4542"
    for stage in ("found", "submitted", "approved", "merged"):
        assert _record(eid, stage)["ok"]

    out = reconcile_external_value_ledger(
        fetch_status=lambda ref: {"ok": True, "payment_receipt": True, "amount_usd": 16.88}
    )

    proposal = out["proposals"][0]["proposal"]
    assert proposal["proposed_stage"] == "paid"
    assert proposal["amount_usd"] == 16.88


def test_reconcile_emits_prioritized_followup_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev_followups.jsonl"))
    assert _record("gh_pr:Scottcjn/Rustchain#1", "found")["ok"]
    for stage in ("found", "submitted", "approved", "merged"):
        assert _record("gh_pr:Scottcjn/Rustchain#2", stage)["ok"]

    out = reconcile_external_value_ledger(fetch_status=lambda ref: {"ok": True, "merged": True})

    assert out["followup_count"] == 2
    assert out["top_followup"]["action"] == "await_payment_receipt"
    assert out["followup_action_counts"]["await_payment_receipt"] == 1
    assert out["followup_action_counts"]["produce_or_submit_proof"] == 1
    assert out["followups"][0]["external_id"] == "gh_pr:Scottcjn/Rustchain#2"


def test_propose_review_waits_for_owner_acceptance():
    event = {"stage": "submitted"}

    wait = propose_external_value_transition(event, {"ok": True, "own_review_state": "CHANGES_REQUESTED"})
    go = propose_external_value_transition(event, {"ok": True, "owner_acceptance_signal": True})

    assert wait["proposed_stage"] == ""
    assert wait["reason"] == "review_exists_but_no_owner_acceptance"
    assert go["proposed_stage"] == "approved"


def test_cli_external_value_reconcile_json(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev4.jsonl"))
    assert _record("gh_review:Scottcjn/Rustchain#4576:4265850272", "found")["ok"]
    assert _record("gh_review:Scottcjn/Rustchain#4576:4265850272", "submitted")["ok"]

    out = run_once(["external-value", "reconcile", "--json"])

    assert out["schema"] == "nomad.external_value_reconcile.v1"
    assert out["observed_count"] == 1
    assert out["live_github"] is False
