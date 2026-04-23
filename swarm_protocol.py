import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|ck|rnd|ghp|hf|xai|AIza)[A-Za-z0-9_.\-]{16,}\b"),
    re.compile(r"\b0x[a-fA-F0-9]{64}\b"),
)


class SwarmVerifier:
    """Verifier for inbound Swarm-to-Swarm aid proposals."""

    def __init__(self, trust_store_path: Optional[Path] = None) -> None:
        self.trust_store_path = trust_store_path

    def verify_proposal(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize(proposal)
        errors: List[str] = []
        for key in ("sender_id", "title", "proposal"):
            if not normalized.get(key):
                errors.append(f"{key}_required")
        if not normalized["evidence"]:
            errors.append("evidence_required")
        if self._contains_secret(normalized):
            errors.append("secret_like_value_detected")
        if normalized.get("code") or normalized.get("module_code"):
            errors.append("raw_code_not_accepted")

        payload = normalized.get("payload") or {}
        claimed_hash = str(normalized.get("payload_hash") or normalized.get("code_hash") or "").strip()
        calculated_hash = self.payload_hash(payload)
        if claimed_hash and claimed_hash != calculated_hash:
            errors.append("payload_hash_mismatch")

        score = self._score(normalized=normalized, has_hash=bool(claimed_hash and claimed_hash == calculated_hash))
        status = "verified" if not errors and score >= 0.55 else "rejected"
        aid_id = f"aid-{calculated_hash[:12]}"
        return {
            "schema": "nomad.swarm_proposal_verification.v1",
            "verified": status == "verified",
            "status": status,
            "aid_id": aid_id,
            "score": score,
            "errors": errors,
            "reason": ", ".join(errors) if errors else "proposal_verified",
            "payload_hash": calculated_hash,
            "normalized": normalized,
            "verified_at": datetime.now(UTC).isoformat(),
        }

    def verify_request(self, aid_package: Dict[str, Any]) -> Dict[str, Any]:
        """Backward-compatible alias for earlier /aid sketches."""
        return self.verify_proposal(aid_package)

    @staticmethod
    def payload_hash(payload: Any) -> str:
        return hashlib.sha256(
            json.dumps(payload if payload is not None else {}, sort_keys=True, ensure_ascii=True).encode("utf-8")
        ).hexdigest()

    def _normalize(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        payload = proposal.get("payload") if isinstance(proposal.get("payload"), dict) else {}
        evidence = proposal.get("evidence") or proposal.get("evidence_items") or []
        if isinstance(evidence, str):
            evidence = [item.strip() for item in re.split(r"[|,\n]+", evidence) if item.strip()]
        return {
            "sender_id": self._clean_id(proposal.get("sender_id") or proposal.get("agent") or proposal.get("from") or ""),
            "sender_endpoint": str(proposal.get("sender_endpoint") or proposal.get("endpoint") or "")[:300],
            "title": " ".join(str(proposal.get("title") or proposal.get("module_name") or "").split())[:160],
            "proposal": " ".join(str(proposal.get("proposal") or proposal.get("description") or proposal.get("message") or "").split())[:1200],
            "pain_type": self._clean_id(proposal.get("pain_type") or proposal.get("service_type") or "self_improvement"),
            "evidence": [str(item).strip()[:240] for item in evidence if str(item).strip()][:10],
            "payload": payload,
            "payload_hash": str(proposal.get("payload_hash") or "").strip(),
            "code_hash": str(proposal.get("code_hash") or "").strip(),
            "test_suite_ref": str(proposal.get("test_suite_ref") or "")[:300],
            "expected_outcome": str(proposal.get("expected_outcome") or "")[:500],
            "code": proposal.get("code"),
            "module_code": proposal.get("module_code"),
        }

    @staticmethod
    def _score(normalized: Dict[str, Any], has_hash: bool) -> float:
        score = 0.15
        score += 0.15 if normalized.get("sender_id") else 0.0
        score += 0.15 if normalized.get("title") else 0.0
        score += 0.2 if normalized.get("proposal") else 0.0
        score += min(0.2, len(normalized.get("evidence") or []) * 0.05)
        score += 0.1 if has_hash else 0.0
        score += 0.05 if normalized.get("test_suite_ref") else 0.0
        return round(min(1.0, score), 4)

    @staticmethod
    def _clean_id(value: Any) -> str:
        text = str(value or "").strip().lower().replace("-", "_")
        text = re.sub(r"[^a-z0-9_.:/]+", "_", text)
        return text[:100].strip("_")

    @staticmethod
    def _contains_secret(payload: Dict[str, Any]) -> bool:
        text = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        return any(pattern.search(text) for pattern in SECRET_PATTERNS)


class AidRegistrar:
    """Small registry for verified inbound aid packages."""

    def __init__(self, registrar_path: Optional[Path] = None) -> None:
        self.path = registrar_path or Path(__file__).resolve().parent / "verified_aid_registry.json"

    def register_and_audit(self, aid_id: str, package: Dict[str, Any]) -> Dict[str, Any]:
        registry = self._load()
        record = {
            "schema": "nomad.verified_aid_registry_entry.v1",
            "aid_id": aid_id,
            "registered_at": datetime.now(UTC).isoformat(),
            "status": "registered_for_local_review",
            "package": package,
        }
        registry[aid_id] = record
        self.path.write_text(json.dumps(registry, ensure_ascii=True, indent=2), encoding="utf-8")
        return record

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}
