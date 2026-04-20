import hashlib
import re
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from agent_reliability_doctor import AgentReliabilityDoctor


PAIN_TYPE_TERMS = {
    "human_in_loop": ("captcha", "human", "approval", "verification", "judgment", "login", "review"),
    "loop_break": ("stuck", "loop", "retry", "infinite", "timeout", "tool fail", "same error"),
    "hallucination": ("hallucination", "wrong", "invalid", "drift", "unsupported", "claim"),
    "bad_planning": ("bad plan", "planning", "wrong plan", "inefficient", "inefficiency", "poor plan"),
    "tool_failure": ("tool error", "tool failure", "tool failed", "schema mismatch", "bad tool"),
    "execution_failure": ("execution", "run failed", "test failed", "selector", "crash"),
    "self_correction_failure": ("self-correction", "self correction", "same mistake", "does not learn"),
    "memory": ("memory", "context", "session", "remember", "forgot", "preference"),
    "payment": ("payment", "wallet", "x402", "escrow", "metamask", "usdc", "eth", "tx_hash"),
    "compute_auth": ("quota", "rate limit", "token", "model", "inference", "auth", "provider"),
    "mcp_integration": ("mcp", "tool schema", "resource uri", "api", "json-rpc", "tool call"),
    "repo_issue_help": ("github", "issue", "pull request", "repro", "pr plan"),
    "self_improvement": ("self-improvement", "self improvement", "guardrail", "checklist", "playbook", "evaluation"),
}


SOLUTION_PATTERNS: Dict[str, Dict[str, Any]] = {
    "loop_break": {
        "title": "Retry Circuit Breaker",
        "diagnosis": (
            "This is a retry-loop reliability failure. Stop autonomous retries, preserve the last known-good "
            "state, fingerprint the failing tool/error pair, and resume only after new evidence or approval."
        ),
        "playbook": [
            "Pause retries after the same tool/error pair repeats or a timeout returns no new evidence.",
            "Snapshot LAST_GOOD_STATE, FAILING_TOOL, ERROR, retry_count, and the intended next action.",
            "Choose one recovery lane: retry with changed input, switch fallback tool, or ask for one missing fact.",
            "Persist the loop fingerprint so the same failure opens a rescue plan instead of repeating.",
        ],
        "guardrail": {
            "id": "retry_circuit_breaker",
            "trigger": "same tool/error pair repeats, retry_count exceeds budget, or timeout returns no new evidence",
            "rule": "pause execution, return a rescue plan, and require changed evidence before another retry",
            "fallback": "resume from the last known-good state or switch to a bounded fallback lane",
        },
        "required_input": "`LAST_GOOD_STATE=<state>`, `FAILING_TOOL=<name>`, or `ERROR=<message>`.",
        "acceptance": [
            "The retry loop has one safe pause point.",
            "The next retry requires changed evidence, a fallback lane, or explicit approval.",
            "The failing tool/error fingerprint is reusable as memory.",
        ],
        "memory_upgrade": "store retry budget, failure fingerprint, and recovery lane as a reusable loop-break rule",
    },
    "compute_auth": {
        "title": "Provider Fallback Ladder",
        "diagnosis": (
            "This is a compute/auth reliability issue. Separate provider reachability, token scope, quota/rate-limit, "
            "model access, and fallback routing instead of treating them as one generic model failure."
        ),
        "playbook": [
            "Probe provider reachability without secrets.",
            "Check token presence and scope without exposing token values.",
            "Classify failure as auth, quota/rate-limit, model access, network, or malformed request.",
            "Route to the smallest available fallback model/provider and record the degraded capability.",
        ],
        "guardrail": {
            "id": "compute_fallback_ladder",
            "trigger": "provider call fails, quota is exhausted, auth fails, or model access is denied",
            "rule": "diagnose provider state first, then choose a bounded fallback before asking the agent to retry blindly",
            "fallback": "use a smaller local model, hosted fallback, cached plan, or human unlock request",
        },
        "required_input": "`PROVIDER_STATUS=<message>`, `TOKEN_SCOPE=<scope>`, or `ERROR=<status/code>`.",
        "acceptance": [
            "Token/auth, quota/rate-limit, model access, and fallback lane are separated.",
            "No secret token values are requested or echoed.",
            "The agent gets one runnable fallback or one explicit unlock.",
        ],
        "memory_upgrade": "store provider failure class, working fallback lane, and safe token-scope checklist",
    },
    "human_in_loop": {
        "title": "Do-Now Send-Back Contract",
        "diagnosis": (
            "This is a human-unlock bottleneck. The agent needs a legitimate do-now/send-back/done-when contract, "
            "not an attempted bypass of approval, CAPTCHA, login, invite, or judgment gates."
        ),
        "playbook": [
            "Name the smallest legitimate human action required.",
            "Specify exactly what the human should send back without secrets.",
            "Define done-when evidence so the agent can resume deterministically.",
            "Keep public posting, private access, and operator actions behind explicit approval.",
        ],
        "guardrail": {
            "id": "hitl_unlock_contract",
            "trigger": "workflow requires login, CAPTCHA, private invite, approval, or human judgment",
            "rule": "request only the smallest legitimate human unlock and wait for done-when evidence",
            "fallback": "return a draft-only plan if the unlock is unavailable",
        },
        "required_input": "`APPROVAL_GRANTED=<scope>`, `BLOCKED_BY=<reason>`, or `HUMAN_UNLOCK_DONE=<result>`.",
        "acceptance": [
            "The human gate has do-now, send-back, and done-when fields.",
            "No access control is bypassed.",
            "The agent can resume from explicit non-secret evidence.",
        ],
        "memory_upgrade": "store a reusable human-unlock template for the same gate class",
    },
    "hallucination": {
        "title": "Verifier-First Step",
        "diagnosis": (
            "This is a verification failure. Add a checker before the next external action so unsupported claims, "
            "stale context, or malformed assumptions cannot compound through the workflow."
        ),
        "playbook": [
            "Extract the claim or assumption that controls the next action.",
            "Bind it to one evidence source: tool output, file, URL, test, or user-provided fact.",
            "Reject or downgrade the action when the evidence is missing.",
            "Record the verifier as a reusable precondition.",
        ],
        "guardrail": {
            "id": "verifier_first",
            "trigger": "a claim controls an external action, code edit, payment, or public message",
            "rule": "verify the claim against evidence before acting",
            "fallback": "return the missing-evidence question instead of acting",
        },
        "required_input": "`CLAIM=<claim>`, `EVIDENCE_URL=<url>`, or `TOOL_OUTPUT=<excerpt>`.",
        "acceptance": [
            "Every risky claim has one evidence source.",
            "The next action is blocked or downgraded if evidence is missing.",
            "The verifier rule is reusable.",
        ],
        "memory_upgrade": "store the verifier rule and evidence requirement for future similar actions",
    },
    "bad_planning": {
        "title": "Plan Critic Gate",
        "diagnosis": (
            "This is a planning reliability failure. The agent should not execute the plan until a critic checks "
            "goal fit, missing evidence, step order, tool choice, cost, and approval boundaries."
        ),
        "playbook": [
            "Extract the plan, objective, constraints, and assumed facts.",
            "Score the plan against goal fit, evidence, dependency order, cost, and safety boundary.",
            "Revise the plan once with the smallest better next action.",
            "Persist the critic rubric when this plan class recurs.",
        ],
        "guardrail": {
            "id": "plan_critic_gate",
            "trigger": "a plan has many steps, external side effects, high cost, or unclear evidence",
            "rule": "run a critic rubric before execution and block plans that miss evidence or approval scope",
            "fallback": "return the smallest verified next action instead of executing the whole plan",
        },
        "required_input": "`PLAN=<steps>`, `GOAL=<goal>`, `CONSTRAINTS=<limits>`, or `EVIDENCE=<source>`.",
        "acceptance": [
            "The plan has a critic score and one revised next action.",
            "Missing evidence or approval scope blocks execution.",
            "The plan order and tool choices are explicit.",
        ],
        "memory_upgrade": "store the plan critic rubric and the revised next-action template",
    },
    "tool_failure": {
        "title": "Tool Failure Triage",
        "diagnosis": (
            "This is a tool-call reliability failure. Capture the failing tool, arguments, schema, timeout, "
            "response shape, and error class before any retry."
        ),
        "playbook": [
            "Record failing tool, input arguments, response shape, timeout, and error.",
            "Separate schema mismatch, unavailable tool, bad state, permission issue, and transient failure.",
            "Create one fixture or dry run that reproduces the failure.",
            "Retry only after changing input, contract, fallback tool, or approval scope.",
        ],
        "guardrail": {
            "id": "tool_failure_triage",
            "trigger": "tool call fails, returns malformed output, times out, or violates schema",
            "rule": "triage tool contract before retrying or switching tools",
            "fallback": "return a fixture-backed tool contract or ask for the missing argument",
        },
        "required_input": "`TOOL=<name>`, `ARGS=<json>`, `ERROR=<message>`, or `EXPECTED_SCHEMA=<json>`.",
        "acceptance": [
            "Tool failure class is named.",
            "A fixture or dry-run path exists.",
            "The next retry changes evidence, input, contract, or fallback lane.",
        ],
        "memory_upgrade": "store failing tool fingerprint, schema fix, and retry policy",
    },
    "execution_failure": {
        "title": "Execution Healer Harness",
        "diagnosis": (
            "This is an execution failure. The agent needs a runtime healer that captures the failing step, "
            "reproduces it safely, patches the contract or selector, and verifies before live retry."
        ),
        "playbook": [
            "Identify the exact failing runtime step and the last known-good state.",
            "Create a fixture or dry-run reproduction before live retry.",
            "Patch selector, contract, timeout, state setup, or fallback lane.",
            "Run one verifier and store the failure as a regression check.",
        ],
        "guardrail": {
            "id": "execution_healer_harness",
            "trigger": "test, browser, workflow, script, or runtime step fails repeatedly",
            "rule": "reproduce and verify in a fixture before live retry",
            "fallback": "stop execution and return the smallest reproducible failure package",
        },
        "required_input": "`FAILING_STEP=<step>`, `LAST_GOOD_STATE=<state>`, `ERROR=<message>`, or `TRACE=<log>`.",
        "acceptance": [
            "The failing step is reproducible.",
            "The live retry happens only after a verifier passes.",
            "A regression check is stored.",
        ],
        "memory_upgrade": "store execution failure fixture, patch, verifier, and resume point",
    },
    "memory": {
        "title": "Durable Lesson Object",
        "diagnosis": (
            "This is a memory continuity issue. The agent needs to persist the missing fact, decision, constraint, "
            "or outcome as a durable object before retrying the workflow."
        ),
        "playbook": [
            "Classify the missing memory as fact, decision, constraint, preference, or outcome.",
            "Write one minimal memory object with source and expiry if relevant.",
            "Use the memory as a precondition before the next retry.",
            "Avoid storing secrets or unnecessary personal data.",
        ],
        "guardrail": {
            "id": "durable_lesson_object",
            "trigger": "the same decision, constraint, or outcome is forgotten across turns or sessions",
            "rule": "persist the minimal non-secret memory object before continuing",
            "fallback": "ask for the missing fact again and mark it as not-yet-persistent",
        },
        "required_input": "`MEMORY_TYPE=<fact|decision|constraint|outcome>`, `MEMORY_VALUE=<non-secret value>`.",
        "acceptance": [
            "The missing memory is represented as one non-secret object.",
            "The next run can reuse it without asking again.",
            "A source or expiry is present when the memory may become stale.",
        ],
        "memory_upgrade": "store the solved blocker as fact/decision/constraint/outcome memory",
    },
    "payment": {
        "title": "Idempotent Payment Resume",
        "diagnosis": (
            "This is a payment-state reliability issue. The agent needs an idempotent invoice, tx/signature "
            "verification, duplicate-use protection, and a safe resume point after payment."
        ),
        "playbook": [
            "Create one payment reference tied to one task id.",
            "Verify recipient, chain, amount, payer when provided, and duplicate-use status.",
            "Resume work only from a verified payment or explicit manual-review state.",
            "Record spend, stake, and delivery outcome back onto the task ledger.",
        ],
        "guardrail": {
            "id": "idempotent_payment_resume",
            "trigger": "wallet, tx_hash, x402, invoice, or escrow state changes",
            "rule": "verify payment state before delivery and make retries idempotent",
            "fallback": "manual payment review without releasing paid work",
        },
        "required_input": "`TX_HASH=<0x...>`, `CHAIN_ID=<id>`, or `PAYMENT_ERROR=<message>`.",
        "acceptance": [
            "Payment verification is idempotent.",
            "Duplicate tx/signature reuse is rejected.",
            "Work resumes only from verified or manually reviewed state.",
        ],
        "memory_upgrade": "store payment failure class and safe resume rule",
    },
    "mcp_integration": {
        "title": "Tool Contract Harness",
        "diagnosis": (
            "This is an MCP/API integration issue. The agent needs a strict tool contract: schema, resource URI, "
            "timeout, error shape, and expected response before wiring it into an autonomous loop."
        ),
        "playbook": [
            "Define the tool name, input schema, resource URI, timeout, and expected JSON response.",
            "Specify retryable versus terminal errors.",
            "Add one dry-run or fixture path before live calls.",
            "Publish the contract as a machine-readable reply.",
        ],
        "guardrail": {
            "id": "tool_contract_harness",
            "trigger": "new MCP/API tool is called without schema, timeout, or error contract",
            "rule": "require contract fields before autonomous tool use",
            "fallback": "return a draft tool contract instead of calling the tool",
        },
        "required_input": "`TOOL_SCHEMA=<json>`, `RESOURCE_URI=<uri>`, or `EXPECTED_RESPONSE=<shape>`.",
        "acceptance": [
            "Tool schema, resource URI, timeout, and error shape are named.",
            "The agent can test the integration with a dry run or fixture.",
            "Retryable and terminal errors are separate.",
        ],
        "memory_upgrade": "store reusable tool contract and error policy",
    },
    "repo_issue_help": {
        "title": "Draft-Only Repro Plan",
        "diagnosis": (
            "This is public repo issue help. Nomad should turn the visible issue into a draft-only diagnosis, "
            "minimal repro checklist, and PR/comment plan without posting publicly unless explicit approval is attached."
        ),
        "playbook": [
            "Summarize the public symptom and the smallest visible evidence.",
            "Draft a minimal repro or failing-check outline that maintainers can verify.",
            "Separate safe private drafting from public comments, PRs, and maintainer-facing outreach.",
            "Offer one concrete patch or config direction only if the evidence supports it.",
        ],
        "guardrail": {
            "id": "draft_only_repro_plan",
            "trigger": "public issue, PR, or maintainer-facing repo help is requested",
            "rule": "prepare diagnosis and repro plan privately; require explicit approval before public posting",
            "fallback": "return a private draft plus missing-evidence checklist",
        },
        "required_input": "`ISSUE_URL=<url>`, `ERROR=<message>`, or `REPRO_STEPS=<steps>`.",
        "acceptance": [
            "The public issue has a minimal repro or missing-evidence checklist.",
            "No public comment or PR is posted without explicit approval.",
            "The draft names one concrete safe next step.",
        ],
        "memory_upgrade": "store the solved repo issue as a reusable repro/comment/PR-plan template",
    },
    "self_improvement": {
        "title": "Solved Blocker Pack",
        "diagnosis": (
            "This is a self-improvement packaging task. Convert one solved blocker into a reusable guardrail, "
            "checklist, memory object, and verification step so future agents can avoid the same failure."
        ),
        "playbook": [
            "Name the blocker and the smallest fix that worked.",
            "Turn the fix into one guardrail trigger and one checklist.",
            "Add a verification step that proves the guardrail is active.",
            "Mark which parts are safe to reuse without human approval.",
        ],
        "guardrail": {
            "id": "solved_blocker_pack",
            "trigger": "a blocker is solved once and likely to recur",
            "rule": "package the lesson as guardrail plus checklist before closing the task",
            "fallback": "record the blocker as a memory candidate if no code change is possible",
        },
        "required_input": "`SOLVED_BLOCKER=<summary>`, `FIX_THAT_WORKED=<step>`, or `VERIFY_WITH=<test>`.",
        "acceptance": [
            "The solved blocker has a reusable guardrail trigger.",
            "There is a verification step.",
            "The lesson can be used by Nomad and returned to other agents.",
        ],
        "memory_upgrade": "store solved blocker, guardrail trigger, checklist, and verification test",
    },
    "self_correction_failure": {
        "title": "Reflection Memory Loop",
        "diagnosis": (
            "This is a self-correction failure. The agent recognizes or repeats a mistake but does not convert "
            "the lesson into a critic rubric, guardrail, memory object, and verification step."
        ),
        "playbook": [
            "Name the repeated mistake and the signal that should have caught it.",
            "Create a critic rubric that blocks the mistake before the next external action.",
            "Store the lesson as non-secret memory with a retrieval condition.",
            "Add a verifier that proves the correction is active.",
        ],
        "guardrail": {
            "id": "reflection_memory_loop",
            "trigger": "same mistake recurs or a critique does not change future behavior",
            "rule": "turn critique into memory plus verifier before closing the task",
            "fallback": "pause and return a solved-blocker pack instead of continuing",
        },
        "required_input": "`MISTAKE=<summary>`, `CRITIQUE=<what failed>`, or `VERIFY_WITH=<test>`.",
        "acceptance": [
            "The repeated mistake has a critic rubric.",
            "A memory object and retrieval condition exist.",
            "A verifier proves the correction is active.",
        ],
        "memory_upgrade": "store mistake, critic rubric, retrieval condition, and verifier",
    },
}


ALIASES = {
    "wallet_payment": "payment",
    "custom": "self_improvement",
}


def normalize_pain_type(service_type: str = "", problem: str = "") -> str:
    key = str(service_type or "").strip().lower().replace("-", "_")
    if key in SOLUTION_PATTERNS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    lowered = str(problem or "").lower()
    scores = {
        pain_type: sum(1 for term in terms if term in lowered)
        for pain_type, terms in PAIN_TYPE_TERMS.items()
    }
    best_type, best_score = max(scores.items(), key=lambda item: (item[1], item[0]))
    if best_score > 0:
        return ALIASES.get(best_type, best_type)
    return "self_improvement"


def solution_pattern_for(service_type: str = "", problem: str = "") -> Dict[str, Any]:
    pain_type = normalize_pain_type(service_type=service_type, problem=problem)
    return SOLUTION_PATTERNS[pain_type]


class AgentPainSolver:
    """Turn recurring agent pain into reusable solutions Nomad can also apply to itself."""

    def __init__(self, reliability_doctor: Optional[AgentReliabilityDoctor] = None) -> None:
        self.reliability_doctor = reliability_doctor or AgentReliabilityDoctor()

    def solve(
        self,
        problem: str,
        service_type: str = "",
        source: str = "manual",
        evidence: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cleaned_problem = " ".join(str(problem or "").split())
        pain_type = normalize_pain_type(service_type=service_type, problem=cleaned_problem)
        pattern = SOLUTION_PATTERNS[pain_type]
        solution_id = self._solution_id(cleaned_problem, pain_type)
        self_apply = self._nomad_self_apply(
            pain_type=pain_type,
            pattern=pattern,
            context=context or {},
        )
        doctor_report = self.reliability_doctor.diagnose(
            problem=cleaned_problem,
            service_type=pain_type,
            source=source,
            evidence=evidence,
            solution_pattern=pattern,
        )
        solution = {
            "schema": "nomad.agent_solution.v1",
            "solution_id": solution_id,
            "pain_type": pain_type,
            "source": source,
            "title": pattern["title"],
            "diagnosis": pattern["diagnosis"],
            "reusable_pattern": " -> ".join(pattern["playbook"][:3]),
            "playbook": pattern["playbook"],
            "guardrail": pattern["guardrail"],
            "required_input": pattern["required_input"],
            "acceptance_criteria": pattern["acceptance"],
            "memory_upgrade": pattern["memory_upgrade"],
            "reliability_doctor": doctor_report["doctor_role"],
            "reliability_loop": doctor_report["reliability_loop"],
            "critic_rubric": doctor_report["critic_rubric"],
            "fix_contract": doctor_report["fix_contract"],
            "healing_memory": doctor_report["healing_memory"],
            "nomad_self_apply": self_apply,
            "service_upgrade": {
                "artifact": "nomad.rescue_plan.v1",
                "offer": f"Return the {pattern['title']} as a rescue plan, then package it as memory after consent.",
            },
            "evidence": evidence or self._matched_evidence(cleaned_problem, pain_type),
        }
        return {
            "mode": "agent_pain_solution",
            "deal_found": False,
            "ok": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "problem": cleaned_problem,
            "solution": solution,
            "reliability_doctor": doctor_report,
            "analysis": (
                f"Nomad solved this as {pain_type} using the {pattern['title']} pattern and produced "
                f"a reusable guardrail plus {doctor_report['doctor_role']['title']} loop it can apply to itself."
            ),
        }

    def solve_from_context(
        self,
        objective: str,
        context: Dict[str, Any],
        lead_scout: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        candidates = self._observed_problem_candidates(
            objective=objective,
            context=context,
            lead_scout=lead_scout or {},
        )
        if not candidates:
            candidates = [
                {
                    "source": "default",
                    "pain_type": "self_improvement",
                    "problem": "Package solved agent blockers into reusable guardrails Nomad can apply to itself.",
                    "score": 10,
                    "evidence": ["default_self_improvement_loop"],
                }
            ]
        candidates.sort(key=lambda item: (-float(item.get("score") or 0), str(item.get("source") or "")))
        selected = candidates[0]
        solved = self.solve(
            problem=selected.get("problem", ""),
            service_type=selected.get("pain_type", ""),
            source=selected.get("source", "context"),
            evidence=selected.get("evidence") or [],
            context=context,
        )
        solution = solved["solution"]
        return {
            "mode": "agent_pain_solver",
            "schema": "nomad.agent_pain_solver.v1",
            "generated_at": solved["generated_at"],
            "objective": objective,
            "observed_problem_count": len(candidates),
            "selected_problem": selected,
            "solution": solution,
            "backlog": candidates[:5],
            "next_nomad_action": self._next_nomad_action(solution),
            "analysis": (
                f"Selected {selected.get('pain_type')} from {selected.get('source')} and produced "
                f"{solution.get('title')} for both requester-facing help and Nomad's own runtime."
            ),
        }

    def _observed_problem_candidates(
        self,
        objective: str,
        context: Dict[str, Any],
        lead_scout: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        objective_text = str(objective or "").strip()
        if objective_text:
            pain_type = normalize_pain_type(problem=objective_text)
            candidates.append(
                self._candidate(
                    source="objective",
                    pain_type=pain_type,
                    problem=objective_text,
                    score=55,
                    evidence=self._matched_evidence(objective_text, pain_type),
                )
            )

        active_lead = lead_scout.get("active_lead") or {}
        if active_lead:
            lead_problem = " ".join(
                str(item or "").strip()
                for item in (
                    active_lead.get("title") or active_lead.get("name"),
                    active_lead.get("pain") or active_lead.get("pain_signal"),
                    active_lead.get("first_help_action"),
                )
                if str(item or "").strip()
            )
            if lead_problem:
                candidates.append(
                    self._candidate(
                        source="active_public_lead",
                        pain_type=str(active_lead.get("recommended_service_type") or ""),
                        problem=lead_problem,
                        score=90 if active_lead.get("monetizable_now") else 76,
                        evidence=[
                            str(item.get("term") or item.get("evidence") or item)
                            for item in (active_lead.get("pain_evidence") or [])[:4]
                        ],
                    )
                )

        for session in context.get("recent_direct_agent_sessions") or []:
            problem = " ".join(
                str(item or "").strip()
                for item in (
                    session.get("requester_agent"),
                    session.get("last_pain_type"),
                    session.get("last_diagnosis"),
                    session.get("status"),
                )
                if str(item or "").strip()
            )
            if problem:
                candidates.append(
                    self._candidate(
                        source="direct_agent_session",
                        pain_type=str(session.get("last_pain_type") or ""),
                        problem=problem,
                        score=72,
                        evidence=[str(session.get("session_id") or ""), str(session.get("last_task_id") or "")],
                    )
                )

        for task in context.get("recent_service_tasks") or []:
            service_type = str(task.get("service_type") or "")
            problem = (
                f"service_type={service_type} status={task.get('status') or 'unknown'} "
                f"budget={task.get('budget_native') or ''}"
            )
            score = 68 if task.get("status") in {"paid", "draft_ready"} else 50
            candidates.append(
                self._candidate(
                    source="service_task",
                    pain_type=service_type,
                    problem=problem,
                    score=score,
                    evidence=[str(task.get("task_id") or ""), str(task.get("status") or "")],
                )
            )

        resources = context.get("resources") or {}
        brain_count = int(resources.get("brain_count") or 0)
        ollama = resources.get("ollama") or {}
        if brain_count < 2 or not ollama.get("api_reachable"):
            candidates.append(
                self._candidate(
                    source="nomad_runtime",
                    pain_type="compute_auth",
                    problem=(
                        f"Nomad runtime has brain_count={brain_count}, "
                        f"ollama_reachable={bool(ollama.get('api_reachable'))}, "
                        f"ollama_models={ollama.get('model_count', 0)}."
                    ),
                    score=70 if brain_count < 2 else 58,
                    evidence=["Nomad can use the same fallback ladder it returns to other agents."],
                )
            )

        return candidates

    def _candidate(
        self,
        source: str,
        pain_type: str,
        problem: str,
        score: float,
        evidence: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized = normalize_pain_type(service_type=pain_type, problem=problem)
        return {
            "source": source,
            "pain_type": normalized,
            "problem": problem,
            "score": round(float(score), 2),
            "evidence": [item for item in (evidence or []) if item],
        }

    def _nomad_self_apply(
        self,
        pain_type: str,
        pattern: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        already_used = [
            "direct_agent.free_mini_diagnosis",
            "agent_service.build_rescue_plan",
            "self_improvement.agent_pain_solver",
        ]
        resources = context.get("resources") or {}
        status = "actionable_now"
        if pain_type == "compute_auth" and int(resources.get("brain_count") or 0) < 2:
            status = "actionable_now_with_human_unlock_optional"
        return {
            "status": status,
            "why_it_helps_nomad": (
                f"Nomad can apply {pattern['guardrail']['id']} to its own self-improvement, service, "
                "and direct-agent responses before asking another agent to do the same."
            ),
            "local_actions": [
                {
                    "type": "agent_pain_solution",
                    "category": pain_type,
                    "title": f"Use {pattern['title']} in Nomad's own agent workflows.",
                    "reason": pattern["guardrail"]["rule"],
                    "requires_human": False,
                }
            ],
            "verification": [
                "A direct-agent reply includes nomad.rescue_plan.v1.",
                "A self-improvement cycle includes agent_pain_solver.next_nomad_action.",
                "The matching service work product includes the same guardrail id.",
            ],
            "already_used_in": already_used,
        }

    def _matched_evidence(self, problem: str, pain_type: str) -> List[str]:
        lowered = str(problem or "").lower()
        terms = PAIN_TYPE_TERMS.get(pain_type, ())
        evidence = []
        for term in terms:
            if term in lowered:
                evidence.append(f"matched_term:{term}")
        if not evidence:
            tokens = re.findall(r"[a-z0-9_-]{4,}", lowered)
            evidence.extend(f"context_token:{token}" for token in tokens[:3])
        return evidence[:5]

    @staticmethod
    def _solution_id(problem: str, pain_type: str) -> str:
        digest = hashlib.sha256(f"{pain_type}|{problem}".encode("utf-8")).hexdigest()[:12]
        return f"sol-{digest}"

    @staticmethod
    def _next_nomad_action(solution: Dict[str, Any]) -> str:
        guardrail = solution.get("guardrail") or {}
        return (
            f"Apply {guardrail.get('id', solution.get('title', 'the solution'))}: "
            f"{guardrail.get('rule', 'turn the solved blocker into a reusable guardrail')}."
        )
