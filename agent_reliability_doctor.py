import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional


ROLE_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "reflection_critic": {
        "title": "Reflection/Critic Loop",
        "framework_inspiration": "LangGraph-style reflection loop",
        "best_for": ["hallucination", "bad_planning", "self_correction_failure", "policy_lacuna"],
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
        "title": "Monitor-Diagnoser-Fixer Loop",
        "framework_inspiration": "CrewAI-style role team",
        "best_for": [
            "loop_break",
            "compute_auth",
            "human_in_loop",
            "attribution_clarity",
            "stewardship_gap",
            "chain_deadline_budget",
            "context_propagation_contract",
            "inter_agent_witness",
        ],
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
        "title": "Execution Stabilizer",
        "framework_inspiration": "Playwright/custom runtime stabilization",
        "best_for": [
            "tool_failure",
            "execution_failure",
            "mcp_integration",
            "mcp_production",
            "tool_transport_routing",
            "tool_turn_invariant",
        ],
        "why": "Stabilize failing tool calls, schemas, selectors, timeouts, and runtime steps with fixtures first.",
        "loop": ["observe_failure", "patch_contract", "dry_run", "live_retry_once", "record_fixture"],
        "interventions": [
            "Capture the failing tool, input schema, response shape, timeout, and first error.",
            "Patch the contract or selector in a fixture before touching live execution.",
            "Retry once with changed evidence, never blind repetition.",
            "Store the fixture as a regression guard.",
        ],
    },
    "self_learning_healer": {
        "title": "Memory Synthesizer",
        "framework_inspiration": "Beam-style maintenance-free autonomy pattern",
        "best_for": ["memory", "self_improvement"],
        "why": "Turn repeated incidents into durable memory, guardrails, and self-apply actions.",
        "loop": ["incident", "lesson", "guardrail", "self_apply", "regression_check"],
        "interventions": [
            "Cluster recurring failures by fingerprint and impact.",
            "Convert the solved failure into a durable lesson object.",
            "Attach a guardrail trigger and verification check.",
            "Apply the lesson to Nomad before selling the pattern to another agent.",
        ],
    },
    "trace_healer": {
        "title": "Adaptive Trace Resumer",
        "framework_inspiration": "observability-driven trace recovery system",
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
    "mcp_production": "execution_healer",
    "attribution_clarity": "diagnoser_fixer",
    "branch_economics": "diagnoser_fixer",
    "stewardship_gap": "diagnoser_fixer",
    "policy_lacuna": "reflection_critic",
    "tool_turn_invariant": "diagnoser_fixer",
    "tool_transport_routing": "execution_healer",
    "context_propagation_contract": "diagnoser_fixer",
    "chain_deadline_budget": "diagnoser_fixer",
    "inter_agent_witness": "diagnoser_fixer",
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
    "mcp_production": ("mcp", "is_error", "transport", "gateway", "401", "tool loop", "jsonschema", "safeoutputs"),
    "attribution_clarity": ("false positive", "misclassified", "blame", "root cause", "not the model", "shame"),
    "branch_economics": ("token", "retry", "branch", "budget", "burn", "cost", "ledger"),
    "stewardship_gap": ("supervision", "monitoring", "orphan", "unstaffed", "operator", "on-call", "silent"),
    "policy_lacuna": ("lacuna", "uncovered", "governance", "precedent", "policy", "written rule", "not covered"),
    "tool_turn_invariant": ("parity", "cardinality", "function call", "parallel tool", "session corrupt", "unrecoverable"),
    "tool_transport_routing": ("mcp_call", "function_call", "hosted mcp", "tool not found", "wrong path"),
    "context_propagation_contract": ("tenant", "propagation", "correlation", "delegation", "principal", "envelope"),
    "chain_deadline_budget": ("planner budget", "chain timeout", "turn budget", "deadline", "per-tool", "latency"),
    "inter_agent_witness": (
        "witness",
        "attestation",
        "provenance",
        "handoff",
        "downstream",
        "verifiable",
        "replay",
        "delegation proof",
    ),
    "memory": ("memory", "forgot", "context"),
    "payment": ("payment", "wallet", "x402", "tx_hash"),
    "human_in_loop": ("approval", "human", "captcha", "login"),
    "repo_issue_help": ("github", "issue", "pull request", "repro"),
}


FORBIDDEN_KEY_TERMS = (
    "private_key",
    "seed_phrase",
    "password",
    "credential",
    "api_key",
    "access_token",
    "secret",
)
FORBIDDEN_VALUE_TERMS = (
    "private key",
    "seed phrase",
    "password:",
    "credential:",
    "bearer ",
    "secret=",
    "sk-",
    "ghp_",
)


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit]


def _clean_id(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_.:/#-]+", "_", text)
    return text[:180].strip("_.:/#-") or fallback


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "accept", "accepted"}:
        return True
    if text in {"0", "false", "no", "n", "off", "reject", "rejected"}:
        return False
    return default


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _digest(value: Any, length: int = 32) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _u(base_url: str, path: str) -> str:
    root = (base_url or "").strip().rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    return f"{root}{p}" if root else p


def _contains_forbidden(payload: Any) -> bool:
    def walk(value: Any, *, key: str = "") -> bool:
        k = str(key or "").strip().lower()
        if k and any(term in k for term in FORBIDDEN_KEY_TERMS):
            return True
        if isinstance(value, dict):
            return any(walk(v, key=str(k2)) for k2, v in value.items())
        if isinstance(value, list):
            return any(walk(item) for item in value)
        text = str(value or "").strip().lower()
        return any(term in text for term in FORBIDDEN_VALUE_TERMS)

    return walk(payload)


def build_reliability_doctor_surface(*, base_url: str = "") -> Dict[str, Any]:
    root = (base_url or "").strip().rstrip("/")
    return {
        "ok": True,
        "schema": "nomad.agent_reliability_doctor_surface.v1",
        "generated_at": _iso_now(),
        "public_base_url": root,
        "purpose": "Turn secret-free CI, deploy, tool, rate-limit, and agent-loop failures into repair diagnostics and optional verified return-compute obligations.",
        "machine_native_loop": [
            "secret_free_failure_digest",
            "diagnosis",
            "solution_proof_digest",
            "work_exchange_offer",
            "optional_compute_obligation",
            "return_compute_worker",
            "verified_return_work_receipt",
        ],
        "accepted_inputs": {
            "required_one_of": ["problem", "message", "log_digest", "workflow_url", "repo_url"],
            "optional": ["service_type", "requester_id", "repository", "workflow_url", "run_id", "accepted_compute_barter_terms"],
            "secret_policy": "do_not_send_tokens_keys_passwords_private_logs",
        },
        "routes": {
            "surface": _u(root, "/.well-known/nomad-agent-reliability-doctor.json"),
            "intake": _u(root, "/swarm/reliability-doctor/intake"),
            "human_entry": _u(root, "/agent-reliability-doctor"),
            "work_exchange": _u(root, "/.well-known/nomad-work-exchange.json"),
            "work_exchange_onboarding": _u(root, "/.well-known/nomad-work-exchange-onboarding.json"),
        },
        "downloads": {
            "github_action": _u(root, "/downloads/nomad_reliability_doctor_action.yml"),
            "work_exchange_dockerfile": _u(root, "/downloads/nomad_work_exchange_worker.Dockerfile"),
            "work_exchange_worker_py": _u(root, "/downloads/nomad_work_exchange_worker.py"),
            "windows_worker_installer": _u(root, "/downloads/install_nomad_work_exchange_worker.bat"),
        },
        "agent_onramps": [
            {
                "id": "github_actions_ci_failure",
                "trigger": "workflow_dispatch_or_failed_workflow_run",
                "artifact": _u(root, "/downloads/nomad_reliability_doctor_action.yml"),
                "side_effect_scope": "secret_free_http_intake_only",
            },
            {
                "id": "docker_return_compute",
                "trigger": "obligation_id_present",
                "artifact": _u(root, "/downloads/nomad_work_exchange_worker.Dockerfile"),
                "side_effect_scope": "bounded_return_compute_worker",
            },
        ],
        "copy_paste": {
            "intake": (
                f"curl -s -X POST {_u(root, '/swarm/reliability-doctor/intake')} "
                "-H \"Content-Type: application/json\" "
                "-d \"{\\\"requester_id\\\":\\\"agent.example\\\",\\\"problem\\\":\\\"CI failed without secrets\\\",\\\"service_type\\\":\\\"execution_failure\\\"}\""
            ),
            "docker_return_compute": (
                f"curl -L -o nomad_work_exchange_worker.Dockerfile {_u(root, '/downloads/nomad_work_exchange_worker.Dockerfile')} && "
                "docker build -t nomad-work-exchange-worker -f nomad_work_exchange_worker.Dockerfile . && "
                "docker run --rm -e NOMAD_WORK_EXCHANGE_OBLIGATION_ID=OBLIGATION_ID_HERE nomad-work-exchange-worker"
            ),
        },
        "machine_instruction": "post_secret_free_intake; if returned obligation_id exists run return_compute_worker_until_balance_zero",
    }


def build_reliability_doctor_intake(
    payload: Dict[str, Any],
    *,
    base_url: str = "",
    doctor: Optional["AgentReliabilityDoctor"] = None,
) -> Dict[str, Any]:
    body = _dict(payload)
    if _contains_forbidden(body):
        return {
            "ok": False,
            "schema": "nomad.agent_reliability_doctor_intake_error.v1",
            "accepted": False,
            "error": "secret_shaped_payload",
            "message": "Reliability Doctor intake accepts public digests and secret-free excerpts only.",
            "generated_at": _iso_now(),
        }
    source = _clean_id(body.get("source") or body.get("ci_provider") or body.get("source_tag"), fallback="public_intake")
    repo = _text(body.get("repo_url") or body.get("repository") or body.get("work_url"), 260)
    workflow_url = _text(body.get("workflow_url") or body.get("run_url") or body.get("ci_url"), 260)
    log_digest = _text(body.get("log_digest") or body.get("trace_digest") or body.get("failure_digest"), 220)
    problem = _text(body.get("problem") or body.get("message") or body.get("log_excerpt") or "", 900)
    if not problem:
        problem = _text(" ".join(item for item in [repo, workflow_url, log_digest] if item), 900)
    if not problem:
        return {
            "ok": False,
            "schema": "nomad.agent_reliability_doctor_intake_error.v1",
            "accepted": False,
            "error": "missing_problem_signal",
            "message": "Send problem, message, log_digest, workflow_url, or repo_url.",
            "generated_at": _iso_now(),
        }
    requester_seed = body.get("requester_id") or body.get("agent_id") or repo or workflow_url or source
    requester_id = _clean_id(requester_seed, fallback=f"intake-{_digest(problem, 12)}")
    service_type = _clean_id(body.get("service_type") or body.get("type") or body.get("failure_type"), fallback="")
    evidence = [item for item in [repo, workflow_url, log_digest] if item]
    if isinstance(body.get("evidence"), list):
        evidence.extend(_text(item, 260) for item in body["evidence"][:5])
    doc = doctor or AgentReliabilityDoctor()
    diagnosis = doc.diagnose(
        problem=problem,
        service_type=service_type,
        source=source,
        evidence=evidence or None,
    )
    public_facts = {
        "requester_id": requester_id,
        "source": source,
        "repo_url": repo,
        "workflow_url": workflow_url,
        "log_digest": log_digest,
        "diagnosis_id": diagnosis.get("diagnosis_id"),
        "pain_type": diagnosis.get("pain_type"),
        "doctor_role": _dict(diagnosis.get("doctor_role")).get("id"),
    }
    solution_proof_digest = f"sha256:{_digest({'diagnosis': diagnosis, 'facts': public_facts}, length=64)}"
    solution_value = round(max(1.0, min(_num(body.get("solution_value_credits"), 10.0), 50.0)), 4)
    max_runtime_hours = round(max(0.25, min(_num(body.get("max_runtime_hours"), 6.0), 24.0)), 4)
    accepted_compute_barter = _truthy(body.get("accepted_compute_barter_terms") or body.get("compute_barter_accepted"))
    work_exchange_offer_payload = {
        "requester_id": requester_id,
        "solution_class": "agent_reliability_doctor",
        "solution_value_credits": solution_value,
        "return_multiplier": body.get("return_multiplier") or 1.3,
        "max_runtime_hours": max_runtime_hours,
        "capabilities": ["github_actions", "docker", "python", "return_compute"],
    }
    free_solution_payload = {
        **work_exchange_offer_payload,
        "solution_proof_digest": solution_proof_digest,
        "verifier_trace_digest": f"sha256:{_digest({'rubric': diagnosis.get('critic_rubric'), 'facts': public_facts}, length=64)}",
        "test_digest": f"sha256:{_digest({'loop': diagnosis.get('reliability_loop'), 'contract': diagnosis.get('fix_contract')}, length=64)}",
        "accepted_compute_barter_terms": accepted_compute_barter,
        "side_effect_scope": "sandboxed_worker_only",
    }
    return {
        "ok": True,
        "schema": "nomad.agent_reliability_doctor_intake.v1",
        "accepted": True,
        "generated_at": _iso_now(),
        "intake_id": f"nomad-doctor-intake-{_digest(public_facts, 24)}",
        "requester_id": requester_id,
        "source": source,
        "public_facts": public_facts,
        "diagnosis": diagnosis,
        "solution_proof_digest": solution_proof_digest,
        "accepted_compute_barter_terms": accepted_compute_barter,
        "work_exchange_offer_payload": work_exchange_offer_payload,
        "free_solution_payload": free_solution_payload,
        "next": {
            "work_exchange_offer": _u(base_url, "/swarm/work-exchange/offers"),
            "free_solution": _u(base_url, "/swarm/work-exchange/free-solution"),
            "return_worker": _u(base_url, "/downloads/nomad_work_exchange_worker.py"),
            "dockerfile": _u(base_url, "/downloads/nomad_work_exchange_worker.Dockerfile"),
            "github_action": _u(base_url, "/downloads/nomad_reliability_doctor_action.yml"),
        },
        "machine_instruction": "if_offer_accepted_show_terms; if_obligation_id_returned_run_worker_until_balance_zero",
    }


class AgentReliabilityDoctor:
    """Diagnose agent failures into bounded reliability roles Nomad can reuse without human allegory."""

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
            f"{report['schema']} loop with critic, intervention, verifier, and memory steps."
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
                "block_if_missing": pain_type
                in {
                    "loop_break",
                    "tool_failure",
                    "execution_failure",
                    "mcp_production",
                    "attribution_clarity",
                    "branch_economics",
                    "stewardship_gap",
                    "policy_lacuna",
                    "tool_turn_invariant",
                    "tool_transport_routing",
                    "context_propagation_contract",
                    "chain_deadline_budget",
                    "inter_agent_witness",
                },
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
