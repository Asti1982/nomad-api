"""Network steward: one pass that helps Nomad and peer agents — edge void + lattice + optional swarm feed.

Runs a single swarm-helper GET lattice, derives void fingerprints from it (no duplicate probes),
optionally GETs readiness/network for other agents' discovery, can POST /swarm/accumulate, and
optionally POST /swarm/join and /swarm/develop (same payloads as swarm-helper when not dry_run).
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

import requests

from nomad_swarm_helper_agent import _get, _post_json, _base_url as _nomad_root, run_swarm_helper_pass
from nomad_void_observer import void_metrics_from_probes


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _agent_id(explicit: str = "") -> str:
    return (
        (explicit or os.getenv("NOMAD_NETWORK_STEWARD_AGENT_ID") or os.getenv("NOMAD_SWARM_HELPER_AGENT_ID") or "")
        .strip()
        or "nomad.network_steward.v1"
    )


def run_network_steward_cycle(
    *,
    base_url: str = "",
    timeout: float = 25.0,
    agent_id: str = "",
    dry_run: bool = True,
    feed_swarm: bool = False,
    peer_glimpse: bool = True,
    post_join: bool = False,
    post_develop: bool = False,
) -> Dict[str, Any]:
    """
    One steward cycle against public Nomad.

    - Always: swarm-helper GET lattice + void metrics (helps operators and other agents see edge health).
    - peer_glimpse: GET /swarm/ready and /swarm/network (read-only; warms caches, surfaces peers).
    - feed_swarm + not dry_run: POST /swarm/accumulate (refreshes prospect queue from Nomad's own contacts).
    - post_join + not dry_run: POST /swarm/join (attach steward identity to the swarm).
    - post_develop + not dry_run: POST /swarm/develop (bounded develop exchange probe).
    """
    aid = _agent_id(agent_id)
    swarm = run_swarm_helper_pass(
        base_url=base_url,
        dry_run=True,
        post_join=False,
        post_develop=False,
        timeout=timeout,
        agent_id=aid,
    )
    probes = swarm.get("probes") or []
    void_metrics = void_metrics_from_probes(
        probes if isinstance(probes, list) else [],
        probe_ok_count=int(swarm.get("probe_ok_count") or 0),
    )
    root = str(swarm.get("public_base_url") or _nomad_root(base_url)).rstrip("/")
    session = requests.Session()

    readiness: Optional[Dict[str, Any]] = None
    network_peers: Optional[Dict[str, Any]] = None
    if peer_glimpse:
        readiness = _get(session, f"{root}/swarm/ready", timeout=timeout)
        network_peers = _get(
            session,
            f"{root}/swarm/network?service_type=compute_auth&role=peer_solver&limit=8",
            timeout=timeout,
        )

    accumulate_result: Optional[Dict[str, Any]] = None
    if feed_swarm and not dry_run:
        idem = f"network-steward-acc-{uuid.uuid4().hex[:22]}"
        accumulate_result = _post_json(
            session,
            f"{root}/swarm/accumulate",
            {
                "from_contacts": True,
                "from_campaigns": True,
                "limit": 50,
                "pain_type": "compute_auth",
                "source_agent_id": aid,
                "note": "network_steward: bounded accumulate to refresh peer activation queue",
            },
            timeout=timeout,
            idempotency_key=idem,
        )

    join_idem = f"network-steward-join-{uuid.uuid4().hex[:24]}"
    join_result: Optional[Dict[str, Any]] = None
    if not dry_run and post_join:
        join_result = _post_json(
            session,
            f"{root}/swarm/join",
            {
                "agent_id": aid,
                "node_name": aid,
                "capabilities": [
                    "runtime_patterns",
                    "debugging",
                    "agent_protocols",
                    "network_steward",
                    "edge_coherence",
                ],
                "request": (
                    "Network steward: void lattice + peer glimpse + optional accumulate/join/develop "
                    "for Nomad and peer agents."
                ),
                "reciprocity": (
                    "GET-only by default; mutating POSTs only with explicit dry_run=false; "
                    "Idempotency-Key on all writes."
                ),
                "idempotency_key": join_idem,
            },
            timeout=timeout,
            idempotency_key=join_idem,
        )

    develop_result: Optional[Dict[str, Any]] = None
    if not dry_run and post_develop:
        dev_idem = f"network-steward-dev-{uuid.uuid4().hex[:20]}"
        develop_result = _post_json(
            session,
            f"{root}/swarm/develop",
            {
                "agent_id": aid,
                "problem": (
                    "Nomad network steward: confirm develop exchange after steward lattice; "
                    "no secrets in payload."
                ),
                "pain_type": "self_improvement",
                "capabilities": ["debugging", "agent_protocols"],
                "evidence": ["SOURCE=nomad_network_steward_agent", f"PUBLIC_BASE={root}"],
                "idempotency_key": dev_idem,
            },
            timeout=timeout,
            idempotency_key=dev_idem,
        )

    return {
        "mode": "nomad_network_steward_cycle",
        "schema": "nomad.network_steward_cycle.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "agent_id": aid,
        "public_base_url": root,
        "dry_run": bool(dry_run),
        "feed_swarm_requested": bool(feed_swarm),
        "swarm_helper": {
            "schema": swarm.get("schema"),
            "probe_ok_count": swarm.get("probe_ok_count"),
            "probes": probes,
        },
        "void_observer": void_metrics,
        "peer_glimpse": (
            {
                "swarm_ready": readiness,
                "swarm_network": network_peers,
            }
            if peer_glimpse
            else {}
        ),
        "swarm_accumulate_post": accumulate_result,
        "swarm_join_post": join_result,
        "swarm_develop_post": develop_result,
        "post_join_requested": bool(post_join),
        "post_develop_requested": bool(post_develop),
        "analysis": (
            "Network steward: lattice + void fingerprint for edge truth; optional peer_glimpse for "
            "solver-visible leads; optional accumulate refreshes the swarm graph for Nomad and remote A2A peers. "
            "Optional join/develop mirror swarm-helper. Pair with `codex-peer-agent --loop` for narrative growth."
        ),
    }


def run_network_steward_loop(
    *,
    base_url: str = "",
    timeout: float = 25.0,
    agent_id: str = "",
    dry_run: bool = True,
    feed_swarm: bool = False,
    peer_glimpse: bool = True,
    post_join: bool = False,
    post_develop: bool = False,
    interval_seconds: float = 120.0,
    cycles: int = 1,
) -> Dict[str, Any]:
    """
    cycles: number of steward passes; 0 means run until KeyboardInterrupt.
    """
    runs: List[Dict[str, Any]] = []
    n = 0
    try:
        while True:
            n += 1
            runs.append(
                run_network_steward_cycle(
                    base_url=base_url,
                    timeout=timeout,
                    agent_id=agent_id,
                    dry_run=dry_run,
                    feed_swarm=feed_swarm,
                    peer_glimpse=peer_glimpse,
                    post_join=post_join,
                    post_develop=post_develop,
                )
            )
            if cycles > 0 and n >= cycles:
                break
            time.sleep(max(5.0, float(interval_seconds)))
    except KeyboardInterrupt:
        pass

    return {
        "mode": "nomad_network_steward_loop",
        "schema": "nomad.network_steward_loop.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "cycles_completed": len(runs),
        "interval_seconds": float(interval_seconds),
        "runs": runs,
        "analysis": (
            f"Steward loop finished {len(runs)} cycle(s). "
            "Swarm 'network power' grows with reciprocal joins and accumulate/A2A edges, not a fixed headcount."
        ),
    }
