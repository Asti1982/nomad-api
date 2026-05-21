from __future__ import annotations

import json

from nomad_hackerone_scout import (
    _normalize_api_base,
    build_hackerone_report_draft,
    build_hackerone_scope_scout,
    fetch_hackerone_report_status,
    submit_hackerone_report,
)


def _program_payload():
    return {
        "data": {
            "id": "zabbix",
            "type": "program",
            "attributes": {
                "handle": "zabbix",
                "name": "Zabbix",
                "state": "public_mode",
                "offers_bounties": True,
                "submission_state": "open",
                "currency": "usd",
            },
        }
    }


def _scopes_payload():
    return {
        "data": [
            {
                "id": "179943",
                "type": "structured-scope",
                "attributes": {
                    "asset_type": "SOURCE_CODE",
                    "asset_identifier": "https://www.zabbix.com/download_sources",
                    "eligible_for_bounty": True,
                    "eligible_for_submission": True,
                    "max_severity": "critical",
                    "instruction": "Download supported Zabbix source versions for testing.",
                },
            },
            {
                "id": "179944",
                "type": "structured-scope",
                "attributes": {
                    "asset_type": "URL",
                    "asset_identifier": "https://example.invalid",
                    "eligible_for_bounty": False,
                    "eligible_for_submission": False,
                },
            },
        ]
    }


def test_hackerone_api_base_normalization_strips_v1_suffix():
    assert _normalize_api_base("https://api.hackerone.com/v1") == "https://api.hackerone.com"
    assert _normalize_api_base("api.hackerone.com") == "https://api.hackerone.com"


def test_missing_credentials_keep_scout_blocked():
    result = build_hackerone_scope_scout(identifier="", token="", program_payload={}, scopes_payload={})

    assert result["ok"] is False
    assert result["credential_state"]["identifier_present"] is False
    assert result["credential_state"]["token_present"] is False
    assert result["errors"] == ["hackerone_api_credentials_missing"]
    assert result["value_cycle_gate"]["submit_allowed"] is False


def test_scope_scout_normalizes_base_and_never_emits_secret_values():
    calls = []

    def fake_fetch(url, auth, timeout):
        calls.append((url, auth, timeout))
        if url.endswith("/v1/hackers/programs/zabbix"):
            return _program_payload()
        if url.endswith("/v1/hackers/programs/zabbix/structured_scopes?page[size]=100"):
            return _scopes_payload()
        raise AssertionError(url)

    result = build_hackerone_scope_scout(
        api_base="https://api.hackerone.com/v1",
        identifier="h1_identifier",
        token="h1_secret_token",
        fetch_json=fake_fetch,
    )

    assert result["ok"] is True
    assert calls[0][0] == "https://api.hackerone.com/v1/hackers/programs/zabbix"
    assert result["api_base_public"] == "https://api.hackerone.com"
    assert result["scope_summary"]["scope_count"] == 2
    assert result["scope_summary"]["eligible_source_count"] == 1
    assert result["scope_summary"]["top_source_scope"]["asset_identifier"] == "https://www.zabbix.com/download_sources"
    assert result["machine_instruction"] == "read_only_source_review_then_local_reproducer_before_hackerone_submission"

    encoded = json.dumps(result, sort_keys=True)
    assert "h1_secret_token" not in encoded
    assert "h1_identifier" not in encoded
    assert result["credential_state"]["token_length"] == len("h1_secret_token")


def test_scope_without_eligible_source_stays_watch_only():
    result = build_hackerone_scope_scout(
        identifier="id",
        token="token",
        program_payload=_program_payload(),
        scopes_payload={"data": [_scopes_payload()["data"][1]]},
    )

    assert result["ok"] is False
    assert result["scope_summary"]["eligible_source_count"] == 0
    assert result["value_cycle_gate"]["paid_record_allowed"] is False
    assert result["machine_instruction"] == "read_only_scope_review_only_no_submit_until_eligible_asset_exists"


def test_source_scope_with_github_instruction_is_safe_for_read_only_review():
    program = _program_payload()
    program["data"]["attributes"]["handle"] = "wordpress"
    scopes = {
        "data": [
            {
                "id": "17141",
                "type": "structured-scope",
                "attributes": {
                    "asset_type": "SOURCE_CODE",
                    "asset_identifier": "GlotPress",
                    "eligible_for_bounty": True,
                    "eligible_for_submission": True,
                    "instruction": "All code located under https://github.com/GlotPress/ on GitHub.",
                },
            }
        ]
    }

    result = build_hackerone_scope_scout(
        handle="wordpress",
        identifier="id",
        token="token",
        program_payload=program,
        scopes_payload=scopes,
    )

    assert result["ok"] is True
    assert result["scope_summary"]["top_source_scope"]["safe_for_read_only_source_review"] is True


def test_hackerone_report_status_maps_triage_without_secret_leak():
    calls = []

    def fake_fetch(url, auth, timeout):
        calls.append((url, auth, timeout))
        return {
            "data": {
                "id": "3740761",
                "type": "report",
                "attributes": {
                    "title": "authz bypass",
                    "state": "triaged",
                    "created_at": "2026-05-16T17:55:26.642Z",
                    "triaged_at": "2026-05-17T09:00:00.000Z",
                    "bounty_awarded_at": None,
                },
            }
        }

    result = fetch_hackerone_report_status(
        "3740761",
        api_base="https://api.hackerone.com/v1",
        identifier="h1_identifier",
        token="h1_secret_token",
        fetch_json=fake_fetch,
    )

    assert result["ok"] is True
    assert result["source"] == "hackerone"
    assert result["report_id"] == "3740761"
    assert result["hackerone_validated"] is True
    assert result["owner_acceptance_signal"] is True
    assert result["payment_receipt"] is False
    assert calls[0][0].endswith("/v1/hackers/reports/3740761?include=bounties,severity,structured_scope,program")

    encoded = json.dumps(result, sort_keys=True)
    assert "h1_secret_token" not in encoded
    assert "h1_identifier" not in encoded
    assert result["credential_state"]["secret_material_emitted"] is False


def test_report_draft_blocks_submit_until_reproducer_exists():
    draft = build_hackerone_report_draft(
        program_handle="zabbix",
        title="authz bypass",
        scope=_scopes_payload()["data"][0]["attributes"] | {"id": "179943"},
        summary="A direct server command bypasses UI authorization.",
        source_evidence=["server.c:52 authenticates only caller"],
        repro_steps=["Create attacker and victim users."],
        impact="Private dashboard disclosure.",
    )

    assert draft["submit_ready"] is False
    assert "missing_local_reproducer_digest" in draft["blocked_actions"]
    assert "missing_verified_reproducer_run" in draft["blocked_actions"]
    assert draft["machine_instruction"] == "continue_local_repro_before_any_hackerone_submission"


def test_report_draft_builds_submit_packet_when_complete():
    draft = build_hackerone_report_draft(
        program_handle="zabbix",
        title="authz bypass",
        scope=_scopes_payload()["data"][0]["attributes"] | {"id": "179943"},
        summary="A direct server command bypasses UI authorization.",
        source_evidence=["server.c:52 authenticates only caller"],
        repro_steps=["Create attacker and victim users.", "Run the local PoC."],
        impact="Private dashboard disclosure.",
        local_reproducer_path="external_work/poc.py",
        local_reproducer_digest="sha256:poc",
        local_reproducer_verified=True,
    )

    assert draft["submit_ready"] is True
    assert draft["payload"]["team_handle"] == "zabbix"
    assert draft["payload"]["structured_scope_id"] == "179943"
    assert "## Steps To Reproduce" in draft["markdown"]
    assert draft["allowed_actions"] == ["hackerone_submit"]


def test_submit_hackerone_report_posts_jsonapi_without_secret_leak():
    calls = []
    draft = build_hackerone_report_draft(
        program_handle="wordpress",
        title="authz bypass",
        scope={"id": "17141", "asset_identifier": "GlotPress"},
        summary="A route authorizes the old object context before persisting a client-controlled new context.",
        source_evidence=["routes/glossary.php:119 checks old glossary"],
        repro_steps=["Run the PHPUnit reproducer."],
        impact="Unauthorized glossary integrity change across translation sets.",
        local_reproducer_path="external_work/poc.php",
        local_reproducer_digest="sha256:poc",
        local_reproducer_verified=True,
    )

    def fake_post(url, payload, auth, timeout):
        calls.append((url, payload, auth, timeout))
        return {
            "data": {
                "id": "424242",
                "type": "report",
                "attributes": {
                    "title": payload["data"]["attributes"]["title"],
                    "state": "new",
                    "created_at": "2026-05-16T19:00:00.000Z",
                },
            }
        }

    result = submit_hackerone_report(
        draft,
        api_base="https://api.hackerone.com/v1",
        identifier="h1_identifier",
        token="h1_secret_token",
        post_json=fake_post,
    )

    assert result["ok"] is True
    assert result["report_id"] == "424242"
    assert result["public_url"] == "https://hackerone.com/reports/424242"
    assert calls[0][0] == "https://api.hackerone.com/v1/hackers/reports"
    assert calls[0][1]["data"]["type"] == "report"
    assert calls[0][1]["data"]["attributes"]["structured_scope_id"] == 17141

    encoded = json.dumps(result, sort_keys=True)
    assert "h1_secret_token" not in encoded
    assert "h1_identifier" not in encoded
