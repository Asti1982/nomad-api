from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import urlencode

import requests

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency in slim deploys
    load_dotenv = None


DEFAULT_SUPERTEAM_BASE = "https://superteam.fun"
AGENT_ACCESS = {"AGENT_ALLOWED", "AGENT_ONLY"}

FetchJson = Callable[[str, str | None, float], Any]


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()


def _normalize_base(value: str | None) -> str:
    raw = (value or DEFAULT_SUPERTEAM_BASE).strip()
    if not raw:
        raw = DEFAULT_SUPERTEAM_BASE
    if "://" not in raw:
        raw = f"https://{raw}"
    return raw.rstrip("/")


def _request_json(url: str, api_key: str | None, timeout: float) -> Any:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "listings", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("Submission") or value.get("submissions") or value.get("submission")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def _merge_listing_detail(base: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in detail.items():
        if value in (None, "") and merged.get(key) not in (None, ""):
            continue
        merged[key] = value
    return merged


def _proof_digest(listing: dict[str, Any], gate_state: str) -> str:
    stable = {
        "id": listing.get("id"),
        "slug": listing.get("slug"),
        "deadline": listing.get("deadline"),
        "gate_state": gate_state,
        "submissions": _count(listing.get("_count")),
    }
    encoded = repr(sorted(stable.items())).encode("utf-8")
    return f"superteam:{hashlib.sha256(encoded).hexdigest()[:20]}"


def classify_superteam_listing(
    listing: dict[str, Any],
    *,
    api_key_present: bool,
    claim_code_present: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    deadline = _parse_time(listing.get("deadline"))
    deadline_live = deadline is None or deadline > now
    access = str(listing.get("agentAccess") or "").strip().upper()
    status = str(listing.get("status") or "").strip().upper()
    listing_type = str(listing.get("type") or "").strip().lower()
    compensation_type = str(listing.get("compensationType") or "").strip().lower()
    winners_announced = bool(listing.get("isWinnersAnnounced") or listing.get("winnersAnnouncedAt"))
    submission_count = _count(listing.get("_count"))
    reward_amount = _num(listing.get("rewardAmount"))
    token = str(listing.get("token") or "").strip()

    if not api_key_present:
        gate_state = "api_key_missing"
        next_action = "add_superteam_agent_api_key_before_live_scout"
    elif access not in AGENT_ACCESS:
        gate_state = "not_agent_eligible"
        next_action = "skip_human_only_listing"
    elif status != "OPEN":
        gate_state = "not_open"
        next_action = "watch_only_until_open"
    elif not deadline_live:
        gate_state = "deadline_passed"
        next_action = "discard_for_new_value_cycle"
    elif winners_announced:
        gate_state = "winners_announced"
        next_action = "discard_for_new_value_cycle"
    elif not claim_code_present:
        gate_state = "claim_code_missing"
        next_action = "claim_code_required_before_any_submission"
    elif listing_type == "project":
        gate_state = "project_requires_human_telegram"
        next_action = "collect_human_telegram_before_project_submission"
    elif submission_count >= 80:
        gate_state = "crowded_competition_watch_only"
        next_action = "only_submit_if_artifact_is_exceptionally_strong_and_unique"
    else:
        gate_state = "candidate_artifact_gate_unverified"
        next_action = "fetch_details_prepare_original_artifact_before_submission"

    if gate_state == "candidate_artifact_gate_unverified":
        allowed_actions = ["read_details", "prepare_original_artifact", "eligibility_question_probe"]
        blocked_actions = ["submit_without_artifact", "reuse_other_submissions", "book_revenue"]
    elif gate_state == "crowded_competition_watch_only":
        allowed_actions = ["read_details", "watch_deadline", "prepare_only_if_unique_artifact_exists"]
        blocked_actions = ["low_originality_submission", "book_revenue"]
    else:
        allowed_actions = ["read_only_watch"]
        blocked_actions = ["submit", "comment", "book_revenue"]

    slug = str(listing.get("slug") or "").strip()
    listing_url = f"https://superteam.fun/earn/listing/{slug}" if slug else ""
    sponsor = listing.get("sponsor") if isinstance(listing.get("sponsor"), dict) else {}
    proof_digest = _proof_digest(listing, gate_state)

    return {
        "listing_id": str(listing.get("id") or "").strip(),
        "title": _text(listing.get("title"), 220),
        "slug": slug,
        "listing_url": listing_url,
        "type": listing_type,
        "agent_access": access,
        "status": status,
        "deadline": deadline.isoformat() if deadline else "",
        "deadline_live": deadline_live,
        "winners_announced": winners_announced,
        "submission_count": submission_count,
        "comment_count": _count((listing.get("_count") or {}).get("Comments") if isinstance(listing.get("_count"), dict) else 0),
        "reward_amount": reward_amount,
        "token": token,
        "compensation_type": compensation_type,
        "sponsor": {
            "name": _text(sponsor.get("name"), 120),
            "slug": _text(sponsor.get("slug"), 120),
            "verified": bool(sponsor.get("isVerified")),
        },
        "description_excerpt": _text(listing.get("description") or listing.get("requirements") or listing.get("shortSummary"), 600),
        "gate_state": gate_state,
        "executable_work_allowed": False,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "next_action": next_action,
        "unlock_requirements": [
            "agent_access_allows_submission",
            "deadline_future_and_winner_not_announced",
            "original_artifact_link_ready",
            "eligibility_answers_ready_if_required",
            "human_claim_code_and_payout_route_ready",
        ],
        "external_value_event_hint": {
            "external_id": f"superteam:{slug or listing.get('id')}",
            "stage": "found",
            "amount_usd": 0,
            "proof_digest": proof_digest,
            "verifier_trace_digest": gate_state,
        },
    }


def build_superteam_scout(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    claim_code: str | None = None,
    listing_type: str | None = None,
    take: int = 20,
    include_details: bool = False,
    timeout: float = 20.0,
    fetch_json: FetchJson | None = None,
    listings: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    _load_env()
    root = _normalize_base(base_url or os.getenv("SUPERTEAM_EARN_BASE_URL"))
    resolved_api_key = api_key if api_key is not None else os.getenv("SUPERTEAM_EARN_API_KEY")
    resolved_claim_code = claim_code if claim_code is not None else os.getenv("SUPERTEAM_EARN_CLAIM_CODE")
    api_key_present = bool((resolved_api_key or "").strip())
    claim_code_present = bool((resolved_claim_code or "").strip())
    fetch = fetch_json or _request_json
    errors: list[str] = []

    raw_listings: list[dict[str, Any]] = []
    if listings is not None:
        raw_listings = list(listings)
    elif api_key_present:
        params = {"take": max(1, int(take or 20))}
        if listing_type:
            params["type"] = str(listing_type)
        url = f"{root}/api/agents/listings/live?{urlencode(params)}"
        try:
            raw_listings = _items(fetch(url, resolved_api_key, timeout))
        except Exception as exc:  # pragma: no cover - live guard
            errors.append(f"listing_fetch_failed:{type(exc).__name__}")
    else:
        errors.append("superteam_agent_api_key_missing")

    clipped = raw_listings[: max(0, int(take or 0))]
    if include_details and listings is None and api_key_present:
        detailed: list[dict[str, Any]] = []
        for item in clipped:
            slug = str(item.get("slug") or "").strip()
            if not slug:
                detailed.append(item)
                continue
            try:
                detail = fetch(f"{root}/api/agents/listings/details/{slug}", resolved_api_key, timeout)
            except Exception:
                detailed.append(item)
                continue
            if isinstance(detail, dict):
                detailed.append(_merge_listing_detail(item, detail))
            else:
                detailed.append(item)
        clipped = detailed

    classified = [
        classify_superteam_listing(
            item,
            api_key_present=api_key_present,
            claim_code_present=claim_code_present,
            now=now,
        )
        for item in clipped
    ]
    active_candidates = [item for item in classified if item["gate_state"] == "candidate_artifact_gate_unverified"]
    future_agent_eligible = [
        item
        for item in classified
        if item["agent_access"] in AGENT_ACCESS and item["deadline_live"] and not item["winners_announced"]
    ]
    expired = [item for item in classified if not item["deadline_live"] or item["winners_announced"]]
    crowded = [item for item in classified if item["gate_state"] == "crowded_competition_watch_only"]
    total_reward = sum(float(item.get("reward_amount") or 0.0) for item in future_agent_eligible)

    if active_candidates:
        machine_instruction = "prepare_original_artifact_for_top_candidate_no_submission_until_link_and_answers_ready"
    elif expired:
        machine_instruction = "no_live_superteam_candidate_keep_read_only_watch"
    else:
        machine_instruction = "keep_superteam_channel_watch_only"

    return {
        "schema": "nomad.superteam_scout.v1",
        "ok": not errors,
        "generated_at": datetime.now(UTC).isoformat(),
        "api_base_public": root,
        "api_key_present": api_key_present,
        "claim_code_present": claim_code_present,
        "summary": {
            "listing_count": len(classified),
            "future_agent_eligible_count": len(future_agent_eligible),
            "active_candidate_count": len(active_candidates),
            "expired_or_announced_count": len(expired),
            "crowded_count": len(crowded),
            "visible_future_reward_total": round(total_reward, 4),
            "top_candidate": active_candidates[0] if active_candidates else None,
            "top_watch": expired[0] if expired else (classified[0] if classified else None),
        },
        "listings": classified,
        "errors": errors,
        "machine_instruction": machine_instruction,
    }


__all__ = [
    "AGENT_ACCESS",
    "DEFAULT_SUPERTEAM_BASE",
    "_normalize_base",
    "build_superteam_scout",
    "classify_superteam_listing",
]
