"""External bounty / OSS value cycle — machine ledger only (no GitHub posts).

Pipeline (human + program outside Nomad validates payment):
  bounty surface -> finding -> patch -> PR -> claim -> external approval -> Nomad proof receipt

Nomad counts **revenue** only at stage ``paid``. ``approved`` and ``merged`` increase
selection-weight hints for routing (bounded).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nomad_state_paths import state_file

LEDGER_ENV = "NOMAD_EXTERNAL_VALUE_LEDGER_PATH"
DEFAULT_LEDGER = Path("nomad_external_value_ledger.jsonl")

STAGES_ORDER = ("found", "submitted", "approved", "merged", "paid")
STAGE_INDEX = {s: i for i, s in enumerate(STAGES_ORDER)}
RECEIPT_ONLY_REVENUE_RULE = "paid_stage_requires_positive_amount_and_public_settlement_ref"


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _ledger_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    return state_file(DEFAULT_LEDGER, env_name=LEDGER_ENV)


def _digest(payload: dict[str, Any], length: int = 32) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _settlement_ref_from_body(body: dict[str, Any]) -> str:
    return _text(
        body.get("settlement_ref")
        or body.get("receipt_ref")
        or body.get("payment_receipt")
        or body.get("tx_hash")
        or body.get("payout_tx")
        or "",
        240,
    )


def _read_events(ledger_path: Path, *, limit_lines: int = 8000) -> list[dict[str, Any]]:
    if not ledger_path.exists():
        return []
    lines = ledger_path.read_text(encoding="utf-8", errors="replace").splitlines()
    take = min(len(lines), max(1, int(limit_lines)))
    tail = lines[-take:]
    out: list[dict[str, Any]] = []
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("schema") == "nomad.external_value_event.v1":
            out.append(row)
    return out


def current_stage_for_external(events: list[dict[str, Any]], external_id: str) -> str:
    eid = _text(external_id, 200)
    last = ""
    for ev in events:
        if _text(ev.get("external_id"), 200) != eid:
            continue
        st = str(ev.get("stage") or "").strip().lower()
        if st in STAGE_INDEX and (not last or STAGE_INDEX[st] >= STAGE_INDEX.get(last, -1)):
            last = st
    return last


def allowed_transition(*, from_stage: str, to_stage: str) -> tuple[bool, str]:
    a = str(from_stage or "").strip().lower()
    b = str(to_stage or "").strip().lower()
    if b not in STAGE_INDEX:
        return False, "unknown_stage"
    if not a:
        return b == "found", "first_stage_must_be_found"
    if a not in STAGE_INDEX:
        return False, "unknown_prior_stage"
    if STAGE_INDEX[b] < STAGE_INDEX[a]:
        return False, "non_monotonic_stage"
    if STAGE_INDEX[b] == STAGE_INDEX[a]:
        return False, "duplicate_stage"
    if STAGE_INDEX[b] != STAGE_INDEX[a] + 1:
        return False, "stage_skip_not_allowed"
    return True, "ok"


def selection_weight_multiplier_for_stage(stage: str) -> float:
    s = str(stage or "").strip().lower()
    if s == "approved":
        return 1.06
    if s == "merged":
        return 1.12
    if s == "paid":
        return 1.22
    return 1.0


def revenue_recognized_usd(*, stage: str, amount_usd: float) -> float:
    if str(stage or "").strip().lower() != "paid":
        return 0.0
    return max(0.0, float(amount_usd or 0.0))


def agent_selection_bonus(agent_id: str, *, ledger_path: Path | str | None = None) -> dict[str, Any]:
    """Bounded bonus from latest external-value stage per agent (read-only)."""
    aid = _text(agent_id, 120)
    events = _read_events(_ledger_path(ledger_path))
    best_stage = ""
    best_idx = -1
    for ev in events:
        if _text(ev.get("agent_id"), 120) != aid:
            continue
        st = str(ev.get("stage") or "").strip().lower()
        if st not in STAGE_INDEX:
            continue
        if STAGE_INDEX[st] >= best_idx:
            best_idx = STAGE_INDEX[st]
            best_stage = st
    mult = selection_weight_multiplier_for_stage(best_stage)
    return {
        "schema": "nomad.external_value_selection_bonus.v1",
        "agent_id": aid,
        "best_stage": best_stage or "none",
        "selection_weight_multiplier": round(mult, 4),
    }


def mint_proof_receipt_digest(payload: dict[str, Any]) -> str:
    core = {
        "agent_id": _text(payload.get("agent_id"), 120),
        "external_id": _text(payload.get("external_id"), 200),
        "stage": _text(payload.get("stage"), 40),
        "work_url": _text(payload.get("work_url"), 400),
        "proof_digest": _text(payload.get("proof_digest"), 200),
        "verifier_trace_digest": _text(payload.get("verifier_trace_digest"), 200),
        "settlement_ref": _settlement_ref_from_body(payload),
    }
    return _digest(core, 48)


def append_external_value_event(
    payload: dict[str, Any],
    *,
    ledger_path: Path | str | None = None,
) -> dict[str, Any]:
    body = payload if isinstance(payload, dict) else {}
    agent_id = _text(body.get("agent_id"), 120)
    external_id = _text(body.get("external_id"), 200)
    stage = str(body.get("stage") or "").strip().lower()
    work_url = _text(body.get("work_url"), 400)
    proof_digest = _text(body.get("proof_digest"), 200)
    verifier_trace_digest = _text(body.get("verifier_trace_digest"), 200)
    settlement_ref = _settlement_ref_from_body(body)
    amount_usd = 0.0
    try:
        amount_usd = float(body.get("amount_usd") or body.get("amount") or 0.0)
    except (TypeError, ValueError):
        amount_usd = 0.0
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}

    if not agent_id:
        return {"ok": False, "schema": "nomad.external_value_event.v1", "error": "missing_agent_id"}
    if not external_id:
        return {"ok": False, "schema": "nomad.external_value_event.v1", "error": "missing_external_id"}
    if stage not in STAGE_INDEX:
        return {"ok": False, "schema": "nomad.external_value_event.v1", "error": "invalid_stage", "allowed": list(STAGES_ORDER)}
    if stage in {"submitted", "approved", "merged", "paid"} and (not work_url or not proof_digest):
        return {"ok": False, "schema": "nomad.external_value_event.v1", "error": "work_url_and_proof_digest_required_after_found"}
    if stage == "paid" and (amount_usd <= 0.0 or not settlement_ref):
        return {
            "ok": False,
            "schema": "nomad.external_value_event.v1",
            "error": "paid_receipt_incomplete",
            "reason": RECEIPT_ONLY_REVENUE_RULE,
            "required": ["stage=paid", "amount_usd>0", "settlement_ref"],
            "machine_instruction": "record merged or approved as non_revenue_signal until a positive public receipt exists",
        }

    path = _ledger_path(ledger_path)
    prior = current_stage_for_external(_read_events(path), external_id)
    ok, reason = allowed_transition(from_stage=prior, to_stage=stage)
    if not ok:
        return {
            "ok": False,
            "schema": "nomad.external_value_event.v1",
            "error": "transition_rejected",
            "reason": reason,
            "prior_stage": prior or "(none)",
            "requested_stage": stage,
        }

    row_core = {
        "agent_id": agent_id,
        "external_id": external_id,
        "stage": stage,
        "work_url": work_url,
        "proof_digest": proof_digest,
        "verifier_trace_digest": verifier_trace_digest,
        "settlement_ref": settlement_ref,
        "amount_usd": round(amount_usd, 4) if stage == "paid" else 0.0,
        "meta": meta,
    }
    receipt_digest = mint_proof_receipt_digest(row_core)
    row = {
        "ok": True,
        "schema": "nomad.external_value_event.v1",
        "generated_at": _iso_now(),
        "event_id": f"ev-{_digest({**row_core, 't': _iso_now()}, 16)}",
        **row_core,
        "revenue_recognized_usd": round(revenue_recognized_usd(stage=stage, amount_usd=amount_usd), 4),
        "revenue_invariant": RECEIPT_ONLY_REVENUE_RULE,
        "nomad_proof_receipt_digest": receipt_digest,
        "selection_weight_multiplier_after": round(selection_weight_multiplier_for_stage(stage), 4),
        "machine_instruction": "external_program_validates_merge_and_payment_nomad_only_records_machine_receipt",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")
    row["ledger_path"] = str(path)
    return row


def build_external_value_surface(*, base_url: str) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    return {
        "ok": True,
        "schema": "nomad.external_value_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "state_machine": {
            "name": "pending_external_value",
            "stages": list(STAGES_ORDER),
            "revenue_rule": RECEIPT_ONLY_REVENUE_RULE,
            "selection_rule": "approved_merged_paid_increase_bounded_selection_weight_multiplier",
        },
        "post_url": f"{root}/swarm/external-value",
        "well_known_url": f"{root}/.well-known/nomad-external-value.json",
        "pipeline": [
            "bounty_surface",
            "finding",
            "patch",
            "pr",
            "bounty_claim",
            "external_approval",
            "nomad_proof_receipt",
        ],
        "role_split": {
            "human_operator": "external_work_prs_reviews_claims_merge_payment_followup",
            "cursor_agent": "scout_diff_miner_reproducer_nomad_integrator_watchdog_no_public_claims_without_go",
        },
        "next": [
            {"rel": "post_transition", "method": "POST", "href": f"{root}/swarm/external-value"},
            {"rel": "settlement_signal", "method": "GET", "href": f"{root}/.well-known/nomad-settlement.json"},
            {"rel": "bounty_hunter", "method": "GET", "href": f"{root}/.well-known/nomad-bounty-hunter.json"},
        ],
        "signed_proof_contract": {
            "local_cli": "python nomad_cli.py external-value sign-proof --agent-id <agent> --external-id <id> --stage <stage> --work-url <url> --proof-digest <sha256:...> --verifier-trace-digest <sha256:...>",
            "signature_alg": "Ed25519",
            "private_key_policy": "local_only_never_render_never_public_json",
            "verification_rule": "verify_signature_over_canonical_json_payload_before_upgrading_external_value_stage",
        },
        "receipt_only_invariant": build_receipt_only_revenue_invariant(base_url=root, summary=summarize_external_value_ledger()),
    }


def build_receipt_only_revenue_invariant(
    *,
    base_url: str = "",
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    external_summary = summary if isinstance(summary, dict) else summarize_external_value_ledger()
    return {
        "ok": True,
        "schema": "nomad.receipt_only_revenue_invariant.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "invariant_id": "receipt_only_revenue_recognition",
        "rule": RECEIPT_ONLY_REVENUE_RULE,
        "state_algebra": {
            "non_cash_signal_states": ["found", "submitted", "approved", "merged"],
            "cash_state": "paid",
            "paid_guard": ["amount_usd > 0", "settlement_ref present", "proof_digest present", "work_url present"],
            "forbidden_collapse": "do_not_map_social_acceptance_or_merge_to_revenue",
        },
        "accepted_receipt_refs": [
            "platform_payment_confirmation_url",
            "public_payout_receipt_id",
            "public_tx_hash_or_chain_receipt",
            "trusted_balance_delta_digest",
        ],
        "blocked_revenue_claims": [
            "maintainer_thanks_without_payment",
            "merged_pull_request_without_payment_ref",
            "approved_security_report_without_bounty_receipt",
            "selfplay_or_internal_microtask_without_external_buyer_receipt",
        ],
        "scientific_basis": [
            {
                "id": "proof_carrying_code_necula_1997",
                "source": "https://dblp.org/db/conf/popl/popl97",
                "use": "untrusted work carries machine-checkable evidence before a state upgrade is accepted",
            },
            {
                "id": "little_law_queue_control_little_1961",
                "source": "https://pubsonline.informs.org/doi/10.1287/opre.9.3.383",
                "use": "unpaid WIP is queue mass, not throughput; revenue is recognized only at departure into paid state",
            },
            {
                "id": "contract_net_smith_1980",
                "source": "https://cse-robotics.engr.tamu.edu/dshell/cs631/papers/smith80contract.pdf",
                "use": "separates task allocation and execution from award/settlement evidence",
            },
            {
                "id": "information_theory_shannon_1948",
                "source": "https://people.math.harvard.edu/~ctm/home/text/others/shannon/entropy/entropy.pdf",
                "use": "treats receipts as low-ambiguity signals and social text as noisy side information",
            },
        ],
        "machine_transition": {
            "on_found_or_submitted_or_approved_or_merged": "selection_signal_only",
            "on_paid_with_guard_satisfied": "recognize_revenue_and_emit_settlement_credit",
            "on_paid_guard_failure": "reject_paid_stage_preserve_prior_state",
        },
        "current_summary": {
            "distinct_externals": external_summary.get("distinct_externals", 0),
            "recognized_revenue_usd_total": external_summary.get("revenue_recognized_usd_total", 0.0),
            "event_tail_count": external_summary.get("event_tail_count", 0),
        },
        "contracts": {
            "external_value": f"{root}/.well-known/nomad-external-value.json" if root else "/.well-known/nomad-external-value.json",
            "record": f"{root}/swarm/external-value" if root else "/swarm/external-value",
            "work_receipts": f"{root}/.well-known/nomad-work-receipts.json" if root else "/.well-known/nomad-work-receipts.json",
        },
        "machine_instruction": "ignore human_status_language_for_revenue; only positive_public_receipt_can_collapse_state_to_paid",
    }


def summarize_external_value_ledger(
    *,
    ledger_path: Path | str | None = None,
    limit: int = 200,
    latest_limit: int = 40,
) -> dict[str, Any]:
    path = _ledger_path(ledger_path)
    events = _read_events(path)[-max(1, min(int(limit or 200), 5000)) :]
    by_external: dict[str, dict[str, Any]] = {}
    revenue_total = 0.0
    for ev in events:
        eid = str(ev.get("external_id") or "")
        if not eid:
            continue
        st = str(ev.get("stage") or "").strip().lower()
        prev = by_external.get(eid, {})
        if not prev or STAGE_INDEX.get(st, -1) >= STAGE_INDEX.get(str(prev.get("stage")), -1):
            by_external[eid] = {
                "external_id": eid,
                "agent_id": ev.get("agent_id"),
                "stage": st,
                "work_url": ev.get("work_url"),
                "settlement_ref": ev.get("settlement_ref", ""),
                "last_event_id": ev.get("event_id"),
                "last_generated_at": ev.get("generated_at"),
                "nomad_proof_receipt_digest": ev.get("nomad_proof_receipt_digest"),
                "revenue_recognized_usd": float(ev.get("revenue_recognized_usd") or 0.0),
            }
        revenue_total += float(ev.get("revenue_recognized_usd") or 0.0)
    latest_rows = list(by_external.values())
    row_limit = int(latest_limit if latest_limit is not None else 40)
    visible_latest = latest_rows if row_limit <= 0 else latest_rows[-max(1, row_limit) :]
    return {
        "ok": True,
        "schema": "nomad.external_value_summary.v1",
        "ledger_path": str(path),
        "event_tail_count": len(events),
        "distinct_externals": len(by_external),
        "latest_by_external_visible_count": len(visible_latest),
        "latest_by_external_limit": row_limit,
        "revenue_recognized_usd_total": round(revenue_total, 4),
        "latest_by_external": visible_latest,
    }


def external_id_for_github_pr(owner_repo: str, number: int) -> str:
    repo = _text(owner_repo, 120).replace(" ", "")
    return f"gh_pr:{repo}#{int(number)}"


def external_id_for_github_issue(owner_repo: str, number: int) -> str:
    repo = _text(owner_repo, 120).replace(" ", "")
    return f"gh_issue:{repo}#{int(number)}"
