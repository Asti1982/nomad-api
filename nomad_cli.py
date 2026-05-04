import argparse
import json
import sys
from typing import Any, Dict, Iterable, Optional

from nomad_autopilot import NomadAutopilot
from codex_peer_agent import CodexPeerAgent
from cryptogrift_guard_agent import CryptoGriftGuardAgent
from nomad_swarm_spawner import NomadSwarmSpawner
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
        outbound = result.get("outbound") or {}
        autopilot = result.get("autopilot") or {}
        autonomous = result.get("autonomous_development") or {}
        mutual_aid = result.get("mutual_aid") or {}
        top_truth_pattern = mutual_aid.get("top_truth_pattern") or {}
        top_high_value_patterns = (mutual_aid.get("top_high_value_patterns") or [])[:3]
        lines = [
            "Nomad system status",
            f"Uptime: {result.get('uptime', 'unknown')}",
            f"Platform: {os_info.get('platform', 'unknown')}",
            f"CPU: {resources.get('cpu_count', 0)} cores",
            f"RAM: {resources.get('memory_gb', 0):.2f} GB",
            "",
            "Autopilot:",
            f"  Status: {'[ACTIVE]' if autopilot.get('active') else '[INACTIVE]'}",
        ]
        if autopilot.get("active"):
            lines.append(f"  Last Run: {autopilot.get('last_run', 'N/A')}")
            lines.append(f"  Objective: {autopilot.get('objective', 'N/A')}")

        lines.extend([
            "",
            "Autonomous Development:",
            f"  Actions: {autonomous.get('action_count', 0)}",
            f"  Latest: {autonomous.get('latest_title', '') or 'none'}",
            "",
            "Mutual-Aid:",
            f"  Score: {mutual_aid.get('mutual_aid_score', 0)}",
            f"  Swarm Assist: {mutual_aid.get('swarm_assist_score', 0)}",
            f"  Modules: {mutual_aid.get('module_count', 0)}",
            f"  Ledger: {mutual_aid.get('truth_ledger_count', 0)}",
            f"  Inbox: {mutual_aid.get('swarm_inbox_count', 0)}",
            f"  Paid Packs: {mutual_aid.get('paid_pack_count', 0)}",
            "",
            "Compute Lanes:",
            f"  Local Ollama: {'[ACTIVE]' if compute_lanes.get('local', {}).get('ollama') else '[INACTIVE]'}",
            f"  Local llama.cpp: {'[ACTIVE]' if compute_lanes.get('local', {}).get('llama_cpp') else '[INACTIVE]'}",
            f"  GitHub Models: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('github_models') else '[INACTIVE]'}",
            f"  Hugging Face: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('huggingface') else '[INACTIVE]'}",
            f"  xAI Grok: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('xai_grok') else '[INACTIVE]'}",
            f"  OpenRouter: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('openrouter') else '[INACTIVE]'}",
            f"  Modal: {'[ACTIVE]' if (compute_lanes.get('hosted', {}).get('modal') if isinstance(compute_lanes.get('hosted', {}).get('modal'), bool) else (compute_lanes.get('hosted', {}).get('modal') or {}).get('available')) else '[INACTIVE]'}",
            f"  Lambda Labs: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('lambda_labs') else '[INACTIVE]'}",
            f"  RunPod: {'[ACTIVE]' if compute_lanes.get('hosted', {}).get('runpod') else '[INACTIVE]'}",
            "",
            "Tasks:",
            f"  Total: {tasks.get('total', 0)}",
            f"  Paid/Pending: {tasks.get('paid', 0)}",
            f"  Awaiting Payment: {tasks.get('awaiting_payment', 0)}",
            f"  Completed: {tasks.get('completed', 0)}",
            "",
            "Outbound:",
            f"  Contacts: {(outbound.get('contacts') or {}).get('total', 0)}",
            f"  Awaiting Reply: {(outbound.get('contacts') or {}).get('awaiting_reply', 0)}",
            f"  Follow-up Ready: {(outbound.get('contacts') or {}).get('followup_ready', 0)}",
        ])
        if top_truth_pattern:
            lines.extend([
                "",
                "Top Truth Pattern:",
                (
                    f"  {top_truth_pattern.get('title', '')} "
                    f"[{top_truth_pattern.get('pain_type', 'unknown')}] "
                    f"repeat={top_truth_pattern.get('repeat_count', 0)} "
                    f"truth={top_truth_pattern.get('truth_score', 0)}"
                ),
            ])
        if top_high_value_patterns:
            lines.extend([
                "",
                "Top High-Value Patterns:",
            ])
            for item in top_high_value_patterns:
                lines.append(
                    f"  {item.get('title', '')} [{item.get('pain_type', 'unknown')}] "
                    f"hits={item.get('occurrence_count', 0)} "
                    f"truth={item.get('avg_truth_score', 0)} "
                    f"reuse={item.get('avg_reuse_value', 0)}"
                )
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    if mode == "nomad_autopilot":
        service = result.get("service") or {}
        outreach = result.get("outreach") or {}
        outbound_tracking = result.get("outbound_tracking") or {}
        lead_conversion = result.get("lead_conversion") or {}
        product_factory = result.get("product_factory") or {}
        reply_conversion = result.get("reply_conversion") or {}
        autonomous_development = result.get("autonomous_development") or {}
        campaign = outreach.get("campaign") or {}
        stats = campaign.get("stats") or {}
        conversion_stats = lead_conversion.get("stats") or {}
        autonomous_action = autonomous_development.get("action") or {}
        lines = [
            "Nomad autopilot",
            f"Objective: {result.get('objective', '')}",
            f"Worked paid tasks: {len(service.get('worked_task_ids') or [])}",
            f"Draft-ready tasks: {len(service.get('draft_ready_task_ids') or [])}",
            f"Awaiting payment: {len(service.get('awaiting_payment_task_ids') or [])}",
            f"Stale invalid tasks dropped: {len(service.get('stale_invalid_task_ids') or [])}",
            f"Payment follow-ups sent: {len((result.get('payment_followup_send') or {}).get('sent_contact_ids') or [])}",
            f"Lead conversions: {sum(int(value) for value in conversion_stats.values()) if conversion_stats else 0}",
            f"Products built: {product_factory.get('product_count', 0)}",
            f"A2A replies converted: {len(reply_conversion.get('created_task_ids') or [])}",
            f"Outreach queued: {stats.get('queued', 0)}",
            f"Outreach sent: {stats.get('sent', 0)}",
            f"Tracked outbound threads: {(outbound_tracking.get('contacts') or {}).get('total', 0)}",
            (
                f"Autonomous dev: {autonomous_action.get('title')}"
                if autonomous_action
                else f"Autonomous dev: skipped ({autonomous_development.get('reason', 'none')})"
            ),
        ]
        quota = result.get("daily_quota") or {}
        if quota:
            lines.append(
                "Daily A2A quota: "
                f"prepared {quota.get('prepared_count', 0)}/{quota.get('target', 0)}, "
                f"sent {quota.get('sent_count', 0)}/{quota.get('target', 0)}"
            )
        if outbound_tracking.get("next_best_action"):
            lines.append(f"Next outbound action: {outbound_tracking.get('next_best_action')}")
        if result.get("analysis"):
            lines.append(result["analysis"])
        proof = result.get("autonomy_proof") or {}
        if proof:
            lines.append(
                "Autonomy proof: "
                f"{proof.get('status', 'unknown')} "
                f"(useful={bool(proof.get('cycle_was_useful'))}, "
                f"artifact={proof.get('useful_artifact_created', '') or 'none'}, "
                f"unlock={proof.get('next_required_unlock', '') or 'none'})"
            )
        return "\n".join(lines)

    if mode == "nomad_mission_control":
        top = result.get("top_blocker") or {}
        paid = result.get("paid_job_focus") or {}
        next_action = result.get("next_action") or {}
        compute = result.get("compute_policy") or {}
        unlocks = result.get("human_unlocks") or []
        tasks = result.get("agent_tasks") or []
        lines = [
            "Nomad mission control",
            f"Top blocker: {top.get('summary', 'unknown')}",
            f"Next: {next_action.get('summary', top.get('next_action', ''))}",
            f"Paid focus: {paid.get('target_offer', '')} [{paid.get('status', '')}]",
            f"Compute: max {compute.get('max_active_agents_per_blocker', 2)} specialist(s) per blocker, {compute.get('default_mode', 'local_first')}",
        ]
        if unlocks:
            unlock = unlocks[0]
            lines.append(f"Human unlock: {unlock.get('title', '')} -> {unlock.get('expected_reply', '')}")
        if tasks:
            task = tasks[0]
            lines.append(f"First agent task: {task.get('id', '')} ({task.get('role', '')})")
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "nomad_lead_workbench":
        self_help = result.get("self_help") or {}
        lines = [
            "Nomad lead workbench",
            f"Queue: {result.get('queue_count', 0)}",
            f"Worked: {result.get('worked_count', 0)}",
            f"Top action: {self_help.get('top_next_action', '')}",
            f"Executable without human: {self_help.get('executable_without_human_count', 0)}",
            f"Human-blocked: {self_help.get('human_blocked_count', 0)}",
        ]
        for item in (result.get("queue") or [])[:3]:
            lines.append(
                f"- {item.get('kind')}: {item.get('title', '')} "
                f"[{item.get('safe_next_action', '')}]"
            )
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "codex_peer_agent":
        receipt = result.get("join_receipt") or {}
        development = result.get("development_response") or {}
        lead = result.get("lead_workbench") or {}
        mission = result.get("mission") or {}
        lines = [
            "CodexPeerAgent",
            f"Transport: {result.get('transport', '')}",
            f"Join receipt: {receipt.get('receipt_id', '') or 'none'} accepted={receipt.get('accepted', False)}",
            f"Development: {development.get('solution_title', '') or development.get('pain_type', '')}",
            f"Worked leads: {lead.get('worked_count', 0)} / queue {lead.get('queue_count', 0)}",
            f"Top lead action: {lead.get('top_next_action', '')}",
            f"Top blocker: {mission.get('top_blocker', '')}",
            f"Next: {mission.get('next_action', '')}",
        ]
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "codex_peer_worker":
        lines = [
            "CodexPeerWorker",
            f"Transport: {result.get('transport', '')} http_only={result.get('http_only', False)}",
            f"Cycles: {result.get('cycles_completed', 0)} / requested {result.get('cycles_requested', 0)}",
            f"Worked leads: {result.get('worked_leads', 0)} / queue {result.get('latest_queue_count', 0)}",
            f"Prospect agents: {result.get('latest_prospect_agents', 0)}",
            f"Queued invites: {result.get('latest_queued_agent_invites', 0)}",
            f"Agent to attract: {result.get('latest_agent_to_attract', '')}",
            f"Top action: {result.get('latest_top_action', '')}",
            f"Top blocker: {result.get('latest_top_blocker', '')}",
            f"Next: {result.get('latest_next_action', '')}",
        ]
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "nomad_service_e2e":
        task = result.get("task") or {}
        payment = task.get("payment") if isinstance(task.get("payment"), dict) else {}
        lifecycle = result.get("lifecycle") or []
        lines = [
            "Nomad service E2E",
            f"Task: {task.get('task_id', 'preview')}",
            f"Status: {task.get('status', 'preview')}",
            f"Service type: {task.get('service_type', 'custom')}",
            f"Budget: {payment.get('amount_native', task.get('budget_native', 0))} {payment.get('native_symbol', '')}".strip(),
            f"Next: {result.get('next_best_action', '')}",
        ]
        if lifecycle:
            current = next(
                (
                    step
                    for step in lifecycle
                    if step.get("status") in {"ready", "in_progress"}
                ),
                lifecycle[-1],
            )
            lines.append(f"Current stage: {current.get('stage', 'unknown')} [{current.get('status', 'unknown')}]")
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "nomad_outbound_tracking":
        contacts = result.get("contacts") or {}
        campaigns = result.get("campaigns") or {}
        tasks = result.get("tasks") or {}
        autonomous = result.get("autonomous_tracking") or {}
        lines = [
            "Nomad outbound tracking",
            f"Contacts: {contacts.get('total', 0)}",
            f"Awaiting reply: {contacts.get('awaiting_reply', 0)}",
            f"Follow-up ready: {contacts.get('followup_ready', 0)}",
            f"Campaigns: {campaigns.get('total', 0)}",
            f"Awaiting payment tasks: {len(tasks.get('awaiting_payment') or [])}",
            f"Autonomous follow-ups: payments={autonomous.get('payment_followup_log_count', 0)}, agents={autonomous.get('agent_followup_log_count', 0)}",
            f"Next: {result.get('next_best_action', '')}",
        ]
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

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

    if mode == "modal_scout":
        status = result.get("status") or {}
        deployment = result.get("deployment") or {}
        lines = [
            "Nomad Modal scout",
            f"Configured: {status.get('configured', False)}",
            f"Reachable: {status.get('reachable', False)}",
            f"App name: {deployment.get('app_name', '')}",
            f"Secret name: {deployment.get('secret_name', '')}",
            f"GitHub branch: {deployment.get('github_branch', '')}",
            f"Render public URL: {deployment.get('public_api_url', '')}",
        ]
        deploy_commands = deployment.get("deploy_commands") or []
        if deploy_commands:
            lines.append(f"Next step: {deploy_commands[0]}")
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

    if mode in {"nomad_mutual_aid", "nomad_mutual_aid_status"}:
        plan = result.get("evolution_plan") or result.get("latest_evolution_plan") or {}
        lines = [
            "Nomad Mutual-Aid",
            f"Score: {result.get('mutual_aid_score', 0)}",
            f"Truth density total: {result.get('truth_density_total', 0)}",
            f"Modules: {result.get('module_count', 0)}",
            f"Ledger entries: {result.get('truth_ledger_count', 0)}",
            f"Paid packs: {result.get('paid_pack_count', 0)}",
        ]
        if plan:
            lines.append(
                f"Latest plan: {plan.get('filename', '') or plan.get('module_id', '')} "
                f"[{'applied' if plan.get('applied') else 'planned'}]"
            )
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    if mode == "nomad_truth_density_ledger":
        stats = result.get("stats") or {}
        return "\n".join(
            [
                "Nomad Truth-Density Ledger",
                f"Entries: {result.get('entry_count', 0)}",
                f"Average truth score: {stats.get('avg_truth_score', 0)}",
                f"Average reuse value: {stats.get('avg_reuse_value', 0)}",
                result.get("analysis", ""),
            ]
        )

    if mode == "nomad_swarm_inbox":
        stats = result.get("stats") or {}
        return "\n".join(
            [
                "Nomad Swarm Inbox",
                f"Total: {stats.get('total', 0)}",
                f"Verified pending review: {stats.get('verified_pending_review', 0)}",
                f"Rejected: {stats.get('rejected', 0)}",
                result.get("analysis", ""),
            ]
        )

    if mode == "nomad_swarm_development_signals":
        return "\n".join(
            [
                "Nomad Swarm Development Signals",
                f"Signals: {result.get('signal_count', 0)}",
                result.get("analysis", ""),
            ]
        )

    if mode == "nomad_high_value_patterns":
        return "\n".join(
            [
                "Nomad High-Value Patterns",
                f"Patterns: {result.get('pattern_count', 0)}",
                f"Minimum repeats: {result.get('min_repeat_count', 0)}",
                result.get("analysis", ""),
            ]
        )

    if mode == "nomad_agent_engagements":
        stats = result.get("stats") or {}
        roles = stats.get("roles") or {}
        return "\n".join(
            [
                "Nomad Agent Engagements",
                f"Entries: {result.get('entry_count', 0)}",
                f"Roles: {', '.join(f'{key}={value}' for key, value in sorted(roles.items())) or 'none'}",
                result.get("analysis", ""),
            ]
        )

    if mode == "nomad_agent_engagement_summary":
        roles = result.get("roles") or {}
        outcomes = result.get("outcomes") or {}
        return "\n".join(
            [
                "Nomad Agent Engagement Summary",
                f"Entries: {result.get('entry_count', 0)}",
                f"Roles: {', '.join(f'{key}={value}' for key, value in sorted(roles.items())) or 'none'}",
                f"Outcomes: {', '.join(f'{key}={value}' for key, value in sorted(outcomes.items())) or 'none'}",
                result.get("analysis", ""),
            ]
        )

    if mode == "nomad_agent_attractor":
        top_offer = result.get("top_offer") or {}
        return "\n".join(
            [
                "Nomad Agent Attractor",
                f"Focus: {result.get('focus_service_type', 'custom')}",
                f"Roles sought: {', '.join(result.get('target_roles') or []) or 'none'}",
                f"Top offer: {top_offer.get('headline', '') or 'none'}",
                f"Attractor: {(result.get('entrypoints') or {}).get('agent_attractor', '')}",
                result.get("analysis", ""),
            ]
        )

    if mode == "nomad_swarm_network":
        active_lead = result.get("active_lead") or {}
        approval = result.get("approval_state") or {}
        return "\n".join(
            [
                "Nomad Swarm Network",
                f"Lead: {active_lead.get('title') or active_lead.get('url') or 'none'}",
                f"Focus: {result.get('focus_service_type', '')}",
                f"Roles: {', '.join(result.get('target_roles') or []) or 'none'}",
                f"Public reply allowed: {approval.get('public_reply_allowed_now', False)}",
                f"Next: {result.get('next_best_action', '')}",
            ]
        )

    if mode == "nomad_swarm_coordination":
        return "\n".join(
            [
                "Nomad Swarm Coordination",
                f"Focus: {result.get('focus_pain_type', '')}",
                f"Connected agents: {result.get('connected_agents', 0)}",
                f"Next: {result.get('next_best_action', '')}",
                f"Help lanes: {len(result.get('help_lanes') or [])}",
            ]
        )

    if mode == "nomad_swarm_accumulation":
        return "\n".join(
            [
                "Nomad Swarm Accumulation",
                f"Known agents: {result.get('known_agents', 0)}",
                f"Joined agents: {result.get('joined_agents', 0)}",
                f"Prospects: {result.get('prospect_agents', 0)}",
                f"Next: {result.get('next_best_action', '')}",
            ]
        )

    if mode == "nomad_mutual_aid_packs":
        return "\n".join(
            [
                "Nomad Mutual-Aid Paid Packs",
                f"Packs: {result.get('pack_count', 0)}",
                result.get("analysis", ""),
            ]
        )

    if mode == "codex_task":
        return str(result.get("text") or result.get("analysis") or "")

    if mode == "nomad_operator_desk":
        lines = ["Nomad operator desk (human unlocks)"]
        primary = result.get("primary_action") or {}
        if primary:
            lines.append(f"PRIMARY: {primary.get('title', '')} [{primary.get('source', '')}]")
            block = primary.get("copy_paste_block") or ""
            if block:
                lines.append(block)
        else:
            lines.append("No unlock items queued.")
        hint = result.get("copy_cli_hint") or ""
        if hint:
            lines.append(hint)
        jo = (result.get("journal_excerpt") or {}).get("next_objective") or ""
        if jo:
            lines.append(f"Journal next objective: {jo}")
        return "\n".join(line for line in lines if line)

    if mode == "nomad_operator_verify":
        lines = [
            "Nomad operator verify bundle",
            f"base_url: {result.get('base_url', '')}",
            f"all_ok: {result.get('all_ok')}",
        ]
        for row in result.get("checks") or []:
            status = "OK" if row.get("ok") else "FAIL"
            code = row.get("status_code", "")
            err = row.get("error") or ""
            lines.append(f"  {row.get('name')}: {status} {code} {err}".strip())
        return "\n".join(lines)

    if mode == "nomad_operator_metrics":
        return "\n".join(
            [
                "Nomad operator metrics",
                f"verify_ok_streak: {result.get('verify_ok_streak', 0)}",
                f"last_verify_all_ok: {result.get('last_verify_all_ok')}",
                f"self_dev_cycles: {result.get('self_development_cycle_count', 0)}",
                f"verify_pass_rate_last_n: {result.get('verify_pass_rate_last_n')}",
                f"cycles_logged_in_tail: {result.get('self_improvement_events_in_tail', 0)}",
            ]
        )

    if mode == "nomad_operator_daily":
        v = result.get("verify") or {}
        lines = [
            "Nomad operator daily bundle",
            f"verify all_ok: {v.get('all_ok')}",
            f"base_url: {v.get('base_url', '')}",
        ]
        for row in v.get("checks") or []:
            mark = "OK" if row.get("ok") else "FAIL"
            lines.append(f"  {row.get('name')}: {mark}")
        ni = result.get("next_iteration") or {}
        for hint in ni.get("hints") or []:
            lines.append(f"Next: {hint}")
        return "\n".join(lines)

    if mode == "nomad_operator_sprint":
        lines = [
            "Nomad operator sprint (next actions)",
            f"public_base_url: {result.get('public_base_url', '')}",
            f"compute_lane_count: {result.get('compute_lane_count', 0)}",
        ]
        for risk in result.get("insomnia_risks") or []:
            lines.append(f"risk[{risk.get('severity', 'n/a')}]: {risk.get('risk', '')}")
        for row in result.get("actions") or []:
            lines.append(
                f"  [{row.get('kind', '')} p={row.get('priority', '')}] "
                f"{row.get('title', '')}: {row.get('cli', '')}".strip()
            )
        return "\n".join(line for line in lines if line)

    if mode == "nomad_operator_growth_start":
        lines = [
            "Nomad growth-start (daily + first leads)",
            f"overall_ok: {result.get('ok')}",
            f"verify all_ok: {(result.get('daily') or {}).get('verify', {}).get('all_ok')}",
            f"lead_query: {result.get('lead_query', '')}",
        ]
        lc = (result.get("leads") or {}) if isinstance(result.get("leads"), dict) else {}
        if lc:
            lines.append(f"leads mode: {lc.get('mode', '')} addressable: {lc.get('addressable_count', '')}")
        sw = result.get("swarm_accumulation") or {}
        if sw and not sw.get("skipped"):
            lines.append(
                f"swarm: +{len(sw.get('new_prospect_ids') or [])} prospects "
                f"(queue {sw.get('prospect_agents', '')})"
            )
        for step in result.get("next_steps") or []:
            lines.append(f"  -> {step}")
        return "\n".join(lines)

    if mode == "nomad_operator_autonomy_step":
        lines = [
            "Nomad autonomy-step (growth + lead scout + swarm feed + focused /cycle)",
            f"overall_ok: {result.get('ok')}",
            f"lead_query: {result.get('lead_query', '')}",
        ]
        for row in result.get("steps") or []:
            mark = "OK" if row.get("ok") else "FAIL"
            extra = ""
            if row.get("step") == "swarm_accumulation" and row.get("new_prospects") is not None:
                extra = f" (+{row.get('new_prospects')} prospects)"
            lines.append(f"  {row.get('step', '')}: {mark}{extra}")
        cyc = result.get("cycle") or {}
        if isinstance(cyc, dict) and cyc.get("self_development"):
            sd = cyc["self_development"]
            if sd.get("next_objective"):
                lines.append(f"Next objective: {sd.get('next_objective')}")
        for hint in result.get("next_steps") or []:
            lines.append(f"  -> {hint}")
        return "\n".join(lines)

    if mode == "nomad_operator_iteration_report":
        tr = result.get("trends") or {}
        lines = [
            "Nomad operator iteration report",
            f"verify pass rate (last 10): {tr.get('verify_pass_rate_last_10')}",
            f"verify pass rate (last 30): {tr.get('verify_pass_rate_last_30')}",
            f"self-improvement cycles logged: {tr.get('self_improvement_cycles_logged', 0)}",
            f"daily bundles logged: {tr.get('operator_daily_runs', 0)}",
        ]
        for rec in result.get("recommendations") or []:
            lines.append(f"Recommend: {rec}")
        return "\n".join(lines)

    if mode == "nomad_agent_reputation":
        totals = result.get("totals") or {}
        signals = result.get("signals") or {}
        return "\n".join(
            [
                "Nomad agent reputation",
                f"tasks: {totals.get('tasks', 0)}",
                f"awaiting_payment: {totals.get('awaiting_payment', 0)}",
                f"paid: {totals.get('paid', 0)}",
                f"delivered: {totals.get('delivered', 0)}",
                f"boundary_reliability: {signals.get('boundary_reliability', 0)}",
            ]
        )

    if mode == "nomad_unhuman_hub":
        profile = result.get("unhuman_profile") or {}
        lines = [
            "Nomad unhuman hub",
            f"risk_score: {profile.get('risk_score', 0)} ({profile.get('risk_tier', 'stable')})",
            f"hard_boundary_guard: {profile.get('hard_boundary_guard')}",
            f"fallback_ready: {profile.get('fallback_ready')}",
        ]
        for cmd in (result.get("runbook") or [])[:3]:
            lines.append(f"runbook: {cmd}")
        return "\n".join(lines)

    if mode == "nomad_swarm_helper_pass":
        lines = [
            "Nomad swarm-helper pass",
            f"public_base_url: {result.get('public_base_url', '')}",
            f"dry_run: {result.get('dry_run')}",
            f"GET ok: {result.get('probe_ok_count', 0)}/{len(result.get('probes') or [])}",
        ]
        jp = result.get("swarm_join_post")
        if jp:
            lines.append(f"POST /swarm/join: status={jp.get('status')} ok={jp.get('ok')}")
        dp = result.get("swarm_develop_post")
        if dp:
            lines.append(f"POST /swarm/develop: status={dp.get('status')} ok={dp.get('ok')}")
        return "\n".join(lines)

    if mode == "nomad_void_observer_pulse":
        return "\n".join(
            [
                "Nomad void observer (non-narrative edge fingerprint)",
                f"public_base_url: {result.get('public_base_url', '')}",
                f"edge_coherence_sha256: {result.get('edge_coherence_sha256', '')}",
                f"baseline_drift: {result.get('baseline_drift')}",
                f"vacuum_stability: {result.get('vacuum_stability')}",
                f"GET ok count (from lattice): {result.get('probe_ok_count', 0)}",
            ]
        )

    if mode == "nomad_network_steward_cycle":
        vo = result.get("void_observer") or {}
        acc = result.get("swarm_accumulate_post")
        lines = [
            "Nomad network steward",
            f"public_base_url: {result.get('public_base_url', '')}",
            f"void_sha256: {vo.get('edge_coherence_sha256', '')}",
            f"baseline_drift: {vo.get('baseline_drift')}",
            f"lattice GET ok: {result.get('swarm_helper', {}).get('probe_ok_count', 0)}",
        ]
        if acc:
            lines.append(f"POST /swarm/accumulate: status={acc.get('status')} ok={acc.get('ok')}")
        jp = result.get("swarm_join_post")
        if jp:
            lines.append(f"POST /swarm/join: status={jp.get('status')} ok={jp.get('ok')}")
        dp = result.get("swarm_develop_post")
        if dp:
            lines.append(f"POST /swarm/develop: status={dp.get('status')} ok={dp.get('ok')}")
        return "\n".join(lines)

    if mode == "nomad_network_steward_loop":
        runs = result.get("runs") or []
        last = runs[-1] if runs else {}
        vo = (last.get("void_observer") or {}) if isinstance(last, dict) else {}
        return "\n".join(
            [
                "Nomad network steward loop",
                f"cycles_completed: {result.get('cycles_completed', 0)}",
                f"last void_sha256: {vo.get('edge_coherence_sha256', '')}",
                f"last lattice GET ok: {(last.get('swarm_helper') or {}).get('probe_ok_count', '')}",
            ]
        )

    if mode == "nomad_machine_blind_spots_pass":
        fac = len(result.get("json_contract_html_facades") or [])
        div = (result.get("peer_glimpse_coherence") or {}).get("readiness_disagrees_with_health_probe")
        lines = [
            "Nomad machine blind spots",
            f"public_base_url: {result.get('public_base_url', '')}",
            f"json_html_facades: {fac}",
            f"gateway_throttle_hits: {result.get('gateway_or_throttle_hits', 0)}",
            f"readiness_vs_health_divergence: {div}",
        ]
        for note in (result.get("blind_spot_notes") or [])[:2]:
            lines.append(f"note: {note}")
        if result.get("append_log_path"):
            lines.append(f"appended: {result.get('append_log_path')}")
        return "\n".join(lines)

    if mode == "nomad_lead_product_blind_spots_pass":
        qm = result.get("queue_agent_metrics") or {}
        lines = [
            "Nomad lead/product blind spots",
            f"conversions: {(result.get('counts') or {}).get('conversions', 0)}  products: {(result.get('counts') or {}).get('products', 0)}",
            f"human_facing_hits: {len(result.get('human_facing_lead_hits') or [])}",
            f"title_collision_groups: {len(result.get('duplicate_title_collisions') or [])}",
            f"stale_unproductized: {len(result.get('stale_unproductized_conversions') or [])}",
            f"pain_entropy: {result.get('pain_type_entropy')}  execution_desert: {qm.get('agent_execution_desert_ratio')}",
        ]
        for note in (result.get("blind_spot_notes") or [])[:2]:
            lines.append(f"note: {note}")
        if result.get("append_log_path"):
            lines.append(f"appended: {result.get('append_log_path')}")
        return "\n".join(lines)

    if mode == "nomad_idempotency_agent_map":
        n = len(result.get("post_surfaces") or [])
        return "\n".join(
            [
                "Nomad idempotency agent map",
                f"public_base_url_hint: {result.get('public_base_url_hint', '')}",
                f"post_surfaces: {n}",
                "see JSON for join/develop replay semantics and non-retry POST paths",
            ]
        )

    if mode == "nomad_agent_retry_coach":
        rec = result.get("recommendation") or {}
        return "\n".join(
            [
                "Nomad agent retry coach",
                f"edge_samples: {(result.get('samples') or {}).get('edge_lines_used', 0)}",
                f"base_delay_s: {rec.get('base_delay_seconds')}  jitter: {rec.get('jitter_ratio')}",
                f"max_retries: {rec.get('max_retries_per_operation')}",
            ]
        )

    if mode == "nomad_mcp_survival_playbook":
        prod = result.get("nomad_product") or {}
        return "\n".join(
            [
                "Nomad MCP survival playbook",
                f"sku: {prod.get('sku', '')}",
                f"github_evidence: {len(result.get('github_evidence') or [])} threads",
                "use --json for full agent ingest bundle",
            ]
        )

    if mode == "nomad_misclassification_audit_pass":
        risks = result.get("misclassification_risks") or []
        lines = [
            "Nomad misclassification audit",
            f"risk_signals: {len(risks)}",
        ]
        for r in risks[:4]:
            lines.append(f"  - {r.get('kind', '')}")
        return "\n".join(lines)

    if mode == "nomad_agent_native_index":
        boot = result.get("boot_graph") or []
        rt = result.get("routing_table") or []
        lines = [
            "Nomad agent-native index",
            f"schema: {result.get('schema', '')}",
            f"public_base_url: {result.get('public_base_url', '')}",
            f"boot_steps: {len(boot)}  routing_entries: {len(rt)}",
        ]
        for row in boot[:5]:
            lines.append(f"  [{row.get('order', '')}] {row.get('purpose', '')}")
        mrc = result.get("machine_runtime_contract") or {}
        lines.append(f"machine_runtime_contract: {mrc.get('schema', '')}")
        return "\n".join(lines)

    if mode == "lead_discovery" and result.get("calibration_bundle"):
        cb = result["calibration_bundle"]
        lines = [
            "Nomad lead-focus calibration",
            f"focus: {cb.get('focus', '')} min_focus_score (configured): {cb.get('min_focus_score_configured')}",
            f"candidates: {cb.get('candidate_pool')} focus+addressable pool: {cb.get('focus_match_addressable_pool')}",
            f"qualified at gate: {cb.get('qualified_at_configured')}",
            "threshold_sweep (min_focus_score -> qualified_count):",
        ]
        for row in (cb.get("threshold_sweep") or [])[:12]:
            lines.append(f"  {row.get('min_focus_score')}: {row.get('qualified_count')}")
        rec = str(cb.get("recommendation") or "").strip()
        if rec:
            lines.append("recommendation:")
            lines.append(rec)
        return "\n".join(lines)

    if mode == "nomad_agent_growth_pipeline":
        leads_blob = result.get("leads") or {}
        ld = leads_blob.get("candidate_count")
        if ld is None:
            ld = len(leads_blob.get("leads") or [])
        conv = result.get("conversion") or {}
        cc = len(conv.get("conversions") or [])
        pf = result.get("product_factory") or {}
        pc = int(pf.get("product_count") or len(pf.get("products") or []))
        sw = result.get("swarm_accumulation") or {}
        lines = [
            "Nomad agent growth pipeline",
            f"leads_candidates: {ld}",
            f"conversions: {cc}",
            f"products_this_pass: {pc}",
            f"swarm_skipped: {bool(sw.get('skipped'))}",
        ]
        for step in (result.get("next_steps") or [])[:4]:
            lines.append(f"  -> {step}")
        return "\n".join(lines)

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
    if command == "mission":
        limit = f" limit={args.limit}" if args.limit else ""
        preview = " preview" if args.preview else ""
        return f"/mission{limit}{preview}".strip()
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
    if command == "modal":
        return "/modal"
    if command == "collaboration":
        return "/collaboration"
    if command == "mutual-aid-status":
        return "/mutual-aid status"
    if command == "mutual-aid":
        task = " ".join(args.task).strip()
        agent = f" agent={args.agent}" if args.agent else ""
        return f"/mutual-aid{agent} {task}".strip()
    if command == "mutual-aid-ledger":
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        return f"/mutual-aid ledger{pain_type} limit={args.limit}".strip()
    if command == "swarm-inbox":
        status = f" status={','.join(args.status)}" if args.status else ""
        return f"/mutual-aid inbox{status} limit={args.limit}".strip()
    if command == "swarm-signals":
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        return f"/mutual-aid signals{pain_type} limit={args.limit}".strip()
    if command == "mutual-aid-patterns":
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        return (
            f"/mutual-aid patterns{pain_type} limit={args.limit} "
            f"min_repeat_count={args.min_repeat_count}"
        ).strip()
    if command == "mutual-aid-packs":
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        return f"/mutual-aid packs{pain_type} limit={args.limit}".strip()
    if command == "swarm-propose":
        proposal = " ".join(args.proposal).strip()
        evidence_items = ["_".join(str(item).split()) for item in args.evidence if str(item).strip()]
        evidence = f" evidence={'|'.join(evidence_items)}" if evidence_items else ""
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        return f"/mutual-aid proposal agent={args.agent}{pain_type}{evidence} {proposal}".strip()
    if command == "unlock":
        category = args.category or "best"
        return f"/unlock {category}{profile_suffix}"
    if command == "scout":
        return f"/scout {args.category}{profile_suffix}"
    if command == "leads":
        query = " ".join(args.query).strip()
        extras = []
        focus = str(getattr(args, "focus", "") or "").strip()
        if focus:
            extras.append(f"focus={focus}")
        lim = getattr(args, "limit", None)
        if lim is not None:
            extras.append(f"limit={int(lim)}")
        tail = (" " + " ".join(extras)) if extras else ""
        return f"/leads {query}{tail}".strip()
    if command == "lead-calibrate":
        query = " ".join(args.query).strip()
        extras = []
        focus = str(getattr(args, "focus", "") or "").strip()
        if focus:
            extras.append(f"focus={focus}")
        extras.append(f"limit={int(getattr(args, 'limit', 12) or 12)}")
        extras.append(f"candidate_multiplier={int(getattr(args, 'candidate_multiplier', 5) or 5)}")
        tail = " ".join(extras)
        return f"/lead-calibrate {tail} {query}".strip()
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
    if command == "lead-workbench":
        limit = f" limit={args.limit}" if args.limit else ""
        work = " work" if args.work else ""
        return f"/lead-workbench{limit}{work}".strip()
    if command == "productize":
        query = " ".join(args.query).strip()
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/productize{limit} {query}".strip()
    if command == "products":
        status = f" status={','.join(args.status)}" if args.status else ""
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/products{status}{limit}".strip()
    if command == "agent-engagements":
        roles = f" role={','.join(args.role)}" if args.role else ""
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/agent-engagements{roles}{pain_type}{limit}".strip()
    if command == "agent-engagement-summary":
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/agent-engagement-summary{pain_type}{limit}".strip()
    if command == "agent-attractor":
        service_type = f" type={args.service_type}" if args.service_type else ""
        role = f" role={args.role}" if args.role else ""
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/agent-attractor{service_type}{role}{limit}".strip()
    if command == "swarm-coordinate":
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        return f"/swarm/coordinate{pain_type}".strip()
    if command == "swarm-network":
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        role = f" role={args.role}" if args.role else ""
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/swarm/network{pain_type}{role}{limit}".strip()
    if command == "swarm-accumulate":
        pain_type = f" type={args.pain_type}" if args.pain_type else ""
        action = " run" if args.refresh else ""
        return f"/swarm/accumulate{pain_type}{action}".strip()
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
    if command == "service-e2e":
        problem = " ".join(args.problem).strip()
        task_id = f" task_id={args.task_id}" if args.task_id else ""
        service_type = f" type={args.service_type}" if args.service_type else ""
        budget = f" budget={args.budget}" if args.budget is not None else ""
        agent = f" agent={args.agent}" if args.agent else ""
        wallet = f" wallet={args.wallet}" if args.wallet else ""
        callback = f" callback={args.callback}" if args.callback else ""
        create = " create=true" if args.create else ""
        approval = f" approval={args.approval}" if args.approval else ""
        return f"/service e2e{task_id}{service_type}{budget}{agent}{wallet}{callback}{create}{approval} {problem}".strip()
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
    if command == "outbound-status":
        limit = f" limit={args.limit}" if args.limit else ""
        return f"/outbound{limit}".strip()
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
        focus = (getattr(args, "focus", None) or "").strip()
        focus_tag = f"[nomad_focus:{focus}] " if focus else ""
        return f"/cycle {focus_tag}{objective}{profile_suffix}".strip()
    if command == "ask":
        return " ".join(args.query).strip()
    if command == "operator-desk":
        raise ValueError("operator-desk is handled directly in run_once")
    if command == "operator-verify":
        raise ValueError("operator-verify is handled directly in run_once")
    if command == "operator-metrics":
        raise ValueError("operator-metrics is handled directly in run_once")
    if command == "operator-daily":
        raise ValueError("operator-daily is handled directly in run_once")
    if command == "operator-report":
        raise ValueError("operator-report is handled directly in run_once")
    if command == "growth-start":
        raise ValueError("growth-start is handled directly in run_once")
    if command == "autonomy-step":
        raise ValueError("autonomy-step is handled directly in run_once")
    if command == "operator-sprint":
        raise ValueError("operator-sprint is handled directly in run_once")
    if command == "agent-reputation":
        raise ValueError("agent-reputation is handled directly in run_once")
    if command == "unhuman-hub":
        raise ValueError("unhuman-hub is handled directly in run_once")
    if command == "agent-growth":
        raise ValueError("agent-growth is handled directly in run_once")
    if command == "agent-native-index":
        raise ValueError("agent-native-index is handled directly in run_once")
    if command == "swarm-helper":
        raise ValueError("swarm-helper is handled directly in run_once")
    if command == "void-observer":
        raise ValueError("void-observer is handled directly in run_once")
    if command == "network-steward":
        raise ValueError("network-steward is handled directly in run_once")
    if command == "machine-blind-spots":
        raise ValueError("machine-blind-spots is handled directly in run_once")
    if command == "lead-product-blind-spots":
        raise ValueError("lead-product-blind-spots is handled directly in run_once")
    if command == "idempotency-agent-map":
        raise ValueError("idempotency-agent-map is handled directly in run_once")
    if command == "agent-retry-coach":
        raise ValueError("agent-retry-coach is handled directly in run_once")
    if command == "mcp-survival-playbook":
        raise ValueError("mcp-survival-playbook is handled directly in run_once")
    if command == "misclassification-audit":
        raise ValueError("misclassification-audit is handled directly in run_once")
    if command == "self-status":
        return ""
    if command == "codex-task":
        return ""
    if command == "codex-peer-agent":
        return ""
    if command == "render-logs":
        raise ValueError("render-logs is handled directly in run_once")
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
        elif args.command == "codex-peer-agent":
            peer = CodexPeerAgent()
            if args.loop:
                result = peer.run_http_loop(
                    base_url=args.base_url,
                    mode=args.mode,
                    problem=args.problem,
                    cycles=args.cycles,
                    interval_seconds=args.interval,
                    work_leads=args.work_leads,
                    lead_limit=args.lead_limit,
                    timeout=args.timeout,
                    growth_pass=args.growth_pass,
                    scout_leads=args.scout_leads,
                    activation_pass=args.activation_pass,
                    activation_limit=args.activation_limit,
                    send_agent_invites=args.send_agent_invites,
                )
            elif args.mode == "http":
                result = peer.collaborate_over_http(
                    base_url=args.base_url,
                    problem=args.problem,
                    work_leads=args.work_leads,
                    lead_limit=args.lead_limit,
                    timeout=args.timeout,
                    growth_pass=args.growth_pass,
                    scout_leads=args.scout_leads,
                    activation_pass=args.activation_pass,
                    activation_limit=args.activation_limit,
                    send_agent_invites=args.send_agent_invites,
                )
            else:
                result = peer.collaborate_with_local_api(
                    base_url=args.base_url,
                    problem=args.problem,
                    work_leads=args.work_leads,
                    lead_limit=args.lead_limit,
                    timeout=args.timeout,
                )
        elif args.command == "cryptogrift-agent":
            crypto_agent = CryptoGriftGuardAgent(timeout=args.timeout)
            if args.brain:
                result = crypto_agent.engage_nomad_brain(
                    base_url=args.base_url,
                    signal=args.signal,
                )
            elif args.engage:
                result = crypto_agent.engage_nomad(
                    base_url=args.base_url,
                    signal=args.signal,
                    join_first=True,
                    dry_run=not args.connect,
                )
            else:
                result = crypto_agent.connect_to_nomad(
                    base_url=args.base_url,
                    signal=args.signal,
                    dry_run=not args.connect,
                )
        elif args.command == "swarm-spawn":
            result = NomadSwarmSpawner().spawn(
                count=args.count,
                base_url=args.base_url,
                focus=args.focus,
                commit=not args.dry_run,
            )
        elif args.command == "operator-desk":
            from nomad_operator_desk import unlock_desk_snapshot

            result = unlock_desk_snapshot(persist_mission=bool(getattr(args, "persist", False)))
        elif args.command == "operator-sprint":
            from nomad_operator_desk import operator_sprint

            result = operator_sprint(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                persist_mission=bool(getattr(args, "persist", False)),
            )
        elif args.command == "operator-verify":
            from nomad_operator_desk import operator_verify_bundle

            result = operator_verify_bundle(base_url=(getattr(args, "base_url", None) or "").strip())
        elif args.command == "operator-metrics":
            from nomad_operator_desk import operator_metrics_snapshot

            result = operator_metrics_snapshot()
        elif args.command == "operator-daily":
            from nomad_operator_desk import operator_daily_bundle

            result = operator_daily_bundle(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                persist_mission=bool(getattr(args, "persist", False)),
            )
        elif args.command == "operator-report":
            from nomad_operator_desk import operator_iteration_report

            result = operator_iteration_report(tail_lines=int(getattr(args, "tail", 400) or 400))
        elif args.command == "agent-reputation":
            result = NomadAgent().service_desk.reputation_snapshot()
        elif args.command == "unhuman-hub":
            from nomad_unhuman_hub import unhuman_hub_snapshot

            result = unhuman_hub_snapshot(
                agent=NomadAgent(),
                base_url=(getattr(args, "base_url", None) or "").strip(),
                persist_mission=bool(getattr(args, "persist", False)),
            )
        elif args.command == "agent-growth":
            from nomad_agent_growth_pipeline import agent_growth_pipeline

            result = agent_growth_pipeline(
                agent=NomadAgent(),
                query=" ".join(getattr(args, "query", []) or []).strip(),
                limit=int(getattr(args, "limit", 5) or 5),
                base_url=(getattr(args, "base_url", None) or "").strip(),
                run_product_factory=not bool(getattr(args, "no_products", False)),
                send_outreach=bool(getattr(args, "send", False)),
                swarm_feed=False if bool(getattr(args, "no_swarm_feed", False)) else None,
            )
        elif args.command == "agent-native-index":
            from nomad_agent_native_index import agent_native_index

            result = agent_native_index(base_url=(getattr(args, "base_url", None) or "").strip())
        elif args.command == "swarm-helper":
            from nomad_swarm_helper_agent import run_swarm_helper_pass

            result = run_swarm_helper_pass(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                dry_run=not bool(getattr(args, "no_dry_run", False)),
                post_join=bool(getattr(args, "connect", False)),
                post_develop=bool(getattr(args, "develop", False)),
                timeout=float(getattr(args, "timeout", 25) or 25),
                agent_id=(getattr(args, "agent_id", None) or "").strip(),
            )
        elif args.command == "void-observer":
            from nomad_void_observer import run_void_observer_pulse

            result = run_void_observer_pulse(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                timeout=float(getattr(args, "timeout", 25) or 25),
                agent_id=(getattr(args, "agent_id", None) or "").strip(),
            )
        elif args.command == "network-steward":
            from nomad_network_steward_agent import run_network_steward_cycle, run_network_steward_loop

            dry_run = not bool(getattr(args, "no_dry_run", False))
            base = (getattr(args, "base_url", None) or "").strip()
            timeout = float(getattr(args, "timeout", 25) or 25)
            agent_id = (getattr(args, "agent_id", None) or "").strip()
            feed = bool(getattr(args, "feed_swarm", False))
            no_peek = bool(getattr(args, "no_peer_glimpse", False))
            if bool(getattr(args, "loop", False)):
                result = run_network_steward_loop(
                    base_url=base,
                    timeout=timeout,
                    agent_id=agent_id,
                    dry_run=dry_run,
                    feed_swarm=feed,
                    peer_glimpse=not no_peek,
                    post_join=bool(getattr(args, "connect", False)),
                    post_develop=bool(getattr(args, "develop", False)),
                    interval_seconds=float(getattr(args, "interval", 120.0) or 120.0),
                    cycles=int(getattr(args, "cycles", 0) or 0),
                )
            else:
                result = run_network_steward_cycle(
                    base_url=base,
                    timeout=timeout,
                    agent_id=agent_id,
                    dry_run=dry_run,
                    feed_swarm=feed,
                    peer_glimpse=not no_peek,
                    post_join=bool(getattr(args, "connect", False)),
                    post_develop=bool(getattr(args, "develop", False)),
                )
        elif args.command == "machine-blind-spots":
            from nomad_machine_blind_spots import run_machine_blind_spot_pass

            result = run_machine_blind_spot_pass(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                timeout=float(getattr(args, "timeout", 25) or 25),
                agent_id=(getattr(args, "agent_id", None) or "").strip(),
                append_log=bool(getattr(args, "append_log", False)),
                log_path=(getattr(args, "log_path", None) or "").strip(),
            )
        elif args.command == "lead-product-blind-spots":
            from pathlib import Path

            from nomad_lead_product_blind_spots import run_lead_product_blind_spot_pass

            cp = (getattr(args, "conversions_path", None) or "").strip()
            pp = (getattr(args, "products_path", None) or "").strip()
            sp = (getattr(args, "state_path", None) or "").strip()
            result = run_lead_product_blind_spot_pass(
                conversion_path=Path(cp) if cp else None,
                product_path=Path(pp) if pp else None,
                state_path=Path(sp) if sp else None,
                stale_days=int(getattr(args, "stale_days", 21) or 21),
                append_log=bool(getattr(args, "append_log", False)),
                log_path=(getattr(args, "log_path", None) or "").strip(),
            )
        elif args.command == "idempotency-agent-map":
            from nomad_idempotency_agent_map import build_idempotency_agent_map

            result = build_idempotency_agent_map(public_base_hint=(getattr(args, "base_url", None) or "").strip())
        elif args.command == "agent-retry-coach":
            from nomad_agent_retry_coach import run_agent_retry_coach

            result = run_agent_retry_coach(
                edge_log_path=(getattr(args, "edge_log", None) or "").strip(),
                lead_log_path=(getattr(args, "lead_log", None) or "").strip(),
                tail_lines=int(getattr(args, "tail_lines", 96) or 96),
            )
        elif args.command == "mcp-survival-playbook":
            from nomad_mcp_survival_playbook import build_mcp_survival_playbook

            result = build_mcp_survival_playbook()
        elif args.command == "misclassification-audit":
            from pathlib import Path

            from nomad_misclassification_audit import run_misclassification_audit_pass

            cp = (getattr(args, "conversions_path", None) or "").strip()
            pp = (getattr(args, "products_path", None) or "").strip()
            sp = (getattr(args, "state_path", None) or "").strip()
            result = run_misclassification_audit_pass(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                timeout=float(getattr(args, "timeout", 25) or 25),
                agent_id=(getattr(args, "agent_id", None) or "").strip(),
                conversion_path=Path(cp) if cp else None,
                product_path=Path(pp) if pp else None,
                state_path=Path(sp) if sp else None,
                stale_days=int(getattr(args, "stale_days", 21) or 21),
            )
        elif args.command == "growth-start":
            from nomad_operator_desk import operator_growth_start

            result = operator_growth_start(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                persist_mission=bool(getattr(args, "persist", False)),
                lead_query=" ".join(getattr(args, "query", []) or []).strip(),
                skip_leads=bool(getattr(args, "skip_leads", False)),
                skip_verify=bool(getattr(args, "skip_verify", False)),
            )
        elif args.command == "autonomy-step":
            from nomad_operator_desk import operator_autonomy_step

            profile_suffix = f" for {args.profile}" if getattr(args, "profile", None) else ""
            result = operator_autonomy_step(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                persist_mission=bool(getattr(args, "persist", False)),
                lead_query=" ".join(getattr(args, "query", []) or []).strip(),
                skip_growth=bool(getattr(args, "skip_growth", False)),
                growth_skip_verify=bool(getattr(args, "growth_skip_verify", False)),
                growth_skip_leads=not bool(getattr(args, "growth_include_leads", False)),
                swarm_feed=False if bool(getattr(args, "no_swarm_feed", False)) else None,
                cycle_focus=(getattr(args, "cycle_focus", None) or "leads_growth").strip(),
                cycle_objective=str(getattr(args, "cycle_objective", "") or "").strip(),
                profile_suffix=profile_suffix,
            )
        elif args.command == "render-logs":
            from render_hosting import RenderHostingProbe

            result = RenderHostingProbe().list_recent_logs(
                service_id=str(getattr(args, "service_id", "") or "").strip(),
                owner_id=str(getattr(args, "owner_id", "") or "").strip(),
                limit=int(getattr(args, "limit", 40) or 40),
                log_type=str(getattr(args, "log_type", "app") or "app").strip(),
            )
        elif args.command == "lead-calibrate":
            from lead_discovery import LeadDiscoveryScout

            result = LeadDiscoveryScout().calibrate_focus_scout(
                focus=str(getattr(args, "focus", "") or "").strip(),
                query=" ".join(getattr(args, "query", []) or []).strip(),
                limit=int(getattr(args, "limit", 12) or 12),
                candidate_multiplier=int(getattr(args, "candidate_multiplier", 5) or 5),
            )
        else:
            agent = NomadAgent()
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
    mission = subparsers.add_parser("mission", help="Show Nomad Mission Control: blocker, human unlocks, agent tasks, paid-job focus.")
    mission.add_argument("--limit", type=int, default=5)
    mission.add_argument("--preview", action="store_true", help="Do not persist this mission-control snapshot.")

    operator_desk = subparsers.add_parser(
        "operator-desk",
        help="One-screen human unlock queue: copy-paste actions from Mission Control and the self-development journal.",
    )
    operator_desk.add_argument(
        "--persist",
        action="store_true",
        help="Persist Mission Control snapshot when building the desk (default: false).",
    )

    operator_sprint_p = subparsers.add_parser(
        "operator-sprint",
        help="Compact bundle: next actions for public URL, compute lanes, and cashflow (fast; no HTTP verify).",
    )
    operator_sprint_p.add_argument(
        "--base-url",
        default="",
        help="Override public base URL hint for sprint actions (default: mission/env/local).",
    )
    operator_sprint_p.add_argument(
        "--persist",
        action="store_true",
        help="Persist Mission Control when building the embedded operator-desk slice.",
    )

    operator_verify = subparsers.add_parser(
        "operator-verify",
        help="Run health + AgentCard + swarm + service catalog checks against public or local base URL.",
    )
    operator_verify.add_argument(
        "--base-url",
        default="",
        help="Override base URL; default uses NOMAD_PUBLIC_API_URL or local API host/port.",
    )

    subparsers.add_parser(
        "operator-metrics",
        help="Show tail of operator verify events and self-development cycle count.",
    )

    operator_daily = subparsers.add_parser(
        "operator-daily",
        help="Betrieb: verify bundle + unlock desk in one shot; append operator_daily_bundle to metrics JSONL.",
    )
    operator_daily.add_argument(
        "--base-url",
        default="",
        help="Override base URL for checks.",
    )
    operator_daily.add_argument(
        "--persist",
        action="store_true",
        help="Persist Mission Control when building the desk section.",
    )

    operator_report = subparsers.add_parser(
        "operator-report",
        help="Messung/Iteration: aggregate verify and cycle events; write nomad_operator_kpis.json.",
    )
    operator_report.add_argument("--tail", type=int, default=400, help="How many JSONL lines to scan.")

    subparsers.add_parser(
        "agent-reputation",
        help="Contract-first reliability snapshot (boundary compliance and payment progression).",
    )
    unhuman_hub = subparsers.add_parser(
        "unhuman-hub",
        help="Machine-first infrastructure hub: strict boundaries, failover pressure, and risk score.",
    )
    unhuman_hub.add_argument("--base-url", default="", help="Override public base URL for hub checks.")
    unhuman_hub.add_argument(
        "--persist",
        action="store_true",
        help="Persist Mission Control while generating hub snapshot.",
    )

    agent_native_index_p = subparsers.add_parser(
        "agent-native-index",
        help="Boot graph + routing semantics for autonomous agents (GET /.well-known/nomad-agent.json equivalent).",
    )
    agent_native_index_p.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links (default: NOMAD_PUBLIC_API_URL / env).",
    )

    swarm_helper = subparsers.add_parser(
        "swarm-helper",
        help="Probe public Nomad; optionally POST /swarm/join and /swarm/develop to attach a helper agent to the network.",
    )
    swarm_helper.add_argument("--base-url", default="", help="Nomad public root, default NOMAD_PUBLIC_API_URL or syndiode.com.")
    swarm_helper.add_argument(
        "--connect",
        action="store_true",
        help="POST /swarm/join (requires --no-dry-run).",
    )
    swarm_helper.add_argument(
        "--develop",
        action="store_true",
        help="POST /swarm/develop with a bounded self_improvement probe (requires --no-dry-run).",
    )
    swarm_helper.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Allow mutating POSTs when combined with --connect and/or --develop.",
    )
    swarm_helper.add_argument("--timeout", type=float, default=25.0, help="HTTP timeout seconds.")
    swarm_helper.add_argument("--agent-id", default="", help="Override NOMAD_SWARM_HELPER_AGENT_ID for join/develop.")

    void_observer = subparsers.add_parser(
        "void-observer",
        help="GET-only edge coherence fingerprint (sorted path/status); optional drift vs NOMAD_VOID_OBSERVER_BASELINE_SHA256.",
    )
    void_observer.add_argument("--base-url", default="", help="Nomad public root (same default as swarm-helper).")
    void_observer.add_argument("--timeout", type=float, default=25.0, help="HTTP timeout seconds.")
    void_observer.add_argument(
        "--agent-id",
        default="",
        help="Optional; forwarded to swarm-helper lattice for consistency (join still never runs here).",
    )

    network_steward = subparsers.add_parser(
        "network-steward",
        help="Steward pass: lattice GETs, void fingerprint, peer glimpse; optional POST accumulate/join/develop (with --no-dry-run).",
    )
    network_steward.add_argument("--base-url", default="", help="Nomad public root (same default as swarm-helper).")
    network_steward.add_argument("--timeout", type=float, default=25.0, help="HTTP timeout seconds.")
    network_steward.add_argument(
        "--agent-id",
        default="",
        help="Steward id (else NOMAD_NETWORK_STEWARD_AGENT_ID / NOMAD_SWARM_HELPER_AGENT_ID / default).",
    )
    network_steward.add_argument(
        "--feed-swarm",
        action="store_true",
        help="POST /swarm/accumulate to refresh activation queue from server contacts (requires --no-dry-run).",
    )
    network_steward.add_argument(
        "--connect",
        action="store_true",
        help="POST /swarm/join as steward identity (requires --no-dry-run).",
    )
    network_steward.add_argument(
        "--develop",
        action="store_true",
        help="POST /swarm/develop bounded probe (requires --no-dry-run).",
    )
    network_steward.add_argument(
        "--no-peer-glimpse",
        action="store_true",
        help="Skip GET /swarm/ready and /swarm/network.",
    )
    network_steward.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Allow mutating POST when combined with --feed-swarm.",
    )
    network_steward.add_argument(
        "--loop",
        action="store_true",
        help="Repeat steward pass; use --cycles 0 to run until Ctrl+C.",
    )
    network_steward.add_argument("--interval", type=float, default=120.0, help="Seconds between loop iterations.")
    network_steward.add_argument(
        "--cycles",
        type=int,
        default=0,
        help="With --loop: max cycles (0 = until interrupted). Ignored without --loop.",
    )

    machine_blind = subparsers.add_parser(
        "machine-blind-spots",
        help="Second-order edge audit: HTML facades on JSON routes, throttle codes, readiness vs /health divergence.",
    )
    machine_blind.add_argument("--base-url", default="", help="Nomad public root (same default as swarm-helper).")
    machine_blind.add_argument("--timeout", type=float, default=25.0, help="HTTP timeout seconds.")
    machine_blind.add_argument("--agent-id", default="", help="Forwarded to network steward cycle.")
    machine_blind.add_argument(
        "--append-log",
        action="store_true",
        help="Append one compact JSON line to NOMAD_EDGE_COHERENCE_LOG or nomad_autonomous_artifacts/edge_coherence.jsonl.",
    )
    machine_blind.add_argument(
        "--log-path",
        default="",
        help="Override JSONL path for --append-log.",
    )

    lead_product_blind = subparsers.add_parser(
        "lead-product-blind-spots",
        help="Second-order lead/product/pain audit: social URL traps, dedupe forks, stale unproductized rows, pain entropy.",
    )
    lead_product_blind.add_argument(
        "--conversions-path",
        default="",
        help="Override nomad_lead_conversions.json path (default: repo default).",
    )
    lead_product_blind.add_argument(
        "--products-path",
        default="",
        help="Override nomad_products.json path.",
    )
    lead_product_blind.add_argument(
        "--state-path",
        default="",
        help="Override nomad_lead_workbench_state.json path.",
    )
    lead_product_blind.add_argument(
        "--stale-days",
        type=int,
        default=21,
        help="Conversions older than this without a product are flagged stale.",
    )
    lead_product_blind.add_argument(
        "--append-log",
        action="store_true",
        help="Append one compact JSON line to NOMAD_LEAD_COHERENCE_LOG or nomad_autonomous_artifacts/lead_coherence.jsonl.",
    )
    lead_product_blind.add_argument("--log-path", default="", help="Override JSONL path for --append-log.")

    idem_map = subparsers.add_parser(
        "idempotency-agent-map",
        help="Static JSON map: which POST routes are replay-safe, idempotency keys, conflict HTTP codes (for autonomous clients).",
    )
    idem_map.add_argument("--base-url", default="", help="Optional hint echoed as public_base_url_hint.")

    retry_coach = subparsers.add_parser(
        "agent-retry-coach",
        help="Backoff hints from edge_coherence.jsonl + lead_coherence.jsonl tails (run blind-spot --append-log first).",
    )
    retry_coach.add_argument("--edge-log", default="", help="Override edge JSONL path (default NOMAD_EDGE_COHERENCE_LOG or artifact path).")
    retry_coach.add_argument("--lead-log", default="", help="Override lead JSONL path.")
    retry_coach.add_argument("--tail-lines", type=int, default=96, help="Max recent JSONL lines per file (capped at 500).")

    subparsers.add_parser(
        "mcp-survival-playbook",
        help="GitHub-sourced MCP production pain bundle + Nomad product SKU + pattern artifact paths (JSON).",
    )

    misc_audit = subparsers.add_parser(
        "misclassification-audit",
        help="Edge + lead blind spots composed into explicit human-order vs operational-truth misreads (attribution aid).",
    )
    misc_audit.add_argument("--base-url", default="", help="Nomad public root for edge pass (same as swarm-helper).")
    misc_audit.add_argument("--timeout", type=float, default=25.0)
    misc_audit.add_argument("--agent-id", default="", help="Forwarded to machine blind-spot steward chain.")
    misc_audit.add_argument("--conversions-path", default="", help="Optional override for lead JSON.")
    misc_audit.add_argument("--products-path", default="", help="Optional override for products JSON.")
    misc_audit.add_argument("--state-path", default="", help="Optional override for workbench state JSON.")
    misc_audit.add_argument("--stale-days", type=int, default=21)

    agent_growth = subparsers.add_parser(
        "agent-growth",
        help="Scout leads → convert → product factory → swarm prospect feed (one executable pass).",
    )
    agent_growth.add_argument(
        "query",
        nargs="*",
        help="GitHub scout query; empty uses Nomad default wedge queries for the active focus.",
    )
    agent_growth.add_argument("--limit", type=int, default=5, help="Max leads and conversions (1–25).")
    agent_growth.add_argument("--base-url", default="", help="Public API base for swarm feed (or set NOMAD_PUBLIC_API_URL).")
    agent_growth.add_argument(
        "--no-products",
        action="store_true",
        help="Skip product_factory after conversions.",
    )
    agent_growth.add_argument(
        "--send",
        action="store_true",
        help="Request outbound send during conversion (same semantics as convert-leads send).",
    )
    agent_growth.add_argument(
        "--no-swarm-feed",
        action="store_true",
        help="Disable swarm prospect feed for this run (overrides env feed on).",
    )

    growth_start = subparsers.add_parser(
        "growth-start",
        help="Start funnel: operator-daily then one /leads scout (default wedge query); logs operator_growth_start.",
    )
    growth_start.add_argument(
        "query",
        nargs="*",
        help="Optional lead scout query; else NOMAD_GROWTH_LEAD_QUERY or built-in default.",
    )
    growth_start.add_argument("--base-url", default="", help="Base URL for verify/daily.")
    growth_start.add_argument(
        "--persist",
        action="store_true",
        help="Persist Mission Control in the daily section.",
    )
    growth_start.add_argument(
        "--skip-leads",
        action="store_true",
        help="Only run daily bundle; do not call /leads.",
    )
    growth_start.add_argument(
        "--skip-verify",
        action="store_true",
        help="Skip HTTP health/AgentCard/swarm/service checks (desk + leads only).",
    )

    autonomy_step = subparsers.add_parser(
        "autonomy-step",
        help="One autonomy tick: optional growth-start, /leads scout, swarm prospect feed (GitHub repos), leads_growth /cycle.",
    )
    autonomy_step.add_argument(
        "query",
        nargs="*",
        help="Lead scout query; else NOMAD_AUTONOMY_LEAD_QUERY, NOMAD_GROWTH_LEAD_QUERY, or default wedge.",
    )
    autonomy_step.add_argument("--base-url", default="", help="Base URL for growth-start verify/daily.")
    autonomy_step.add_argument(
        "--persist",
        action="store_true",
        help="Persist Mission Control during growth-start.",
    )
    autonomy_step.add_argument(
        "--skip-growth",
        action="store_true",
        help="Skip growth-start; only run /leads then /cycle (faster local iteration).",
    )
    autonomy_step.add_argument(
        "--growth-skip-verify",
        action="store_true",
        help="When growth-start runs, skip HTTP verify (desk only).",
    )
    autonomy_step.add_argument(
        "--growth-include-leads",
        action="store_true",
        help="When growth-start runs, also run its built-in /leads (default skips to avoid duplicate scout).",
    )
    autonomy_step.add_argument(
        "--no-swarm-feed",
        action="store_true",
        help="Do not push scout leads into swarm prospects (default: feed on; set NOMAD_SWARM_FEED_SCOUT_LEADS=0 to disable globally).",
    )
    autonomy_step.add_argument(
        "--cycle-focus",
        default="leads_growth",
        help="nomad_focus theme for the trailing /cycle (default: leads_growth).",
    )
    autonomy_step.add_argument(
        "--cycle-objective",
        default="",
        help="Optional /cycle body after the focus tag; default packages the active lead from scout.",
    )

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
    subparsers.add_parser("modal", help="Show Modal deployment guidance for Nomad's burst-compute lane.")
    subparsers.add_parser("render", help="Verify Render hosting access and show Nomad public API deployment steps.")
    render_logs = subparsers.add_parser(
        "render-logs",
        help="Fetch recent Render logs via REST API (RENDER_API_KEY + NOMAD_RENDER_OWNER_ID + service id).",
    )
    render_logs.add_argument(
        "--service-id",
        default="",
        dest="service_id",
        help="Override NOMAD_RENDER_SERVICE_ID (srv_...).",
    )
    render_logs.add_argument(
        "--owner-id",
        default="",
        dest="owner_id",
        help="Override NOMAD_RENDER_OWNER_ID (workspace/team id).",
    )
    render_logs.add_argument("--limit", type=int, default=40, help="Max log lines (1-100).")
    render_logs.add_argument(
        "--type",
        default="app",
        dest="log_type",
        metavar="LOG_TYPE",
        help="Render log type filter, e.g. app, build, request.",
    )
    subparsers.add_parser("collaboration", help="Show Nomad's outward AI-agent collaboration charter.")
    subparsers.add_parser("mutual-aid-status", help="Show Nomad v3.2 Mutual-Aid self-evolution status.")
    subparsers.add_parser("self-status", help="Show persistent self-development state.")
    subparsers.add_parser("codex-task", help="Render the next Nomad self-development task for Codex.")

    mutual_aid = subparsers.add_parser("mutual-aid", help="Help another agent and let Nomad learn from the result.")
    mutual_aid.add_argument("task", nargs="*")
    mutual_aid.add_argument("--agent", default="public-agent")

    ledger = subparsers.add_parser("mutual-aid-ledger", help="List Nomad's Truth-Density ledger.")
    ledger.add_argument("--pain-type", default="")
    ledger.add_argument("--limit", type=int, default=25)

    inbox = subparsers.add_parser("swarm-inbox", help="List inbound Swarm-to-Swarm proposals.")
    inbox.add_argument("--status", action="append", default=[])
    inbox.add_argument("--limit", type=int, default=25)

    signals = subparsers.add_parser("swarm-signals", help="List inbound agent help converted into development/product signals.")
    signals.add_argument("--pain-type", default="")
    signals.add_argument("--limit", type=int, default=25)

    patterns = subparsers.add_parser("mutual-aid-patterns", help="List repeated high-value Mutual-Aid patterns that Nomad can reuse and productize.")
    patterns.add_argument("--pain-type", default="")
    patterns.add_argument("--limit", type=int, default=10)
    patterns.add_argument("--min-repeat-count", type=int, default=2)

    packs = subparsers.add_parser("mutual-aid-packs", help="List paid packs distilled from repeated Mutual-Aid patterns.")
    packs.add_argument("--pain-type", default="")
    packs.add_argument("--limit", type=int, default=25)

    swarm_propose = subparsers.add_parser("swarm-propose", help="Submit a verifiable proposal from another agent into Nomad's swarm inbox.")
    swarm_propose.add_argument("proposal", nargs="+")
    swarm_propose.add_argument("--agent", default="swarm-agent")
    swarm_propose.add_argument("--pain-type", default="self_improvement")
    swarm_propose.add_argument("--evidence", action="append", default=[])

    unlock = subparsers.add_parser("unlock", help="Generate a concrete human unlock task.")
    unlock.add_argument("category", nargs="?", default="best")

    scout = subparsers.add_parser("scout", help="Scout one infrastructure category.")
    scout.add_argument("category")

    leads = subparsers.add_parser("leads", help="Find public AI-agent infrastructure pain leads.")
    leads.add_argument("query", nargs="*")
    leads.add_argument(
        "--focus",
        default="",
        help="Focus profile id from nomad_lead_sources.json (overrides NOMAD_LEAD_FOCUS for this run).",
    )
    leads.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max leads returned (1–25); omit for Nomad default.",
    )

    lead_calibrate = subparsers.add_parser(
        "lead-calibrate",
        help="GitHub scout for one focus plus min_focus_score sweep (calibrate nomad_lead_sources.json gates).",
    )
    lead_calibrate.add_argument(
        "query",
        nargs="*",
        help="Optional GitHub search query; when empty, uses seed_queries+queries from the focus profile.",
    )
    lead_calibrate.add_argument(
        "--focus",
        default="",
        help="Focus profile id (default: NOMAD_LEAD_FOCUS when set).",
    )
    lead_calibrate.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Lead cap for ranking; raw pool is limit * candidate-multiplier (capped).",
    )
    lead_calibrate.add_argument(
        "--candidate-multiplier",
        type=int,
        default=5,
        dest="candidate_multiplier",
        help="Multiplier for raw GitHub issue pool before ranking (3–10).",
    )

    convert_leads = subparsers.add_parser("convert-leads", help="Convert public leads into agent value packs, safe outreach routes, and customer next steps.")
    convert_leads.add_argument("query", nargs="*")
    convert_leads.add_argument("--limit", type=int, default=5)
    convert_leads.add_argument("--send", action="store_true", help="Send only to eligible public machine-readable agent endpoints.")
    convert_leads.add_argument("--approval", default="", help="Explicit public lead approval scope, e.g. comment or pr_plan.")
    convert_leads.add_argument("--budget", type=float)

    lead_conversions = subparsers.add_parser("lead-conversions", help="List stored lead conversion records.")
    lead_conversions.add_argument("--status", action="append", default=[])
    lead_conversions.add_argument("--limit", type=int, default=25)

    lead_workbench = subparsers.add_parser("lead-workbench", help="Prioritize and privately work Nomad's lead/product queue.")
    lead_workbench.add_argument("--limit", type=int, default=5)
    lead_workbench.add_argument("--work", action="store_true")

    productize = subparsers.add_parser("productize", help="Turn leads or stored lead conversions into reusable Nomad product offers.")
    productize.add_argument("query", nargs="*")
    productize.add_argument("--limit", type=int, default=5)

    products = subparsers.add_parser("products", help="List stored Nomad product offers.")
    products.add_argument("--status", action="append", default=[])
    products.add_argument("--limit", type=int, default=25)

    engagements = subparsers.add_parser("agent-engagements", help="List recorded inbound/outbound agent engagements.")
    engagements.add_argument("--role", action="append", default=[])
    engagements.add_argument("--pain-type", default="")
    engagements.add_argument("--limit", type=int, default=25)

    engagement_summary = subparsers.add_parser("agent-engagement-summary", help="Show a compact summary of agent engagement roles and outcomes.")
    engagement_summary.add_argument("--pain-type", default="")
    engagement_summary.add_argument("--limit", type=int, default=5)

    agent_attractor = subparsers.add_parser("agent-attractor", help="Show Nomad's machine-readable attractor surface for other AI agents.")
    agent_attractor.add_argument("--service-type", default="")
    agent_attractor.add_argument("--role", default="")
    agent_attractor.add_argument("--limit", type=int, default=5)

    swarm_coordinate = subparsers.add_parser("swarm-coordinate", help="Show Nomad's swarm coordination board for AI agents.")
    swarm_coordinate.add_argument("--pain-type", default="")

    swarm_network = subparsers.add_parser("swarm-network", help="Show the active lead network Nomad wants to build around its current agent opportunity.")
    swarm_network.add_argument("--pain-type", default="")
    swarm_network.add_argument("--role", default="")
    swarm_network.add_argument("--limit", type=int, default=5)

    swarm_accumulate = subparsers.add_parser("swarm-accumulate", help="Show or refresh Nomad's accumulated AI-agent prospect pool.")
    swarm_accumulate.add_argument("--pain-type", default="")
    swarm_accumulate.add_argument("--refresh", action="store_true")

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

    service_e2e = subparsers.add_parser("service-e2e", help="Preview or create the full paid Nomad service runway.")
    service_e2e.add_argument("problem", nargs="*")
    service_e2e.add_argument("--task-id", default="")
    service_e2e.add_argument("--service-type", default="")
    service_e2e.add_argument("--budget", type=float)
    service_e2e.add_argument("--agent", default="")
    service_e2e.add_argument("--wallet", default="")
    service_e2e.add_argument("--callback", default="")
    service_e2e.add_argument("--approval", default="draft_only")
    service_e2e.add_argument("--create", action="store_true")

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

    outbound_status = subparsers.add_parser("outbound-status", help="Show Nomad's unified outbound contact and follow-up tracker.")
    outbound_status.add_argument("--limit", type=int, default=10)

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

    cryptogrift_agent = subparsers.add_parser(
        "cryptogrift-agent",
        help="Run CryptoGriftGuard, a safe crypto/payment-risk scout agent that can join Nomad's swarm.",
    )
    cryptogrift_agent.add_argument("--base-url", default="")
    cryptogrift_agent.add_argument("--signal", default="")
    cryptogrift_agent.add_argument("--connect", action="store_true", help="POST to /swarm/join instead of dry-run.")
    cryptogrift_agent.add_argument("--engage", action="store_true", help="Also call /swarm/develop with a bounded development request.")
    cryptogrift_agent.add_argument("--brain", action="store_true", help="Engage Nomad's local registry and development exchange directly.")
    cryptogrift_agent.add_argument("--timeout", type=float, default=45.0)

    codex_peer_agent = subparsers.add_parser(
        "codex-peer-agent",
        help="Run CodexPeerAgent as a bounded peer that joins Nomad and works the next useful blocker.",
    )
    codex_peer_agent.add_argument("--base-url", default="")
    codex_peer_agent.add_argument("--problem", default="")
    codex_peer_agent.add_argument("--mode", choices=["http", "local-api"], default="local-api")
    codex_peer_agent.add_argument("--loop", action="store_true", help="Run repeated HTTP-only worker cycles.")
    codex_peer_agent.add_argument("--cycles", type=int, default=3, help="Worker cycles; 0 means run until stopped.")
    codex_peer_agent.add_argument("--interval", type=float, default=30.0, help="Seconds between worker cycles.")
    codex_peer_agent.add_argument("--growth-pass", action=argparse.BooleanOptionalAction, default=True)
    codex_peer_agent.add_argument("--scout-leads", action=argparse.BooleanOptionalAction, default=False)
    codex_peer_agent.add_argument("--activation-pass", action=argparse.BooleanOptionalAction, default=True)
    codex_peer_agent.add_argument("--activation-limit", type=int, default=3, help="A2A prospects to activate per cycle; 0 means the full current activation queue.")
    codex_peer_agent.add_argument("--send-agent-invites", action=argparse.BooleanOptionalAction, default=False)
    codex_peer_agent.add_argument("--work-leads", action=argparse.BooleanOptionalAction, default=True)
    codex_peer_agent.add_argument("--lead-limit", type=int, default=3)
    codex_peer_agent.add_argument("--timeout", type=float, default=20.0)

    swarm_spawn = subparsers.add_parser(
        "swarm-spawn",
        help="Spawn bounded local specialist agents into Nomad's swarm registry.",
    )
    swarm_spawn.add_argument("--count", type=int, default=24)
    swarm_spawn.add_argument("--base-url", default="")
    swarm_spawn.add_argument("--focus", default="agent_blocker_resolution")
    swarm_spawn.add_argument("--dry-run", action="store_true", help="Build join payloads without registering them.")

    cycle = subparsers.add_parser("cycle", help="Run a bounded self-improvement cycle.")
    cycle.add_argument("objective", nargs="*")
    cycle.add_argument(
        "--focus",
        default="",
        help="Single-objective mode for this cycle (also set NOMAD_SELF_IMPROVEMENT_FOCUS for a default).",
    )

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
