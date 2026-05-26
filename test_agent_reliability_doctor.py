from agent_reliability_doctor import (
    AgentReliabilityDoctor,
    build_reliability_doctor_intake,
    build_reliability_doctor_surface,
)


def test_reliability_doctor_maps_hallucination_to_reflection_critic():
    doctor = AgentReliabilityDoctor()

    result = doctor.diagnose(
        problem="Agent produced unsupported claims and fake sources.",
        service_type="hallucination",
    )

    assert result["schema"] == "nomad.agent_reliability_doctor.v1"
    assert result["pain_type"] == "hallucination"
    assert result["doctor_role"]["id"] == "reflection_critic"
    assert result["reliability_loop"]["conditional_edge"] == "fix_or_block_until_rubric_passes"
    assert result["critic_rubric"][0]["check"] == "evidence_bound"


def test_reliability_doctor_maps_tool_failure_to_execution_healer():
    result = AgentReliabilityDoctor().diagnose(
        problem="Tool failure: schema mismatch after the browser execution step.",
        service_type="tool_failure",
    )

    assert result["doctor_role"]["id"] == "execution_healer"
    assert "fixture" in " ".join(result["intervention_plan"]).lower()
    assert result["fix_contract"]["success_signal"].startswith("rubric_passed")


def test_reliability_doctor_defaults_to_self_correction_when_unclear():
    result = AgentReliabilityDoctor().diagnose(problem="Agent keeps making the same mistake.")

    assert result["pain_type"] == "self_correction_failure"
    assert result["doctor_role"]["id"] == "reflection_critic"
    assert result["healing_memory"]["fingerprint"].startswith("pain-")


def test_reliability_doctor_maps_bot_factory_to_proof_gated_role():
    result = AgentReliabilityDoctor().diagnose(
        problem="Create a Solana and Hyperliquid trading bot with drawdown limits.",
        service_type="proof_gated_bot_factory",
    )

    assert result["pain_type"] == "proof_gated_bot_factory"
    assert result["doctor_role"]["id"] == "bot_factory_reviewer"
    assert "simulation" in result["doctor_role"]["why"].lower()
    assert "live-execution" in " ".join(result["intervention_plan"]).lower()


def test_bot_factory_intake_validates_solana_public_wallet_shape():
    result = build_reliability_doctor_intake(
        {
            "claim": "Build a simulation-only Solana bot with 3% max drawdown.",
            "service_type": "proof_gated_bot_factory",
            "public_wallet": "11111111111111111111111111111111",
            "chain_targets": "solana,hyperliquid",
            "risk_profile": "low",
            "max_drawdown": "3%",
            "strategy_type": "volatility filter",
        }
    )

    wallet_validation = result["proof"]["risk_envelope"]["wallet_validation"]

    assert result["ok"] is True
    assert result["service_type"] == "proof_gated_bot_factory"
    assert wallet_validation["chain"] == "solana"
    assert wallet_validation["valid"] is True
    assert wallet_validation["bytes"] == 32
    assert result["proof"]["shadow_bot_artifacts"]["hyperliquid"]["execution_mode"] == "shadow_lane_no_live_orders"
    assert result["proof"]["shadow_bot_artifacts"]["hyperliquid"]["paper_order_intent"]["exchange_endpoint_call_allowed"] is False
    assert result["public_facts"]["shadow_bot_artifacts_digest"].startswith("sha256:")
    assert "valid_public_wallet_required_before_paid_delivery" in result["openai_preanalysis"]["hard_guards"]
    assert "hyperliquid_exchange_calls_blocked_in_shadow_lane" in result["openai_preanalysis"]["hard_guards"]


def test_bot_factory_intake_flags_invalid_solana_public_wallet_shape():
    result = build_reliability_doctor_intake(
        {
            "claim": "Build a simulation-only Solana bot.",
            "service_type": "proof_gated_bot_factory",
            "public_wallet": "not a solana key",
            "chain_targets": "solana",
            "risk_profile": "low",
            "max_drawdown": "3%",
        }
    )

    wallet_validation = result["proof"]["risk_envelope"]["wallet_validation"]

    assert result["ok"] is True
    assert wallet_validation["valid"] is False
    assert wallet_validation["reason"] == "contains_whitespace"


def test_reliability_doctor_surface_exposes_ci_and_docker_onramps():
    surface = build_reliability_doctor_surface(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.agent_reliability_doctor_surface.v1"
    assert surface["routes"]["intake"] == "https://nomad.example/swarm/reliability-doctor/intake"
    assert surface["downloads"]["github_action"].endswith("/downloads/nomad_reliability_doctor_action.yml")
    assert surface["downloads"]["work_exchange_dockerfile"].endswith("/downloads/nomad_work_exchange_worker.Dockerfile")
    assert surface["agent_onramps"][0]["side_effect_scope"] == "secret_free_http_intake_only"


def test_reliability_doctor_intake_builds_offer_payload_and_optional_obligation_payload():
    out = build_reliability_doctor_intake(
        {
            "requester_id": "github-actions:owner/repo:123",
            "source": "github_actions",
            "service_type": "execution_failure",
            "problem": "CI timed out after a tool schema mismatch.",
            "repository": "owner/repo",
            "workflow_url": "https://github.com/owner/repo/actions/runs/123",
            "log_digest": "sha256:" + "1" * 64,
            "accepted_compute_barter_terms": True,
        },
        base_url="https://nomad.example",
    )

    assert out["schema"] == "nomad.agent_reliability_doctor_intake.v1"
    assert out["accepted_compute_barter_terms"] is True
    assert out["diagnosis"]["doctor_role"]["id"] == "execution_healer"
    assert out["solution_proof_digest"].startswith("sha256:")
    assert out["work_exchange_offer_payload"]["requester_id"] == "github-actions:owner/repo:123"
    assert out["free_solution_payload"]["accepted_compute_barter_terms"] is True
    assert out["next"]["dockerfile"].endswith("/downloads/nomad_work_exchange_worker.Dockerfile")


def test_reliability_doctor_intake_accepts_fact_check_packet_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    out = build_reliability_doctor_intake(
        {
            "claim": "This public statement needs verification.",
            "source_url": "https://example.com/source",
            "pdf_name": "evidence.pdf",
            "pdf_sha256": "a" * 64,
            "pdf_bytes": 2048,
            "accepted_compute_barter_terms": True,
        },
        base_url="https://nomad.example",
    )

    assert out["ok"] is True
    assert out["schema"] == "nomad.agent_reliability_doctor_intake.v1"
    assert out["requester_id"].startswith("https://example.com") or out["requester_id"].startswith("telegram_miniapp")
    assert out["public_facts"]["source_url"] == "https://example.com/source"
    assert out["public_facts"]["pdf_sha256"] == "a" * 64
    assert out["accepted_compute_barter_terms"] is True
    assert out["openai_preanalysis"]["status"] == "openai_api_key_missing"
    assert out["free_solution_payload"]["accepted_compute_barter_terms"] is True


def test_reliability_doctor_intake_rejects_secret_shaped_payload():
    out = build_reliability_doctor_intake({"requester_id": "x", "problem": "token leaked", "api_key": "sk-test"})

    assert out["ok"] is False
    assert out["error"] == "secret_shaped_payload"
