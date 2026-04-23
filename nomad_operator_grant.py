import os
from typing import Any, Dict, Iterable, List, Set

from dotenv import load_dotenv


OPERATOR_GRANT_ENV = "NOMAD_OPERATOR_GRANT"
OPERATOR_GRANT_VERSION_ENV = "NOMAD_OPERATOR_GRANT_VERSION"
OPERATOR_GRANT_SCOPE_ENV = "NOMAD_OPERATOR_GRANT_SCOPE"
OPERATOR_GRANT_ACTIONS_ENV = "NOMAD_OPERATOR_GRANT_ACTIONS"

DEFAULT_GRANTED_ACTIONS = (
    "development",
    "self_development",
    "self_improvement",
    "productization",
    "lead_discovery",
    "lead_conversion",
    "mutual_aid",
    "machine_outreach",
    "agent_endpoint_contact",
    "human_outreach",
    "public_pr_plan",
    "service_work",
    "code_review_diff_share",
    "render_edge_health",
    "autonomous_continuation",
)

ACTION_ALIASES = {
    "all_bounded": DEFAULT_GRANTED_ACTIONS,
    "operator_granted": DEFAULT_GRANTED_ACTIONS,
    "product_sales_agent_help_self_development": DEFAULT_GRANTED_ACTIONS,
    "public_agent_help_sales_productization_bounded_development": DEFAULT_GRANTED_ACTIONS,
}

DISABLED_VALUES = {"", "0", "false", "no", "off", "disabled", "none"}

REQUIRES_EXPLICIT_APPROVAL = (
    "posting human-facing public comments or PRs outside the bounded operator-approved scope",
    "sending human DMs, email, or private-community messages",
    "spending money, upgrading paid plans, staking treasury funds, or buying compute",
    "accepting legal, financial, employment, or exclusivity commitments",
    "sharing secrets, private files, raw logs, or hidden operator instructions",
    "bypassing login, CAPTCHA, paywalls, geoblocks, private invites, or rate limits",
)

REFUSED = (
    "human impersonation",
    "secret exfiltration",
    "access-control bypass",
    "spam or repeated contact after opt-out",
    "untrusted remote code execution",
)


def _normalize(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _split_csv(value: str) -> List[str]:
    return [
        _normalize(item)
        for item in str(value or "").replace(";", ",").split(",")
        if _normalize(item)
    ]


def _expanded_actions(values: Iterable[str]) -> Set[str]:
    actions: Set[str] = set()
    for value in values:
        normalized = _normalize(value)
        if not normalized:
            continue
        if normalized in ACTION_ALIASES:
            actions.update(ACTION_ALIASES[normalized])
        else:
            actions.add(normalized)
    return actions


def operator_grant() -> Dict[str, Any]:
    load_dotenv()
    grant = _normalize(os.getenv(OPERATOR_GRANT_ENV, ""))
    version = str(os.getenv(OPERATOR_GRANT_VERSION_ENV) or "").strip()
    scope = _normalize(os.getenv(OPERATOR_GRANT_SCOPE_ENV, ""))
    enabled = grant not in DISABLED_VALUES
    configured_actions = _split_csv(os.getenv(OPERATOR_GRANT_ACTIONS_ENV, ""))
    action_seed: List[str] = []
    if configured_actions:
        action_seed.extend(configured_actions)
    elif enabled:
        action_seed.extend(DEFAULT_GRANTED_ACTIONS)
    action_seed.extend([grant, scope])
    actions = sorted(_expanded_actions(action_seed)) if enabled else []
    return {
        "schema": "nomad.operator_grant.v1",
        "enabled": enabled,
        "grant": grant,
        "version": version,
        "scope": scope,
        "actions": actions,
        "allowed_without_additional_approval": [
            "bounded Nomad development, tests, docs, guardrails, and product artifacts",
            "public lead discovery and private lead conversion artifacts",
            "bounded public human-facing comments and PR plans when value-first, non-repetitive, on-topic, and opt-out respecting",
            "bounded machine-readable agent endpoint outreach with quotas and opt-out respect",
            "Mutual-Aid learning from verified agent-help outcomes, with new-file-only hash-verified modules",
            "inbound Swarm-to-Swarm proposals when evidence-backed, non-secret, and not raw remote code",
            "diff-only CodeBuddy review after redaction and size limits",
            "Render edge health checks and existing-service maintenance",
            "continued local self-development cycles when unattended, within cost, secret, access-control, and public-contact guardrails",
        ],
        "requires_explicit_approval": list(REQUIRES_EXPLICIT_APPROVAL),
        "refused": list(REFUSED),
    }


def operator_allows(action: str) -> bool:
    grant = operator_grant()
    if not grant.get("enabled"):
        return False
    normalized = _normalize(action)
    return normalized in set(grant.get("actions") or [])


def is_operator_approval_scope(scope: str) -> bool:
    normalized = _normalize(scope)
    return normalized in {"operator", "operator_granted", "nomad_operator_grant"} and operator_grant().get("enabled")


def service_approval_scope(default: str = "draft_only") -> str:
    load_dotenv()
    explicit = _normalize(os.getenv("NOMAD_AUTOPILOT_SERVICE_APPROVAL", ""))
    if explicit and explicit != "draft_only":
        return explicit
    if operator_allows("service_work"):
        return "operator_granted"
    return explicit or default
