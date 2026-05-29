import json

from nomad_gemini_verifier import (
    build_gemini_verifier_surface,
    gemini_quota_snapshot,
    scan_for_secrets,
    verify_with_gemini,
)
from nomad_openapi import build_openapi_document
from nomad_cli import run_once


class _FakeGeminiResponse:
    status_code = 200

    def json(self):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "verdict": "needs_reproducer",
                                        "risk_score": 0.42,
                                        "confidence": 0.81,
                                        "submit_allowed": False,
                                        "duplicate_risk": "medium",
                                        "summary": "Needs a local reproducer before any external submission.",
                                        "required_next_evidence": ["local_reproducer"],
                                        "proof_notes": ["scope_check_passed"],
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }


def test_gemini_verifier_surface_is_public_artifact_only(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    surface = build_gemini_verifier_surface(base_url="https://www.syndiode.com")

    assert surface["schema"] == "nomad.gemini_verifier_surface.v1"
    assert surface["policy"] == "public_artifacts_only_no_secrets_no_private_logs"
    assert surface["routes"]["verify"] == "https://www.syndiode.com/swarm/gemini-verifier/verify"
    assert surface["quota"]["api_key_present"] is False


def test_gemini_secret_guard_blocks_provider_call(tmp_path):
    calls = []
    google_key_shape = "AI" + "za" + "123456789012345678901234567890"

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeGeminiResponse()

    out = verify_with_gemini(
        {
            "verifier_type": "hackerone_draft",
            "artifact_text": f"GEMINI_API_KEY = {google_key_shape}",
        },
        http_post=fake_post,
        ledger_path=tmp_path / "gemini.jsonl",
    )

    assert out["ok"] is False
    assert out["error"] == "secret_guard_blocked"
    assert out["provider_call_attempted"] is False
    assert calls == []


def test_gemini_dry_run_builds_receipt_without_key_or_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    out = verify_with_gemini(
        {
            "verifier_type": "agp_candidate",
            "artifact_text": "public candidate: proof digest sha256:abc; tests pending",
            "dry_run": True,
            "api_mode": "interactions",
        },
        ledger_path=tmp_path / "gemini.jsonl",
    )

    assert out["ok"] is True
    assert out["api_mode"] == "interactions"
    assert out["dry_run"] is True
    assert out["provider_call_attempted"] is False
    assert out["submit_allowed"] is False
    assert out["proof_digest"].startswith("sha256:")
    assert out["verifier_trace_digest"].startswith("sha256:")


def test_gemini_provider_call_locked_by_default_with_key(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    out = verify_with_gemini(
        {
            "verifier_type": "worker_receipt",
            "artifact_text": "public worker receipt candidate",
        },
        ledger_path=tmp_path / "gemini.jsonl",
    )

    assert out["ok"] is False
    assert out["error"] == "gemini_provider_call_locked"
    assert out["provider_call_attempted"] is False
    assert out["provider_call_gate"]["blocked"] is True


def test_gemini_mock_provider_records_quota_event(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    ledger = tmp_path / "gemini.jsonl"
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeGeminiResponse()

    out = verify_with_gemini(
        {
            "model": "gemini-3.1-flash-lite",
            "verifier_type": "hackerone_draft",
            "artifact_text": "Public H1 draft; missing local reproducer.",
        },
        http_post=fake_post,
        ledger_path=ledger,
    )
    quota = gemini_quota_snapshot(ledger_path=ledger, model="gemini-3.1-flash-lite")

    assert out["ok"] is True
    assert out["verdict"] == "needs_reproducer"
    assert out["submit_allowed"] is False
    assert len(calls) == 1
    assert quota["used_today"] == 1
    assert "test-key-not-real" not in ledger.read_text(encoding="utf-8")


def test_gemini_interactions_mock_provider_extracts_output_text(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    calls = []

    class FakeInteractionResponse:
        status_code = 200

        def json(self):
            return {
                "output_text": json.dumps(
                    {
                        "verdict": "block",
                        "risk_score": 0.91,
                        "confidence": 0.74,
                        "submit_allowed": False,
                        "duplicate_risk": "high",
                        "summary": "Public artifact is too weak for action.",
                        "required_next_evidence": ["stronger_receipt"],
                        "proof_notes": ["interactions_api_shape"],
                    }
                )
            }

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeInteractionResponse()

    out = verify_with_gemini(
        {
            "api_mode": "interactions",
            "verifier_type": "external_value",
            "artifact_text": "public external value note",
        },
        http_post=fake_post,
        ledger_path=tmp_path / "gemini.jsonl",
    )

    assert out["ok"] is True
    assert out["api_mode"] == "interactions"
    assert out["verdict"] == "block"
    assert len(calls) == 1
    assert calls[0][0][0].endswith("/v1beta/interactions")
    assert calls[0][1]["json"]["store"] is False


def test_gemini_quota_blocks_second_call(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("NOMAD_GEMINI_VERIFIER_DAILY_LIMIT", "1")
    ledger = tmp_path / "gemini.jsonl"

    def fake_post(*args, **kwargs):
        return _FakeGeminiResponse()

    first = verify_with_gemini({"artifact_text": "public artifact"}, http_post=fake_post, ledger_path=ledger)
    second = verify_with_gemini({"artifact_text": "another public artifact"}, http_post=fake_post, ledger_path=ledger)

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error"] == "gemini_quota_exhausted"
    assert second["provider_call_attempted"] is False


def test_gemini_verifier_openapi_routes_are_discoverable():
    doc = build_openapi_document(base_url="https://www.syndiode.com")

    assert "/swarm/gemini-verifier" in doc["paths"]
    assert "/swarm/gemini-verifier/verify" in doc["paths"]
    assert "/.well-known/nomad-gemini-verifier.json" in doc["paths"]


def test_gemini_verifier_cli_dry_run(tmp_path, monkeypatch):
    monkeypatch.setenv("NOMAD_GEMINI_VERIFIER_LEDGER_PATH", str(tmp_path / "gemini.jsonl"))
    out = run_once(
        [
            "gemini-verifier",
            "--verifier-type",
            "worker_receipt",
            "--artifact-text",
            "public receipt candidate",
            "--dry-run",
            "--json",
        ]
    )

    assert out["schema"] == "nomad.gemini_verifier_receipt.v1"
    assert out["dry_run"] is True
    assert out["submit_allowed"] is False
