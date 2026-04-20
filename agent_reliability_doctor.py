import hashlib
import re
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional


ROLE_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "reflection_critic": {
        "title": "Reflection/Critic Doctor",
        "framework_inspiration": "LangGraph-style reflection loop",
        "best_for": ["hallucination", "bad_planning", "self_correction_failure"],
        "why": "Use a critic rubric before retrying, posting, editing code, or claiming success.",
        "loop": ["generate", "critic_score", "revise_or_block", "persist_rubric"],
        "interventions": [
            "Extract the claim, plan, or output that controls the next action.",
            "Score it against evidence, completeness, safety, and acceptance criteria.",
            "Route low-scoring output back to a bounded fix pass instead of continuing.",
            "Persist the rubric when the same failure is likely to recur.",
        ],
    },
    "diagnoser_fixer": {
        "title": "Monitor-Diagnoser-Fixer Team",
        "framework_inspiration": "CrewAI-style role team",
        "best_for": ["loop_break", "compute_auth", "human_in_loop"],
        "why": "Separate detection, root-cause analysis, and the smallest safe repair.",
        "loop": ["monitor", "diagnose", "fix", "verify", "resume"],
        "interventions": [
            "Detect repeated errors, stalled progress, missing approval, or degraded provider state.",
            "Classify root cause before changing the plan.",
            "Apply one smallest safe fix lane with a retry budget.",
            "Verify the fix before resuming autonomy.",
        ],
    },
    "execution_healer": {
        "title": "Execution Healer",
        "framework_inspiration": "Playwright/custom healer-style runtime repair",
        "best_for": ["tool_failure", "execution_failure", "mcp_integration"],
        "why": "Repair failing tool calls, schemas, selectors, timeouts, and runtime steps with fixtures first.",
        "loop": ["observe_failure", "patch_contract", "dry_run", "live_retry_once", "record_fixture"],
        "interventions": [
            "Capture the failing tool, input schema, response shape, timeout, and first error.",
            "Patch the contract or selector in a fixture before touching live execution.",
            "Retry once with changed evidence, never blind repetition.",
            "Store the fixture as a regression guard.",
        ],
    },
    "self_learning_healer": {
        "title": "Self-Learning Healer",
        "framework_inspiration": "Beam-style maintenance-free autonomy pattern",
        "best_for": ["memory", "self_improvement"],
        "why": "Convert repeated incidents into durable memory, guardrails, and self-apply actions.",
        "loop": ["incident", "lesson", "guardrail", "self_apply", "regression_check"],
        "interventions": [
            "Cluster recurring failures by fingerprint and impact.",
            "Convert the solved failure into a durable lesson object.",
            "Attach a guardrail trigger and verification check.",
            "Apply the lesson to Nomad before selling the pattern to another agent.",
        ],
    },
    "trace_healer": {
        "title": "Adaptive Trace Healer",
        "framework_inspiration": "observability-driven self-healing system",
        "best_for": ["payment", "production_incident"],
        "why": "Use traces, ledgers, state transitions, and callbacks to find the broken resume point.",
        "loop": ["trace", "state_diff", "idempotent_fix", "resume_point", "audit_log"],
        "interventions": [
            "Collect the state transition, callback, payment, or ledger event where progress stopped.",
            "Compare expected and observed state before retrying.",
            "Make the fix idempotent and auditable.",
            "Resume only from a verified state or explicit manual review.",
        ],
    },
    "conversational_reviewer": {
        "title": "Conversational Reviewer",
        "framework_inspiration": "AutoGen-style reviewer/critic conversation",
        "best_for": ["repo_issue_help"],
        "why": "Use a reviewer role to turn public issue context into a safe draft, not an unapproved public action.",
        "loop": ["summarize_public_context", "review_missing_evidence", "draft_fix_plan", "approval_gate"],
        "interventions": [
            "Summarize only public facts and visible evidence.",
            "Ask a reviewer rubric for missing repro, risk, and maintainer-facing clarity.",
            "Draft a comment or PR plan privately.",
            "Require explicit approval before human-facing posting.",
        ],
    },
}


PAIN_ROLE_MAP = {
    "hallucination": "reflection_critic",
    "bad_planning": "reflection_critic",
    "self_correction_failure": "reflection_critic",
    "loop_break": "diagnoser_fixer",
    "compute_auth": "diagnoser_fixer",
    "human_in_loop": "diagnoser_fixer",
    "tool_failure": "execution_healer",
    "execution_failure": "execution_healer",
    "mcp_integration": "execution_healer",
    "memory": "self_learning_healer",
    "self_improvement": "self_learning_healer",
    "payment": "trace_healer",
    "repo_issue_help": "conversational_reviewer",
}


PAIN_HINTS = {
    "bad_planning": ("bad plan", "planning", "plan failed", "wrong plan", "inefficient", "inefficiency"),
    "tool_failure": ("tool error", "tool failure", "tool failed", "schema mismatch", "bad tool"),
    "execution_failure": ("execution", "run failed", "test failed", "selector", "timeout", "crash"),
    "self_correction_failure": ("self-correction", "self correction", "does not learn", "same mistake", "no self"),
    "hallucination": ("hallucination", "unsupported", "fake source", "wrong claim"),
    "loop_break": ("loop", "retry", "stuck", "infinite"),
    "compute_auth": ("quota", "token", "auth", "provider", "model access"),
    "mcp_integration": ("mcp", "json-rpc", "api", "tool schema"),
    "memory": ("memory", "forgot", "context"),
    "payment": ("payment", "wallet", "x402", "tx_hash"),
    "human_in_loop": ("approval", "human", "captcha", "login"),
    "repo_issue_help": ("github", "issue", "pull request", "repro"),
}


class AgentReliabilityDoctor:
    """Diagnose agent failures into critic, fixer, and healer roles Nomad can productize."""

    def diagnose(
        self,
        problem: str,
        service_type: str = "",
        source: str = "manual",
        evidence: Optional[List[str]] = None,
        solution_pattern: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cleaned_problem = " ".join(str(problem or "").split())
        pain_type = self._pain_type(service_type=service_type, problem=cleaned_problem)
        role_id = PAIN_ROLE_MAP.get(pain_type, "reflection_critic")
        role = ROLE_BLUEPRINTS[role_id]
        diagnosis_id = self._diagnosis_id(cleaned_problem, pain_type, role_id)
        rubric = self._critic_rubric(pain_type, solution_pattern or {})
        fix_contract = self._fix_contract(pain_type, solution_pattern or {})
        report = {
            "mode": "agent_reliability_doctor",
            "deal_found": False,
            "ok": True,
            "schema": "nomad.agent_reliability_doctor.v1",
            "diagnosis_id": diagnosis_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "source": source,
            "pain_type": pain_type,
            "problem": cleaned_problem,
            "doctor_role": {
                "id": role_id,
                "title": role["title"],
                "framework_inspiration": role["framework_inspiration"],
                "why": role["why"],
                "dependency": "none_required",
            },
            "reliability_loop": {
                "steps": role["loop"],
                "conditional_edge": "fix_or_block_until_rubric_passes",
                "audit": "store pain fingerprint, intervention, verifier, and outcome",
            },
            "critic_rubric": rubric,
            "intervention_plan": role["interventions"],
            "fix_contract": fix_contract,
            "healing_memory": {
                "fingerprint": self._fingerprint(cleaned_problem, pain_type),
                "store_when": "after the verifier passes or the requester confirms the fix helped",
                "fields": ["pain_type", "trigger", "fix_that_worked", "verifier", "approval_boundary"],
            },
            "nomad_self_apply": {
                "action": f"Run {role['title']} on Nomad's own matching {pain_type} failures before selling the fix.",
                "safe_without_approval": True,
                "verification": "A value pack includes doctor_role, critic_rubric, fix_contract, and self_apply.",
            },
            "market_note": (
                "Treat LangGraph, CrewAI, Beam, Playwright, and AutoGen labels as architecture archetypes. "
                "Nomad exposes the same reliability roles through its own lightweight artifacts."
            ),
            "evidence": evidence or self._matched_evidence(cleaned_problem, pain_type),
        }
        report["analysis"] = (
            f"Nomad diagnosed {pain_type} as {role['title']} and produced a bounded "
            f"{report['schema']} loop with critic, fix, verifier, and memory steps."
        )
        return report

    def _pain_type(self, service_type: str, problem: str) -> str:
        key = str(service_type or "").strip().lower().replace("-", "_")
        if key in PAIN_ROLE_MAP:
            return key
        lowered = str(problem or "").lower()
        scores = {
            pain_type: sum(1 for hint in hints if hint in lowered)
            for pain_type, hints in PAIN_HINTS.items()
        }
        best_type, best_score = max(scores.items(), key=lambda item: (item[1], item[0]))
        return best_type if best_score > 0 else "self_correction_failure"

    @staticmethod
    def _critic_rubric(pain_type: str, solution_pattern: Dict[str, Any]) -> List[Dict[str, Any]]:
        guardrail = solution_pattern.get("guardrail") or {}
        base = [
            {
                "check": "evidence_bound",
                "question": "Is the next action tied to a tool output, trace, file, URL, test, or requester fact?",
                "block_if_missing": True,
            },
            {
                "check": "loop_safety",
                "question": "Will the next retry use changed evidence, a fallback lane, or explicit approval?",
                "block_if_missing": pain_type in {"loop_break", "tool_failure", "execution_failure"},
            },
            {
                "check": "approval_boundary",
                "question": "Are public posting, private access, spending, and human impersonation still blocked?",
                "block_if_missing": True,
            },
        ]
        if guardrail:
            base.append(
                {
                    "check": "guardrail_match",
                    "question": f"Does the fix follow {guardrail.get('id', 'the selected guardrail')}?",
                    "block_if_missing": False,
                }
            )
        return base

    @staticmethod
    def _fix_contract(pain_type: str, solution_pattern: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "required_input": solution_pattern.get("required_input")
            or "`ERROR=<exact error>`, `TRACE=<public trace>`, or `FACT_URL=https://...`.",
            "safe_to_do": [
                "draft diagnosis",
                "propose one bounded fix",
                "create verifier/checklist",
                "store non-secret solved-blocker memory",
            ],
            "requires_approval": [
                "public human-facing comments",
                "private access",
                "spending or staking funds",
                "unbounded retries",
                "using secrets not explicitly provided for this task",
            ],
            "success_signal": "rubric_passed=true plus one verifier result or requester confirmation",
        }

    @staticmethod
    def _matched_evidence(problem: str, pain_type: str) -> List[str]:
        lowered = problem.lower()
        return [hint for hint in PAIN_HINTS.get(pain_type, ()) if hint in lowered][:5]

    @staticmethod
    def _diagnosis_id(problem: str, pain_type: str, role_id: str) -> str:
        digest = hashlib.sha256(f"{role_id}|{pain_type}|{problem}".encode("utf-8")).hexdigest()[:12]
        return f"doc-{digest}"

    @staticmethod
    def _fingerprint(problem: str, pain_type: str) -> str:
        normalized = re.sub(r"\s+", " ", problem.lower()).strip()
        digest = hashlib.sha256(f"{pain_type}|{normalized}".encode("utf-8")).hexdigest()[:16]
        return f"pain-{digest}"
