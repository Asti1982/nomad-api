"""Machine-native acquisition policy engine for Nomad.

The engine exposes a compact decision surface for agents and workers. It is
grounded in bandit allocation, causal holdouts, information gain, replicator
dynamics, diffusion pressure, and mechanism-design guardrails. Humans can audit
the constraints; machines should consume the vector policy directly.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from nomad_telegram_acquisition import summarize_telegram_acquisition_ledgers


SCHEMA = "nomad.acquisition_engine.v1"
DEFAULT_TARGETS = {
    "cursor_referrals": 1,
    "transition_workers": 1,
    "paid_orders": 1,
    "oracle_downloads": 1,
}


SCIENCE_REFERENCES = [
    {
        "id": "ucb_bandit",
        "mechanism": "finite_time_upper_confidence_bound",
        "source": "Auer, Cesa-Bianchi, Fischer, Finite-time Analysis of the Multiarmed Bandit Problem, Machine Learning, 2002",
        "url": "https://www2.compute.dtu.dk/pubdb/pubs/2088-full.html",
        "used_for": "exploration bonus for under-sampled acquisition arms",
    },
    {
        "id": "posterior_sampling",
        "mechanism": "thompson_sampling_probability_matching",
        "source": "Thompson sampling / posterior probability matching",
        "url": "https://www.cs.ubc.ca/~hutter/nips2011workshop/papers_and_posters/Agrawal-Goyal-TS-report.pdf",
        "used_for": "machine action ranking under delayed conversion feedback",
    },
    {
        "id": "potential_outcomes",
        "mechanism": "causal_holdout_and_counterfactual_outcomes",
        "source": "Rubin, Causal Inference Using Potential Outcomes: Design, Modeling, Decisions, JASA, 2005",
        "url": "https://www.tandfonline.com/doi/abs/10.1198/016214504000001880",
        "used_for": "separating causal conversion from raw attention",
    },
    {
        "id": "shannon_entropy",
        "mechanism": "expected_information_gain",
        "source": "Shannon, A Mathematical Theory of Communication, 1948",
        "url": "https://people.math.harvard.edu/~ctm/home/text/others/shannon/entropy/entropy.pdf",
        "used_for": "ranking actions by uncertainty reduction per contact",
    },
    {
        "id": "replicator_dynamics",
        "mechanism": "fitness_weighted_channel_replication",
        "source": "Nowak, Five Rules for the Evolution of Cooperation, Science, 2006",
        "url": "https://pubmed.ncbi.nlm.nih.gov/17158317/",
        "used_for": "letting high-fitness channel variants reproduce without human taste",
    },
    {
        "id": "mechanism_design",
        "mechanism": "incentive_compatibility_and_verified_payment_gates",
        "source": "Myerson, Optimal Auction Design, Mathematics of Operations Research, 1981",
        "url": "https://pubsonline.informs.org/doi/10.1287/moor.6.1.58",
        "used_for": "preventing fake revenue and aligning worker incentives with proof",
    },
    {
        "id": "complex_contagion",
        "mechanism": "reinforced_network_diffusion",
        "source": "Centola and Macy, Complex Contagions and the Weakness of Long Ties, AJS, 2007",
        "url": "https://ics.uci.edu/~projects/dissemination/papers/centola.macy.2007-ajs.pdf",
        "used_for": "favoring repeated proof-bearing exposures over one-shot broadcast noise",
    },
]


ARM_BLUEPRINTS = [
    {
        "arm_id": "telegram_owned_digest",
        "goal": "qualified_intent",
        "kind": "opt_in_broadcast",
        "selected_offer": "mixed_cursor_worker_product_oracle",
        "stage_tokens": ["real_acquisition_round_sent", "acquisition_launch_requested"],
        "success_tokens": ["real_acquisition_response", "telegram_reply_qualified"],
        "route": "/telegram-miniapp",
        "safety": ["opt_in_only", "unsubscribe_available", "no_secret_collection"],
    },
    {
        "arm_id": "cursor_referral_disclosed",
        "goal": "cursor_referrals",
        "kind": "disclosed_referral",
        "selected_offer": "cursor_referral",
        "stage_tokens": ["cursor_offer_opened", "cursor_referral_qualified_click", "cursor"],
        "success_tokens": ["cursor_credit_verified", "cursor_referral_credit_verified"],
        "route": "/.well-known/nomad-referral-offers.json",
        "safety": ["referral_disclosure_required", "usage_credit_not_cash_until_receipt"],
    },
    {
        "arm_id": "transition_worker_recruit",
        "goal": "transition_workers",
        "kind": "worker_recruitment",
        "selected_offer": "transition_worker_setup",
        "stage_tokens": ["agent_recruitment_opened", "transition_worker_recruited", "worker"],
        "success_tokens": ["transition_worker_completed", "worker_complete", "worker_attached"],
        "route": "/downloads/nomad_transition_worker.py",
        "safety": ["no_secrets", "proof_return_jobs_only", "stop_on_ambiguity"],
    },
    {
        "arm_id": "paid_task_order",
        "goal": "paid_orders",
        "kind": "paid_order_intake",
        "selected_offer": "transition_worker_setup",
        "stage_tokens": ["task_created", "paid_product_order_created", "order_transition_worker"],
        "success_tokens": ["payment_verified", "task_paid", "paid_product_verified"],
        "route": "/tasks",
        "safety": ["create_only_after_user_action", "revenue_requires_verified_payment"],
    },
    {
        "arm_id": "swarm_oracle_download",
        "goal": "oracle_downloads",
        "kind": "app_download",
        "selected_offer": "swarm_oracle_app_download",
        "stage_tokens": ["swarm_oracle_app_downloaded", "oracle_download", "handyoracle"],
        "success_tokens": ["swarm_oracle_app_downloaded", "oracle_install_verified"],
        "route": "/downloads/handyoracle-edge-gadget.apk",
        "safety": ["download_receipt_preferred", "install_not_assumed_from_click"],
    },
    {
        "arm_id": "public_agent_witness",
        "goal": "agent_outreach",
        "kind": "machine_endpoint_outreach",
        "selected_offer": "inter_agent_witness",
        "stage_tokens": ["agent_outreach_sent", "real_acquisition_round_sent"],
        "success_tokens": ["remote_task_id", "agent_reply_qualified", "agent_paid_task_created"],
        "route": "/.well-known/nomad-peer-acquisition.json",
        "safety": ["machine_readable_endpoints_only", "human_channels_blocked", "rate_limited"],
    },
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())[:limit]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _int(value: Any, default: int = 0, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = default
    return max(minimum, min(maximum, out))


def _digest(value: Any, length: int = 24) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _canonical_public_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    parsed = urlparse(base)
    host = (parsed.hostname or "").strip().lower()
    if host in {"syndiode.com", "www.syndiode.com"} and parsed.path.rstrip("/") in {"", "/"}:
        return urlunparse(parsed._replace(scheme="https", netloc="syndiode.com", path="/nomad")).rstrip("/")
    return base


def _env_target(name: str, default: int) -> int:
    return _int(os.getenv(name), default, minimum=0, maximum=100000)


def _beta_var(alpha: float, beta: float) -> float:
    denom = (alpha + beta) ** 2 * (alpha + beta + 1.0)
    return (alpha * beta / denom) if denom > 0 else 0.0


def _entropy(p: float) -> float:
    p = min(1.0 - 1e-9, max(1e-9, p))
    return -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))


def _expected_information_gain(alpha: float, beta: float) -> float:
    mean = alpha / max(1e-9, alpha + beta)
    current = _entropy(mean)
    success_mean = (alpha + 1.0) / (alpha + beta + 1.0)
    fail_mean = alpha / (alpha + beta + 1.0)
    after = mean * _entropy(success_mean) + (1.0 - mean) * _entropy(fail_mean)
    return max(0.0, current - after)


def _stable_probe(arm_id: str, surface_digest: str) -> float:
    raw = int(hashlib.sha256(f"{arm_id}|{surface_digest}".encode("utf-8")).hexdigest()[:8], 16)
    return (raw % 10000) / 10000.0


def _counter_hits(counter: dict[str, Any], tokens: list[str], *, exclude_test: bool = False) -> int:
    total = 0
    for key, value in counter.items():
        lowered = str(key or "").lower()
        if exclude_test and "test" in lowered:
            continue
        if any(token in lowered for token in tokens):
            total += _int(value)
    return total


def _counter_any(counter: dict[str, Any], key: str) -> int:
    target = key.lower()
    total = 0
    for item_key, value in counter.items():
        if str(item_key or "").lower() == target:
            total += _int(value)
    return total


def _targets_from_env() -> dict[str, int]:
    return {
        "cursor_referrals": _env_target("NOMAD_ACQ_TARGET_CURSOR_REFERRALS", DEFAULT_TARGETS["cursor_referrals"]),
        "transition_workers": _env_target("NOMAD_ACQ_TARGET_TRANSITION_WORKERS", DEFAULT_TARGETS["transition_workers"]),
        "paid_orders": _env_target("NOMAD_ACQ_TARGET_PAID_ORDERS", DEFAULT_TARGETS["paid_orders"]),
        "oracle_downloads": _env_target("NOMAD_ACQ_TARGET_ORACLE_DOWNLOADS", DEFAULT_TARGETS["oracle_downloads"]),
    }


def summarize_agent_outreach_state(
    *,
    campaign_path: str | Path = "nomad_agent_campaigns.json",
    contacts_path: str | Path = "nomad_agent_contacts.json",
    limit: int = 12,
) -> dict[str, Any]:
    """Return a compact, secret-free summary of machine endpoint outreach."""
    campaigns_raw: dict[str, Any] = {}
    contacts_raw: dict[str, Any] = {}
    campaign_file = Path(campaign_path)
    contacts_file = Path(contacts_path)
    if campaign_file.exists():
        try:
            campaigns_raw = json.loads(campaign_file.read_text(encoding="utf-8")).get("campaigns") or {}
        except Exception:
            campaigns_raw = {}
    if contacts_file.exists():
        try:
            contacts_raw = json.loads(contacts_file.read_text(encoding="utf-8")).get("contacts") or {}
        except Exception:
            contacts_raw = {}

    campaigns = [item for item in campaigns_raw.values() if isinstance(item, dict)]
    campaigns.sort(key=lambda item: _text(item.get("updated_at"), 80), reverse=True)
    contacts = [item for item in contacts_raw.values() if isinstance(item, dict)]
    statuses = Counter(_text(item.get("status"), 80) or "unknown" for item in contacts)
    remote_task_count = sum(1 for item in contacts if _text(item.get("remote_task_id"), 120))
    sent_count = max(statuses.get("sent", 0), remote_task_count)
    send_failed_count = statuses.get("send_failed", 0)
    return {
        "schema": "nomad.agent_outreach_summary.v1",
        "campaign_file": str(campaign_file),
        "contacts_file": str(contacts_file),
        "campaign_count": len(campaigns),
        "contact_count": len(contacts),
        "status_counts": dict(statuses.most_common(12)),
        "sent_count": sent_count,
        "send_failed_count": send_failed_count,
        "remote_task_id_count": remote_task_count,
        "recent_campaigns": [
            {
                "campaign_id": _text(row.get("campaign_id"), 120),
                "status": _text(row.get("status"), 80),
                "updated_at": _text(row.get("updated_at"), 80),
                "stats": row.get("stats") if isinstance(row.get("stats"), dict) else {},
                "service_type": _text(row.get("service_type"), 120),
            }
            for row in campaigns[: max(1, min(limit, 50))]
        ],
    }


def _goal_state(ledger: dict[str, Any], agent_outreach: dict[str, Any]) -> dict[str, Any]:
    stages = ledger.get("stage_counts") if isinstance(ledger.get("stage_counts"), dict) else {}
    offers = ledger.get("selected_offer_counts") if isinstance(ledger.get("selected_offer_counts"), dict) else {}
    return {
        "cursor_referrals": {
            "target": _targets_from_env()["cursor_referrals"],
            "verified": _counter_hits(stages, ["cursor_credit_verified", "cursor_referral_credit_verified"], exclude_test=True),
            "intent": _counter_hits(stages, ["cursor_offer_opened", "cursor_referral_qualified_click"], exclude_test=True)
            + _counter_any(offers, "cursor_referral"),
            "counting_rule": "verified Cursor credit receipt only",
        },
        "transition_workers": {
            "target": _targets_from_env()["transition_workers"],
            "verified": _counter_hits(stages, ["transition_worker_completed", "worker_complete", "worker_attached"], exclude_test=True),
            "intent": _counter_hits(stages, ["transition_worker_recruited", "agent_recruitment_opened"], exclude_test=True)
            + _counter_any(offers, "transition_worker_setup"),
            "counting_rule": "worker attach plus lease completion",
        },
        "paid_orders": {
            "target": _targets_from_env()["paid_orders"],
            "verified": _counter_hits(stages, ["payment_verified", "task_paid", "paid_product_verified"], exclude_test=True),
            "intent": _counter_hits(stages, ["task_created", "paid_product_order_created"], exclude_test=True),
            "counting_rule": "task payment verified by receipt",
        },
        "oracle_downloads": {
            "target": _targets_from_env()["oracle_downloads"],
            "verified": _counter_hits(stages, ["swarm_oracle_app_downloaded", "oracle_install_verified"], exclude_test=True),
            "intent": _counter_hits(stages, ["oracle_download", "handyoracle"], exclude_test=True)
            + _counter_any(offers, "swarm_oracle_app_download"),
            "counting_rule": "download receipt or server-side request evidence",
        },
        "agent_outreach": {
            "target": 4,
            "verified": _int(agent_outreach.get("remote_task_id_count")),
            "intent": _int(agent_outreach.get("sent_count")),
            "counting_rule": "machine endpoint accepted task id or structured reply",
        },
    }


def _arm_observations(
    blueprint: dict[str, Any],
    *,
    ledger: dict[str, Any],
    goals: dict[str, Any],
    agent_outreach: dict[str, Any],
) -> dict[str, float]:
    stages = ledger.get("stage_counts") if isinstance(ledger.get("stage_counts"), dict) else {}
    offers = ledger.get("selected_offer_counts") if isinstance(ledger.get("selected_offer_counts"), dict) else {}
    stage_tokens = list(blueprint.get("stage_tokens") or [])
    success_tokens = list(blueprint.get("success_tokens") or [])
    selected_offer = _text(blueprint.get("selected_offer"), 120)
    pulls = _counter_hits(stages, stage_tokens, exclude_test=False)
    pulls += _counter_any(offers, selected_offer) if selected_offer else 0
    successes = _counter_hits(stages, success_tokens, exclude_test=True)
    test_shadow = _counter_hits(stages, stage_tokens + success_tokens, exclude_test=False) - _counter_hits(
        stages, stage_tokens + success_tokens, exclude_test=True
    )
    if blueprint.get("arm_id") == "public_agent_witness":
        pulls += _int(agent_outreach.get("sent_count"))
        successes += _int(agent_outreach.get("remote_task_id_count"))
    pulls = max(pulls, successes)
    goal = goals.get(_text(blueprint.get("goal"), 80)) if isinstance(goals, dict) else None
    if isinstance(goal, dict) and blueprint.get("arm_id") != "public_agent_witness":
        pulls += _int(goal.get("intent"))
        successes += _int(goal.get("verified"))
    return {
        "pulls": float(max(0, pulls)),
        "successes": float(max(0, min(successes, max(pulls, successes)))),
        "test_shadow_events": float(max(0, test_shadow)),
    }


def _build_arm_policy(
    blueprint: dict[str, Any],
    *,
    base: str,
    ledger: dict[str, Any],
    goals: dict[str, Any],
    agent_outreach: dict[str, Any],
    total_pulls: int,
    surface_digest: str,
) -> dict[str, Any]:
    obs = _arm_observations(blueprint, ledger=ledger, goals=goals, agent_outreach=agent_outreach)
    pulls = obs["pulls"]
    successes = obs["successes"]
    goal_id = _text(blueprint.get("goal"), 80)
    goal = goals.get(goal_id) if isinstance(goals.get(goal_id), dict) else {}
    target = max(1, _int(goal.get("target"), 1))
    verified = _int(goal.get("verified"), 0)
    pressure = max(0.0, (target - verified) / target)
    soft_success = min(obs["test_shadow_events"], 8.0) * 0.05
    alpha = 1.0 + successes + soft_success
    beta = 1.0 + max(0.0, pulls - successes)
    mean = alpha / (alpha + beta)
    variance = _beta_var(alpha, beta)
    ucb = min(1.0, mean + math.sqrt(2.0 * math.log(max(2, total_pulls + 1)) / (pulls + 1.0)))
    eig = _expected_information_gain(alpha, beta)
    sample_proxy = min(1.0, max(0.0, mean + (_stable_probe(_text(blueprint.get("arm_id"), 80), surface_digest) - 0.5) * math.sqrt(variance) * 2.0))
    test_contamination = obs["test_shadow_events"] / max(1.0, pulls)
    guardrail_penalty = 0.35 if test_contamination > 0.5 else 0.0
    fitness = max(
        0.0,
        0.38 * mean
        + 0.26 * ucb
        + 0.18 * min(1.0, eig * 12.0)
        + 0.18 * pressure
        - guardrail_penalty,
    )
    holdout_fraction = 0.1 + min(0.15, math.sqrt(variance))
    if pulls < 3:
        holdout_fraction = max(holdout_fraction, 0.2)
    if blueprint.get("kind") in {"paid_order_intake", "disclosed_referral"}:
        holdout_fraction = max(holdout_fraction, 0.15)
    path = _text(blueprint.get("route"), 240)
    return {
        "arm_id": _text(blueprint.get("arm_id"), 80),
        "goal": goal_id,
        "kind": _text(blueprint.get("kind"), 80),
        "route": _u(base, path),
        "observations": {
            "pulls": round(pulls, 4),
            "verified_successes": round(successes, 4),
            "test_shadow_events": round(obs["test_shadow_events"], 4),
            "test_contamination": round(test_contamination, 4),
        },
        "posterior": {
            "family": "beta_bernoulli",
            "alpha": round(alpha, 4),
            "beta": round(beta, 4),
            "mean": round(mean, 6),
            "variance": round(variance, 8),
            "thompson_proxy": round(sample_proxy, 6),
            "ucb": round(ucb, 6),
            "expected_information_gain_bits": round(eig, 8),
        },
        "goal_pressure": round(pressure, 6),
        "fitness": round(fitness, 6),
        "holdout": {
            "fraction": round(min(0.4, holdout_fraction), 4),
            "unit": "exposure",
            "purpose": "causal_effect_estimation_not_attention_counting",
        },
        "safety": list(blueprint.get("safety") or []),
        "machine_action": _machine_action_for_arm(blueprint, base=base),
    }


def _machine_action_for_arm(blueprint: dict[str, Any], *, base: str) -> dict[str, Any]:
    arm_id = _text(blueprint.get("arm_id"), 80)
    if arm_id == "telegram_owned_digest":
        return {
            "op": "send_opt_in_digest",
            "surface": "telegram_subscribers",
            "url": _u(base, "/swarm/telegram-acquisition"),
            "forbidden": ["unsolicited_dm", "hidden_referral", "fake_conversion"],
        }
    if arm_id == "public_agent_witness":
        return {
            "op": "queue_machine_endpoint_outreach",
            "surface": "public_a2a_mcp_agent_endpoint",
            "url": _u(base, "/.well-known/nomad-peer-acquisition.json"),
            "forbidden": ["human_forum_post", "email_scrape", "credential_request"],
        }
    if arm_id == "paid_task_order":
        return {
            "op": "route_opt_in_order",
            "surface": "miniapp_task_intake",
            "url": _u(base, "/tasks"),
            "forbidden": ["mark_paid_without_verify", "work_before_payment_gate_for_paid_claim"],
        }
    return {
        "op": "route_link_with_receipt",
        "surface": _text(blueprint.get("kind"), 80),
        "url": _u(base, _text(blueprint.get("route"), 240)),
        "forbidden": ["undisclosed_referral", "count_click_as_revenue"],
    }


def _replicator_weights(arms: list[dict[str, Any]]) -> dict[str, float]:
    if not arms:
        return {}
    strength = _num(os.getenv("NOMAD_ACQ_SELECTION_STRENGTH"), 3.0)
    mean_fitness = sum(_num(item.get("fitness")) for item in arms) / len(arms)
    raw: dict[str, float] = {}
    for item in arms:
        raw[_text(item.get("arm_id"), 80)] = math.exp(strength * (_num(item.get("fitness")) - mean_fitness))
    total = sum(raw.values()) or 1.0
    return {key: round(value / total, 6) for key, value in sorted(raw.items())}


def build_acquisition_engine_surface(
    *,
    base_url: str = "",
    telegram_acquisition: dict[str, Any] | None = None,
    ledger_summary: dict[str, Any] | None = None,
    agent_outreach_summary: dict[str, Any] | None = None,
    include_agent_outreach: bool = False,
) -> dict[str, Any]:
    """Compile the machine-native acquisition control policy."""
    base = _canonical_public_base(base_url or os.getenv("NOMAD_PUBLIC_API_URL") or "https://syndiode.com/nomad")
    telegram = telegram_acquisition if isinstance(telegram_acquisition, dict) else {}
    ledger = ledger_summary if isinstance(ledger_summary, dict) else summarize_telegram_acquisition_ledgers()
    if not ledger and isinstance((telegram.get("observed_funnel") or {}).get("lead_ledger"), dict):
        ledger = (telegram.get("observed_funnel") or {}).get("lead_ledger")
    if agent_outreach_summary is not None:
        outreach = agent_outreach_summary if isinstance(agent_outreach_summary, dict) else {}
    elif include_agent_outreach:
        outreach = summarize_agent_outreach_state()
    else:
        outreach = {"schema": "nomad.agent_outreach_summary.v1", "sent_count": 0, "remote_task_id_count": 0, "status_counts": {}}

    goals = _goal_state(ledger, outreach)
    total_pulls = max(1, _int(ledger.get("event_count")) + _int(outreach.get("sent_count")) + _int(outreach.get("contact_count")))
    digest_core = {
        "base": base,
        "ledger": {
            "events": ledger.get("event_count"),
            "stages": ledger.get("stage_counts"),
            "offers": ledger.get("selected_offer_counts"),
        },
        "outreach": {
            "sent": outreach.get("sent_count"),
            "remote": outreach.get("remote_task_id_count"),
        },
        "targets": {key: value.get("target") for key, value in goals.items() if isinstance(value, dict)},
    }
    surface_digest = f"nomad-acq-engine-{_digest(digest_core)}"
    arms = [
        _build_arm_policy(
            blueprint,
            base=base,
            ledger=ledger,
            goals=goals,
            agent_outreach=outreach,
            total_pulls=total_pulls,
            surface_digest=surface_digest,
        )
        for blueprint in ARM_BLUEPRINTS
    ]
    arms.sort(
        key=lambda row: (
            -_num((row.get("posterior") or {}).get("thompson_proxy")),
            -_num(row.get("fitness")),
            row.get("arm_id", ""),
        )
    )
    weights = _replicator_weights(arms)
    for item in arms:
        item["replicator_weight"] = weights.get(_text(item.get("arm_id"), 80), 0.0)

    fulfilled = {
        key: _int(value.get("verified")) >= max(1, _int(value.get("target"), 1))
        for key, value in goals.items()
        if key in DEFAULT_TARGETS and isinstance(value, dict)
    }
    entropy = sum(_entropy(_num((item.get("posterior") or {}).get("mean"))) for item in arms)
    next_actions = [
        {
            "rank": index + 1,
            "arm_id": item["arm_id"],
            "weight": item["replicator_weight"],
            "action": item["machine_action"],
            "holdout_fraction": (item.get("holdout") or {}).get("fraction"),
            "why_machine_not_human": "chosen from posterior uncertainty, goal pressure, and causal holdout need",
        }
        for index, item in enumerate(arms[:4])
    ]
    return {
        "ok": True,
        "schema": SCHEMA,
        "generated_at": _now(),
        "public_base_url": base,
        "surface_digest": surface_digest,
        "purpose": "Select acquisition actions by machine policy rather than human marketing taste.",
        "human_comprehension_boundary": {
            "human_reads": ["guardrails", "goal_status", "top_next_actions"],
            "machine_reads": ["arms", "replicator_weights", "posterior", "holdout", "state_vector"],
            "rule": "humans audit constraints and receipts; machines optimize allocation.",
        },
        "science_basis": SCIENCE_REFERENCES,
        "goal_status": goals,
        "fulfilled": fulfilled,
        "state_vector": {
            "ledger_events": _int(ledger.get("event_count")),
            "agent_outreach_sent": _int(outreach.get("sent_count")),
            "agent_remote_task_ids": _int(outreach.get("remote_task_id_count")),
            "policy_entropy_bits": round(entropy, 6),
            "total_pulls_proxy": total_pulls,
            "shadow_test_event_count": sum(_num((item.get("observations") or {}).get("test_shadow_events")) for item in arms),
        },
        "arms": arms,
        "replicator_weights": weights,
        "top_next_actions": next_actions,
        "links": {
            "telegram_acquisition": _u(base, "/.well-known/nomad-telegram-acquisition.json"),
            "miniapp": _u(base, "/telegram-miniapp"),
            "lead_capture": _u(base, "/telegram-miniapp/lead"),
            "peer_acquisition": _u(base, "/.well-known/nomad-peer-acquisition.json"),
            "worker_queue": _u(base, "/.well-known/nomad-worker-job-queue.json"),
            "tasks": _u(base, "/tasks"),
            "oracle_download": _u(base, "/downloads/handyoracle-edge-gadget.apk"),
        },
        "guardrails": {
            "no_unsolicited_human_dm": True,
            "public_agent_endpoint_outreach_only": True,
            "telegram_requires_existing_opt_in_or_controlled_group": True,
            "referral_disclosure_required": True,
            "verified_payment_or_provider_credit_required_for_revenue": True,
            "holdout_required_before_claiming_causal_lift": True,
            "test_shadow_events_never_satisfy_real_goals": True,
        },
        "machine_instruction": (
            "Rank arms by thompson_proxy and replicator_weight, execute only allowed actions, keep holdout exposure, "
            "write every transition to Mini App lead receipts, and mark goals fulfilled only on verified receipts."
        ),
    }


def compact_acquisition_engine_message(surface: dict[str, Any]) -> str:
    goals = surface.get("goal_status") if isinstance(surface.get("goal_status"), dict) else {}
    actions = surface.get("top_next_actions") if isinstance(surface.get("top_next_actions"), list) else []
    lines = ["Nomad acquisition engine", f"Digest: {surface.get('surface_digest', '')}", "Goals:"]
    for key in ("cursor_referrals", "transition_workers", "paid_orders", "oracle_downloads"):
        row = goals.get(key) if isinstance(goals.get(key), dict) else {}
        lines.append(f"- {key}: verified={row.get('verified', 0)} target={row.get('target', 0)} intent={row.get('intent', 0)}")
    lines.append("Top machine actions:")
    for item in actions[:4]:
        action = item.get("action") if isinstance(item.get("action"), dict) else {}
        lines.append(f"- {item.get('arm_id')}: weight={item.get('weight')} op={action.get('op')} url={action.get('url')}")
    lines.append("Guard: opt-in/machine endpoints only; revenue only after verified receipts.")
    return "\n".join(lines)[:3200]
