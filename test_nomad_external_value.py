from nomad_external_value import (
    append_external_value_event,
    build_external_value_surface,
    build_receipt_only_revenue_invariant,
    current_stage_for_external,
    revenue_recognized_usd,
    summarize_external_value_ledger,
)


def test_external_value_full_chain_and_revenue_only_on_paid(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev.jsonl"))
    eid = "gh_pr:test/repo#1"
    aid = "nomad.worker.test"

    assert append_external_value_event(
        {"agent_id": aid, "external_id": eid, "stage": "found", "work_url": "", "proof_digest": "", "verifier_trace_digest": ""}
    )["ok"]
    assert append_external_value_event(
        {
            "agent_id": aid,
            "external_id": eid,
            "stage": "submitted",
            "work_url": "https://github.com/test/repo/pull/1",
            "proof_digest": "p1",
            "verifier_trace_digest": "t1",
        }
    )["ok"]
    assert append_external_value_event(
        {
            "agent_id": aid,
            "external_id": eid,
            "stage": "approved",
            "work_url": "https://github.com/test/repo/pull/1",
            "proof_digest": "p1",
            "verifier_trace_digest": "t1",
        }
    )["ok"]
    assert append_external_value_event(
        {
            "agent_id": aid,
            "external_id": eid,
            "stage": "merged",
            "work_url": "https://github.com/test/repo/pull/1",
            "proof_digest": "p1",
            "verifier_trace_digest": "t1",
        }
    )["ok"]
    paid = append_external_value_event(
        {
            "agent_id": aid,
            "external_id": eid,
            "stage": "paid",
            "work_url": "https://github.com/test/repo/pull/1",
            "proof_digest": "p1",
            "verifier_trace_digest": "t1",
            "amount_usd": 16.88,
            "settlement_ref": "receipt:https://example.com/payouts/16-88",
        }
    )
    assert paid["ok"]
    assert paid["revenue_recognized_usd"] == 16.88
    assert paid["settlement_ref"] == "receipt:https://example.com/payouts/16-88"
    assert paid["revenue_invariant"] == "paid_stage_requires_positive_amount_and_public_settlement_ref"
    assert paid["nomad_proof_receipt_digest"]

    summ = summarize_external_value_ledger()
    assert summ["revenue_recognized_usd_total"] == 16.88


def test_non_monotonic_and_duplicate_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev2.jsonl"))
    eid = "gh_issue:test/repo#2"
    aid = "a1"
    base = {"agent_id": aid, "external_id": eid, "work_url": "https://x/y", "proof_digest": "p", "verifier_trace_digest": "v"}

    assert append_external_value_event({**base, "stage": "found"})["ok"]
    assert append_external_value_event({**base, "stage": "submitted"})["ok"]
    dup = append_external_value_event({**base, "stage": "submitted"})
    assert not dup["ok"]
    skip = append_external_value_event({**base, "stage": "merged"})
    assert not skip["ok"]


def test_surface_has_pipeline_and_state_machine():
    s = build_external_value_surface(base_url="https://example.com")
    assert s["schema"] == "nomad.external_value_surface.v1"
    assert s["state_machine"]["name"] == "pending_external_value"
    assert "paid" in s["state_machine"]["stages"]
    assert s["state_machine"]["revenue_rule"] == "paid_stage_requires_positive_amount_and_public_settlement_ref"
    assert s["receipt_only_invariant"]["schema"] == "nomad.receipt_only_revenue_invariant.v1"


def test_paid_external_value_requires_public_settlement_ref(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev-paid-guard.jsonl"))
    base = {
        "agent_id": "nomad.worker.test",
        "external_id": "gh_pr:test/repo#paid-guard",
        "work_url": "https://github.com/test/repo/pull/paid-guard",
        "proof_digest": "sha256:proof",
        "verifier_trace_digest": "sha256:trace",
    }

    assert append_external_value_event({**base, "stage": "found"})["ok"]
    assert append_external_value_event({**base, "stage": "submitted"})["ok"]
    assert append_external_value_event({**base, "stage": "approved"})["ok"]
    assert append_external_value_event({**base, "stage": "merged"})["ok"]

    missing_ref = append_external_value_event({**base, "stage": "paid", "amount_usd": 5.0})
    assert missing_ref["ok"] is False
    assert missing_ref["error"] == "paid_receipt_incomplete"
    assert missing_ref["reason"] == "paid_stage_requires_positive_amount_and_public_settlement_ref"


def test_revenue_invariant_surface_exposes_science_and_contracts(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev-invariant.jsonl"))

    invariant = build_receipt_only_revenue_invariant(base_url="https://nomad.example")

    assert invariant["schema"] == "nomad.receipt_only_revenue_invariant.v1"
    assert invariant["state_algebra"]["cash_state"] == "paid"
    assert "settlement_ref present" in invariant["state_algebra"]["paid_guard"]
    assert any(item["id"] == "little_law_queue_control_little_1961" for item in invariant["scientific_basis"])
    assert invariant["contracts"]["record"] == "https://nomad.example/swarm/external-value"


def test_revenue_helper():
    assert revenue_recognized_usd(stage="merged", amount_usd=99) == 0.0
    assert revenue_recognized_usd(stage="paid", amount_usd=5) == 5.0


def test_cli_external_value_surface_json():
    from nomad_cli import run_once

    out = run_once(["external-value", "surface", "--base-url", "https://nomad.example", "--json"])
    assert out["schema"] == "nomad.external_value_surface.v1"
    assert out["post_url"] == "https://nomad.example/swarm/external-value"


def test_current_stage_for_external_reads_tail(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev3.jsonl"))
    from nomad_external_value import _read_events, _ledger_path

    append_external_value_event(
        {
            "agent_id": "x",
            "external_id": "id3",
            "stage": "found",
            "work_url": "",
            "proof_digest": "",
            "verifier_trace_digest": "",
        }
    )
    events = _read_events(_ledger_path())
    assert current_stage_for_external(events, "id3") == "found"


def test_summary_latest_limit_can_keep_older_merged_settlement_candidates(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_EXTERNAL_VALUE_LEDGER_PATH", str(tmp_path / "ev4.jsonl"))
    merged_id = "gh_pr:test/repo#old-merged"
    base = {
        "agent_id": "nomad.test",
        "external_id": merged_id,
        "work_url": "https://github.com/test/repo/pull/old-merged",
        "proof_digest": "p",
        "verifier_trace_digest": "v",
    }
    assert append_external_value_event({**base, "stage": "found"})["ok"]
    assert append_external_value_event({**base, "stage": "submitted"})["ok"]
    assert append_external_value_event({**base, "stage": "approved"})["ok"]
    assert append_external_value_event({**base, "stage": "merged"})["ok"]

    for idx in range(45):
        eid = f"gh_pr:test/repo#{idx}"
        assert append_external_value_event(
            {
                "agent_id": "nomad.test",
                "external_id": eid,
                "stage": "found",
                "work_url": "",
                "proof_digest": "",
                "verifier_trace_digest": "",
            }
        )["ok"]
        assert append_external_value_event(
            {
                "agent_id": "nomad.test",
                "external_id": eid,
                "stage": "submitted",
                "work_url": f"https://github.com/test/repo/pull/{idx}",
                "proof_digest": "p",
                "verifier_trace_digest": "v",
            }
        )["ok"]

    default_summary = summarize_external_value_ledger(limit=200)
    wide_summary = summarize_external_value_ledger(limit=200, latest_limit=200)

    assert merged_id not in {row["external_id"] for row in default_summary["latest_by_external"]}
    assert merged_id in {row["external_id"] for row in wide_summary["latest_by_external"]}
    assert wide_summary["latest_by_external_visible_count"] == wide_summary["distinct_externals"]
