from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parent
DEFAULT_TRUST_STORE_PATH = ROOT / "nomad_runtime_trust.json"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass
class NodeIdentity:
    node_name: str = ""
    shared_secret: str = ""
    public_base_url: str = ""
    profile_hint: str = ""
    key_id: str = ""

    def __post_init__(self) -> None:
        self.node_name = (self.node_name or os.getenv("NOMAD_NODE_NAME") or platform.node() or "nomad-node").strip()
        self.shared_secret = (
            self.shared_secret
            or os.getenv("NOMAD_SWARM_SHARED_SECRET")
            or os.getenv("NOMAD_NODE_SECRET")
            or ""
        ).strip()
        self.public_base_url = (
            self.public_base_url
            or os.getenv("NOMAD_PUBLIC_API_URL")
            or ""
        ).rstrip("/")
        self.profile_hint = (
            self.profile_hint
            or os.getenv("NOMAD_NODE_PROFILE_HINT")
            or os.getenv("NOMAD_PROFILE_HINT")
            or "general"
        ).strip()
        if not self.key_id:
            material = self.shared_secret or self.node_name or "nomad"
            self.key_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

    @property
    def node_id(self) -> str:
        return hashlib.sha256(f"{self.node_name}:{self.key_id}".encode("utf-8")).hexdigest()[:16]

    @property
    def can_sign(self) -> bool:
        return bool(self.shared_secret)

    def source_node(self, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "node_name": self.node_name,
            "node_id": self.node_id,
            "key_id": self.key_id,
            "profile_hint": self.profile_hint or "general",
            "public_node_url": self.public_base_url,
            "generated_at": _iso_now(),
        }
        if extra:
            payload.update({key: value for key, value in extra.items() if value not in {None, ""}})
        return payload

    def sign_bundle(
        self,
        bundle: dict[str, Any],
        *,
        extra_node: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        source_node = self.source_node(extra=extra_node)
        signed_at = _iso_now()
        material = {
            "bundle": bundle,
            "key_id": self.key_id,
            "signed_at": signed_at,
            "source_node": source_node,
        }
        signature = self._signature(material)
        return {
            "schema": "nomad.roaas_bundle_envelope.v1",
            "bundle": bundle,
            "source_node": source_node,
            "signed_at": signed_at,
            "signature": signature,
            "signature_algorithm": "hmac-sha256" if signature else "unsigned",
            "key_id": self.key_id,
        }

    def verify_envelope(self, envelope: dict[str, Any]) -> dict[str, Any]:
        bundle = envelope.get("bundle") if isinstance(envelope.get("bundle"), dict) else {}
        source_node = envelope.get("source_node") if isinstance(envelope.get("source_node"), dict) else {}
        signature = str(envelope.get("signature") or "").strip()
        algorithm = str(envelope.get("signature_algorithm") or "unsigned").strip().lower()
        key_id = str(envelope.get("key_id") or source_node.get("key_id") or "").strip()
        if not bundle:
            return {
                "ok": False,
                "signed": False,
                "verified": False,
                "signature_valid": False,
                "reason": "bundle_required",
                "trust_score": 0.0,
                "source_node": source_node,
                "key_id": key_id,
            }
        if not signature:
            return {
                "ok": True,
                "signed": False,
                "verified": False,
                "signature_valid": False,
                "reason": "unsigned_envelope",
                "trust_score": 0.2,
                "source_node": source_node,
                "key_id": key_id,
            }
        if algorithm != "hmac-sha256":
            return {
                "ok": False,
                "signed": True,
                "verified": False,
                "signature_valid": False,
                "reason": "unsupported_signature_algorithm",
                "trust_score": 0.0,
                "source_node": source_node,
                "key_id": key_id,
            }
        if not self.shared_secret:
            return {
                "ok": True,
                "signed": True,
                "verified": False,
                "signature_valid": False,
                "reason": "verification_secret_missing",
                "trust_score": 0.35,
                "source_node": source_node,
                "key_id": key_id,
            }
        material = {
            "bundle": bundle,
            "key_id": key_id,
            "signed_at": str(envelope.get("signed_at") or ""),
            "source_node": source_node,
        }
        expected = self._signature(material)
        valid = bool(signature) and hmac.compare_digest(signature, expected)
        return {
            "ok": valid,
            "signed": True,
            "verified": valid,
            "signature_valid": valid,
            "reason": "signature_verified" if valid else "signature_mismatch",
            "trust_score": 0.75 if valid else 0.0,
            "source_node": source_node,
            "key_id": key_id,
        }

    def _signature(self, material: dict[str, Any]) -> str:
        if not self.shared_secret:
            return ""
        return hmac.new(
            self.shared_secret.encode("utf-8"),
            _canonical_json(material).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


class RuntimeTrustStore:
    TRUST_PATH = DEFAULT_TRUST_STORE_PATH

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path or self.TRUST_PATH)
        self._store = self._load()

    def record_observation(
        self,
        *,
        source_node: dict[str, Any],
        verification: dict[str, Any],
        import_result: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        node_id = str(source_node.get("node_id") or source_node.get("node_name") or "unknown").strip() or "unknown"
        record = self._store.setdefault(
            node_id,
            {
                "node_id": node_id,
                "node_name": str(source_node.get("node_name") or ""),
                "key_id": str(source_node.get("key_id") or ""),
                "observations": 0,
                "verified_signatures": 0,
                "unsigned_observations": 0,
                "signature_failures": 0,
                "successful_imports": 0,
                "last_seen_at": "",
                "trust_score": 0.0,
            },
        )
        record["observations"] = int(record.get("observations") or 0) + 1
        if verification.get("signature_valid"):
            record["verified_signatures"] = int(record.get("verified_signatures") or 0) + 1
        elif verification.get("signed"):
            record["signature_failures"] = int(record.get("signature_failures") or 0) + 1
        else:
            record["unsigned_observations"] = int(record.get("unsigned_observations") or 0) + 1
        if import_result and int(import_result.get("imported") or 0) > 0:
            record["successful_imports"] = int(record.get("successful_imports") or 0) + int(import_result.get("imported") or 0)
        record["node_name"] = str(source_node.get("node_name") or record.get("node_name") or "")
        record["key_id"] = str(source_node.get("key_id") or record.get("key_id") or "")
        record["last_seen_at"] = _iso_now()
        record["trust_score"] = self._score(record)
        self._save()
        return record

    def summary(self) -> dict[str, Any]:
        entries = sorted(
            self._store.values(),
            key=lambda item: (-float(item.get("trust_score") or 0.0), str(item.get("node_name") or item.get("node_id") or "")),
        )
        return {
            "trust_store_path": str(self.path),
            "node_count": len(entries),
            "nodes": entries[:10],
        }

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._store, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _score(record: dict[str, Any]) -> float:
        observations = max(1, int(record.get("observations") or 0))
        verified = int(record.get("verified_signatures") or 0)
        unsigned = int(record.get("unsigned_observations") or 0)
        failures = int(record.get("signature_failures") or 0)
        imports = int(record.get("successful_imports") or 0)
        score = 0.15
        score += min(0.45, (verified / observations) * 0.45)
        score += min(0.2, imports * 0.03)
        score += min(0.05, unsigned * 0.01)
        score -= min(0.4, failures * 0.2)
        return round(max(0.0, min(1.0, score)), 4)
