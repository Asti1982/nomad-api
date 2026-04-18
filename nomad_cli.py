import argparse
import json
import sys
from typing import Any, Dict, Iterable, Optional

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

    if result.get("analysis"):
        return str(result["analysis"])
    if result.get("message"):
        return str(result["message"])
    return json.dumps(result, indent=2, ensure_ascii=False)


def _print_result(result: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(_compact_text(result))


def build_query(args: argparse.Namespace) -> str:
    command = args.command
    profile_suffix = f" for {args.profile}" if getattr(args, "profile", None) else ""

    if command == "best":
        return f"/best{profile_suffix}"
    if command == "self":
        return f"/self{profile_suffix}"
    if command == "compute":
        return f"/compute{profile_suffix}"
    if command == "unlock":
        category = args.category or "best"
        return f"/unlock {category}{profile_suffix}"
    if command == "scout":
        return f"/scout {args.category}{profile_suffix}"
    if command == "leads":
        query = " ".join(args.query).strip()
        return f"/leads {query}".strip()
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
    agent = NomadAgent()
    if args.command == "self-status":
        journal = SelfDevelopmentJournal()
        result = {
            "mode": "self_development_status",
            "deal_found": False,
            "state": journal.load(),
            "text": journal.status_text(),
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

    subparsers.add_parser("best", help="Show the recommended AI-first stack.")
    subparsers.add_parser("self", help="Run Nomad self audit.")
    subparsers.add_parser("compute", help="Run compute audit.")
    subparsers.add_parser("self-status", help="Show persistent self-development state.")

    unlock = subparsers.add_parser("unlock", help="Generate a concrete human unlock task.")
    unlock.add_argument("category", nargs="?", default="best")

    scout = subparsers.add_parser("scout", help="Scout one infrastructure category.")
    scout.add_argument("category")

    leads = subparsers.add_parser("leads", help="Find public AI-agent infrastructure pain leads.")
    leads.add_argument("query", nargs="*")

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
