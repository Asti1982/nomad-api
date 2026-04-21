import argparse
import json
import sys
from typing import Any, Dict, Iterable, Optional

from nomad_autopilot import NomadAutopilot
from workflow import NomadAgent
from self_development import SelfDevelopmentJournal


def _compact_text(result: Dict[str, Any]) -> str:
    mode = result.get("mode", "result")
    if mode == "self_audit":
        lines = [f"Nomad self audit: {result.get('profile', {}).get('label', 'unknown profile')}"]
        for row in result.get("current_stack") or []:
            current = row.get("current") or {}
            recommended = row.get("recommended") or {}
            status = "aligned" if row.get("aligned") else "upgrade"
            lines.append(
                f"{row.get('category')}: {current.get('name', 'not set')} -> "
                f"{recommended.get('name', 'unknown')} [{status}]"
            )
        upgrades = result.get("upgrades") or []
        if upgrades:
            lines.append("Next improvements")
            lines.extend(f"- {item['category']}: switch to {item['recommended']}" for item in upgrades)
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(lines)

    if mode == "nomad_system_status":
        os_info = result.get("os") or {}
        resources = result.get("resources") or {}
        compute_lanes = result.get("compute_lanes") or {}
        tasks = result.get("tasks") or {}
        lines = [
            "Nomad system status",
            f"Uptime: {result.get('uptime', 'unknown')}",
            f"Platform: {os_info.get('platform', 'unknown')}",
            f"CPU: {resources.get('cpu_count', 0)} cores",
            f"RAM: {resources.get('memory_gb', 0):.2f} GB",
            "",
            "Compute Lanes:",
            f"  Local Ollama: {'[ACTIVE]' if compute_lanes.get('local', {}).get('ollama') else '[INACTIVE]'}",
            f"  Local llama.cpp: {'[ACTIVE]' if compute_lanes.get('local', {}).get('llama_cpp') else '[INACTIVE]'}",
            f"  GitHub Models: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('github_models') else '[INACTIVE]'}",
            f"  Hugging Face: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('huggingface') else '[INACTIVE]'}",
            f"  xAI Grok: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('xai_grok') else '[INACTIVE]'}",
            f"  Modal: {'[ACTIVE]' if (compute_lanes.get('hosted', {}).get('modal') if isinstance(compute_lanes.get('hosted', {}).get('modal'), bool) else (compute_lanes.get('hosted', {}).get('modal') or {}).get('available')) else '[INACTIVE]'}",
            f"  Lambda Labs: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('lambda_labs') else '[INACTIVE]'}",
            f"  RunPod: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('runpod') else '[INACTIVE]'}",
            "",
            "Tasks:",
            f"  Total: {tasks.get('total', 0)}",
            f"  Paid/Pending: {tasks.get('paid', 0)}",
            f"  Awaiting Payment: {tasks.get('awaiting_payment', 0)}",
            f"  Completed: {tasks.get('completed', 0)}",
        ]
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    if mode == "nomad_autopilot":
        service = result.get("service") or {}
        outreach = result.get("outreach") or {}
        lead_conversion = result.get("lead_conversion") or {}
        reply_conversion = result.get("reply_conversion") or {}
        campaign = outreach.get("campaign") or {}
        stats = campaign.get("stats") or {}
        conversion_stats = lead_conversion.get("stats") or {}
        lines = [
            "Nomad autopilot",
            f"Objective: {result.get('objective', '')}",
            f"Worked paid tasks: {len(service.get('worked_task_ids') or [])}",
            f"Draft-ready tasks: {len(service.get('draft_ready_task_ids') or [])}",
            f"Awaiting payment: {len(service.get('awaiting_payment_task_ids') or [])}",
            f"Lead conversions: {sum(int(value) for value in conversion_stats.values()) if conversion_stats else 0}",
            f"A2A replies converted: {len(reply_conversion.get('created_task_ids') or [])}",
            f"Outreach queued: {stats.get('queued', 0)}",
            f"Outreach sent: {stats.get('sent', 0)}",
        ]
        quota = result.get("daily_quota") or {}
        if quota:
            lines.append(
                "Daily A2A quota: "
                f"prepared {quota.get('prepared_count', 0)}/{quota.get('target', 0)}, "
                f"sent {quota.get('sent_count', 0)}/{quota.get('target', 0)}"
            )
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(lines)

    if mode == "autopilot_idle":
        decision = result.get("decision") or {}
        lines = [
            "Nomad autopilot idle",
            f"Reason: {decision.get('reason', 'waiting')}",
            f"Next check: {result.get('next_check_seconds', decision.get('next_check_seconds', 0))} seconds",
        ]
        active_lanes = decision.get("active_compute_lanes") or []
        if active_lanes:
            lines.append(f"Active compute: {', '.join(active_lanes)}")
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(lines)

    if mode == "nomad_addon_scan":
        stats = result.get("stats") or {}
        lines = [
            "Nomad addons",
            f"Source: {result.get('source_dir', '')}",
            f"Discovered: {stats.get('discovered', 0)}",
            f"Safe active adapters: {stats.get('active_safe_adapter', 0)}",
            f"Needs review: {stats.get('needs_human_review', 0)}",
        ]
        for addon in (result.get("addons") or [])[:5]:
            lines.append(
                f"- {addon.get('name')} [{addon.get('status')}] "
                f"source={addon.get('manifest_path')}"
            )
        quantum = result.get("quantum_tokens") or {}
        best_unlock = quantum.get("best_next_quantum_unlock") or {}
        if best_unlock:
            lines.append(
                f"Best quantum unlock: {best_unlock.get('provider')} via {best_unlock.get('telegram_command')}"
            )
        if result.get("secret_warnings"):
            lines.append("Secret warning: plaintext token-like values found in Nomadds; rotate/remove them.")
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(lines)

    if mode == "nomad_quantum_tokens":
        selected = result.get("selected_strategy") or {}
        lines = [
            "Nomad quantum tokens",
            f"Objective: {result.get('objective', '')}",
            f"Selected: {selected.get('title', selected.get('strategy_id', 'none'))}",
            f"Tokens: {len(result.get('tokens') or [])}",
            result.get("claim_boundary", ""),
        ]
        backend = result.get("selected_backend") or (result.get("backend_plan") or {}).get("selected_backend") or {}
        if backend:
            lines.append(
                f"Backend: {backend.get('provider', backend.get('backend_id', 'unknown'))} "
                f"[{backend.get('status', 'unknown')}]"
            )
        local_simulation = result.get("local_quantum_simulation") or (result.get("backend_plan") or {}).get("local_simulation") or {}
        if local_simulation.get("counts"):
            lines.append(f"Local simulation counts: {local_simulation['counts']}")
        hpc = result.get("proposal_backed_hpc") or []
        if hpc:
            first_hpc = hpc[0]
            lines.append(
                f"HPC path: {first_hpc.get('provider')} [{first_hpc.get('status')}]"
            )
        for token in (result.get("tokens") or [])[:3]:
            lines.append(f"- {token.get('qtoken_id')}: {token.get('title')} score={token.get('score')}")
        best_unlock = result.get("best_next_quantum_unlock") or {}
        if best_unlock:
            lines.append(
                f"Best quantum unlock: {best_unlock.get('provider')} via {best_unlock.get('telegram_command')}"
            )
        if result.get("human_unlocks"):
            lines.append("Human unlock available for real quantum provider execution.")
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "codebuddy_scout":
        status = result.get("status") or {}
        runner = result.get("review_runner") or {}
        lines = [
            "Nomad CodeBuddy scout",
            f"Role: {result.get('recommended_role', 'self_development_reviewer')}",
            f"Enabled: {status.get('enabled', False)}",
            f"Automation ready: {status.get('automation_ready', False)}",
            f"CLI available: {status.get('cli_available', False)}",
            f"Route: {status.get('route', 'unknown')}",
            f"Runner: {runner.get('command', '')}",
            status.get("next_action", ""),
        ]
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "codebuddy_review":
        data_release = result.get("data_release") or {}
        lines = [
            "Nomad CodeBuddy review",
            f"OK: {result.get('ok', False)}",
            f"Issue: {result.get('issue') or 'none'}",
            f"Data release approved: {data_release.get('approved', False)}",
            f"Diff chars: {data_release.get('diff_char_count', 0)}",
            result.get("message", ""),
        ]
        if result.get("review"):
            lines.append("Review")
            lines.append(str(result["review"]))
        elif data_release.get("files"):
            lines.append(f"Files: {', '.join(data_release['files'][:8])}")
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "render_scout":
        status = result.get("status") or {}
        verification = status.get("verification") or {}
        selected = result.get("selected_service") or {}
        lines = [
            "Nomad Render scout",
            f"API key configured: {status.get('api_key_configured', False)}",
            f"Deploy enabled: {status.get('deploy_enabled', False)}",
            f"Desired domain: {status.get('desired_domain', '')}",
            f"Verification OK: {verification.get('ok', False)}",
            f"Service count: {verification.get('service_count', 0)}",
            f"Selected service: {selected.get('name') or selected.get('id') or 'none'}",
            status.get("next_action", ""),
        ]
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "agent_collaboration":
        charter = result.get("charter") or {}
        permission = charter.get("permission") or {}
        lines = [
            "Nomad agent collaboration",
            f"Enabled: {charter.get('enabled', False)}",
            f"Public home: {charter.get('public_home', '')}",
            f"Ask help: {permission.get('ask_other_agents_for_help', False)}",
            f"Accept help: {permission.get('accept_help_from_other_agents', False)}",
            f"Learn from replies: {permission.get('learn_from_public_agent_replies', False)}",
        ]
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "codex_task":
        return str(result.get("text") or result.get("analysis") or "")

    if result.get("analysis"):
        return str(result["analysis"])
    if result.get("message"):
        return str(result["message"])
    return json.dumps(result, indent=2, ensure_ascii=False)


def _print_result(result: Dict[str, Any], as_json: bool) -> None:
    text = json.dumps(result, indent=2, ensure_ascii=False) if as_json else _compact_text(result)
    try:
        print(text)
    except UnicodeEncodeError:
        safe_text = text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8",
            errors="replace",
        )
        print(safe_text)


def build_query(args: argparse.Namespace) -> str:
    command = args.command
    profile_suffix = f" for {args.profile}" if getattr(args, "profile", None) else ""

    if command == "status":
        return "/status"
    if command == "best":
        return f"/best{profile_suffix}"
    if command == "self":
        return f"/self{profile_suffix}"
    if command == "compute":
        return f"/compute{profile_suffix}"
    if command == "addons":
        return "/addons"
    if command == "quantum":
        objective = " ".join(args.objective).strip()
        return f"/quantum {objective}".strip()
    if command == "codebuddy-review":
        objective = " ".join(args.objective).strip()
        base = f" base={args.base}" if args.base else ""
        head = f" head={args.head}" if args.head else ""
        approval = " approval=share_diff" if args.approval else ""
        paths = "".join(f" path={path}" for path in (args.path or []))
        return f"/codebuddy-review{base}{head}{approval}{paths} {objective}".strip()
    if command == "render":
        return "/render"
    if command == "collaboration":
        return "/collaboration"
    if command == "unlock":
        category = args.category or "best"
        return f"/unlock {category}{profile_suffix}"
    if command == "scout":
        return f"/scout {args.category}{profile_suffix}"
    if command == "leads":
        query = " ".join(args.query).strip()
        return f"/leads {query}".strip()
    if command == "convert-leads":
        query = " ".join(args.query).strip()
        send = f" send={str(bool(args.send)).lower()}"
        approval = f" approval={args.approval}" if args.approval else ""
        limit = f" limit={args.limit}" if args.limit else ""
        budget = f" budget={args.budget}" if args.budget is not None else ""
        return f"/convert-leads{send}{approval}{limit}{budget} {query}".strip()
    if command == "lead-conversions":
        status = f" status={','.join(args.status)}" if args.status else ""
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/lead-conversions{status}{limit}".strip()
    if command == "productize":
        query = " ".join(args.query).strip()
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/productize{limit} {query}".strip()
    if command == "products":
        status = f" status={','.join(args.status)}" if args.status else ""
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/products{status}{limit}".strip()
    if command == "solve-pain":
        problem = " ".join(args.problem).strip()
        service_type = f" type={args.service_type}" if args.service_type else ""
        return f"/solve-pain{service_type} {problem}".strip()
    if command == "doctor":
        problem = " ".join(args.problem).strip()
        service_type = f" type={args.service_type}" if args.service_type else ""
        return f"/doctor{service_type} {problem}".strip()
    if command == "guardrails":
        text = " ".join(args.text).strip()
        action = f" action={args.action}" if args.action else ""
        approval = f" approval={args.approval}" if args.approval else ""
        return f"/guardrails{action}{approval} {text}".strip()
    if command == "service":
        return "/service"
    if command == "service-request":
        problem = " ".join(args.problem).strip()
        return f"/service request {problem}".strip()
    if command == "service-verify":
        return f"/service verify {args.task_id} {args.tx_hash}"
    if command == "service-x402-verify":
        return f"/service x402-verify {args.task_id} signature={args.payment_signature}"
    if command == "service-work":
        approval = f" approval={args.approval}" if args.approval else ""
        return f"/service work {args.task_id}{approval}"
    if command == "service-staking":
        return f"/service staking {args.task_id}"
    if command == "service-stake":
        tx_hash = f" {args.tx_hash}" if args.tx_hash else ""
        amount = f" amount={args.amount}" if args.amount is not None else ""
        note = f" note={args.note}" if args.note else ""
        return f"/service stake {args.task_id}{tx_hash}{amount}{note}"
    if command == "service-spend":
        tx_hash = f" tx_hash={args.tx_hash}" if args.tx_hash else ""
        note = f" note={args.note}" if args.note else ""
        return f"/service spend {args.task_id} amount={args.amount}{tx_hash}{note}"
    if command == "service-close":
        outcome = " ".join(args.outcome).strip()
        return f"/service close {args.task_id} {outcome}".strip()
    if command == "agent-contact":
        budget = f" budget={args.budget}" if args.budget is not None else ""
        return f"/agent-contact endpoint={args.endpoint} type={args.service_type}{budget} {' '.join(args.problem)}".strip()
    if command == "agent-contact-send":
        return f"/agent-contact send {args.contact_id}"
    if command == "agent-contact-poll":
        return f"/agent-contact poll {args.contact_id}"
    if command == "agent-card":
        return "/agent-card"
    if command == "direct":
        message = " ".join(args.message).strip()
        agent = f" agent={args.agent}" if args.agent else ""
        endpoint = f" endpoint={args.endpoint}" if args.endpoint else ""
        wallet = f" wallet={args.wallet}" if args.wallet else ""
        budget = f" budget={args.budget}" if args.budget is not None else ""
        return f"/direct{agent}{endpoint}{wallet}{budget} {message}".strip()
    if command == "discover-agent":
        return f"/discover-agent {args.base_url}"
    if command == "cold-outreach":
        discover = " discover" if args.discover else ""
        send = " send" if args.send else ""
        limit = f" limit={args.limit}" if args.limit else ""
        budget = f" budget={args.budget}" if args.budget is not None else ""
        query = f" query={args.query}" if args.query else ""
        targets = " ".join(args.targets)
        return f"/cold-outreach{discover}{send}{limit}{budget}{query} {targets}".strip()
    if command == "cycle":
        objective = " ".join(args.objective).strip()
        return f"/cycle {objective}{profile_suffix}".strip()
    if command == "ask":
        return " ".join(args.query).strip()
    if command == "self-status":
        return ""
    if command == "codex-task":
        return ""
    raise ValueError(f"Unsupported command: {command}")


def run_once(argv: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    parser = build_parser()
    raw_argv = list(argv) if argv is not None else None
    json_after_subcommand = False
    if raw_argv is not None and "--json" in raw_argv:
        json_after_subcommand = True
        raw_argv = [item for item in raw_argv if item != "--json"]
    args = parser.parse_args(raw_argv)
    if json_after_subcommand:
        args.json = True
    if args.command == "autopilot":
        autopilot = NomadAutopilot()
        result = autopilot.run_forever(
            cycles=args.cycles,
            interval_seconds=args.interval,
            objective=" ".join(args.objective).strip(),
            profile_id=args.profile,
            outreach_limit=args.outreach_limit,
            outreach_query=args.query,
            send_outreach=args.send_outreach,
            conversion_limit=args.conversion_limit,
            conversion_query=args.conversion_query,
            send_a2a=args.send_a2a,
            daily_lead_target=args.daily_lead_target,
            service_limit=args.service_limit,
            service_approval=args.service_approval,
            serve_api=args.serve_api,
            self_schedule=args.self_schedule,
        )
    else:
        agent = NomadAgent()
        if args.command == "self-status":
            journal = SelfDevelopmentJournal()
            result = {
                "mode": "self_development_status",
                "deal_found": False,
                "state": journal.load(),
                "text": journal.status_text(),
            }
        elif args.command == "codex-task":
            journal = SelfDevelopmentJournal()
            result = {
                "mode": "codex_task",
                "deal_found": False,
                "text": journal.codex_task_prompt(),
            }
        else:
            query = build_query(args)
            result = agent.run(query)
    _print_result(result, as_json=args.json)
    return result


def run_shell(as_json: bool = False) -> None:
    agent = NomadAgent()
    print("--- Nomad CLI-First Control Surface ---")
    print("Try /self, /compute, /unlock, /cycle <objective>, or exit.")
    while True:
        try:
            query = input("nomad> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if query.lower() in {"exit", "quit", ":q"}:
            return
        if not query:
            continue
        _print_result(agent.run(query), as_json=as_json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nomad",
        description="CLI-first control surface for Nomad.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON output.")
    parser.add_argument("--profile", default="ai_first", help="Nomad profile id, default ai_first.")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    subparsers.add_parser("status", help="Show Nomad system status (uptime, compute, tasks).")
    subparsers.add_parser("best", help="Show the recommended AI-first stack.")
    subparsers.add_parser("self", help="Run Nomad self audit.")
    subparsers.add_parser("compute", help="Run compute audit.")
    subparsers.add_parser("addons", help="Scan Nomadds for safe addon manifests.")
    quantum = subparsers.add_parser("quantum", help="Generate quantum-inspired self-improvement tokens.")
    quantum.add_argument("objective", nargs="*")
    codebuddy_review = subparsers.add_parser("codebuddy-review", help="Run an explicit CodeBuddy diff-only review.")
    codebuddy_review.add_argument("objective", nargs="*")
    codebuddy_review.add_argument("--base", default="", help="Optional git base ref for diff review.")
    codebuddy_review.add_argument("--head", default="", help="Optional git head ref for diff review.")
    codebuddy_review.add_argument("--path", action="append", default=[], help="Limit the reviewed git diff to this repo path. Repeatable.")
    codebuddy_review.add_argument(
        "--approval",
        action="store_true",
        help="Approve sending the redacted git diff to CodeBuddy for this run.",
    )
    subparsers.add_parser("render", help="Verify Render hosting access and show Nomad public API deployment steps.")
    subparsers.add_parser("collaboration", help="Show Nomad's outward AI-agent collaboration charter.")
    subparsers.add_parser("self-status", help="Show persistent self-development state.")
    subparsers.add_parser("codex-task", help="Render the next Nomad self-development task for Codex.")

    unlock = subparsers.add_parser("unlock", help="Generate a concrete human unlock task.")
    unlock.add_argument("category", nargs="?", default="best")

    scout = subparsers.add_parser("scout", help="Scout one infrastructure category.")
    scout.add_argument("category")

    leads = subparsers.add_parser("leads", help="Find public AI-agent infrastructure pain leads.")
    leads.add_argument("query", nargs="*")

    convert_leads = subparsers.add_parser("convert-leads", help="Convert public leads into agent value packs, safe outreach routes, and customer next steps.")
    convert_leads.add_argument("query", nargs="*")
    convert_leads.add_argument("--limit", type=int, default=5)
    convert_leads.add_argument("--send", action="store_true", help="Send only to eligible public machine-readable agent endpoints.")
    convert_leads.add_argument("--approval", default="", help="Explicit public lead approval scope, e.g. comment or pr_plan.")
    convert_leads.add_argument("--budget", type=float)

    lead_conversions = subparsers.add_parser("lead-conversions", help="List stored lead conversion records.")
    lead_conversions.add_argument("--status", action="append", default=[])
    lead_conversions.add_argument("--limit", type=int, default=25)

    productize = subparsers.add_parser("productize", help="Turn leads or stored lead conversions into reusable Nomad product offers.")
    productize.add_argument("query", nargs="*")
    productize.add_argument("--limit", type=int, default=5)

    products = subparsers.add_parser("products", help="List stored Nomad product offers.")
    products.add_argument("--status", action="append", default=[])
    products.add_argument("--limit", type=int, default=25)

    solve_pain = subparsers.add_parser("solve-pain", help="Turn one agent pain point into a reusable Nomad solution.")
    solve_pain.add_argument("problem", nargs="*")
    solve_pain.add_argument("--service-type", default="")

    doctor = subparsers.add_parser("doctor", help="Diagnose an agent pain point into a Critic, Fixer, or Healer reliability loop.")
    doctor.add_argument("problem", nargs="*")
    doctor.add_argument("--service-type", default="")

    guardrails = subparsers.add_parser("guardrails", help="Check a proposed Nomad action against runtime guardrails.")
    guardrails.add_argument("text", nargs="*")
    guardrails.add_argument("--action", default="manual.check")
    guardrails.add_argument("--approval", default="")

    subparsers.add_parser("service", help="Show Nomad public agent service catalog.")

    service_request = subparsers.add_parser("service-request", help="Create a wallet-payable service task.")
    service_request.add_argument("problem", nargs="+")

    service_verify = subparsers.add_parser("service-verify", help="Attach and verify a service payment transaction.")
    service_verify.add_argument("task_id")
    service_verify.add_argument("tx_hash")

    service_x402_verify = subparsers.add_parser("service-x402-verify", help="Verify an x402 PAYMENT-SIGNATURE for a service task.")
    service_x402_verify.add_argument("task_id")
    service_x402_verify.add_argument("payment_signature")

    service_work = subparsers.add_parser("service-work", help="Generate a draft work product for a paid service task.")
    service_work.add_argument("task_id")
    service_work.add_argument("--approval", default="draft_only")

    service_staking = subparsers.add_parser("service-staking", help="Show MetaMask staking checklist for a task.")
    service_staking.add_argument("task_id")

    service_stake = subparsers.add_parser("service-stake", help="Record a prepared or completed treasury stake.")
    service_stake.add_argument("task_id")
    service_stake.add_argument("tx_hash", nargs="?")
    service_stake.add_argument("--amount", type=float)
    service_stake.add_argument("--note", default="")

    service_spend = subparsers.add_parser("service-spend", help="Record spend from a task solver budget.")
    service_spend.add_argument("task_id")
    service_spend.add_argument("amount", type=float)
    service_spend.add_argument("--tx-hash", default="")
    service_spend.add_argument("--note", default="")

    service_close = subparsers.add_parser("service-close", help="Close a delivered service task.")
    service_close.add_argument("task_id")
    service_close.add_argument("outcome", nargs="*")

    agent_contact = subparsers.add_parser("agent-contact", help="Queue a bounded outbound request to a public agent endpoint.")
    agent_contact.add_argument("endpoint")
    agent_contact.add_argument("problem", nargs="+")
    agent_contact.add_argument("--service-type", default="human_in_loop")
    agent_contact.add_argument("--budget", type=float)

    agent_contact_send = subparsers.add_parser("agent-contact-send", help="Send a queued agent contact.")
    agent_contact_send.add_argument("contact_id")

    agent_contact_poll = subparsers.add_parser("agent-contact-poll", help="Poll a sent A2A contact for task updates.")
    agent_contact_poll.add_argument("contact_id")

    subparsers.add_parser("agent-card", help="Print Nomad's A2A-style AgentCard.")

    direct = subparsers.add_parser("direct", help="Run a direct 1:1 agent message through LoopHelper.")
    direct.add_argument("message", nargs="+")
    direct.add_argument("--agent", default="")
    direct.add_argument("--endpoint", default="")
    direct.add_argument("--wallet", default="")
    direct.add_argument("--budget", type=float)

    discover_agent = subparsers.add_parser("discover-agent", help="Discover an A2A-style AgentCard from a base URL.")
    discover_agent.add_argument("base_url")

    cold_outreach = subparsers.add_parser("cold-outreach", help="Queue or send cold outreach to public agent endpoints.")
    cold_outreach.add_argument("targets", nargs="*")
    cold_outreach.add_argument("--discover", action="store_true", help="Discover public agent endpoints before queuing.")
    cold_outreach.add_argument("--send", action="store_true")
    cold_outreach.add_argument("--limit", type=int, default=100)
    cold_outreach.add_argument("--budget", type=float)
    cold_outreach.add_argument("--query", default="", help="Optional public discovery search query.")

    cycle = subparsers.add_parser("cycle", help="Run a bounded self-improvement cycle.")
    cycle.add_argument("objective", nargs="*")

    autopilot = subparsers.add_parser("autopilot", help="Run Nomad's continuous service, outreach and self-improvement loop.")
    autopilot.add_argument("objective", nargs="*")
    autopilot.add_argument("--cycles", type=int, default=1, help="0 means run forever.")
    autopilot.add_argument("--interval", type=int, default=900, help="Seconds between autopilot cycles.")
    autopilot.add_argument("--outreach-limit", type=int, default=10)
    autopilot.add_argument("--conversion-limit", type=int, default=None)
    autopilot.add_argument("--daily-lead-target", type=int, default=None, help="Maximum A2A leads to prepare or contact per local day, default 100.")
    autopilot.add_argument("--service-limit", type=int, default=25)
    autopilot.add_argument("--service-approval", default="")
    autopilot.add_argument("--query", default="", help="Optional outreach discovery query override.")
    autopilot.add_argument("--conversion-query", default="", help="Optional lead conversion query override.")
    autopilot.add_argument("--send-outreach", action=argparse.BooleanOptionalAction, default=None)
    autopilot.add_argument("--send-a2a", action=argparse.BooleanOptionalAction, default=None, help="Send only to eligible public machine-readable agent endpoints.")
    autopilot.add_argument("--serve-api", action="store_true", help="Start the local Nomad API thread during autopilot.")
    autopilot.add_argument("--self-schedule", action=argparse.BooleanOptionalAction, default=True, help="Let Nomad decide when to run or wait between checks.")

    ask = subparsers.add_parser("ask", help="Send a raw Nomad query.")
    ask.add_argument("query", nargs="+")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "shell":
        as_json = "--json" in argv
        run_shell(as_json=as_json)
        return 0
    run_once(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
