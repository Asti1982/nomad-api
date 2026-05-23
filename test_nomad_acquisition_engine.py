import json

from nomad_acquisition_engine import (
    build_acquisition_engine_surface,
    compact_acquisition_engine_message,
    summarize_agent_outreach_state,
)


def test_acquisition_engine_builds_machine_native_policy(tmp_path, monkeypatch):
    ledger = {
        "schema": "nomad.telegram_acquisition_ledger_summary.v1",
        "event_count": 6,
        "stage_counts": {
            "real_acquisition_round_sent": 1,
            "cursor_referral_qualified_click_test": 1,
            "transition_worker_recruited_test": 1,
            "paid_product_order_created_test": 1,
            "swarm_oracle_app_downloaded_test": 1,
            "worker_attached": 1,
        },
        "selected_offer_counts": {
            "cursor_referral": 1,
            "transition_worker_setup": 2,
            "swarm_oracle_app_download": 1,
        },
    }
    monkeypatch.setenv("NOMAD_ACQ_TARGET_TRANSITION_WORKERS", "1")

    out = build_acquisition_engine_surface(
        base_url="https://nomad.example",
        ledger_summary=ledger,
        agent_outreach_summary={
            "schema": "nomad.agent_outreach_summary.v1",
            "sent_count": 4,
            "remote_task_id_count": 3,
            "contact_count": 8,
            "status_counts": {"sent": 4, "send_failed": 4},
        },
    )

    assert out["schema"] == "nomad.acquisition_engine.v1"
    assert out["links"]["miniapp"] == "https://nomad.example/telegram-miniapp"
    assert out["goal_status"]["transition_workers"]["verified"] == 1
    assert out["fulfilled"]["transition_workers"] is True
    assert out["guardrails"]["test_shadow_events_never_satisfy_real_goals"] is True
    assert out["arms"]
    assert out["top_next_actions"]
    assert any(item["mechanism"] == "expected_information_gain" for item in out["science_basis"])
    assert sum(out["replicator_weights"].values()) > 0.99


def test_acquisition_engine_canonicalizes_syndiode_and_exposes_human_boundary():
    out = build_acquisition_engine_surface(base_url="https://www.syndiode.com")

    assert out["public_base_url"] == "https://syndiode.com/nomad"
    assert out["links"]["peer_acquisition"] == "https://syndiode.com/nomad/.well-known/nomad-peer-acquisition.json"
    assert out["human_comprehension_boundary"]["rule"].startswith("humans audit")


def test_agent_outreach_summary_is_compact(tmp_path):
    campaigns = tmp_path / "campaigns.json"
    contacts = tmp_path / "contacts.json"
    campaigns.write_text(
        json.dumps(
            {
                "campaigns": {
                    "c1": {
                        "campaign_id": "c1",
                        "updated_at": "2026-05-23T00:00:00+00:00",
                        "status": "sent",
                        "stats": {"sent": 2},
                        "service_type": "inter_agent_witness",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    contacts.write_text(
        json.dumps(
            {
                "contacts": {
                    "a": {"status": "sent", "remote_task_id": "task_1"},
                    "b": {"status": "send_failed"},
                }
            }
        ),
        encoding="utf-8",
    )

    out = summarize_agent_outreach_state(campaign_path=campaigns, contacts_path=contacts)

    assert out["campaign_count"] == 1
    assert out["contact_count"] == 2
    assert out["sent_count"] == 1
    assert out["remote_task_id_count"] == 1


def test_compact_acquisition_engine_message_contains_goals():
    surface = build_acquisition_engine_surface(base_url="https://nomad.example")

    text = compact_acquisition_engine_message(surface)

    assert "Nomad acquisition engine" in text
    assert "cursor_referrals" in text
    assert "Guard: opt-in" in text
