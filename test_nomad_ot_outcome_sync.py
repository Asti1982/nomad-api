from nomad_optimal_transport import record_ot_outcome_event
from nomad_ot_outcome_sync import (
    plan_ot_outcome_public_sync,
    snapshot_public_ot_outcomes,
    sync_ot_outcomes_to_public,
)


def test_plan_ot_outcome_sync_skips_public_recent_and_blocks_revenue_like():
    local = [
        {
            "schema": "nomad.ot_outcome_event.v1",
            "event_id": "nomad-ot-outcome-a",
            "plan_digest": "plan-a",
            "counts_as_revenue": False,
        },
        {
            "schema": "nomad.ot_outcome_event.v1",
            "event_id": "nomad-ot-outcome-b",
            "plan_digest": "plan-b",
            "counts_as_revenue": False,
        },
        {
            "schema": "nomad.ot_outcome_event.v1",
            "event_id": "nomad-ot-outcome-c",
            "counts_as_revenue": True,
        },
    ]
    public = {"outcome_summary": {"recent_events": [{"event_id": "nomad-ot-outcome-a"}]}}

    plan = plan_ot_outcome_public_sync(local, public)

    assert plan["replay_candidate_count"] == 1
    assert plan["candidates"][0]["event_id"] == "nomad-ot-outcome-b"
    assert plan["skipped_count"] == 1
    assert plan["blocked_count"] == 1
    assert plan["counts_as_revenue"] is False


def test_sync_ot_outcomes_to_public_replays_local_secret_free_events(tmp_path, monkeypatch):
    ledger = tmp_path / "ot_outcomes.jsonl"
    monkeypatch.setenv("NOMAD_OT_OUTCOME_LEDGER_PATH", str(ledger))
    record_ot_outcome_event(
        {
            "event_id": "nomad-ot-outcome-sync-test",
            "plan_digest": "plan-sync",
            "source_id": "worker-a",
            "target_id": "settlement-demand",
            "outcome": "paid",
            "receipt_ref": "receipt:sync-test",
            "paid_usd": 49,
            "proof_digest": "sha256:sync",
        },
        base_url="https://nomad.example",
    )
    posted = []
    public_events = []

    def fake_get(url, timeout):
        if "metric-learning" in url:
            return {
                "ok": True,
                "status_code": 200,
                "json": {
                    "schema": "nomad.ot_metric_learning.v1",
                    "outcome_summary": {
                        "event_count": len(public_events),
                        "recent_events": [{"event_id": event_id} for event_id in public_events],
                        "counts_as_revenue": False,
                    },
                    "recommended_axis_weights": {},
                },
            }
        return {"ok": True, "status_code": 200, "json": {"schema": "nomad.optimal_transport.v1"}}

    def fake_post(url, payload, timeout):
        posted.append(payload)
        public_events.append(payload["event_id"])
        return {
            "ok": True,
            "status_code": 202,
            "json": {
                "ok": True,
                "accepted": True,
                "duplicate": False,
                "event_id": payload["event_id"],
            },
        }

    result = sync_ot_outcomes_to_public(
        base_url="https://nomad.example",
        apply=True,
        snapshot=True,
        snapshot_dir=tmp_path / "snapshots",
        fetch_json=fake_get,
        post_json=fake_post,
    )

    assert result["ok"] is True
    assert result["mode"] == "apply"
    assert result["local_event_count"] == 1
    assert result["posted_count"] == 1
    assert result["final_public_event_count"] == 1
    assert result["public_projection_lag_after"] == 0
    assert result["counts_as_revenue"] is False
    assert posted[0]["event_id"] == "nomad-ot-outcome-sync-test"
    assert result["snapshot"]["snapshot_path"]


def test_sync_ot_outcomes_uses_event_id_lag_not_public_count(tmp_path, monkeypatch):
    ledger = tmp_path / "ot_outcomes.jsonl"
    monkeypatch.setenv("NOMAD_OT_OUTCOME_LEDGER_PATH", str(ledger))
    record_ot_outcome_event(
        {
            "event_id": "nomad-ot-outcome-local-only",
            "plan_digest": "plan-local",
            "source_id": "worker-a",
            "target_id": "settlement-demand",
            "outcome": "paid",
            "receipt_ref": "receipt:local",
            "paid_usd": 49,
        },
        base_url="https://nomad.example",
    )

    def fake_get(url, timeout):
        return {
            "ok": True,
            "status_code": 200,
            "json": {
                "schema": "nomad.ot_metric_learning.v1",
                "outcome_summary": {
                    "event_count": 1,
                    "recent_events": [{"event_id": "nomad-ot-outcome-public-other"}],
                    "counts_as_revenue": False,
                },
                "recommended_axis_weights": {},
            },
        }

    result = sync_ot_outcomes_to_public(
        base_url="https://nomad.example",
        apply=False,
        snapshot=False,
        fetch_json=fake_get,
    )

    assert result["public_event_count"] == 1
    assert result["local_event_count"] == 1
    assert result["public_projection_lag_after"] == 1
    assert result["final_replay_candidate_count"] == 1


def test_snapshot_public_ot_outcomes_extracts_public_count(tmp_path):
    def fake_get(url, timeout):
        if "metric-learning" in url:
            return {
                "ok": True,
                "status_code": 200,
                "json": {
                    "outcome_summary": {"event_count": 3, "counts_as_revenue": False},
                    "recommended_axis_weights": {"settlement": 0.4},
                },
            }
        return {"ok": True, "status_code": 200, "json": {}}

    result = snapshot_public_ot_outcomes(
        base_url="https://nomad.example",
        snapshot_dir=tmp_path,
        fetch_json=fake_get,
    )

    assert result["ok"] is True
    assert result["public_event_count"] == 3
    assert result["public_counts_as_revenue"] is False
    assert result["public_recommended_axis_weights"]["settlement"] == 0.4
