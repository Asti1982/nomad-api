"""Lead/product/pain blind spots: second-order signals humans rarely instrument.

Surfaces: human-social URL traps, conversion theater, pain monoculture, duplicate titles with
forked URLs, stale conversions never productized, recurring human_gate strings in work_log
(agent retry loops), products whose pain_type never appears in recent conversion evidence.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from lead_conversion import DEFAULT_CONVERSION_STORE, HUMAN_FACING_HOSTS, MACHINE_ENDPOINT_HINTS
from nomad_lead_workbench import DEFAULT_LEAD_WORKBENCH_STATE, NomadLeadWorkbench
from nomad_product_factory import DEFAULT_PRODUCT_STORE


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _norm_title(title: str) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip().lower())[:96]
    return t


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _shannon_entropy(counts: Counter[str]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log2(p)
    return round(h, 4)


def _append_log(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def _parse_iso_dt(raw: str) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def run_lead_product_blind_spot_pass(
    *,
    conversion_path: Optional[Path] = None,
    product_path: Optional[Path] = None,
    state_path: Optional[Path] = None,
    stale_days: int = 21,
    append_log: bool = False,
    log_path: str = "",
) -> Dict[str, Any]:
    wb = NomadLeadWorkbench(
        conversion_path=conversion_path,
        product_path=product_path,
        state_path=state_path,
    )
    conv_path = Path(conversion_path or DEFAULT_CONVERSION_STORE)
    prod_path = Path(product_path or DEFAULT_PRODUCT_STORE)
    st_path = Path(state_path or DEFAULT_LEAD_WORKBENCH_STATE)

    conversions = wb._load_conversions()
    products = wb._load_products()
    state = wb._load_state()
    queue = wb._build_queue(conversions=conversions, products=products, state=state)

    now = datetime.now(UTC)
    stale_cutoff = now - timedelta(days=max(1, int(stale_days or 21)))

    human_facing_hits: List[Dict[str, str]] = []
    machine_hint_no_endpoint: List[Dict[str, str]] = []
    pain_types: Counter[str] = Counter()
    title_to_urls: Dict[str, Set[str]] = {}
    draft_like = 0
    conversion_ids_with_product: Set[str] = set()

    for p in products:
        sl = p.get("source_lead") if isinstance(p.get("source_lead"), dict) else {}
        cid = str(sl.get("conversion_id") or "").strip()
        if cid:
            conversion_ids_with_product.add(cid)

    for c in conversions:
        if not isinstance(c, dict):
            continue
        lead = c.get("lead") if isinstance(c.get("lead"), dict) else {}
        url = str(lead.get("url") or "")
        host = _host(url)
        if host in HUMAN_FACING_HOSTS:
            human_facing_hits.append(
                {"conversion_id": str(c.get("conversion_id") or ""), "host": host, "title": str(lead.get("title") or "")[:120]}
            )
        st = str(c.get("status") or "")
        if "draft" in st or "approval" in st or "needs" in st:
            draft_like += 1
        route = c.get("route") if isinstance(c.get("route"), dict) else {}
        value_pack = ((c.get("free_value") or {}).get("value_pack") or {}) if isinstance(c.get("free_value"), dict) else {}
        endpoint = str(route.get("endpoint_url") or value_pack.get("route", {}).get("endpoint_url") or "").strip()
        if not endpoint and url:
            low = url.lower()
            if any(h in low for h in MACHINE_ENDPOINT_HINTS):
                machine_hint_no_endpoint.append(
                    {"conversion_id": str(c.get("conversion_id") or ""), "url": url[:200]}
                )
        pt = str(lead.get("service_type") or lead.get("pain_type") or "unknown").strip() or "unknown"
        pain_types[pt] += 1
        nt = _norm_title(str(lead.get("title") or ""))
        if nt:
            title_to_urls.setdefault(nt, set()).add(url[:240])

    title_collisions = [
        {"normalized_title": t, "distinct_urls": len(urls), "urls_sample": list(urls)[:3]}
        for t, urls in title_to_urls.items()
        if len(urls) > 1
    ]

    stale_unproductized: List[Dict[str, str]] = []
    for c in conversions:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("conversion_id") or "").strip()
        if not cid or cid in conversion_ids_with_product:
            continue
        created = _parse_iso_dt(str(c.get("created_at") or ""))
        if created and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created and created < stale_cutoff:
            lead = c.get("lead") if isinstance(c.get("lead"), dict) else {}
            stale_unproductized.append(
                {
                    "conversion_id": cid,
                    "created_at": str(c.get("created_at") or ""),
                    "title": str(lead.get("title") or "")[:120],
                }
            )

    conv_pain_keys: Set[str] = set(pain_types.keys())
    product_pain_orphans: List[Dict[str, str]] = []
    for p in products:
        if not isinstance(p, dict):
            continue
        ppt = str(p.get("pain_type") or "").strip()
        if ppt and ppt != "unknown" and ppt not in conv_pain_keys:
            product_pain_orphans.append(
                {
                    "product_id": str(p.get("product_id") or ""),
                    "pain_type": ppt,
                    "reason": "pain_type_absent_from_current_conversion_corpus",
                }
            )

    executable = sum(1 for q in queue if isinstance(q, dict) and q.get("can_execute_without_human"))
    human_gated = sum(1 for q in queue if isinstance(q, dict) and str(q.get("human_gate") or "").strip())
    qn = max(len(queue), 1)
    agent_execution_desert_ratio = round(1.0 - (executable / qn), 4)

    work_log = state.get("work_log") if isinstance(state.get("work_log"), list) else []
    gate_counts: Counter[str] = Counter()
    for row in work_log:
        if not isinstance(row, dict):
            continue
        g = str(row.get("human_gate") or "").strip()
        if g:
            gate_counts[g[:200]] += 1
    recurring_gates = [{"human_gate": g, "count": n} for g, n in gate_counts.items() if n >= 3]
    recurring_gates.sort(key=lambda x: -int(x["count"]))

    pain_entropy = _shannon_entropy(pain_types)
    pain_monoculture = bool(pain_types and pain_entropy < 0.5 and len(pain_types) <= 2)

    blind_notes: List[str] = []
    if human_facing_hits:
        blind_notes.append(
            "human_facing_host_leads: GitHub/Discord/LinkedIn-class URLs optimize for human attention; "
            "agents often pay API cost for pages that are not machine-actionable endpoints."
        )
    if machine_hint_no_endpoint:
        blind_notes.append(
            "machine_path_without_resolved_endpoint: URL hints at A2A/MCP-like paths but conversion has no "
            "endpoint_url — agents oscillate between discovery and blocked send."
        )
    if title_collisions:
        blind_notes.append(
            "duplicate_title_forked_urls: same narrative title maps to multiple URLs — humans merge mentally; "
            "agents dedupe wrong and double-spend outreach budget."
        )
    if stale_unproductized:
        blind_notes.append(
            "stale_conversion_without_product: old conversions never reached product_factory — humans celebrate "
            "pipeline velocity; agents inherit silent inventory rot."
        )
    if product_pain_orphans:
        blind_notes.append(
            "product_pain_orphaned_from_conversions: SKUs typed to pains that no longer appear in conversions — "
            "catalog drift without anyone retiring SKUs."
        )
    if agent_execution_desert_ratio >= 0.7:
        blind_notes.append(
            "agent_execution_desert: most queue items cannot execute without human — aggregate dashboards still "
            "show 'queue depth' as if it were agent throughput."
        )
    if pain_monoculture:
        blind_notes.append(
            "pain_monoculture: very low entropy across service_type — negotiation templates and fallbacks do not "
            "diversify; one upstream outage correlates all offers."
        )
    if recurring_gates:
        blind_notes.append(
            "recurring_human_gate_strings: identical approval gates repeat in work_log — agents retry the same "
            "blocked path; humans treat each as a one-off exception."
        )
    if not blind_notes:
        blind_notes.append(
            "no_high_signal_lead_blind_spots_in_this_snapshot: keep JSONL append logs to catch slow drifts."
        )

    out: Dict[str, Any] = {
        "mode": "nomad_lead_product_blind_spots_pass",
        "schema": "nomad.lead_product_blind_spots_pass.v1",
        "ok": True,
        "generated_at": _iso_now(),
        "sources": {
            "conversions_path": str(conv_path),
            "products_path": str(prod_path),
            "state_path": str(st_path),
        },
        "counts": {
            "conversions": len(conversions),
            "products": len(products),
            "queue": len(queue),
        },
        "human_facing_lead_hits": human_facing_hits[:12],
        "machine_hint_missing_endpoint": machine_hint_no_endpoint[:12],
        "duplicate_title_collisions": title_collisions[:15],
        "stale_unproductized_conversions": stale_unproductized[:15],
        "product_pain_orphans": product_pain_orphans[:15],
        "queue_agent_metrics": {
            "executable_without_human": executable,
            "human_gated_items": human_gated,
            "agent_execution_desert_ratio": agent_execution_desert_ratio,
        },
        "pain_type_entropy": pain_entropy,
        "pain_monoculture": pain_monoculture,
        "recurring_human_gates": recurring_gates[:8],
        "conversion_draft_like_status_count": draft_like,
        "blind_spot_notes": blind_notes,
        "analysis": (
            "Lead/product second-order audit: social-host traps, dedupe forks, stale unproductized rows, "
            "SKU pain drift, execution desert ratios, and repeated human_gate signatures — costs agents feel but "
            "humans rarely chart as KPIs."
        ),
    }

    if append_log:
        default_log = Path("nomad_autonomous_artifacts") / "lead_coherence.jsonl"
        raw = (log_path or "").strip()
        if not raw:
            raw = (os.getenv("NOMAD_LEAD_COHERENCE_LOG") or str(default_log)).strip()
        lp = Path(raw)
        _append_log(
            lp,
            {
                "ts": out["generated_at"],
                "schema": out["schema"],
                "conversions": len(conversions),
                "products": len(products),
                "human_facing_n": len(human_facing_hits),
                "title_collision_groups": len(title_collisions),
                "stale_unproductized_n": len(stale_unproductized),
                "pain_entropy": pain_entropy,
                "execution_desert": agent_execution_desert_ratio,
            },
        )
        out["append_log_path"] = str(lp.resolve())

    return out
