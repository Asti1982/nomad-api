from nomad_external_value import (
    append_external_value_event,
    build_external_value_surface,
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
        }
    )
    assert paid["ok"]
    assert paid["revenue_recognized_usd"] == 16.88
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
