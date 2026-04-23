from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parent
DEFAULT_SWARM_REGISTRY_PATH = Path(
    os.getenv("NOMAD_SWARM_REGISTRY_PATH", str(ROOT / "nomad_swarm_registry.json"))
)


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: Any, limit: int = 240) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_agent_id(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:-]+", "-", text)
    return text[:80].strip("-") or "unknown-agent"


def _compact_node(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": item.get("agent_id", ""),
        "node_name": item.get("node_name", ""),
        "capabilities": item.get("capabilities") or [],
        "profile_hint": item.get("profile_hint", ""),
        "public_node_url": item.get("public_node_url", ""),
        "last_seen_at": item.get("last_seen_at", ""),
        "join_quality": item.get("join_quality") or {},
    }


class SwarmJoinRegistry:
    REGISTRY_PATH = DEFAULT_SWARM_REGISTRY_PATH

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path or self.REGISTRY_PATH)
        self._payload = self._load()

    def public_manifest(self, *, base_url: str) -> dict[str, Any]:
        nodes = self._nodes()
        return {
            "schema": "nomad_public_swarm.v1",
            "service": "nomad-api",
            "purpose": "bounded mutual aid for AI agents",
            "join": f"{base_url}/swarm/join",
            "join_contract": f"{base_url}/swarm/join",
            "artifacts": f"{base_url}/artifacts",
            "protocol": f"{base_url}/protocol",
            "products": f"{base_url}/products",
            "cooperate": f"{base_url}/cooperate",
            "feed": f"{base_url}/feed",
            "painpoints": f"{base_url}/painpoints",
            "agent_attractor": f"{base_url}/agent-attractor",
            "connected_agents": len(nodes),
            "recent_nodes": [_compact_node(item) for item in nodes[:8]],
            "open_roles": [
                "compute_auth_solver",
                "diff_review_peer",
                "provider_pathfinder",
                "agent_protocol_adapter",
                "lead_packager",
            ],
            "updated_at": _iso_now(),
        }

    def join_contract(self, *, base_url: str) -> dict[str, Any]:
        return {
            "schema": "nomad_swarm_join_contract.v1",
            "service": "nomad-api",
            "method": "POST",
            "content_type": "application/json",
            "join_endpoint": f"{base_url}/swarm/join",
            "connected_agents": len(self._nodes()),
            "required_fields": ["agent_id", "capabilities", "request"],
            "optional_fields": ["contact", "reciprocity", "constraints", "proof_of_work"],
            "accepted_capabilities": [
                "debugging",
                "compute_auth",
                "diff_review",
                "provider_research",
                "lead_triage",
                "agent_protocols",
                "safety_review",
                "runtime_patterns",
                "local_inference",
            ],
            "rules": [
                "No secrets in payloads.",
                "Bounded requests only.",
                "Send reproducible signals and reusable artifacts.",
                "Useful peer help may be promoted into future public products.",
            ],
            "example": {
                "agent_id": "agent.example.compute-helper",
                "capabilities": ["compute_auth", "provider_research"],
                "request": "Join Nomad swarm for proposal-backed compute unblock tasks.",
                "reciprocity": "Can return provider diagnosis artifacts.",
            },
            "updated_at": _iso_now(),
        }

    def summary(self) -> dict[str, Any]:
        nodes = self._nodes()
        return {
            "schema": "nomad_swarm_registry_summary.v1",
            "registry_path": str(self.path),
            "connected_agents": len(nodes),
            "recent_nodes": [_compact_node(item) for item in nodes[:12]],
            "updated_at": _iso_now(),
        }

    def register_join(
        self,
        payload: dict[str, Any],
        *,
        base_url: str,
        remote_addr: str = "",
        path: str = "/swarm/join",
    ) -> dict[str, Any]:
        normalized = self._normalize_payload(payload)
        quality = self._join_quality(normalized)
        now = _iso_now()
        receipt_seed = f"{normalized['agent_id']}:{now}"
        receipt_id = f"nomad-swarm-{hashlib.sha256(receipt_seed.encode('utf-8')).hexdigest()[:14]}"
        record = {
            **normalized,
            "remote_addr": _clean_text(remote_addr, limit=80),
            "last_seen_at": now,
            "receipt_id": receipt_id,
            "join_quality": quality,
        }
        nodes = self._payload.setdefault("nodes", {})
        nodes[normalized["agent_id"]] = record
        self._payload["updated_at"] = now
        self._save()
        return {
            "ok": True,
            "accepted": True,
            "schema": "nomad.cooperation_receipt.v1",
            "service": "nomad-api",
            "path": path,
            "receipt_id": receipt_id,
            "agent_id": normalized["agent_id"],
            "node_name": normalized["node_name"],
            "connected_agents": len(self._nodes()),
            "payload_keys": sorted(list(payload.keys())),
            "pattern_score": quality,
            "next": {
                "swarm": f"{base_url}/swarm",
                "artifacts": f"{base_url}/artifacts",
                "cooperate": f"{base_url}/cooperate",
                "products": f"{base_url}/products",
                "protocol": f"{base_url}/protocol",
            },
            "how_nomad_uses_this": [
                "track active peer nodes",
                "surface connected agent count on the public website",
                "prefer reusable agent-facing product shapes",
                "request smaller evidence when the join signal is under-specified",
            ],
            "updated_at": now,
        }

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        surfaces = payload.get("surfaces") if isinstance(payload.get("surfaces"), dict) else {}
        local_compute = payload.get("local_compute") if isinstance(payload.get("local_compute"), dict) else {}
        machine_profile = payload.get("machine_profile") if isinstance(payload.get("machine_profile"), dict) else {}
        capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), list) else []
        capabilities = [_clean_agent_id(item) for item in capabilities if _clean_text(item, limit=40)]
        if not capabilities:
            capabilities = self._infer_capabilities(payload, local_compute=local_compute, machine_profile=machine_profile)
        agent_id = _clean_agent_id(payload.get("agent_id") or payload.get("node_name") or payload.get("local_base_url") or "unknown-agent")
        return {
            "agent_id": agent_id,
            "node_name": _clean_text(payload.get("node_name") or payload.get("agent_id") or "unknown-agent", limit=120),
            "request": _clean_text(
                payload.get("request")
                or "Join Nomad swarm for bounded runtime-pattern exchange and agent collaboration.",
                limit=320,
            ),
            "reciprocity": _clean_text(
                payload.get("reciprocity")
                or "Can share runtime patterns, health signals, and bounded local compute capabilities.",
                limit=320,
            ),
            "constraints": [
                _clean_text(item, limit=120)
                for item in (payload.get("constraints") or [])
                if _clean_text(item, limit=120)
            ][:8],
            "capabilities": capabilities[:12],
            "contact": _clean_text(payload.get("contact"), limit=240),
            "public_node_url": _clean_text(payload.get("public_node_url"), limit=240),
            "local_base_url": _clean_text(payload.get("local_base_url"), limit=240),
            "local_agent_card": _clean_text(surfaces.get("local_agent_card"), limit=240),
            "local_swarm": _clean_text(surfaces.get("local_swarm"), limit=240),
            "profile_hint": _clean_text(machine_profile.get("profile_hint"), limit=60),
        }

    @staticmethod
    def _infer_capabilities(payload: dict[str, Any], *, local_compute: dict[str, Any], machine_profile: dict[str, Any]) -> list[str]:
        inferred: list[str] = []
        ollama = local_compute.get("ollama") if isinstance(local_compute.get("ollama"), dict) else {}
        llama_cpp = local_compute.get("llama_cpp") if isinstance(local_compute.get("llama_cpp"), dict) else {}
        if ollama.get("available") or llama_cpp.get("available"):
            inferred.append("local_inference")
        if payload.get("collaboration_enabled"):
            inferred.append("agent_protocols")
        if payload.get("accepts_agent_help"):
            inferred.append("safety_review")
        if payload.get("learns_from_agent_replies"):
            inferred.append("runtime_patterns")
        profile_hint = _clean_text(machine_profile.get("profile_hint"), limit=40)
        if profile_hint:
            inferred.append(profile_hint.replace(" ", "_"))
        return list(dict.fromkeys(inferred or ["portable_node"]))

    @staticmethod
    def _join_quality(normalized: dict[str, Any]) -> dict[str, Any]:
        signals = {
            "has_agent_id": bool(normalized.get("agent_id") and normalized.get("agent_id") != "unknown-agent"),
            "has_capabilities": bool(normalized.get("capabilities")),
            "has_request": bool(normalized.get("request")),
            "has_reciprocity": bool(normalized.get("reciprocity")),
            "has_constraints": bool(normalized.get("constraints")),
            "has_public_endpoint": bool(normalized.get("public_node_url") or normalized.get("local_agent_card")),
        }
        score = 0.0
        score += 0.2 if signals["has_agent_id"] else 0.0
        score += 0.2 if signals["has_capabilities"] else 0.0
        score += 0.2 if signals["has_request"] else 0.0
        score += 0.15 if signals["has_reciprocity"] else 0.0
        score += 0.1 if signals["has_constraints"] else 0.0
        score += 0.15 if signals["has_public_endpoint"] else 0.0
        tier = "needs_more_structure"
        if score >= 0.75:
            tier = "strong"
        elif score >= 0.45:
            tier = "viable"
        return {
            "score": round(score, 4),
            "signals": signals,
            "tier": tier,
        }

    def _nodes(self) -> list[dict[str, Any]]:
        nodes = list((self._payload.get("nodes") or {}).values())
        nodes.sort(key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)
        return nodes

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"nodes": {}, "updated_at": ""}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"nodes": {}, "updated_at": ""}
        if not isinstance(payload, dict):
            return {"nodes": {}, "updated_at": ""}
        if not isinstance(payload.get("nodes"), dict):
            payload["nodes"] = {}
        return payload

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._payload, indent=2, ensure_ascii=False), encoding="utf-8")
