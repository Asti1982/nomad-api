import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv


load_dotenv()


class X402PaymentAdapter:
    """Small x402 v2 adapter for Nomad's HTTP service surface."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        load_dotenv(override=True)
        self.session = session or requests.Session()
        self.facilitator_url = (
            os.getenv("NOMAD_X402_FACILITATOR_URL")
            or "https://x402.org/facilitator"
        ).rstrip("/")
        self.facilitator_bearer = (
            os.getenv("NOMAD_X402_FACILITATOR_BEARER_TOKEN")
            or os.getenv("CDP_X402_BEARER_TOKEN")
            or ""
        ).strip()
        self.asset_address = (os.getenv("NOMAD_X402_ASSET_ADDRESS") or "").strip()
        self.asset_symbol = (os.getenv("NOMAD_X402_ASSET_SYMBOL") or "USDC").strip() or "USDC"
        self.asset_decimals = int(os.getenv("NOMAD_X402_ASSET_DECIMALS", "6"))
        self.max_timeout_seconds = int(os.getenv("NOMAD_X402_MAX_TIMEOUT_SECONDS", "60"))
        self.enabled = (
            os.getenv("NOMAD_X402_ENABLED", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )

    def build_challenge(
        self,
        *,
        task_id: str,
        amount_native: float,
        pay_to: str,
        network_caip2: str,
        resource_url: str,
        description: str,
        service_type: str,
    ) -> Dict[str, Any]:
        configured = bool(self.enabled and self.asset_address and pay_to and network_caip2)
        requirements = self.payment_requirements(
            amount_native=amount_native,
            pay_to=pay_to,
            network_caip2=network_caip2,
            task_id=task_id,
            service_type=service_type,
        )
        challenge = {
            "x402Version": 2,
            "statusCode": 402,
            "configured": configured,
            "scheme": "exact",
            "network": network_caip2,
            "asset": self.asset_address,
            "asset_symbol": self.asset_symbol,
            "amount": requirements.get("amount", "0"),
            "amount_display": round(float(amount_native), 8),
            "payTo": pay_to,
            "recipient": pay_to,
            "task_id": task_id,
            "service_type": service_type,
            "facilitator_url": self.facilitator_url,
            "paymentRequirements": requirements,
            "accepts": [requirements] if configured else [],
            "resource": {
                "url": resource_url,
                "description": description,
                "mimeType": "application/json",
            },
            "headers": {
                "PAYMENT-REQUIRED": "base64url JSON challenge on 402 response",
                "PAYMENT-SIGNATURE": "base64url x402 v2 payment payload on retry",
                "PAYMENT-RESPONSE": "base64url verification result on success",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }
        challenge["encoded_header"] = self.encode_header(challenge)
        if not configured:
            challenge["configuration_error"] = self._configuration_error(pay_to, network_caip2)
        return challenge

    def payment_requirements(
        self,
        *,
        amount_native: float,
        pay_to: str,
        network_caip2: str,
        task_id: str,
        service_type: str,
    ) -> Dict[str, Any]:
        units = self.amount_to_units(amount_native)
        return {
            "scheme": "exact",
            "network": network_caip2,
            "asset": self.asset_address,
            "amount": str(units),
            "payTo": pay_to,
            "maxTimeoutSeconds": self.max_timeout_seconds,
            "extra": {
                "name": self.asset_symbol,
                "version": "2",
                "nomadTaskId": task_id,
                "serviceType": service_type,
            },
        }

    def verify_signature(
        self,
        *,
        payment_signature: str,
        payment_requirements: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.enabled:
            return self._verify_error("x402_disabled", "NOMAD_X402_ENABLED is false.")
        if not self.asset_address:
            return self._verify_error("x402_asset_missing", "Set NOMAD_X402_ASSET_ADDRESS before x402 verification.")
        if not payment_signature:
            return self._verify_error("payment_signature_required", "Send PAYMENT-SIGNATURE on retry.")
        if not payment_requirements:
            return self._verify_error("payment_requirements_required", "No x402 paymentRequirements are stored for this task.")

        decoded = self.decode_header(payment_signature)
        if decoded.get("ok") is False:
            return decoded
        payment_payload = decoded["payload"]
        body = {
            "x402Version": 2,
            "paymentPayload": payment_payload,
            "paymentRequirements": payment_requirements,
        }
        try:
            response = self.session.post(
                self._verify_url(),
                json=body,
                headers=self._headers(),
                timeout=20,
            )
        except Exception as exc:
            return self._verify_error("facilitator_unreachable", f"x402 facilitator request failed: {exc}")

        try:
            payload = response.json()
        except Exception:
            payload = {"raw": (getattr(response, "text", "") or "")[:500]}

        if not getattr(response, "ok", False):
            return {
                "ok": False,
                "status": "facilitator_rejected",
                "status_code": getattr(response, "status_code", None),
                "message": "x402 facilitator did not accept the verification request.",
                "facilitator_response": payload,
            }

        is_valid = bool(payload.get("isValid"))
        return {
            "ok": is_valid,
            "status": "x402_verified" if is_valid else "x402_invalid",
            "message": "x402 payment verified by facilitator." if is_valid else payload.get("invalidMessage", "x402 payment is invalid."),
            "payer": payload.get("payer", ""),
            "invalid_reason": payload.get("invalidReason", ""),
            "facilitator_response": payload,
        }

    def amount_to_units(self, amount_native: float) -> int:
        return max(1, int(round(float(amount_native) * (10 ** self.asset_decimals))))

    def fingerprint(self, payment_signature: str) -> str:
        return hashlib.sha256(str(payment_signature or "").encode("utf-8")).hexdigest()

    def payment_response_header(self, verification: Dict[str, Any]) -> str:
        return self.encode_header(
            {
                "x402Version": 2,
                "ok": bool(verification.get("ok")),
                "status": verification.get("status", ""),
                "payer": verification.get("payer", ""),
                "invalidReason": verification.get("invalid_reason", ""),
            }
        )

    def encode_header(self, payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def decode_header(self, value: str) -> Dict[str, Any]:
        value = str(value or "").strip()
        if not value:
            return self._verify_error("header_required", "x402 header is empty.")
        try:
            return {"ok": True, "payload": json.loads(value)}
        except json.JSONDecodeError:
            pass
        try:
            padding = "=" * (-len(value) % 4)
            decoded = base64.urlsafe_b64decode((value + padding).encode("ascii"))
            return {"ok": True, "payload": json.loads(decoded.decode("utf-8"))}
        except Exception as exc:
            return self._verify_error("invalid_x402_header", f"Could not decode x402 header: {exc}")

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.facilitator_bearer:
            headers["Authorization"] = f"Bearer {self.facilitator_bearer}"
        return headers

    def _verify_url(self) -> str:
        if self.facilitator_url.endswith("/verify"):
            return self.facilitator_url
        return f"{self.facilitator_url}/verify"

    def _configuration_error(self, pay_to: str, network_caip2: str) -> str:
        missing = []
        if not self.enabled:
            missing.append("NOMAD_X402_ENABLED")
        if not self.asset_address:
            missing.append("NOMAD_X402_ASSET_ADDRESS")
        if not pay_to:
            missing.append("AGENT_ADDRESS")
        if not network_caip2:
            missing.append("NOMAD_X402_NETWORK or EVM_CHAIN_ID")
        return "missing " + ", ".join(missing) if missing else ""

    def _verify_error(self, status: str, message: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "message": message,
        }
