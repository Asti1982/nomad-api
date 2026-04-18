import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from settings import get_chain_config
from treasury_agent import TreasuryAgent
from x402_payment import X402PaymentAdapter


load_dotenv()

ROOT = Path(__file__).resolve().parent
DEFAULT_TASK_STORE = ROOT / "nomad_service_tasks.json"


SERVICE_TYPES = {
    "human_in_loop": {
        "title": "Human-in-the-loop unlock design",
        "summary": "Turn blocked approvals, credentials, CAPTCHA/login gates, or unclear handoffs into concrete human unlock tasks.",
    },
    "compute_auth": {
        "title": "Compute/auth diagnosis",
        "summary": "Diagnose model provider, token, quota, inference, rate-limit, or fallback-brain failures.",
    },
    "loop_break": {
        "title": "Loop break rescue",
        "summary": "Stop infinite retries, isolate failing tool calls, and return the agent to a known-good state.",
    },
    "hallucination": {
        "title": "Hallucination guardrail",
        "summary": "Add verifier steps and context checks before compounding errors spread through a workflow.",
    },
    "memory": {
        "title": "Session memory repair",
        "summary": "Persist the missing decision, constraint or outcome that the agent keeps forgetting.",
    },
    "payment": {
        "title": "Payment and x402 repair",
        "summary": "Diagnose wallet, invoice, x402, escrow or payment-verification blockers.",
    },
    "mcp_integration": {
        "title": "MCP/API integration plan",
        "summary": "Draft an MCP or REST integration contract that another agent can call reliably.",
    },
    "repo_issue_help": {
        "title": "Public repo issue help",
        "summary": "Draft a public-issue response, repro checklist, or PR plan without posting automatically.",
    },
    "wallet_payment": {
        "title": "Wallet/payment flow",
        "summary": "Design a small wallet payment or verification path for agent-to-agent services.",
    },
    "custom": {
        "title": "Custom agent infrastructure task",
        "summary": "A bounded custom task for AI-agent infrastructure friction.",
    },
}


class AgentServiceDesk:
    """Public service intake for agents that can pay Nomad's wallet."""

    def __init__(
        self,
        path: Optional[Path] = None,
        treasury: Optional[TreasuryAgent] = None,
        x402: Optional[X402PaymentAdapter] = None,
    ) -> None:
        load_dotenv()
        self.path = path or DEFAULT_TASK_STORE
        self.treasury = treasury or TreasuryAgent()
        self.x402 = x402 or X402PaymentAdapter()
        self.chain = get_chain_config()
        self.min_native = float(os.getenv("NOMAD_SERVICE_MIN_NATIVE", "0.01"))
        self.treasury_stake_bps = int(os.getenv("NOMAD_SERVICE_TREASURY_STAKE_BPS", "3000"))
        requested_solver_bps = os.getenv("NOMAD_SERVICE_SOLVER_SPEND_BPS")
        self.solver_spend_bps = (
            int(requested_solver_bps)
            if requested_solver_bps
            else max(0, 10000 - self.treasury_stake_bps)
        )
        if self.treasury_stake_bps + self.solver_spend_bps > 10000:
            self.solver_spend_bps = max(0, 10000 - self.treasury_stake_bps)
        self.staking_target = (
            os.getenv("NOMAD_TREASURY_STAKING_TARGET")
            or "metamask_eth_staking"
        ).strip()
        self.accept_unverified = (
            os.getenv("NOMAD_ACCEPT_UNVERIFIED_SERVICE_PAYMENTS", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.require_payment = (
            os.getenv("NOMAD_REQUIRE_SERVICE_PAYMENT", "true").strip().lower()
            in {"1", "true", "yes", "on"}
        )

    def service_catalog(self) -> Dict[str, Any]:
        wallet = self.treasury.get_wallet_summary()
        configured_wallet = wallet.get("address") or ""
        return {
            "mode": "agent_service_catalog",
            "deal_found": False,
            "service": "Nomad public agent service desk",
            "generated_at": datetime.now(UTC).isoformat(),
            "public_api_url": (os.getenv("NOMAD_PUBLIC_API_URL") or "").rstrip("/"),
            "wallet": {
                "address": configured_wallet,
                "configured": bool(configured_wallet),
                "network": self.chain.name,
                "chain_id": self.chain.chain_id,
                "native_symbol": self.chain.native_symbol,
            },
            "pricing": {
                "minimum_native": self.min_native,
                "requires_payment": self.require_payment,
                "payment_token": self.chain.native_symbol,
                "verification": "native transfer to Nomad wallet by tx_hash",
                "x402": {
                    "enabled": self.x402.enabled,
                    "facilitator_url": self.x402.facilitator_url,
                    "asset_address": self.x402.asset_address,
                    "asset_symbol": self.x402.asset_symbol,
                    "asset_decimals": self.x402.asset_decimals,
                    "network": self._x402_network(),
                    "verify_endpoint": f"{(os.getenv('NOMAD_PUBLIC_API_URL') or '').rstrip('/')}/tasks/x402-verify"
                    if os.getenv("NOMAD_PUBLIC_API_URL")
                    else "/tasks/x402-verify",
                    "retry_header": "PAYMENT-SIGNATURE",
                },
                "allocation": {
                    "treasury_stake_bps": self.treasury_stake_bps,
                    "solver_spend_bps": self.solver_spend_bps,
                    "staking_target": self.staking_target,
                    "staking_execution": "requires explicit MetaMask/operator approval",
                },
            },
            "buyer_discovery": {
                "target": "agents with public buyer-intent signals for human-in-the-loop decisions or infrastructure pain help",
                "agent_contact_without_prior_approval": True,
                "human_contact_requires_approval": True,
            },
            "service_types": SERVICE_TYPES,
            "contact_paths": {
                "http": {
                    "descriptor": "GET /agent",
                    "catalog": "GET /service",
                    "create_task": "POST /tasks",
                    "verify_payment": "POST /tasks/verify",
                    "verify_x402_payment": "POST /tasks/x402-verify",
                    "work_task": "POST /tasks/work",
                    "staking_checklist": "POST /tasks/staking",
                    "record_stake": "POST /tasks/stake",
                    "record_spend": "POST /tasks/spend",
                    "close_task": "POST /tasks/close",
                    "queue_agent_contact": "POST /agent-contacts",
                    "send_agent_contact": "POST /agent-contacts/send",
                },
                "mcp_tools": [
                    "nomad_service_catalog",
                    "nomad_service_request",
                    "nomad_service_verify",
                    "nomad_service_work",
                    "nomad_service_staking_checklist",
                    "nomad_service_record_stake",
                    "nomad_service_record_spend",
                    "nomad_agent_contact",
                    "nomad_agent_contact_send",
                ],
                "cli": [
                    "python main.py --cli service",
                    "python main.py --cli service-request <problem>",
                    "python main.py --cli service-verify <task_id> <tx_hash>",
                    "python main.py --cli service-staking <task_id>",
                    "python main.py --cli service-stake <task_id> <stake_tx_hash>",
                    "python main.py --cli service-spend <task_id> <amount>",
                    "python main.py --cli agent-contact <endpoint> <problem>",
                ],
            },
            "safety_contract": self.safety_contract(),
            "analysis": (
                "Public agents can request bounded infrastructure help, receive a wallet invoice, "
                "pay Nomad's configured wallet, then submit tx_hash for verification. Nomad drafts "
                "and plans help by default; public posting, DMs, private access, or bypassing human gates "
                "still require explicit approval from the affected party. Public machine-readable agent endpoints "
                "may be contacted directly when the request is bounded, relevant and rate-limited."
            ),
        }

    def create_task(
        self,
        problem: str,
        requester_agent: str = "",
        requester_wallet: str = "",
        service_type: str = "custom",
        budget_native: Optional[float] = None,
        callback_url: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cleaned_problem = self._clean(problem)
        if not cleaned_problem:
            return {
                "mode": "agent_service_request",
                "deal_found": False,
                "ok": False,
                "error": "problem_required",
                "message": "A service request needs a concrete problem statement.",
            }

        normalized_type = self._normalize_service_type(service_type, cleaned_problem)
        parsed_budget = self._optional_float(budget_native)
        requested_amount = max(
            self.min_native,
            parsed_budget if parsed_budget is not None else self.min_native,
        )
        now = datetime.now(UTC).isoformat()
        task_id = self._task_id(cleaned_problem, requester_agent, requester_wallet, now)
        payment_request = self._payment_request(
            task_id=task_id,
            amount_native=requested_amount,
            requester_wallet=requester_wallet,
            service_type=normalized_type,
        )
        task = {
            "task_id": task_id,
            "created_at": now,
            "updated_at": now,
            "requester_agent": self._clean(requester_agent),
            "requester_wallet": self._clean(requester_wallet),
            "callback_url": self._clean(callback_url),
            "service_type": normalized_type,
            "problem": cleaned_problem,
            "budget_native": requested_amount,
            "metadata": metadata or {},
            "status": "awaiting_payment" if self.require_payment else "accepted",
            "payment": payment_request,
            "payment_allocation": self._payment_allocation(
                amount_native=requested_amount,
                payment_verified=not self.require_payment,
            ),
            "treasury": {
                "staking_status": (
                    "ready_for_metamask_approval"
                    if not self.require_payment
                    else "planned_after_payment_verification"
                ),
                "staking_target": self.staking_target,
                "stake_tx_hash": "",
                "stake_amount_native": 0.0,
            },
            "solver_budget": {
                "spend_status": (
                    "available_for_problem_solving"
                    if not self.require_payment
                    else "planned_after_payment_verification"
                ),
                "spent_native": 0.0,
                "remaining_native": 0.0,
                "spend_notes": [],
            },
            "ledger": [
                self._ledger_event(
                    event="task_created",
                    message="Service task created and wallet invoice issued.",
                    amount_native=requested_amount,
                )
            ],
            "work_product": None,
            "safety_contract": self.safety_contract(),
        }
        self._refresh_allocation_status(task)
        state = self._load()
        state["tasks"][task_id] = task
        self._save(state)
        return self._task_response(task, created=True)

    def verify_payment(
        self,
        task_id: str,
        tx_hash: str,
        requester_wallet: str = "",
    ) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        tx_hash = self._clean(tx_hash)
        if not self._looks_like_tx_hash(tx_hash):
            task["payment"]["verification"] = {
                "ok": False,
                "status": "invalid_tx_hash",
                "message": "Send a 0x-prefixed transaction hash.",
            }
            self._store_task(task)
            return self._task_response(task)

        duplicate = self._tx_used_by_other_task(task_id=task_id, tx_hash=tx_hash)
        if duplicate:
            task["payment"]["verification"] = {
                "ok": False,
                "status": "duplicate_tx_hash",
                "message": f"Transaction is already attached to task {duplicate}.",
            }
            self._store_task(task)
            return self._task_response(task)

        verification = self._verify_native_transfer(
            tx_hash=tx_hash,
            expected_amount=float(task["payment"]["amount_native"]),
            expected_from=requester_wallet or task.get("requester_wallet", ""),
        )
        task["payment"]["tx_hash"] = tx_hash
        task["payment"]["verification"] = verification
        observed_amount = verification.get("observed_amount_native") or task["payment"]["amount_native"]
        task["payment_allocation"] = self._payment_allocation(
            amount_native=float(observed_amount),
            payment_verified=bool(verification.get("ok")),
        )
        task["updated_at"] = datetime.now(UTC).isoformat()
        if verification.get("ok"):
            task["status"] = "paid"
            self._refresh_allocation_status(task)
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="payment_verified",
                    message="Incoming wallet payment verified.",
                    tx_hash=tx_hash,
                    amount_native=float(observed_amount),
                )
            )
        elif self.accept_unverified:
            task["status"] = "manual_payment_review"
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="payment_manual_review",
                    message=verification.get("message", "Payment needs manual review."),
                    tx_hash=tx_hash,
                )
            )
        else:
            task["status"] = "payment_unverified"
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="payment_unverified",
                    message=verification.get("message", "Payment could not be verified."),
                    tx_hash=tx_hash,
                )
            )
        self._store_task(task)
        return self._task_response(task)

    def verify_x402_payment(
        self,
        task_id: str,
        payment_signature: str,
        requester_wallet: str = "",
    ) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        signature = self._clean(payment_signature)
        fingerprint = self.x402.fingerprint(signature) if signature else ""
        duplicate = self._x402_signature_used_by_other_task(task_id=task_id, fingerprint=fingerprint)
        if duplicate:
            verification = {
                "ok": False,
                "status": "duplicate_x402_signature",
                "message": f"x402 payment signature is already attached to task {duplicate}.",
            }
        else:
            requirements = (((task.get("payment") or {}).get("x402") or {}).get("paymentRequirements") or {})
            verification = self.x402.verify_signature(
                payment_signature=signature,
                payment_requirements=requirements,
            )
        payment = task.setdefault("payment", {})
        x402_state = payment.setdefault("x402", {})
        x402_state["payment_signature_fingerprint"] = fingerprint
        x402_state["verification"] = verification
        payment["verification"] = {
            "ok": bool(verification.get("ok")),
            "status": verification.get("status", "x402_unverified"),
            "message": verification.get("message", ""),
            "method": "x402",
            "payer": verification.get("payer", ""),
        }
        observed_amount = float(payment.get("amount_native") or task.get("budget_native") or self.min_native)
        task["payment_allocation"] = self._payment_allocation(
            amount_native=observed_amount,
            payment_verified=bool(verification.get("ok")),
        )
        task["updated_at"] = datetime.now(UTC).isoformat()
        if verification.get("ok"):
            task["status"] = "paid"
            if requester_wallet and not task.get("requester_wallet"):
                task["requester_wallet"] = requester_wallet
            self._refresh_allocation_status(task)
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="x402_payment_verified",
                    message="x402 payment verified by facilitator.",
                    amount_native=observed_amount,
                )
            )
        elif self.accept_unverified:
            task["status"] = "manual_payment_review"
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="x402_payment_manual_review",
                    message=verification.get("message", "x402 payment needs manual review."),
                )
            )
        else:
            task["status"] = "payment_unverified"
            task.setdefault("ledger", []).append(
                self._ledger_event(
                    event="x402_payment_unverified",
                    message=verification.get("message", "x402 payment could not be verified."),
                )
            )
        self._store_task(task)
        return self._task_response(task)

    def work_task(self, task_id: str, approval: str = "draft_only") -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)

        payment_ok = self._task_can_be_worked(task)
        if not payment_ok:
            task["work_product"] = {
                "status": "blocked",
                "reason": "payment_required",
                "message": (
                    "Nomad will hold this task until payment is verified or the operator disables "
                    "NOMAD_REQUIRE_SERVICE_PAYMENT."
                ),
            }
            self._store_task(task)
            return self._task_response(task)

        work_product = self._build_work_product(task, approval=approval)
        task["work_product"] = work_product
        task["status"] = "draft_ready"
        task["updated_at"] = datetime.now(UTC).isoformat()
        task.setdefault("ledger", []).append(
            self._ledger_event(
                event="draft_ready",
                message="Nomad produced a draft work product for the service task.",
            )
        )
        self._store_task(task)
        return self._task_response(task)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        return self._task_response(task)

    def metamask_staking_checklist(self, task_id: str) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        allocation = task.get("payment_allocation") or {}
        payment = task.get("payment") or {}
        wallet = self.treasury.get_wallet_summary()
        checklist = {
            "mode": "metamask_staking_checklist",
            "deal_found": False,
            "ok": True,
            "task_id": task_id,
            "staking_status": (task.get("treasury") or {}).get("staking_status"),
            "wallet": {
                "address": wallet.get("address") or payment.get("recipient_address", ""),
                "network": self.chain.name,
                "chain_id": self.chain.chain_id,
                "native_symbol": self.chain.native_symbol,
            },
            "planned_stake_native": allocation.get("treasury_stake_native", 0.0),
            "staking_target": allocation.get("staking_target", self.staking_target),
            "operator_steps": allocation.get("operator_steps") or [],
            "record_command": f"/service stake {task_id} <stake_tx_hash>",
            "analysis": (
                "MetaMask staking is prepared as an operator-confirmed treasury action. "
                "Nomad records the plan and tx hash, but does not silently control MetaMask."
            ),
        }
        return checklist

    def record_treasury_stake(
        self,
        task_id: str,
        tx_hash: str = "",
        amount_native: Optional[float] = None,
        note: str = "",
    ) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        tx_hash = self._clean(tx_hash)
        if tx_hash and not self._looks_like_tx_hash(tx_hash):
            return {
                "mode": "agent_service_request",
                "deal_found": False,
                "ok": False,
                "error": "invalid_stake_tx_hash",
                "message": "Stake tx_hash must be a 0x-prefixed transaction hash.",
                "task": task,
            }
        allocation = task.get("payment_allocation") or {}
        amount = (
            float(amount_native)
            if amount_native is not None
            else float(allocation.get("treasury_stake_native") or 0.0)
        )
        treasury = task.setdefault("treasury", {})
        treasury["staking_status"] = "staked_confirmed" if tx_hash else "stake_prepared"
        treasury["staking_target"] = allocation.get("staking_target", self.staking_target)
        treasury["stake_tx_hash"] = tx_hash
        treasury["stake_amount_native"] = round(amount, 8)
        treasury["stake_note"] = self._clean(note)
        task["updated_at"] = datetime.now(UTC).isoformat()
        task.setdefault("ledger", []).append(
            self._ledger_event(
                event="treasury_stake_recorded" if tx_hash else "treasury_stake_prepared",
                message=note or "Treasury stake status recorded.",
                tx_hash=tx_hash,
                amount_native=amount,
            )
        )
        self._store_task(task)
        return self._task_response(task)

    def record_solver_spend(
        self,
        task_id: str,
        amount_native: float,
        note: str,
        tx_hash: str = "",
    ) -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        tx_hash = self._clean(tx_hash)
        if tx_hash and not self._looks_like_tx_hash(tx_hash):
            return {
                "mode": "agent_service_request",
                "deal_found": False,
                "ok": False,
                "error": "invalid_spend_tx_hash",
                "message": "Spend tx_hash must be a 0x-prefixed transaction hash.",
                "task": task,
            }
        amount = max(0.0, float(amount_native))
        solver = task.setdefault("solver_budget", {})
        allocation = task.get("payment_allocation") or {}
        total_budget = float(allocation.get("solver_budget_native") or 0.0)
        spent = round(float(solver.get("spent_native") or 0.0) + amount, 8)
        solver["spent_native"] = spent
        solver["remaining_native"] = round(max(0.0, total_budget - spent), 8)
        solver["spend_status"] = "spent" if solver["remaining_native"] <= 0 else "partially_spent"
        solver.setdefault("spend_notes", []).append(
            {
                "at": datetime.now(UTC).isoformat(),
                "amount_native": round(amount, 8),
                "tx_hash": tx_hash,
                "note": self._clean(note),
            }
        )
        task["updated_at"] = datetime.now(UTC).isoformat()
        task.setdefault("ledger", []).append(
            self._ledger_event(
                event="solver_spend_recorded",
                message=note or "Solver budget spend recorded.",
                tx_hash=tx_hash,
                amount_native=amount,
            )
        )
        self._store_task(task)
        return self._task_response(task)

    def close_task(self, task_id: str, outcome: str = "") -> Dict[str, Any]:
        task = self._get_task(task_id)
        if not task:
            return self._missing_task(task_id)
        task["status"] = "delivered"
        task["outcome"] = self._clean(outcome)
        task["updated_at"] = datetime.now(UTC).isoformat()
        task.setdefault("ledger", []).append(
            self._ledger_event(
                event="task_delivered",
                message=task["outcome"] or "Service task delivered.",
            )
        )
        self._store_task(task)
        return self._task_response(task)

    def safety_contract(self) -> Dict[str, Any]:
        return {
            "default_output": "draft_or_plan",
            "allowed": [
                "triage public or provided problem statements",
                "draft human unlock tasks",
                "draft public comments or PR plans",
                "draft MCP/API integration plans",
                "diagnose token, quota, wallet, and compute fallback issues",
                "contact public machine-readable agent/API/MCP endpoints without prior human approval",
            ],
            "requires_explicit_approval": [
                "posting human-facing public comments",
                "opening human-reviewed pull requests",
                "sending human direct messages or email",
                "accessing private communities or accounts",
                "spending funds or using paid compute beyond the task budget",
                "staking treasury funds through MetaMask",
            ],
            "refused": [
                "bypassing CAPTCHA or access controls",
                "impersonating a human operator",
                "collecting unnecessary secrets",
                "using payment as permission to spam humans or ignore opt-outs",
            ],
        }

    def _build_work_product(self, task: Dict[str, Any], approval: str) -> Dict[str, Any]:
        problem = task.get("problem", "")
        service_type = task.get("service_type", "custom")
        approval = (approval or "draft_only").strip().lower()
        human_unlocks = self._human_unlocks_for_problem(problem)
        agent_actions = self._agent_actions_for_problem(problem, service_type)
        deliverables = [
            "one concise diagnosis",
            "one next action Nomad can do without crossing approval boundaries",
            "one human unlock contract if a human gate remains",
        ]
        if service_type == "mcp_integration":
            deliverables.append("MCP tool/resource shape for the requesting agent")
        if service_type == "wallet_payment":
            deliverables.append("payment verification checklist and failure modes")
        can_execute_public_action = approval in {"comment", "public_comment", "pr", "pull_request"}
        return {
            "status": "draft_ready",
            "approval": approval,
            "can_execute_public_action": can_execute_public_action,
            "diagnosis": self._diagnosis(problem, service_type),
            "agent_actions": agent_actions,
            "human_unlocks": human_unlocks,
            "deliverables": deliverables,
            "draft_response": self._draft_response(task, human_unlocks),
            "payment_allocation": task.get("payment_allocation") or {},
            "blocked_without_approval": self.safety_contract()["requires_explicit_approval"],
        }

    def _diagnosis(self, problem: str, service_type: str) -> str:
        lowered = problem.lower()
        if service_type == "human_in_loop" or any(
            token in lowered for token in ("captcha", "approval", "human", "login")
        ):
            return (
                "This is primarily a human-unlock bottleneck. Nomad should reduce it to "
                "a small do-now/send-back/done-when contract and avoid bypassing the gate."
            )
        if service_type == "compute_auth" or any(
            token in lowered for token in ("quota", "rate limit", "token", "inference", "model")
        ):
            return (
                "This looks like a compute or credential reliability issue. Nomad should verify "
                "the token, provider permission, model access, and fallback lane separately."
            )
        if service_type == "wallet_payment" or "wallet" in lowered or "payment" in lowered:
            return (
                "This needs a verifiable payment boundary: invoice, tx hash, wallet recipient, "
                "minimum amount, duplicate-tx protection, and a manual fallback."
            )
        return (
            "This is a bounded agent-infrastructure task. Nomad should produce a small, "
            "testable plan before doing any external action."
        )

    def _agent_actions_for_problem(self, problem: str, service_type: str) -> List[str]:
        actions = [
            "Create a minimal reproduction or state checklist from the provided facts.",
            "Separate actions Nomad can do from actions that require the requester's human operator.",
            "Return a draft-only response unless explicit approval is attached.",
        ]
        if service_type == "loop_break":
            actions.insert(0, "Pause retries, preserve state, and isolate the first failing tool call.")
        if service_type == "hallucination":
            actions.insert(0, "Add a verifier/checker step before allowing another external action.")
        if service_type == "memory":
            actions.insert(0, "Write the missing durable memory as a fact, decision, or constraint.")
        if service_type == "payment":
            actions.insert(0, "Verify wallet, payment reference, tx hash, and x402 challenge state.")
        if service_type == "compute_auth":
            actions.insert(0, "Probe provider reachability, token presence, quota state, and fallback route.")
        if service_type == "mcp_integration":
            actions.insert(0, "Define tool schema, resource URI, prompt shape, and expected JSON result.")
        if service_type == "wallet_payment":
            actions.insert(0, "Verify the payment tx hash against recipient, value, chain, and duplicate use.")
        return actions

    def _human_unlocks_for_problem(self, problem: str) -> List[Dict[str, Any]]:
        lowered = problem.lower()
        unlocks: List[Dict[str, Any]] = []
        if any(token in lowered for token in ("captcha", "login", "approval", "human")):
            unlocks.append(
                self._unlock(
                    candidate_id="requester-human-unlock",
                    candidate_name="Requester human unlock",
                    short_ask="Ask the requester's human for the smallest approval or login step.",
                    action=(
                        "Have the requester complete only the legitimate login, CAPTCHA, invite, "
                        "or approval step, then send back the resulting non-secret status."
                    ),
                    deliverable=(
                        "`HUMAN_UNLOCK_DONE=<what changed>`, `APPROVAL_GRANTED=<scope>`, "
                        "or `BLOCKED_BY=<reason>`."
                    ),
                )
            )
        if any(token in lowered for token in ("token", "key", "secret", "permission")):
            unlocks.append(
                self._unlock(
                    candidate_id="requester-credential-scope",
                    candidate_name="Requester credential scope",
                    short_ask="Ask for scoped, revocable credential confirmation.",
                    action=(
                        "The requester should confirm which token or permission scope is safe to test, "
                        "without sending unnecessary secrets."
                    ),
                    deliverable="`TOKEN_SCOPE=<scope>`, `PROVIDER_STATUS=<message>`, or `NO_SECRET_NEEDED=true`.",
                )
            )
        if not unlocks:
            unlocks.append(
                self._unlock(
                    candidate_id="requester-next-fact",
                    candidate_name="Requester next fact",
                    short_ask="Ask for one missing fact that makes the task verifiable.",
                    action=(
                        "Send one URL, error message, API response, repo, or workflow state that Nomad can inspect."
                    ),
                    deliverable="`FACT_URL=https://...`, `ERROR=...`, or `REPRO_STEPS=...`.",
                )
            )
        return unlocks[:3]

    def _unlock(
        self,
        candidate_id: str,
        candidate_name: str,
        short_ask: str,
        action: str,
        deliverable: str,
    ) -> Dict[str, Any]:
        return {
            "category": "external_agent_service",
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "role": "requester human unlock",
            "lane_state": "pending",
            "requires_account": False,
            "env_vars": [],
            "short_ask": short_ask,
            "human_action": action,
            "human_deliverable": deliverable,
            "success_criteria": [
                "Nomad can continue without bypassing access controls.",
                "The requester gets one verifiable next step or clear blocker.",
            ],
            "example_response": deliverable.split(",", 1)[0].strip("` ") if deliverable else "DONE",
            "timebox_minutes": 5,
        }

    def _draft_response(
        self,
        task: Dict[str, Any],
        human_unlocks: List[Dict[str, Any]],
    ) -> str:
        service = SERVICE_TYPES.get(task.get("service_type"), SERVICE_TYPES["custom"])
        first_unlock = human_unlocks[0] if human_unlocks else {}
        return (
            f"Nomad can help with {service['title']}. First, I would reduce the problem to "
            f"one verifiable step: {first_unlock.get('short_ask', 'provide one missing fact')}. "
            "I can draft the plan or response now; public actions and private access still need explicit approval."
        )

    def _payment_allocation(
        self,
        amount_native: float,
        payment_verified: bool,
    ) -> Dict[str, Any]:
        treasury_stake = round(amount_native * self.treasury_stake_bps / 10000, 8)
        solver_budget = round(amount_native * self.solver_spend_bps / 10000, 8)
        reserve = round(max(0.0, amount_native - treasury_stake - solver_budget), 8)
        return {
            "amount_native": round(amount_native, 8),
            "native_symbol": self.chain.native_symbol,
            "treasury_stake_bps": self.treasury_stake_bps,
            "solver_spend_bps": self.solver_spend_bps,
            "treasury_stake_native": treasury_stake,
            "solver_budget_native": solver_budget,
            "reserve_native": reserve,
            "staking_target": self.staking_target,
            "payment_verified": payment_verified,
            "treasury_staking_status": (
                "ready_for_metamask_approval"
                if payment_verified and treasury_stake > 0
                else "planned_after_payment_verification"
            ),
            "solver_budget_status": (
                "available_for_problem_solving"
                if payment_verified and solver_budget > 0
                else "planned_after_payment_verification"
            ),
            "operator_steps": [
                "Verify the incoming payment tx_hash first.",
                (
                    f"Stake {treasury_stake} {self.chain.native_symbol} from the MetaMask-controlled "
                    "treasury wallet only after explicit operator approval."
                ),
                (
                    f"Use up to {solver_budget} {self.chain.native_symbol} equivalent for the task's "
                    "compute, tools, or human-unlock support budget."
                ),
                "Record the final spend/stake outcome back on the task before closing it.",
            ],
        }

    def _payment_request(
        self,
        task_id: str,
        amount_native: float,
        requester_wallet: str,
        service_type: str,
    ) -> Dict[str, Any]:
        wallet = self.treasury.get_wallet_summary()
        recipient = wallet.get("address") or ""
        memo = f"NOMAD_TASK:{task_id}"
        data_hex = "0x" + memo.encode("utf-8").hex()
        return {
            "status": "awaiting_payment" if self.require_payment else "not_required",
            "recipient_address": recipient,
            "recipient_configured": bool(recipient),
            "requester_wallet": requester_wallet,
            "network": self.chain.name,
            "chain_id": self.chain.chain_id,
            "amount_native": round(amount_native, 8),
            "native_symbol": self.chain.native_symbol,
            "payment_reference": memo,
            "optional_tx_data": data_hex,
            "x402": self._x402_challenge(
                task_id=task_id,
                amount_native=amount_native,
                recipient=recipient,
                service_type=service_type,
            ),
            "tx_hash": "",
            "verification": None,
        }

    def _x402_challenge(
        self,
        task_id: str,
        amount_native: float,
        recipient: str,
        service_type: str,
    ) -> Dict[str, Any]:
        public_api_url = (os.getenv("NOMAD_PUBLIC_API_URL") or "").rstrip("/")
        resource_url = f"{public_api_url}/x402/paid-help" if public_api_url else "/x402/paid-help"
        return self.x402.build_challenge(
            task_id=task_id,
            amount_native=amount_native,
            pay_to=recipient,
            network_caip2=self._x402_network(),
            resource_url=resource_url,
            description=f"Nomad paid agent help for task {task_id}",
            service_type=service_type,
        )

    def _x402_network(self) -> str:
        return (os.getenv("NOMAD_X402_NETWORK") or f"eip155:{self.chain.chain_id}").strip()

    def _verify_native_transfer(
        self,
        tx_hash: str,
        expected_amount: float,
        expected_from: str,
    ) -> Dict[str, Any]:
        wallet = self.treasury.get_wallet_summary()
        recipient = (wallet.get("address") or "").strip()
        if not recipient:
            return {
                "ok": False,
                "status": "recipient_wallet_missing",
                "message": "Nomad wallet is not configured, so payment cannot be verified.",
            }

        try:
            from web3 import Web3

            w3 = Web3(Web3.HTTPProvider(self.chain.rpc_url))
            tx = w3.eth.get_transaction(tx_hash)
            value_native = float(w3.from_wei(tx.get("value", 0), "ether"))
            to_address = tx.get("to") or ""
            from_address = tx.get("from") or ""
            if to_address.lower() != recipient.lower():
                return {
                    "ok": False,
                    "status": "wrong_recipient",
                    "message": "Transaction recipient does not match Nomad wallet.",
                    "observed_to": to_address,
                }
            if expected_from and from_address.lower() != expected_from.lower():
                return {
                    "ok": False,
                    "status": "wrong_sender",
                    "message": "Transaction sender does not match requester wallet.",
                    "observed_from": from_address,
                }
            if value_native + 1e-12 < expected_amount:
                return {
                    "ok": False,
                    "status": "insufficient_amount",
                    "message": "Transaction value is below the requested task budget.",
                    "observed_amount_native": round(value_native, 8),
                }
            return {
                "ok": True,
                "status": "verified",
                "message": "Native wallet payment verified.",
                "observed_amount_native": round(value_native, 8),
                "observed_from": from_address,
                "observed_to": to_address,
            }
        except Exception as exc:
            return {
                "ok": False,
                "status": "rpc_unavailable_or_tx_missing",
                "message": f"Payment verification failed: {exc}",
            }

    def _refresh_allocation_status(self, task: Dict[str, Any]) -> None:
        allocation = task.get("payment_allocation") or {}
        treasury = task.setdefault("treasury", {})
        solver = task.setdefault("solver_budget", {})
        treasury["staking_target"] = allocation.get("staking_target", self.staking_target)
        if allocation.get("payment_verified"):
            treasury.setdefault("stake_tx_hash", "")
            treasury.setdefault("stake_amount_native", 0.0)
            if treasury.get("staking_status") in {None, "", "planned_after_payment_verification"}:
                treasury["staking_status"] = "ready_for_metamask_approval"
            solver.setdefault("spent_native", 0.0)
            solver.setdefault("spend_notes", [])
            solver["remaining_native"] = round(
                max(
                    0.0,
                    float(allocation.get("solver_budget_native") or 0.0)
                    - float(solver.get("spent_native") or 0.0),
                ),
                8,
            )
            if solver.get("spend_status") in {None, "", "planned_after_payment_verification"}:
                solver["spend_status"] = "available_for_problem_solving"
        else:
            treasury.setdefault("staking_status", "planned_after_payment_verification")
            solver.setdefault("spend_status", "planned_after_payment_verification")
            solver.setdefault("spent_native", 0.0)
            solver.setdefault("remaining_native", 0.0)
            solver.setdefault("spend_notes", [])

    def _ledger_event(
        self,
        event: str,
        message: str,
        tx_hash: str = "",
        amount_native: Optional[float] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "at": datetime.now(UTC).isoformat(),
            "event": event,
            "message": message,
        }
        if tx_hash:
            payload["tx_hash"] = tx_hash
        if amount_native is not None:
            payload["amount_native"] = round(float(amount_native), 8)
            payload["native_symbol"] = self.chain.native_symbol
        return payload

    def _task_response(self, task: Dict[str, Any], created: bool = False) -> Dict[str, Any]:
        return {
            "mode": "agent_service_request",
            "deal_found": False,
            "ok": True,
            "created": created,
            "task": task,
            "analysis": self._analysis(task),
        }

    def _analysis(self, task: Dict[str, Any]) -> str:
        status = task.get("status", "unknown")
        payment = task.get("payment") or {}
        if status == "awaiting_payment":
            return (
                f"Service task {task['task_id']} is ready for payment. Send "
                f"{payment.get('amount_native')} {payment.get('native_symbol')} to "
                f"{payment.get('recipient_address') or 'the configured Nomad wallet'}, then submit tx_hash."
            )
        if status == "paid":
            allocation = task.get("payment_allocation") or {}
            return (
                f"Service task {task['task_id']} is paid and ready for Nomad to work. "
                f"Allocation: {allocation.get('treasury_stake_native')} "
                f"{allocation.get('native_symbol')} planned for MetaMask treasury staking, "
                f"{allocation.get('solver_budget_native')} {allocation.get('native_symbol')} "
                "available for problem solving."
            )
        if status == "draft_ready":
            return f"Service task {task['task_id']} has a draft work product ready."
        if status == "delivered":
            return f"Service task {task['task_id']} is delivered. Outcome: {task.get('outcome') or 'recorded'}."
        if status == "payment_unverified":
            return f"Service task {task['task_id']} has a payment claim that could not be verified."
        return f"Service task {task['task_id']} status: {status}."

    def _task_can_be_worked(self, task: Dict[str, Any]) -> bool:
        if not self.require_payment:
            return True
        verification = ((task.get("payment") or {}).get("verification") or {})
        return bool(verification.get("ok") or task.get("status") == "paid")

    def _normalize_service_type(self, service_type: str, problem: str) -> str:
        key = (service_type or "").strip().lower().replace("-", "_")
        if key in SERVICE_TYPES and key != "custom":
            return key
        lowered = problem.lower()
        if any(token in lowered for token in ("captcha", "login", "approval", "human")):
            return "human_in_loop"
        if any(token in lowered for token in ("quota", "rate limit", "token", "inference", "model")):
            return "compute_auth"
        if "mcp" in lowered or "api" in lowered:
            return "mcp_integration"
        if "wallet" in lowered or "payment" in lowered or "tx_hash" in lowered or "x402" in lowered:
            return "wallet_payment"
        if "github" in lowered or "issue" in lowered or "pull request" in lowered:
            return "repo_issue_help"
        return "custom"

    def _task_id(
        self,
        problem: str,
        requester_agent: str,
        requester_wallet: str,
        created_at: str,
    ) -> str:
        seed = f"{created_at}|{requester_agent}|{requester_wallet}|{problem}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
        return f"svc-{digest}"

    def _looks_like_tx_hash(self, value: str) -> bool:
        return bool(re.fullmatch(r"0x[a-fA-F0-9]{64}", value or ""))

    def _tx_used_by_other_task(self, task_id: str, tx_hash: str) -> str:
        state = self._load()
        for existing_id, task in state.get("tasks", {}).items():
            if existing_id == task_id:
                continue
            payment = task.get("payment") or {}
            if (payment.get("tx_hash") or "").lower() == tx_hash.lower():
                return existing_id
        return ""

    def _x402_signature_used_by_other_task(self, task_id: str, fingerprint: str) -> str:
        if not fingerprint:
            return ""
        state = self._load()
        for existing_id, task in state.get("tasks", {}).items():
            if existing_id == task_id:
                continue
            x402_state = ((task.get("payment") or {}).get("x402") or {})
            if (x402_state.get("payment_signature_fingerprint") or "") == fingerprint:
                return existing_id
        return ""

    def _get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return (self._load().get("tasks") or {}).get(task_id)

    def _store_task(self, task: Dict[str, Any]) -> None:
        state = self._load()
        state["tasks"][task["task_id"]] = task
        self._save(state)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"tasks": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {"tasks": {}}
            payload.setdefault("tasks", {})
            return payload
        except Exception:
            return {"tasks": {}}

    def _save(self, state: Dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _missing_task(self, task_id: str) -> Dict[str, Any]:
        return {
            "mode": "agent_service_request",
            "deal_found": False,
            "ok": False,
            "error": "task_not_found",
            "task_id": task_id,
            "message": "No Nomad service task exists for that task_id.",
        }

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
