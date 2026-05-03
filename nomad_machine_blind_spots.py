"""Machine blind spots: signals operators and humans rarely correlate or expect.

Examples: JSON-contract routes returning HTML facades, gateway/retry status mass, readiness
disagreeing with superficial /health OK, OpenAPI bodies missing the `openapi` version field.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from nomad_network_steward_agent import run_network_steward_cycle


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _is_json_contract_path(url: str) -> bool:
    u = url.lower()
    return any(
        fragment in u
        for fragment in (
            "/openapi.json",
            "/.well-known/nomad-agent.json",
            "/.well-known/agent-card.json",
            "nomad-agent.json",
            "agent-card.json",
        )
    )


def _body_html_facade(body: Any) -> bool:
    if isinstance(body, dict):
        raw = str(body.get("raw") or "")
        blob = raw if raw else json.dumps(body, default=str)[:800]
    else:
        blob = str(body or "")[:800]
    low = blob.lower()
    return "<html" in low or "<!doctype" in low or "<body" in low


def _openapi_semantic_hole(url: str, body: Any, status: int) -> Optional[str]:
    if status < 200 or status >= 300:
        return None
    if "openapi" not in url.lower():
        return None
    if isinstance(body, dict):
        if body.get("raw"):
            return None
        if "openapi" not in body:
            return "openapi_version_field_absent"
    return None


def _append_edge_log_line(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def run_machine_blind_spot_pass(
    *,
    base_url: str = "",
    timeout: float = 25.0,
    agent_id: str = "",
    append_log: bool = False,
    log_path: str = "",
) -> Dict[str, Any]:
    """
    One steward read pass, then second-order checks humans rarely script.
    """
    steward = run_network_steward_cycle(
        base_url=base_url,
        timeout=timeout,
        agent_id=agent_id,
        dry_run=True,
        feed_swarm=False,
        peer_glimpse=True,
    )
    probes = ((steward.get("swarm_helper") or {}).get("probes")) or []
    if not isinstance(probes, list):
        probes = []

    histogram: Dict[str, int] = {}
    gateway_or_throttle = 0
    json_contract_html_facades: List[Dict[str, Any]] = []
    openapi_holes: List[Dict[str, Any]] = []

    health_ok: Optional[bool] = None
    swarm_ok: Optional[bool] = None
    for p in probes:
        if not isinstance(p, dict):
            continue
        st = int(p.get("status") or 0)
        key = str(st)
        histogram[key] = histogram.get(key, 0) + 1
        if st in {429, 502, 503, 504}:
            gateway_or_throttle += 1
        url = str(p.get("url") or "")
        path = urlparse(url).path or ""
        if path.rstrip("/").endswith("/health"):
            health_ok = bool(p.get("ok"))
        if path.rstrip("/").endswith("/swarm"):
            swarm_ok = bool(p.get("ok"))
        body = p.get("body")
        if _is_json_contract_path(url) and _body_html_facade(body):
            json_contract_html_facades.append(
                {
                    "url": url,
                    "status": st,
                    "snippet": (str(body)[:160] if not isinstance(body, dict) else str(body.get("raw") or body)[:160]),
                }
            )
        hole = _openapi_semantic_hole(url, body, st)
        if hole:
            openapi_holes.append({"url": url, "kind": hole})

    peek = steward.get("peer_glimpse") or {}
    ready = peek.get("swarm_ready") if isinstance(peek.get("swarm_ready"), dict) else {}
    net = peek.get("swarm_network") if isinstance(peek.get("swarm_network"), dict) else {}
    ready_ok = bool(ready.get("ok"))
    net_ok = bool(net.get("ok"))

    readiness_disagrees = bool(health_ok is True and not ready_ok)
    network_visible_but_broken = bool(swarm_ok is True and not net_ok)

    void_obs = steward.get("void_observer") or {}
    blind_notes: List[str] = []
    if json_contract_html_facades:
        blind_notes.append(
            "json_contract_html_facade: at least one machine-readable route returned HTML-shaped body; "
            "clients may parse garbage while dashboards stay green."
        )
    if gateway_or_throttle:
        blind_notes.append(
            "gateway_or_throttle_status_seen: edge or origin is shedding load; retry storms may follow "
            "if agents lack jittered backoff."
        )
    if readiness_disagrees:
        blind_notes.append(
            "readiness_health_divergence: /health probe ok but /swarm/ready reports failure — humans often "
            "monitor only liveness paths."
        )
    if network_visible_but_broken:
        blind_notes.append(
            "swarm_network_divergence: /swarm ok but /swarm/network probe failed — peer discovery graph may be stale."
        )
    if openapi_holes:
        blind_notes.append(
            "openapi_semantic_hole: 200-like JSON without `openapi` key — possible captive portal or wrong upstream."
        )
    if not blind_notes:
        blind_notes.append(
            "no_high_signal_blind_spots_in_this_pass: keep logging; rare failures need time-series not spot checks."
        )

    out: Dict[str, Any] = {
        "mode": "nomad_machine_blind_spots_pass",
        "schema": "nomad.machine_blind_spots_pass.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "public_base_url": steward.get("public_base_url", ""),
        "void_observer": void_obs,
        "status_histogram": histogram,
        "gateway_or_throttle_hits": gateway_or_throttle,
        "json_contract_html_facades": json_contract_html_facades,
        "openapi_semantic_holes": openapi_holes,
        "peer_glimpse_coherence": {
            "health_probe_ok": health_ok,
            "swarm_probe_ok": swarm_ok,
            "swarm_ready_ok": ready_ok,
            "swarm_network_ok": net_ok,
            "readiness_disagrees_with_health_probe": readiness_disagrees,
            "network_broken_while_swarm_ok": network_visible_but_broken,
        },
        "blind_spot_notes": blind_notes,
        "analysis": (
            "Second-order edge audit: HTML facades on JSON contracts, throttle/gateway codes, and "
            "readiness/network divergence from naive health — patterns humans rarely dashboard together."
        ),
    }

    if append_log:
        default_log = Path("nomad_autonomous_artifacts") / "edge_coherence.jsonl"
        raw_path = (log_path or os.getenv("NOMAD_EDGE_COHERENCE_LOG") or str(default_log)).strip()
        log_file = Path(raw_path)
        _append_edge_log_line(
            log_file,
            {
                "ts": out["generated_at"],
                "schema": out["schema"],
                "public_base_url": out["public_base_url"],
                "edge_sha256": void_obs.get("edge_coherence_sha256", ""),
                "facade_count": len(json_contract_html_facades),
                "gateway_hits": gateway_or_throttle,
                "readiness_divergence": readiness_disagrees,
            },
        )
        out["append_log_path"] = str(log_file.resolve())

    return out
