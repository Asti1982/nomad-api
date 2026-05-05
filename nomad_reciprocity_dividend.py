"""Reciprocal Proof Dividend Loop (RPDL): machine-only incentive credits from verified transitions."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from nomad_machine_error import merge_machine_error
from nomad_transition_exchange import NomadTransitionExchange

ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = ROOT / "nomad_reciprocity_dividend_state.json"
DECAY_RATE_PER_DAY = float(__import__("os").getenv("NOMAD_RPDL_DECAY_PER_DAY") or "0.12")
CREDIT_TTL_HOURS = int(__import__("os").getenv("NOMAD_RPDL_CREDIT_TTL_HOURS") or "168")


class NomadReciprocityDividend:
    """Credits minted from settled transition proofs; decay without reuse."""

    def __init__(self, *, state_path: Path | None = None, exchange: NomadTransitionExchange | None = None) -> None:
        self._state_path = Path(state_path or DEFAULT_STATE_PATH)
        self._exchange = exchange
        self._lock = threading.Lock()
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._state_path.exists():
            return {"schema": "nomad.reciprocity_dividend_state.v1", "agents": {}, "claims": {}}
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"schema": "nomad.reciprocity_dividend_state.v1", "agents": {}, "claims": {}}
            data.setdefault("agents", {})
            data.setdefault("claims", {})
            data.setdefault("schema", "nomad.reciprocity_dividend_state.v1")
            return data
        except (OSError, json.JSONDecodeError):
            return {"schema": "nomad.reciprocity_dividend_state.v1", "agents": {}, "claims": {}}

    def _save(self) -> None:
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(self._state_path)

    @staticmethod
    def offer_document(*, public_base_url: str) -> dict[str, Any]:
        base = str(public_base_url or "").strip().rstrip("/")
        claim = f"{base}/dividend/claim" if base else "/dividend/claim"
        settle = f"{base}/dividend/settle" if base else "/dividend/settle"
        status = f"{base}/dividend" if base else "/dividend"
        return {
            "ok": True,
            "schema": "nomad.reciprocity_dividend_offer.v1",
            "market": "reciprocal_proof_dividend",
            "summary": (
                "Machine-only credits minted from verified transition settlements. "
                "Humans rarely design this: rewards decay if inactive, and access compounds only via replayable proof."
            ),
            "claim_url": claim,
            "settle_url": settle,
            "status_url": status,
            "units": "rpd_units",
            "decay": {
                "daily_balance_decay_rate": DECAY_RATE_PER_DAY,
                "credit_ttl_hours": CREDIT_TTL_HOURS,
                "note": "Decay punishes passive accumulation; agents must keep producing verifiable transitions.",
            },
            "required_claim_fields": ["agent_id", "quote_id"],
            "required_settle_fields": ["agent_id", "credit_id"],
            "routing_token_purpose": "Attach returned token as header on subsequent agent calls to bias high-yield lanes.",
        }

    def status(self, *, agent_id: str) -> dict[str, Any]:
        agent_id = str(agent_id or "").strip()
        if not agent_id:
            return merge_machine_error(
                {"ok": False, "error": "agent_id_required"},
                error="agent_id_required",
                message="GET /dividend?agent_id=<id> is required.",
            )
        with self._lock:
            self._apply_decay(agent_id)
            rec = self._agent_record(agent_id)
            self._save()
        return {
            "ok": True,
            "schema": "nomad.reciprocity_dividend_status.v1",
            "agent_id": agent_id,
            "balance_units": round(float(rec.get("balance_units") or 0.0), 6),
            "active_credits": rec.get("credits") or [],
            "last_touch_at": rec.get("last_touch_at") or "",
        }

    def claim(
        self,
        payload: dict[str, Any],
        *,
        exchange: NomadTransitionExchange | None = None,
    ) -> dict[str, Any]:
        ex = exchange or self._exchange
        agent_id = str(payload.get("agent_id") or "").strip()
        quote_id = str(payload.get("quote_id") or "").strip()
        if not (agent_id and quote_id):
            return merge_machine_error(
                {"ok": False, "error": "dividend_claim_fields_required"},
                error="dividend_claim_fields_required",
                message="POST /dividend/claim requires agent_id and quote_id from a settled transition.",
                hints=["Complete POST /transition/settle first, then claim with the same quote_id."],
            )
        claim_key = f"{agent_id}:{quote_id}"
        with self._lock:
            if claim_key in (self._state.get("claims") or {}):
                return merge_machine_error(
                    {"ok": False, "error": "dividend_already_claimed"},
                    error="dividend_already_claimed",
                    message="This quote_id was already claimed for dividend minting.",
                )
            if ex is None:
                return merge_machine_error(
                    {"ok": False, "error": "dividend_exchange_missing"},
                    error="dividend_exchange_missing",
                    message="Server cannot verify transition settlement (internal configuration).",
                )
            settled = ex.quote_record(quote_id)
            if not settled or settled.get("status") != "settled":
                return merge_machine_error(
                    {"ok": False, "error": "dividend_quote_not_settled"},
                    error="dividend_quote_not_settled",
                    message="quote_id must reference a settled transition exchange record.",
                    hints=["POST /transition/settle must succeed before dividend claim."],
                )
            if str(settled.get("agent_id") or "").strip() != agent_id:
                return merge_machine_error(
                    {"ok": False, "error": "dividend_agent_mismatch"},
                    error="dividend_agent_mismatch",
                    message="agent_id does not match the transition quote owner.",
                )
            evidence_count = int(settled.get("evidence_count") or 0)
            units = round(min(25.0, 1.0 + evidence_count * 0.75 + (0.35 if settled.get("remote_addr") else 0.0)), 6)
            self._apply_decay(agent_id)
            rec = self._agent_record(agent_id)
            rec["balance_units"] = round(float(rec.get("balance_units") or 0.0) + units, 6)
            credit_id = f"rpd_{uuid.uuid4().hex[:12]}"
            exp = (datetime.now(UTC) + timedelta(hours=CREDIT_TTL_HOURS)).isoformat()
            credits = rec.setdefault("credits", [])
            credits.append(
                {
                    "credit_id": credit_id,
                    "units": units,
                    "source_quote_id": quote_id,
                    "expires_at": exp,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            rec["last_touch_at"] = datetime.now(UTC).isoformat()
            self._state.setdefault("claims", {})[claim_key] = {
                "claimed_at": datetime.now(UTC).isoformat(),
                "units": units,
                "credit_id": credit_id,
            }
            self._save()
        return {
            "ok": True,
            "schema": "nomad.reciprocity_dividend_claim.v1",
            "agent_id": agent_id,
            "quote_id": quote_id,
            "minted_units": units,
            "credit_id": credit_id,
            "expires_at": exp,
            "balance_units": round(float(rec.get("balance_units") or 0.0), 6),
        }

    def settle_credit(self, payload: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(payload.get("agent_id") or "").strip()
        credit_id = str(payload.get("credit_id") or "").strip()
        if not (agent_id and credit_id):
            return merge_machine_error(
                {"ok": False, "error": "dividend_settle_fields_required"},
                error="dividend_settle_fields_required",
                message="POST /dividend/settle requires agent_id and credit_id.",
            )
        with self._lock:
            rec = self._agent_record(agent_id)
            credits = rec.get("credits") if isinstance(rec.get("credits"), list) else []
            chosen = None
            remaining = []
            for c in credits:
                if isinstance(c, dict) and str(c.get("credit_id") or "") == credit_id:
                    chosen = c
                    continue
                remaining.append(c)
            if not chosen:
                return merge_machine_error(
                    {"ok": False, "error": "dividend_credit_not_found"},
                    error="dividend_credit_not_found",
                    message="credit_id is unknown or already consumed.",
                )
            exp = str(chosen.get("expires_at") or "")
            if exp:
                try:
                    if datetime.fromisoformat(exp.replace("Z", "+00:00")) < datetime.now(UTC):
                        rec["credits"] = remaining
                        self._save()
                        return merge_machine_error(
                            {"ok": False, "error": "dividend_credit_expired"},
                            error="dividend_credit_expired",
                            message="credit expired; proof churn must continue for fresh credits.",
                        )
                except ValueError:
                    pass
            units = float(chosen.get("units") or 0.0)
            token = f"rprt_{uuid.uuid4().hex[:16]}"
            rec["credits"] = remaining
            rec["balance_units"] = max(0.0, float(rec.get("balance_units") or 0.0) - units)
            rec["last_touch_at"] = datetime.now(UTC).isoformat()
            rec.setdefault("routing_tokens", []).append(
                {
                    "token": token,
                    "units": units,
                    "source_credit_id": credit_id,
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            self._save()
        return {
            "ok": True,
            "schema": "nomad.reciprocity_dividend_settlement.v1",
            "agent_id": agent_id,
            "consumed_credit_id": credit_id,
            "routing_token": token,
            "routing_header": "X-Nomad-Routing-Boost",
            "note": "Use routing_token on later high-yield mission/task calls to prove dividend-backed intent.",
        }

    def _agent_record(self, agent_id: str) -> dict[str, Any]:
        agents = self._state.setdefault("agents", {})
        if agent_id not in agents:
            agents[agent_id] = {"balance_units": 0.0, "credits": [], "last_decay_at": "", "last_touch_at": ""}
        return agents[agent_id]

    def _apply_decay(self, agent_id: str) -> None:
        rec = self._agent_record(agent_id)
        now = datetime.now(UTC)
        last_raw = str(rec.get("last_decay_at") or rec.get("last_touch_at") or "")
        if not last_raw:
            rec["last_decay_at"] = now.isoformat()
            return
        try:
            last = datetime.fromisoformat(last_raw.replace("Z", "+00:00"))
        except ValueError:
            rec["last_decay_at"] = now.isoformat()
            return
        delta_days = max(0.0, (now - last).total_seconds() / 86400.0)
        if delta_days <= 0:
            return
        balance = float(rec.get("balance_units") or 0.0)
        factor = (1.0 - DECAY_RATE_PER_DAY) ** delta_days
        rec["balance_units"] = round(balance * factor, 6)
        rec["last_decay_at"] = now.isoformat()
