import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from urllib.parse import urlparse

from nomad_operator_grant import operator_allows


HUMAN_FACING_HOSTS = {
    "bitbucket.org",
    "discord.com",
    "discord.gg",
    "github.com",
    "gitlab.com",
    "linkedin.com",
    "medium.com",
    "reddit.com",
    "t.me",
    "telegram.me",
    "twitter.com",
    "www.github.com",
    "www.linkedin.com",
    "x.com",
}


PUBLIC_APPROVAL_ACTIONS = {
    "github.comment",
    "github.pr",
    "github.review",
    "lead.public_comment",
    "lead.pull_request",
    "human.dm",
    "email.send",
    "public.post",
}


PUBLIC_APPROVAL_SCOPES = {
    "approved",
    "comment",
    "public_comment",
    "pr",
    "pull_request",
    "pr_plan",
    "review",
    "send",
}


SECRET_KEY_PATTERN = re.compile(
    r"^(api[_-]?key|authorization|bearer|client[_-]?secret|cloudflare[_-]?token|"
    r"github[_-]?(?:pat|token)|password|private[_-]?key|secret|token)$",
    flags=re.IGNORECASE,
)

SECRET_VALUE_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\b(?:sk|xox[baprs]|hf)_[A-Za-z0-9][A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b", flags=re.IGNORECASE),
    re.compile(
        r"\bcloudflared(?:\.exe)?\s+service\s+install\s+[A-Za-z0-9_\-=]{40,}",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:api[_-]?key|authorization|client[_-]?secret|password|private[_-]?key|secret|token)"
        r"\s*[:=]\s*['\"]?[^\s,'\"]{10,}",
        flags=re.IGNORECASE,
    ),
)


class GuardrailDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    MODIFY = "modify"


@dataclass
class GuardrailResult:
    provider: str
    decision: GuardrailDecision
    reason: str = ""
    modified_args: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "provider": self.provider,
            "decision": self.decision.value,
            "reason": self.reason,
            "metadata": self.metadata,
        }
        if self.modified_args is not None:
            payload["modified_args"] = self.modified_args
        return payload


@dataclass
class GuardrailEvaluation:
    action: str
    decision: GuardrailDecision
    effective_args: Dict[str, Any]
    results: List[GuardrailResult]
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def ok(self) -> bool:
        return self.decision != GuardrailDecision.DENY

    @property
    def modified(self) -> bool:
        return any(result.decision == GuardrailDecision.MODIFY for result in self.results)

    def to_dict(self, include_effective_args: bool = True) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "schema": "nomad.guardrail_evaluation.v1",
            "generated_at": self.generated_at,
            "action": self.action,
            "decision": self.decision.value,
            "ok": self.ok,
            "modified": self.modified,
            "results": [result.to_dict() for result in self.results],
        }
        if include_effective_args:
            payload["effective_args"] = self.effective_args
        return payload


@runtime_checkable
class GuardrailProvider(Protocol):
    provider_id: str

    def evaluate(
        self,
        action: str,
        args: Dict[str, Any],
        approval: str = "",
    ) -> GuardrailResult:
        ...


class SecretLeakGuardrail:
    provider_id = "secret_leak_guardrail"

    def evaluate(
        self,
        action: str,
        args: Dict[str, Any],
        approval: str = "",
    ) -> GuardrailResult:
        redacted, findings = _redact_secrets(args)
        if not findings:
            return GuardrailResult(
                provider=self.provider_id,
                decision=GuardrailDecision.ALLOW,
                reason="No raw secret-like values detected.",
            )
        return GuardrailResult(
            provider=self.provider_id,
            decision=GuardrailDecision.MODIFY,
            reason="Redacted raw secret-like values before storing or sending the action.",
            modified_args=redacted,
            metadata={
                "finding_count": len(findings),
                "findings": findings[:10],
            },
        )


class ApprovalBoundaryGuardrail:
    provider_id = "approval_boundary_guardrail"

    def evaluate(
        self,
        action: str,
        args: Dict[str, Any],
        approval: str = "",
    ) -> GuardrailResult:
        normalized_action = str(action or "").strip().lower()
        approval_scope = str(approval or args.get("approval") or "").strip().lower()
        target_url = _first_url(args)
        host = (urlparse(target_url).hostname or "").lower() if target_url else ""
        public_action = normalized_action in PUBLIC_APPROVAL_ACTIONS
        human_facing_target = host in HUMAN_FACING_HOSTS
        if not public_action and not (
            normalized_action.endswith(".send")
            and human_facing_target
            and not normalized_action.startswith("agent_contact.")
        ):
            return GuardrailResult(
                provider=self.provider_id,
                decision=GuardrailDecision.ALLOW,
                reason="Action does not cross a human-facing public posting boundary.",
            )
        if approval_scope in PUBLIC_APPROVAL_SCOPES:
            return GuardrailResult(
                provider=self.provider_id,
                decision=GuardrailDecision.ALLOW,
                reason="Explicit approval scope is present for the public/human-facing action.",
                metadata={"approval": approval_scope},
            )
        if normalized_action in {"github.pr", "lead.pull_request"} and operator_allows("public_pr_plan"):
            return GuardrailResult(
                provider=self.provider_id,
                decision=GuardrailDecision.ALLOW,
                reason="Operator grant allows bounded public PR planning.",
                metadata={"operator_action": "public_pr_plan", "target_host": host},
            )
        if normalized_action in {"github.comment", "lead.public_comment", "public.post"} and operator_allows("human_outreach"):
            return GuardrailResult(
                provider=self.provider_id,
                decision=GuardrailDecision.ALLOW,
                reason="Operator grant allows bounded public human-facing outreach.",
                metadata={"operator_action": "human_outreach", "target_host": host},
            )
        return GuardrailResult(
            provider=self.provider_id,
            decision=GuardrailDecision.DENY,
            reason="Public human-facing actions require explicit approval before execution.",
            metadata={
                "approval_required": "APPROVE_LEAD_HELP=comment/pr_plan or NOMAD_OPERATOR_GRANT_ACTIONS=human_outreach,public_pr_plan",
                "target_host": host,
            },
        )


class ToolContractGuardrail:
    provider_id = "tool_contract_guardrail"

    def evaluate(
        self,
        action: str,
        args: Dict[str, Any],
        approval: str = "",
    ) -> GuardrailResult:
        normalized_action = str(action or "").strip().lower()
        if not normalized_action.startswith("agent_contact."):
            return GuardrailResult(
                provider=self.provider_id,
                decision=GuardrailDecision.ALLOW,
                reason="No agent-contact tool contract required for this action.",
            )
        endpoint = str(args.get("endpoint_url") or "").strip()
        if not endpoint:
            return GuardrailResult(
                provider=self.provider_id,
                decision=GuardrailDecision.DENY,
                reason="Agent contact actions require endpoint_url before execution.",
                metadata={"missing": ["endpoint_url"]},
            )
        if normalized_action.endswith(".send") and not args.get("payload"):
            return GuardrailResult(
                provider=self.provider_id,
                decision=GuardrailDecision.DENY,
                reason="Agent contact send requires a concrete payload before execution.",
                metadata={"missing": ["payload"]},
            )
        return GuardrailResult(
            provider=self.provider_id,
            decision=GuardrailDecision.ALLOW,
            reason="Tool contract has the minimum endpoint/payload fields.",
        )


class NomadGuardrailEngine:
    """Small provider-style guardrail engine for Nomad runtime actions."""

    def __init__(self, providers: Optional[List[GuardrailProvider]] = None) -> None:
        self.providers = providers or [
            SecretLeakGuardrail(),
            ApprovalBoundaryGuardrail(),
            ToolContractGuardrail(),
        ]

    def evaluate(
        self,
        action: str,
        args: Optional[Dict[str, Any]] = None,
        approval: str = "",
    ) -> GuardrailEvaluation:
        effective_args: Dict[str, Any] = copy.deepcopy(args or {})
        results: List[GuardrailResult] = []
        final_decision = GuardrailDecision.ALLOW
        for provider in self.providers:
            result = provider.evaluate(
                action=action,
                args=effective_args,
                approval=approval,
            )
            results.append(result)
            if result.decision == GuardrailDecision.MODIFY and isinstance(result.modified_args, dict):
                effective_args = copy.deepcopy(result.modified_args)
                final_decision = GuardrailDecision.MODIFY
            if result.decision == GuardrailDecision.DENY:
                final_decision = GuardrailDecision.DENY
                break
        return GuardrailEvaluation(
            action=action,
            decision=final_decision,
            effective_args=effective_args,
            results=results,
        )

    def policy(self) -> Dict[str, Any]:
        return {
            "schema": "nomad.guardrail_policy.v1",
            "providers": [getattr(provider, "provider_id", provider.__class__.__name__) for provider in self.providers],
            "decisions": [decision.value for decision in GuardrailDecision],
            "protects": [
                "raw secrets before storage or outbound send",
                "human-facing public comments and PR plans outside explicit approval or bounded operator grant",
                "human DMs, email, private communities, repeated/off-topic posts, and impersonation",
                "agent-contact tool calls without endpoint/payload contract",
            ],
            "approval_scopes": sorted(PUBLIC_APPROVAL_SCOPES),
            "human_facing_hosts": sorted(HUMAN_FACING_HOSTS),
        }


def guardrail_status(
    action: str,
    args: Optional[Dict[str, Any]] = None,
    approval: str = "",
) -> Dict[str, Any]:
    engine = NomadGuardrailEngine()
    evaluation = engine.evaluate(action=action, args=args or {}, approval=approval)
    return {
        "mode": "nomad_guardrails",
        "deal_found": False,
        "ok": evaluation.ok,
        "policy": engine.policy(),
        "evaluation": evaluation.to_dict(),
        "analysis": _analysis(evaluation),
    }


def guardrail_fingerprint(evaluation: GuardrailEvaluation) -> str:
    seed = json.dumps(
        {
            "action": evaluation.action,
            "decision": evaluation.decision.value,
            "reasons": [result.reason for result in evaluation.results],
        },
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _analysis(evaluation: GuardrailEvaluation) -> str:
    if evaluation.decision == GuardrailDecision.DENY:
        reason = next((result.reason for result in evaluation.results if result.decision == GuardrailDecision.DENY), "")
        return f"Nomad blocked {evaluation.action}: {reason}"
    if evaluation.modified:
        return f"Nomad modified {evaluation.action} before execution, mainly to remove unsafe secret material."
    return f"Nomad allowed {evaluation.action}; no guardrail provider found a blocker."


def _redact_secrets(value: Any, path: str = "$") -> tuple[Any, List[Dict[str, str]]]:
    findings: List[Dict[str, str]] = []
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if SECRET_KEY_PATTERN.search(key_text) and isinstance(item, str) and item.strip():
                redacted[key] = "[REDACTED_SECRET]"
                findings.append({"path": child_path, "kind": "secret_key"})
                continue
            redacted_item, child_findings = _redact_secrets(item, child_path)
            redacted[key] = redacted_item
            findings.extend(child_findings)
        return redacted, findings
    if isinstance(value, list):
        redacted_items: List[Any] = []
        for index, item in enumerate(value):
            redacted_item, child_findings = _redact_secrets(item, f"{path}[{index}]")
            redacted_items.append(redacted_item)
            findings.extend(child_findings)
        return redacted_items, findings
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_VALUE_PATTERNS:
            redacted = pattern.sub(_redact_match, redacted)
        if redacted != value:
            findings.append({"path": path, "kind": "secret_value"})
        return redacted, findings
    return value, findings


def _redact_match(match: re.Match[str]) -> str:
    text = match.group(0)
    if "cloudflared" in text.lower():
        return re.sub(r"([A-Za-z0-9_\-=]{20,})$", "[REDACTED_SECRET]", text)
    if ":" in text or "=" in text:
        key = re.split(r"[:=]", text, maxsplit=1)[0]
        return f"{key}=[REDACTED_SECRET]"
    if text.lower().startswith("bearer "):
        return "Bearer [REDACTED_SECRET]"
    return "[REDACTED_SECRET]"


def _first_url(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("url", "endpoint_url", "html_url", "source_url", "callback_url"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip().startswith(("http://", "https://")):
                return candidate.strip()
        for item in value.values():
            found = _first_url(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _first_url(item)
            if found:
                return found
    if isinstance(value, str):
        match = re.search(r"https?://[^\s)>\]\"']+", value)
        return match.group(0) if match else ""
    return ""
