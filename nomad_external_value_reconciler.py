"""Read-only reconciliation for Nomad external-value claims.

The reconciler turns outside program state into *proposed* Nomad ledger
transitions. It never posts to GitHub and never records revenue by itself.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from typing import Any, Callable

from nomad_external_value import STAGE_INDEX, _ledger_path, _read_events


StatusFetcher = Callable[[dict[str, Any]], dict[str, Any]]


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "ok", "paid", "merged", "accepted"}


def _amount(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _latest_by_external(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for ev in events:
        eid = _text(ev.get("external_id"), 220)
        stage = str(ev.get("stage") or "").strip().lower()
        if not eid or stage not in STAGE_INDEX:
            continue
        prev = latest.get(eid)
        if not prev or STAGE_INDEX[stage] >= STAGE_INDEX.get(str(prev.get("stage")), -1):
            latest[eid] = ev
    return latest


def parse_github_external_ref(external_id: str, work_url: str = "") -> dict[str, Any]:
    """Parse the GitHub-shaped external IDs Nomad writes to its ledger."""
    eid = _text(external_id, 260)
    url = _text(work_url, 500)
    patterns = [
        (r"^gh_review:([^#]+/[^#]+)#([0-9]+):([0-9]+)$", "review"),
        (r"^gh_pr:([^#]+/[^#]+)#([0-9]+)$", "pr"),
        (r"^gh_issue:([^#]+/[^#]+)#([0-9]+)$", "issue"),
        (r"^gh_issue_comment:([^#]+/[^#]+)#([0-9]+):([0-9]+)$", "issue_comment"),
    ]
    for pattern, kind in patterns:
        match = re.match(pattern, eid)
        if match:
            out = {
                "ok": True,
                "kind": kind,
                "repo": match.group(1),
                "number": int(match.group(2)),
                "external_id": eid,
            }
            if kind == "review":
                out["review_id"] = int(match.group(3))
            if kind == "issue_comment":
                out["comment_id"] = int(match.group(3))
            return out

    url_match = re.search(r"github\.com/([^/\s]+/[^/\s]+)/(?:pull|issues)/([0-9]+)", url)
    if url_match:
        kind = "pr" if "/pull/" in url else "issue"
        review_match = re.search(r"pullrequestreview-([0-9]+)", url)
        issue_comment_match = re.search(r"issuecomment-([0-9]+)", url)
        return {
            "ok": True,
            "kind": "review" if review_match else "issue_comment" if issue_comment_match else kind,
            "repo": url_match.group(1),
            "number": int(url_match.group(2)),
            "review_id": int(review_match.group(1)) if review_match else None,
            "comment_id": int(issue_comment_match.group(1)) if issue_comment_match else None,
            "external_id": eid,
            "work_url": url,
        }

    return {"ok": False, "kind": "unknown", "external_id": eid, "work_url": url}


def fetch_github_status(ref: dict[str, Any]) -> dict[str, Any]:
    """Best-effort read-only GitHub state through local gh auth."""
    if not ref.get("ok") or not ref.get("repo") or not ref.get("number"):
        return {"ok": False, "source": "gh", "error": "unparseable_github_ref"}
    if ref.get("kind") in {"issue", "issue_comment"}:
        return _fetch_github_issue_status(ref)
    repo = str(ref["repo"])
    number = int(ref["number"])
    cmd = [
        "gh",
        "pr",
        "view",
        str(number),
        "--repo",
        repo,
        "--json",
        "number,title,url,state,mergedAt,reviewDecision,mergeStateStatus,reviews,comments",
    ]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=35,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "source": "gh", "error": f"gh_unavailable:{type(exc).__name__}"}
    if proc.returncode != 0:
        return {"ok": False, "source": "gh", "error": "gh_pr_view_failed", "stderr": _text(proc.stderr, 500)}
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "source": "gh", "error": "gh_json_decode_failed"}

    reviews = payload.get("reviews") if isinstance(payload.get("reviews"), list) else []
    comments = payload.get("comments") if isinstance(payload.get("comments"), list) else []
    review_id = str(ref.get("review_id") or "")
    own_review = {}
    if review_id:
        for review in reviews:
            if str(review.get("id") or "") == review_id or str(review.get("databaseId") or "") == review_id:
                own_review = review
                break
        if not own_review:
            review_status = _fetch_github_review_status(repo=repo, number=number, review_id=review_id)
            if review_status.get("ok"):
                own_review = review_status
    acceptance = _comment_acceptance_signals(comments, ref=ref)

    return {
        "ok": True,
        "source": "gh",
        "repo": repo,
        "number": number,
        "state": payload.get("state"),
        "merged": bool(payload.get("mergedAt")),
        "merged_at": payload.get("mergedAt"),
        "review_decision": payload.get("reviewDecision"),
        "merge_state_status": payload.get("mergeStateStatus"),
        "own_review_state": own_review.get("state"),
        "owner_acceptance_signal": acceptance["owner_acceptance_signal"],
        "soft_ack_signal": acceptance["soft_ack_signal"],
        "payment_receipt": acceptance["payment_receipt"],
        "amount_usd": acceptance["amount_usd"],
        "acceptance_evidence_count": acceptance["acceptance_evidence_count"],
        "review_count": len(reviews),
        "comment_count": len(comments),
    }


def _comment_acceptance_signals(comments: list[dict[str, Any]], *, ref: dict[str, Any]) -> dict[str, Any]:
    """Read claim-specific acceptance hints without treating social ack as payment."""
    acceptance_tokens = ("accepted", "payout", "queued", "reward", "paid", "approved claim", "accepted review")
    soft_tokens = ("+1", "lgtm", "looks good", "approved")
    trusted_assoc = {"OWNER", "MEMBER", "COLLABORATOR"}
    target_url = str(ref.get("work_url") or "")
    target_comment = str(ref.get("comment_id") or "")
    target_pr = f"/pull/{int(ref['number'])}" if ref.get("kind") in {"pr", "review"} and ref.get("number") else ""
    target_author = ""
    owner_acceptance = False
    soft_ack = False
    payment_receipt = False
    amount_usd = 0.0
    evidence_count = 0
    target_seen = False if target_comment else True

    for comment in comments:
        url = str(comment.get("url") or "")
        author = _comment_author(comment)
        body_raw = str(comment.get("body") or "")
        body = body_raw.lower()
        assoc = str(comment.get("authorAssociation") or "").upper()
        if target_comment and f"issuecomment-{target_comment}" in url:
            target_seen = True
            target_author = author
            continue
        if not target_seen:
            continue
        if comment.get("viewerDidAuthor") or (target_author and author and author == target_author):
            continue
        claim_related = (
            not target_url
            or ref.get("kind") in {"pr", "review"}
            or target_url in body_raw
            or (target_pr and target_pr in body_raw)
            or "asti1982" in body
            or "nomad" in body
        )
        if not claim_related and body.strip() not in {"+1"}:
            continue
        if assoc in trusted_assoc and any(token in body for token in acceptance_tokens):
            owner_acceptance = True
            evidence_count += 1
        if any(token in body for token in soft_tokens):
            soft_ack = True
        if assoc in trusted_assoc and (
            "tx hash" in body
            or "paid" in body
            or "payment sent" in body
            or "payout executed" in body
            or "confirms at" in body
        ):
            payment_receipt = True
        usd = re.search(r"\$([0-9][0-9,]*(?:\.[0-9]+)?)", body)
        if usd and assoc in trusted_assoc:
            amount_usd = max(amount_usd, float(usd.group(1).replace(",", "")))

    return {
        "owner_acceptance_signal": owner_acceptance,
        "soft_ack_signal": soft_ack,
        "payment_receipt": payment_receipt,
        "amount_usd": round(amount_usd, 4),
        "acceptance_evidence_count": evidence_count,
    }


def _comment_author(comment: dict[str, Any]) -> str:
    author = comment.get("author")
    if isinstance(author, dict):
        return str(author.get("login") or "")
    return str(author or "")


def _fetch_github_issue_status(ref: dict[str, Any]) -> dict[str, Any]:
    repo = str(ref["repo"])
    number = int(ref["number"])
    cmd = [
        "gh",
        "issue",
        "view",
        str(number),
        "--repo",
        repo,
        "--comments",
        "--json",
        "number,title,url,state,comments",
    ]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=35,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "source": "gh", "error": f"gh_unavailable:{type(exc).__name__}"}
    if proc.returncode != 0:
        return {"ok": False, "source": "gh", "error": "gh_issue_view_failed", "stderr": _text(proc.stderr, 500)}
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "source": "gh", "error": "gh_json_decode_failed"}
    comments = payload.get("comments") if isinstance(payload.get("comments"), list) else []
    acceptance = _comment_acceptance_signals(comments, ref=ref)
    return {
        "ok": True,
        "source": "gh",
        "repo": repo,
        "number": number,
        "state": payload.get("state"),
        "merged": False,
        "merged_at": None,
        "review_decision": "",
        "merge_state_status": "",
        "own_review_state": None,
        "owner_acceptance_signal": acceptance["owner_acceptance_signal"],
        "soft_ack_signal": acceptance["soft_ack_signal"],
        "payment_receipt": acceptance["payment_receipt"],
        "amount_usd": acceptance["amount_usd"],
        "acceptance_evidence_count": acceptance["acceptance_evidence_count"],
        "review_count": 0,
        "comment_count": len(comments),
    }


def _fetch_github_review_status(*, repo: str, number: int, review_id: str) -> dict[str, Any]:
    cmd = ["gh", "api", f"repos/{repo}/pulls/{number}/reviews/{review_id}"]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {"ok": False}
    if proc.returncode != 0:
        return {"ok": False}
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False}
    return {
        "ok": True,
        "id": payload.get("id"),
        "state": payload.get("state"),
        "submittedAt": payload.get("submitted_at"),
        "author": (payload.get("user") or {}).get("login") if isinstance(payload.get("user"), dict) else "",
    }


def propose_external_value_transition(event: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    """Return the next monotonic stage proposal, if outside state justifies it."""
    current = str(event.get("stage") or "").strip().lower()
    if current not in STAGE_INDEX:
        return {"proposed_stage": "", "reason": "unknown_current_stage", "confidence": 0.0}
    if current == "paid":
        return {"proposed_stage": "", "reason": "already_paid", "confidence": 1.0}
    if not status.get("ok"):
        return {"proposed_stage": "", "reason": str(status.get("error") or "status_unavailable"), "confidence": 0.0}

    merged = _truthy(status.get("merged"))
    owner_acceptance = _truthy(status.get("owner_acceptance_signal") or status.get("maintainer_accepted"))
    payment_receipt = _truthy(status.get("payment_receipt"))
    amount_usd = _amount(status.get("amount_usd"))
    review_state = str(status.get("own_review_state") or "").upper()
    review_exists = review_state in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}

    if current == "submitted":
        if owner_acceptance:
            return {"proposed_stage": "approved", "reason": "owner_acceptance_signal", "confidence": 0.78}
        if merged:
            return {"proposed_stage": "approved", "reason": "merged_implies_external_acceptance_monotonic_step", "confidence": 0.72}
        if review_exists:
            return {"proposed_stage": "", "reason": "review_exists_but_no_owner_acceptance", "confidence": 0.35}
        return {"proposed_stage": "", "reason": "awaiting_external_acceptance", "confidence": 0.2}

    if current == "approved":
        if merged:
            return {"proposed_stage": "merged", "reason": "github_pr_merged", "confidence": 0.90}
        if payment_receipt and amount_usd > 0:
            return {"proposed_stage": "merged", "reason": "payment_receipt_requires_monotonic_merge_step_first", "confidence": 0.70}
        return {"proposed_stage": "", "reason": "approved_not_merged_or_settled", "confidence": 0.3}

    if current == "merged":
        if payment_receipt and amount_usd > 0:
            return {
                "proposed_stage": "paid",
                "reason": "payment_receipt_with_positive_amount",
                "confidence": 0.95,
                "amount_usd": round(amount_usd, 4),
            }
        return {"proposed_stage": "", "reason": "merged_but_no_payment_receipt", "confidence": 0.45}

    return {"proposed_stage": "", "reason": "stage_waiting", "confidence": 0.0}


def build_external_value_followup(
    event: dict[str, Any],
    status: dict[str, Any],
    proposal: dict[str, Any],
) -> dict[str, Any]:
    """Compact machine next-action contract for unsettled external value."""
    current = str(event.get("stage") or "").strip().lower()
    eid = _text(event.get("external_id"), 220)
    work_url = _text(event.get("work_url"), 500)
    reason = str(proposal.get("reason") or "")
    proposed = str(proposal.get("proposed_stage") or "").strip().lower()

    if proposed:
        return {
            "action": "record_monotonic_stage_candidate",
            "priority": 0.88 if proposed == "paid" else 0.74,
            "target_stage": proposed,
            "external_id": eid,
            "work_url": work_url,
            "reason": reason,
            "required_evidence": [
                "current_ledger_stage",
                "external_status_snapshot",
                "proof_digest",
                "verifier_trace_digest",
            ],
            "machine_instruction": "apply_only_if_transition_remains_monotonic_and_evidence_snapshot_is_attached",
        }

    if current == "paid":
        return {
            "action": "close_external_value_loop",
            "priority": 0.05,
            "target_stage": "",
            "external_id": eid,
            "work_url": work_url,
            "reason": "already_paid",
            "required_evidence": [],
            "machine_instruction": "do_not_reopen_paid_external_value_without_new_external_id",
        }

    if not status.get("ok"):
        return {
            "action": "refresh_external_status",
            "priority": 0.42,
            "target_stage": "",
            "external_id": eid,
            "work_url": work_url,
            "reason": reason or str(status.get("error") or "status_unavailable"),
            "required_evidence": ["live_status_snapshot"],
            "machine_instruction": "retry_read_only_status_before_any_public_followup",
        }

    merged = _truthy(status.get("merged"))
    payment_receipt = _truthy(status.get("payment_receipt"))
    amount_usd = _amount(status.get("amount_usd"))
    owner_acceptance = _truthy(status.get("owner_acceptance_signal") or status.get("maintainer_accepted"))
    soft_ack = _truthy(status.get("soft_ack_signal"))
    review_state = str(status.get("own_review_state") or "").upper()

    if current == "found":
        return {
            "action": "produce_or_submit_proof",
            "priority": 0.68,
            "target_stage": "submitted",
            "external_id": eid,
            "work_url": work_url,
            "reason": "found_needs_public_work_url_and_proof",
            "required_evidence": ["work_url", "proof_digest", "verifier_trace_digest"],
            "machine_instruction": "create_reproducible_work_before_public_claim_or_submission",
        }

    if current == "submitted":
        if review_state in {"APPROVED", "CHANGES_REQUESTED", "COMMENTED"}:
            priority = 0.61
            action = "await_program_owner_acceptance"
            if review_state == "CHANGES_REQUESTED":
                priority = 0.57
                action = "await_author_fix_or_owner_acceptance"
            return {
                "action": action,
                "priority": priority,
                "target_stage": "approved",
                "external_id": eid,
                "work_url": work_url,
                "reason": reason or "review_exists_without_owner_acceptance",
                "required_evidence": ["owner_or_maintainer_acceptance_signal"],
                "machine_instruction": "do_not_count_value_from_self_authored_or_social_acknowledgement",
            }
        if soft_ack and not owner_acceptance:
            return {
                "action": "ignore_soft_ack_wait_for_owner_signal",
                "priority": 0.36,
                "target_stage": "approved",
                "external_id": eid,
                "work_url": work_url,
                "reason": "soft_ack_is_not_acceptance",
                "required_evidence": ["owner_or_maintainer_acceptance_signal"],
                "machine_instruction": "treat_social_ack_as_routing_hint_only_not_value",
            }
        return {
            "action": "await_external_acceptance",
            "priority": 0.52,
            "target_stage": "approved",
            "external_id": eid,
            "work_url": work_url,
            "reason": reason or "awaiting_external_acceptance",
            "required_evidence": ["owner_or_maintainer_acceptance_signal", "merged_pr", "program_acceptance_comment"],
            "machine_instruction": "watch_read_only_until_external_program_accepts_work",
        }

    if current == "approved":
        return {
            "action": "await_merge_or_settlement",
            "priority": 0.63,
            "target_stage": "merged",
            "external_id": eid,
            "work_url": work_url,
            "reason": reason or "approved_not_merged_or_settled",
            "required_evidence": ["merged_pr", "program_settlement_signal"],
            "machine_instruction": "record_merge_before_paid_even_when_payment_receipt_arrives_first",
        }

    if current == "merged":
        return {
            "action": "await_payment_receipt",
            "priority": 0.91 if merged and not (payment_receipt and amount_usd > 0) else 0.72,
            "target_stage": "paid",
            "external_id": eid,
            "work_url": work_url,
            "reason": reason or "merged_but_no_payment_receipt",
            "required_evidence": [
                "trusted_owner_member_or_collaborator_payment_receipt",
                "positive_amount_usd",
                "public_or_private_receipt_digest",
            ],
            "machine_instruction": "never_mint_paid_from_merge_alone_wait_for_positive_receipt",
        }

    return {
        "action": "hold",
        "priority": 0.2,
        "target_stage": "",
        "external_id": eid,
        "work_url": work_url,
        "reason": reason or "no_action",
        "required_evidence": [],
        "machine_instruction": "hold_until_new_external_state",
    }


def reconcile_external_value_ledger(
    *,
    ledger_path: str | None = None,
    fetch_status: StatusFetcher | None = None,
    live_github: bool = False,
    limit: int = 40,
) -> dict[str, Any]:
    path = _ledger_path(ledger_path)
    latest = list(_latest_by_external(_read_events(path)).values())[-max(1, min(int(limit or 40), 200)) :]
    fetcher = fetch_status or (fetch_github_status if live_github else None)
    observations: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    followups: list[dict[str, Any]] = []

    for event in latest:
        ref = parse_github_external_ref(str(event.get("external_id") or ""), str(event.get("work_url") or ""))
        status = fetcher(ref) if fetcher else {"ok": False, "source": "local", "error": "live_status_not_requested"}
        proposal = propose_external_value_transition(event, status)
        followup = build_external_value_followup(event, status, proposal)
        row = {
            "external_id": event.get("external_id"),
            "agent_id": event.get("agent_id"),
            "current_stage": event.get("stage"),
            "work_url": event.get("work_url"),
            "ref": ref,
            "status": status,
            "proposal": proposal,
            "followup": followup,
            "apply_allowed": False,
            "paid_guard": "paid_requires_payment_receipt_with_positive_amount_and_current_stage_merged",
        }
        observations.append(row)
        if followup.get("action") not in {"close_external_value_loop", "hold"}:
            followups.append(row)
        if proposal.get("proposed_stage"):
            proposals.append(row)

    followups.sort(key=lambda item: float((item.get("followup") or {}).get("priority") or 0.0), reverse=True)
    action_counts: dict[str, int] = {}
    for row in followups:
        action = str((row.get("followup") or {}).get("action") or "")
        if action:
            action_counts[action] = action_counts.get(action, 0) + 1
    next_action = followups[0]["followup"] if followups else {
        "action": "no_external_value_followup",
        "priority": 0.0,
        "machine_instruction": "discover_or_create_new_proof_carrying_external_value_work",
    }

    return {
        "ok": True,
        "schema": "nomad.external_value_reconcile.v1",
        "generated_at": _iso_now(),
        "ledger_path": str(path),
        "live_github": bool(live_github),
        "observed_count": len(observations),
        "proposal_count": len(proposals),
        "followup_count": len(followups),
        "followup_action_counts": action_counts,
        "top_followup": next_action,
        "proposals": proposals,
        "followups": followups[:20],
        "observations": observations,
        "machine_instruction": "read_only_reconcile_external_program_state_then_route_next_agent_action_by_followup_priority",
    }
