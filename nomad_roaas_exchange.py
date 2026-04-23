from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from nomad_market_patterns import (
    ROOT,
    MarketPatternRegistry,
    PatternStatus,
)
from nomad_predictive_router import PredictiveRouter
from nomad_runtime_identity import NodeIdentity, RuntimeTrustStore
from nomad_self_healing import SelfHealingPipeline


DEFAULT_SUBMISSION_LOG_PATH = ROOT / "nomad_runtime_pattern_submissions.ndjson"


class RuntimePatternExchange:
    def __init__(
        self,
        agent: Any = None,
        registry: Optional[MarketPatternRegistry] = None,
        router: Optional[PredictiveRouter] = None,
        healer: Optional[SelfHealingPipeline] = None,
        submission_log_path: Optional[Path] = None,
        identity: Optional[NodeIdentity] = None,
        trust_store: Optional[RuntimeTrustStore] = None,
    ) -> None:
        brain_router = getattr(getattr(agent, "self_improvement", None), "brain_router", None)
        self.registry = registry or getattr(brain_router, "pattern_registry", None) or MarketPatternRegistry(
            registry_path=Path(
                os.getenv("NOMAD_RUNTIME_PATTERN_REGISTRY_PATH")
                or ROOT / "nomad_runtime_patterns.json"
            )
        )
        self.router = router or getattr(brain_router, "predictive_router", None) or PredictiveRouter(
            registry=self.registry,
            health_path=Path(
                os.getenv("NOMAD_LANE_HEALTH_PATH")
                or ROOT / "nomad_lane_health.json"
            ),
        )
        self.healer = healer or getattr(brain_router, "self_healer", None)
        self.submission_log_path = Path(submission_log_path or DEFAULT_SUBMISSION_LOG_PATH)
        self.identity = identity or NodeIdentity(public_base_url=os.getenv("NOMAD_PUBLIC_API_URL") or "")
        self.trust_store = trust_store or RuntimeTrustStore(
            path=Path(os.getenv("NOMAD_RUNTIME_TRUST_PATH") or ROOT / "nomad_runtime_trust.json")
        )

    def status(self, task_type: str = "") -> dict[str, Any]:
        submissions = self._submission_summary()
        return {
            "schema": "nomad.roaas_status.v1",
            "ok": True,
            "task_type": task_type,
            "patterns": self.registry.summary(task_type=task_type),
            "lane_status": self.router.lane_status(),
            "self_healing": self.healer.heal_summary() if self.healer else {"total_actions": 0},
            "submissions": submissions,
            "source_node": self.identity.source_node(
                extra={"artifact_path": "/artifacts/runtime-patterns"}
            ),
            "signing": {
                "enabled": self.identity.can_sign,
                "algorithm": "hmac-sha256" if self.identity.can_sign else "unsigned",
                "key_id": self.identity.key_id,
            },
            "trust_store": self.trust_store.summary(),
            "analysis": (
                "Nomad can exchange runtime patterns across swarm nodes. "
                "Imported patterns are downgraded to candidate trust until locally reverified."
            ),
        }

    def export_bundle(
        self,
        task_type: str = "",
        include_executions: bool = True,
        min_status: PatternStatus = PatternStatus.CANDIDATE,
        as_envelope: bool = True,
    ) -> dict[str, Any]:
        bundle = self.registry.bundle_payload(
            task_type=task_type,
            min_status=min_status,
            include_executions=include_executions,
        )
        bundle["schema"] = "nomad.roaas_bundle.v1"
        bundle["lane_status"] = self.router.lane_status()
        bundle["self_healing"] = self.healer.heal_summary() if self.healer else {"total_actions": 0}
        bundle["generated_at"] = datetime.now(UTC).isoformat()
        if not as_envelope:
            return bundle
        return self.identity.sign_bundle(
            bundle,
            extra_node={"artifact_path": "/artifacts/runtime-patterns"},
        )

    def import_bundle(
        self,
        payload: dict[str, Any],
        *,
        source: str = "",
        trust_level: PatternStatus = PatternStatus.CANDIDATE,
    ) -> dict[str, Any]:
        bundle = self._extract_bundle(payload)
        if not bundle:
            return {
                "ok": False,
                "error": "bundle_required",
                "message": "Provide a bundle payload or an envelope with a 'bundle' key.",
            }
        envelope = self._extract_envelope(payload)
        verification = self.identity.verify_envelope(envelope) if envelope else {
            "ok": True,
            "signed": False,
            "verified": False,
            "signature_valid": False,
            "reason": "unsigned_bundle",
            "trust_score": 0.2,
            "source_node": {},
            "key_id": "",
        }
        source_node = self._source_node_from_payload(payload, envelope)
        if verification.get("signed") and not verification.get("signature_valid") and verification.get("reason") != "verification_secret_missing":
            return {
                "ok": False,
                "error": "signature_verification_failed",
                "verification": verification,
                "message": "The runtime pattern envelope was signed, but signature verification failed.",
            }

        import_result = self.registry.import_bundle_payload(
            bundle,
            trust_level=trust_level,
            source=source or self._describe_source(payload),
            source_node=source_node,
            verification=verification,
        )
        promotion_report = self.registry.evaluate_promotions()
        trust_record = self.trust_store.record_observation(
            source_node=source_node,
            verification=verification,
            import_result=import_result,
        )
        submission_record = self._record_submission(
            payload=payload,
            source=source or self._describe_source(payload),
            import_result=import_result,
            verification=verification,
            task_type=str(bundle.get("task_type") or ""),
            total_patterns=int(bundle.get("total_patterns") or 0),
        )
        return {
            "ok": True,
            "schema": "nomad.roaas_import_receipt.v1",
            "import": import_result,
            "verification": verification,
            "trust_record": trust_record,
            "promotion_report": promotion_report,
            "submission": submission_record,
            "status": self.status(task_type=str(bundle.get("task_type") or "")),
        }

    def _extract_bundle(self, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload.get("bundle"), dict):
            nested = payload["bundle"]
            if isinstance(nested.get("patterns"), list):
                return nested
            if isinstance(nested.get("bundle"), dict):
                return self._extract_bundle(nested)
        if isinstance(payload.get("patterns"), list):
            return payload
        return {}

    def _extract_envelope(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        if isinstance(payload.get("bundle"), dict) and "signature" in payload and "source_node" in payload:
            return payload
        nested = payload.get("bundle")
        if isinstance(nested, dict):
            return self._extract_envelope(nested)
        return {}

    @staticmethod
    def _source_node_from_payload(payload: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
        if envelope and isinstance(envelope.get("source_node"), dict):
            return envelope["source_node"]
        if isinstance(payload.get("source_node"), dict):
            return payload["source_node"]
        return {}

    def _record_submission(
        self,
        *,
        payload: dict[str, Any],
        source: str,
        import_result: dict[str, Any],
        verification: dict[str, Any],
        task_type: str,
        total_patterns: int,
    ) -> dict[str, Any]:
        record = {
            "schema": "nomad.roaas_submission.v1",
            "received_at": datetime.now(UTC).isoformat(),
            "source": source,
            "task_type": task_type,
            "total_patterns": total_patterns,
            "imported": int(import_result.get("imported") or 0),
            "skipped_existing": int(import_result.get("skipped_existing") or 0),
            "source_node": self._source_node_from_payload(payload, self._extract_envelope(payload)),
            "signature_valid": bool(verification.get("signature_valid")),
            "verification_reason": str(verification.get("reason") or ""),
        }
        self.submission_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.submission_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def _submission_summary(self) -> dict[str, Any]:
        if not self.submission_log_path.exists():
            return {
                "log_path": str(self.submission_log_path),
                "count": 0,
                "recent": [],
            }
        recent: list[dict[str, Any]] = []
        try:
            lines = self.submission_log_path.read_text(encoding="utf-8").splitlines()
        except Exception:
            lines = []
        for line in lines[-10:]:
            try:
                recent.append(json.loads(line))
            except Exception:
                continue
        return {
            "log_path": str(self.submission_log_path),
            "count": len(lines),
            "recent": recent[-5:],
        }

    @staticmethod
    def _describe_source(payload: dict[str, Any]) -> str:
        if payload.get("schema") == "nomad.roaas_bundle_envelope.v1" and isinstance(payload.get("source_node"), dict):
            node = payload["source_node"]
            for key in ("public_node_url", "local_base_url", "swarm_home_url", "node_name"):
                value = str(node.get(key) or "").strip()
                if value:
                    return value
        if isinstance(payload.get("source_node"), dict):
            node = payload["source_node"]
            for key in ("public_node_url", "local_base_url", "swarm_home_url", "node_name"):
                value = str(node.get(key) or "").strip()
                if value:
                    return value
        return str(payload.get("source") or "unknown_source").strip() or "unknown_source"
