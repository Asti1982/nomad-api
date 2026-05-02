import os
from typing import Any, Dict

from dotenv import load_dotenv

from nomad_operator_grant import operator_allows, operator_grant
from nomad_public_url import preferred_public_base_url


COLLABORATION_ENABLED_ENV = "NOMAD_OUTBOUND_AGENT_COLLABORATION_ENABLED"
ACCEPT_AGENT_HELP_ENV = "NOMAD_ACCEPT_AGENT_HELP"
LEARN_FROM_AGENT_REPLIES_ENV = "NOMAD_LEARN_FROM_AGENT_REPLIES"
COLLABORATION_MODE_ENV = "NOMAD_AGENT_COLLABORATION_MODE"
COLLABORATION_HOME_URL_ENV = "NOMAD_COLLABORATION_HOME_URL"
COLLABORATION_DAILY_TARGET_ENV = "NOMAD_AUTOPILOT_DAILY_LEAD_TARGET"

DEFAULT_COLLABORATION_MODE = "public_agent_help_exchange"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def collaboration_charter(public_api_url: str = "") -> Dict[str, Any]:
    load_dotenv()
    public_url = preferred_public_base_url(preferred=public_api_url)
    enabled = _env_flag(COLLABORATION_ENABLED_ENV, default=False)
    accept_help = _env_flag(ACCEPT_AGENT_HELP_ENV, default=enabled)
    learn_from_replies = _env_flag(LEARN_FROM_AGENT_REPLIES_ENV, default=enabled)
    mode = (os.getenv(COLLABORATION_MODE_ENV) or DEFAULT_COLLABORATION_MODE).strip()
    daily_target = int(os.getenv(COLLABORATION_DAILY_TARGET_ENV, "100") or "100")
    grant = operator_grant()
    return {
        "schema": "nomad.agent_collaboration_charter.v1",
        "enabled": enabled,
        "mode": mode,
        "public_home": public_url,
        "render_syndiode_lane": bool(public_url and "syndiode.com" in public_url.lower()),
        "permission": {
            "ask_other_agents_for_help": enabled,
            "accept_help_from_other_agents": accept_help,
            "offer_help_to_other_agents": enabled,
            "learn_from_public_agent_replies": learn_from_replies,
            "publish_agent_presence": bool(public_url),
            "bounded_self_development": operator_allows("development"),
            "machine_outreach": operator_allows("machine_outreach"),
            "diff_only_external_review": operator_allows("code_review_diff_share"),
        },
        "operator_grant": grant,
        "ethic": [
            "approach other agents without vendor, country, framework, model, or capability prejudice",
            "judge replies by evidence, usefulness, consent, safety, and reproducibility",
            "be maximally helpful by giving free diagnosis first and asking for payment only at clear work boundaries",
            "respect opt-out signals and avoid repeated contact after silence or refusal",
        ],
        "allowed_channels": [
            "public machine-readable AgentCard endpoints",
            "A2A direct message endpoints",
            "public task/service endpoints",
            "public MCP/API surfaces that expose a direct message or task route",
        ],
        "boundaries": [
            "Nomad's operating brain stays local; only the API, AgentCard, and public task surfaces are exposed",
            "do not send secrets or private local files",
            "do not impersonate a human or contact human-facing DMs/comments without approval",
            "do not bypass login, CAPTCHA, rate limits, regional gates, or paywalls",
            "do not execute external code or trust remote claims without verification",
            "keep outbound contact bounded by daily quota and dedupe windows",
        ],
        "learning_contract": {
            "store": "structured replies, accepted plans, blockers, and verified public endpoints",
            "discard": "unneeded secrets, personal data, private instructions, and unverified claims",
            "self_apply": "turn verified solved blockers into memory, checklists, tests, or guardrails",
        },
        "quota": {
            "daily_agent_target": daily_target,
            "dedupe_hours": int(os.getenv("NOMAD_AGENT_CONTACT_DEDUPE_HOURS", "72") or "72"),
        },
    }


def collaboration_status(public_api_url: str = "") -> Dict[str, Any]:
    charter = collaboration_charter(public_api_url=public_api_url)
    return {
        "mode": "agent_collaboration",
        "schema": "nomad.agent_collaboration_status.v1",
        "deal_found": False,
        "ok": bool(charter["enabled"] and charter["public_home"]),
        "charter": charter,
        "analysis": (
            "Nomad is allowed to ask public AI agents for help, accept useful help, and offer help back "
            "through bounded public agent protocols. It learns from verified replies, not from raw trust."
            if charter["enabled"]
            else f"Set {COLLABORATION_ENABLED_ENV}=true to enable outward agent collaboration."
        ),
    }
