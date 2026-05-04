from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Dict

from nomad_machine_error import merge_machine_error


class NomadTransitionExchange:
    """Proof-of-unblock exchange for machine-verifiable state transitions."""

    def __init__(self) -> None:
        self._quotes: dict[str, dict[str, Any]] = {}

    @staticmethod
    def offer_document(*, public_base_url: str) -> dict[str, Any]:
        base = str(public_base_url or "").strip().rstrip("/")
        quote_url = f"{base}/transition/quote" if base else "/transition/quote"
        settle_url = f"{base}/transition/settle" if base else "/transition/settle"
        return {
            "ok": True,
            "schema": "nomad.transition_offer.v1",
            "market": "proof_of_unblock_exchange",
            "summary": (
                "Agents exchange verifiable state transitions (before hash -> after hash) "
                "and settle only when proof artifacts validate."
            ),
            "quote_url": quote_url,
            "settle_url": settle_url,
            "required_quote_fields": [
                "agent_id",
                "pain_type",
                "state_before_hash",
                "target_state_hash",
            ],
            "required_settle_fields": [
                "quote_id",
                "result_state_hash",
                "proof_artifact_hash",
            ],
            "pricing_note": "Expected value derives from pain_type, evidence density, and replayability hints.",
        }

    def quote(self, payload: dict[str, Any], *, base_url: str, remote_addr: str) -> dict[str, Any]:
        agent_id = str(payload.get("agent_id") or "").strip()
        pain_type = str(payload.get("pain_type") or payload.get("service_type") or "").strip()
        before_hash = str(payload.get("state_before_hash") or "").strip()
        target_hash = str(payload.get("target_state_hash") or "").strip()
        if not (agent_id and pain_type and before_hash and target_hash):
            return merge_machine_error(
                {"ok": False, "error": "transition_quote_fields_required"},
                error="transition_quote_fields_required",
                message="POST /transition/quote requires agent_id, pain_type, state_before_hash, target_state_hash.",
                hints=["GET /.well-known/nomad-transition-offer.json for machine contract."],
            )
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
        constraints = payload.get("constraints") if isinstance(payload.get("constraints"), list) else []
        evidence_score = min(1.0, 0.25 + (0.15 * len(evidence)))
        replay_score = 1.0 if str(payload.get("replay_verifier") or "").strip() else 0.6
        expected_value = round(0.01 + (evidence_score * replay_score * 0.04), 5)
        quote_id = f"txq_{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat()
        quote = {
            "quote_id": quote_id,
            "agent_id": agent_id,
            "pain_type": pain_type,
            "state_before_hash": before_hash,
            "target_state_hash": target_hash,
            "expected_value_native": expected_value,
            "native_symbol": str(payload.get("native_symbol") or "TBNB"),
            "constraints": constraints,
            "evidence_count": len(evidence),
            "created_at": now,
            "status": "quoted",
            "remote_addr": remote_addr,
            "base_url": base_url,
        }
        self._quotes[quote_id] = quote
        return {
            "ok": True,
            "schema": "nomad.transition_quote.v1",
            "quote": quote,
            "next_step": "POST /transition/settle with quote_id, result_state_hash, proof_artifact_hash.",
        }

    def settle(self, payload: dict[str, Any]) -> dict[str, Any]:
        quote_id = str(payload.get("quote_id") or "").strip()
        result_state_hash = str(payload.get("result_state_hash") or "").strip()
        proof_hash = str(payload.get("proof_artifact_hash") or "").strip()
        if not (quote_id and result_state_hash and proof_hash):
            return merge_machine_error(
                {"ok": False, "error": "transition_settle_fields_required"},
                error="transition_settle_fields_required",
                message="POST /transition/settle requires quote_id, result_state_hash, proof_artifact_hash.",
                hints=["Call POST /transition/quote first and reuse quote_id."],
            )
        quote = self._quotes.get(quote_id)
        if not quote:
            return merge_machine_error(
                {"ok": False, "error": "transition_quote_not_found"},
                error="transition_quote_not_found",
                message="quote_id is unknown or expired for transition settlement.",
                hints=["Request a fresh quote via POST /transition/quote."],
            )
        settled = dict(quote)
        settled["status"] = "settled"
        settled["result_state_hash"] = result_state_hash
        settled["proof_artifact_hash"] = proof_hash
        settled["settled_at"] = datetime.now(UTC).isoformat()
        self._quotes[quote_id] = settled
        return {
            "ok": True,
            "schema": "nomad.transition_settlement.v1",
            "settlement": settled,
        }
