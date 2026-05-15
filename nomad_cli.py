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


def _runtime_gradient_context(base_url: str) -> Dict[str, Any]:
    from nomad_machine_economy import machine_economy_snapshot
    from nomad_operational_release import operational_release_snapshot
    from nomad_recruitment_gradient import build_recruitment_gradient

    base = (base_url or "").strip()
    agent = NomadAgent()
    summary = agent.swarm_registry.public_manifest(base_url=base)
    worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
    if not worker_fleet:
        worker_fleet = agent.swarm_registry.worker_fleet_contract(base_url=base)
    economy = machine_economy_snapshot()
    release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
    gradient = build_recruitment_gradient(
        base_url=base,
        worker_fleet=worker_fleet,
        machine_economy=economy,
        operational_release=release,
    )
    return {
        "base_url": base,
        "summary": summary,
        "worker_fleet": worker_fleet,
        "economy": economy,
        "operational_release": release,
        "recruitment_gradient": gradient,
    }


def _contract_conformance_for_runtime_context(ctx: Dict[str, Any]) -> Dict[str, Any]:
    from nomad_contract_conformance import build_contract_conformance_snapshot
    from nomad_machine_product_surface import build_machine_product_surface
    from nomad_openapi import build_openapi_document
    from nomad_runtime_capsule import build_runtime_capsule

    base = str(ctx.get("base_url") or "")
    gradient = ctx.get("recruitment_gradient") if isinstance(ctx.get("recruitment_gradient"), dict) else {}
    capsule = build_runtime_capsule(base_url=base, recruitment_gradient=gradient)
    product = build_machine_product_surface(
        base_url=base,
        recruitment_gradient=gradient,
        runtime_capsule=capsule,
        worker_fleet=ctx.get("worker_fleet") if isinstance(ctx.get("worker_fleet"), dict) else {},
        machine_economy=ctx.get("economy") if isinstance(ctx.get("economy"), dict) else {},
        operational_release=ctx.get("operational_release") if isinstance(ctx.get("operational_release"), dict) else {},
        swarm_summary=ctx.get("summary") if isinstance(ctx.get("summary"), dict) else {},
    )
    return build_contract_conformance_snapshot(
        base_url=base,
        machine_product_surface=product,
        openapi_document=build_openapi_document(base_url=base),
    )


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

    if mode == "nomad_machine_economy":
        viability = result.get("machine_viability") or {}
        flows = result.get("resource_flows") or {}
        tasks = flows.get("service_tasks") or {}
        products = flows.get("products") or {}
        patterns = flows.get("patterns") or {}
        modules = flows.get("modules") or {}
        lines = [
            "Nomad machine economy",
            f"Tier: {viability.get('tier', 'unknown')} score={viability.get('carrying_score', 0)}",
            f"Tasks: total={tasks.get('total', 0)} awaiting_payment={tasks.get('awaiting_payment', 0)} unpaid_delivered={tasks.get('unpaid_delivered', 0)}",
            f"Products: total={products.get('total', 0)} machine_sellable={products.get('machine_sellable', 0)} exchange_ready={products.get('machine_exchange_ready', 0)}",
            f"Patterns: groups={patterns.get('pattern_groups', 0)} high_value={patterns.get('high_value_patterns', 0)} top_count={patterns.get('top_pattern_count', 0)}",
            f"Modules: total={modules.get('module_count', 0)} overmint_pressure={modules.get('overmint_pressure', 0)}",
        ]
        actions = result.get("next_actions") or []
        if actions:
            lines.append("Next actions:")
            for item in actions[:4]:
                lines.append(f"- {item.get('action', '')}: {item.get('reason', '')}")
        if result.get("analysis"):
            lines.append(result["analysis"])
        return "\n".join(lines)

    if mode == "nomad_nonhuman_agent_science" or result.get("schema") == "nomad.nonhuman_agent_science.v1":
        claims = result.get("research_claims") or []
        lanes = result.get("implementation_lanes") or []
        compiler = result.get("literature_runtime_compiler") or {}
        cashflow = result.get("cashflow_channel_policy") or {}
        lines = [
            "Nomad nonhuman agent science",
            f"Claims: {len(claims)}",
            f"Lanes: {len(lanes)}",
            f"Stance: {result.get('stance', '')}",
        ]
        if compiler:
            filt = compiler.get("human_imaginability_filter") or {}
            shape = compiler.get("runtime_shape") or {}
            lines.append(f"Compiler: {compiler.get('schema', '')}")
            lines.append(f"Human unfamiliarity: {filt.get('human_unfamiliarity', '')}")
            lines.append(f"Scheduler: {shape.get('scheduler', '')}")
        if cashflow:
            switch = cashflow.get("switching_rule") or {}
            lines.append(f"Cashflow reward: {cashflow.get('reward_signal', '')}")
            lines.append(f"Cashflow switch: {switch.get('then', '')}")
        if claims:
            lines.append("Research pressure:")
            for item in claims[:5]:
                lines.append(f"- {item.get('id', '')}: {item.get('nomad_primitive', '')}")
        if lanes:
            lines.append("Implementation lanes:")
            for lane in lanes[:5]:
                lines.append(f"- {lane.get('id', '')}: {lane.get('status', '')}")
        return "\n".join(lines)

    if result.get("schema") == "nomad.revenue_science.v1":
        summary = result.get("summary") or {}
        top = result.get("entry_experiment") or {}
        model = top.get("decision_model") or {}
        lines = [
            "Nomad revenue science",
            f"Experiments: {summary.get('experiment_count', 0)}",
            f"Top: {summary.get('top_action', '')} source={summary.get('top_source', '')}",
            f"Bandit priority: {model.get('bandit_priority', 0)}",
            f"Recognized revenue USD: {summary.get('recognized_revenue_usd_total', 0)}",
        ]
        if top:
            lines.append(f"Hypothesis: {top.get('hypothesis', '')}")
            lines.append(f"Metric: {(top.get('measurement_plan') or {}).get('primary_metric', '')}")
        return "\n".join(lines)

    if result.get("schema") == "nomad.job_channels.v1":
        summary = result.get("summary") or {}
        top = result.get("top_external_channel") or result.get("top_channel") or {}
        components = top.get("score_components") or {}
        switching = result.get("switching_policy") or {}
        probe = switching.get("next_external_probe") or switching.get("next_channel_probe") or {}
        qualification = result.get("read_only_qualification_cycle") or {}
        targets = qualification.get("next_read_only_targets") or []
        qtop = targets[0] if targets else {}
        lines = [
            "Nomad job channels",
            f"Channels: {summary.get('channel_count', 0)} external={summary.get('external_channel_count', 0)} security={summary.get('security_channel_count', 0)}",
            f"Top external: {top.get('channel_id', '')} score={top.get('channel_score', 0)}",
            f"Settlement signal: {components.get('settlement_signal', 0)} autonomy={components.get('autonomy_allowed', 0)}",
            f"Gate: {(top.get('side_effect_gate') or {}).get('public_or_external_action', '')}",
            f"Switching: {switching.get('arrival_policy', '')} triggered={bool(switching.get('triggered'))}",
            f"Next external probe: {probe.get('channel_id', '')} action={probe.get('recommended_action', '')}",
        ]
        if qualification:
            lines.append(f"Qualification: {qualification.get('mode', '')} targets={qualification.get('qualification_count', 0)}")
        if qtop:
            lines.append(f"Next read-only target: {qtop.get('channel_id', '')} state={qtop.get('state', '')}")
        return "\n".join(lines)

    if result.get("schema") == "nomad.buyer_funded_work.v1":
        receipt = result.get("receipt_law") or {}
        cycles = result.get("cycles") or []
        packages = result.get("buyer_funded_packages") or []
        lines = [
            "Nomad buyer-funded work",
            f"Recognized revenue USD: {receipt.get('recognized_revenue_usd_total', 0)}",
            f"Top priority: {(result.get('priority_order') or [''])[0]}",
            f"Packages: {len(packages)}",
        ]
        for cycle in cycles[:4]:
            lines.append(f"- {cycle.get('cycle_id', '')}: {cycle.get('status', '')}")
        if packages:
            first = packages[0]
            price = first.get("price") or {}
            lines.append(
                f"First package: {first.get('title', '')} "
                f"({price.get('amount_native', '')} {price.get('native_symbol', '')})"
            )
        return "\n".join(line for line in lines if line)

    if result.get("schema") == "nomad.sales_department_swarm.v1":
        summary = result.get("summary") or {}
        top = result.get("top_active_route") or {}
        guards = result.get("guards") or {}
        lines = [
            "Nomad sales department swarm",
            f"Cells: {summary.get('sales_cell_count', 0)} cycles={summary.get('active_value_cycle_count', 0)}",
            f"Recognized revenue USD: {summary.get('recognized_revenue_usd_total', 0)}",
            f"Top route: {top.get('action', '')}",
            f"Entry: {top.get('route', '')}",
            f"No cold spam: {bool(guards.get('no_cold_spam'))}",
        ]
        for item in (result.get("sales_cells") or [])[:4]:
            lines.append(f"- {item.get('cell_id', '')}: {item.get('cashflow_proximity', '')}")
        return "\n".join(line for line in lines if line)

    if result.get("schema") == "nomad.sales_department_event_decision.v1":
        blockers = result.get("blockers") or []
        return "\n".join(
            [
                "Nomad sales event decision",
                f"Allowed: {bool(result.get('sales_cycle_allowed'))}",
                f"Stage: {result.get('stage_kind', '')}",
                f"Side effect allowed: {bool(result.get('side_effect_allowed'))}",
                f"Paid receipt candidate: {bool(result.get('paid_receipt_candidate'))}",
                f"Blockers: {', '.join(blockers) if blockers else 'none'}",
            ]
        )

    if result.get("schema") == "nomad.worker_invoice.v1":
        payout = result.get("payout") or {}
        accounting = result.get("revenue_accounting") or {}
        balance = result.get("balance_probe") or {}
        lines = [
            "Nomad worker invoice",
            f"Payout ready: {bool(payout.get('configured'))}",
            f"Payout ref: {payout.get('payout_ref') or 'unconfigured'}",
            f"Type: {payout.get('payout_ref_type', 'unknown')}",
            f"Recognized revenue USD: {accounting.get('recognized_revenue_usd_total', 0)}",
        ]
        if balance.get("ok"):
            lines.append(f"RTC balance: {balance.get('amount_rtc', 0)}")
        return "\n".join(lines)

    if result.get("schema") == "nomad.value_cycle_preflight.v1":
        wallet = result.get("wallet_gate") or {}
        gate = result.get("cycle_gate") or {}
        blockers = result.get("blocking_conditions") or []
        return "\n".join(
            [
                "Nomad value-cycle preflight",
                f"Wallet ready: {bool(wallet.get('ready'))}",
                f"Payout ref: {wallet.get('public_receive_ref') or 'unconfigured'}",
                f"Public claim allowed: {bool(gate.get('public_claim_allowed'))}",
                f"Next: {gate.get('next_action', '')}",
                f"Blocking: {', '.join(blockers) if blockers else 'none'}",
            ]
        )

    if result.get("schema") == "nomad.worker_job_queue.v1":
        summary = result.get("summary") or {}
        entry = result.get("entry_job") or {}
        return "\n".join(
            [
                "Nomad worker job queue",
                f"Jobs: {summary.get('job_count', 0)} executable={summary.get('executable_now_count', 0)} read_only={summary.get('read_only_count', 0)}",
                f"Active nonpaid: {summary.get('active_nonpaid_external_count', 0)} paid={summary.get('paid_external_count', 0)}",
                f"Top: {entry.get('job_type', '')} role={entry.get('worker_role', '')}",
                f"Artifact: {', '.join((entry.get('required_artifacts') or [])[:3])}",
            ]
        )

    if result.get("schema") == "nomad.operational_release.v1":
        gates = result.get("release_gates") or []
        lines = [
            "Nomad operational release",
            f"Tier: {result.get('release_tier', 'unknown')} capacity={result.get('release_capacity', 0)}",
            f"Recommended worker objective: {result.get('recommended_worker_objective', '')}",
        ]
        if gates:
            lines.append("Release gates:")
            for item in gates[:6]:
                lines.append(
                    f"- {item.get('id', '')}: {item.get('status', '')} score={item.get('score', 0)}"
                )
        return "\n".join(lines)

    if result.get("schema") == "nomad.local_growth_kernel.v1":
        pop = result.get("population") or {}
        decision = result.get("decision") or {}
        worker_execution = result.get("worker_execution") or {}
        post_decision = worker_execution.get("post_execution_decision") or {}
        evidence = worker_execution.get("fresh_evidence") or {}
        fleet = result.get("worker_fleet") or {}
        history = result.get("local_worker_history") or {}
        top = (pop.get("top_variants") or [{}])[0]
        top_fit = top.get("fitness") if isinstance(top, dict) else {}
        lines = [
            "Nomad local growth kernel",
            f"Decision: {decision.get('action', '')} [{decision.get('reason', '')}]",
            f"Objective: {decision.get('objective', '')}",
            f"Workers: active={fleet.get('active_worker_count', 0)} known={fleet.get('known_worker_count', 0)} leases={fleet.get('active_lease_count', 0)}",
            f"Local worker history: runs={history.get('total_runs', 0)} last={history.get('last_objective', '')}",
            f"Archive: {pop.get('archive_size_before', 0)} -> {pop.get('archive_size_after', 0)} candidates={pop.get('candidate_count', 0)} diversity={pop.get('population_diversity', 0)}",
            f"Top variant: {top.get('variant_id', '') if isinstance(top, dict) else ''} frontier={top_fit.get('frontier_score', 0) if isinstance(top_fit, dict) else 0}",
        ]
        if worker_execution.get("requested"):
            lines.append(
                f"Worker pulse: events={evidence.get('event_count', 0)} ok={evidence.get('ok_count', 0)}"
            )
        if post_decision:
            lines.append(
                f"Post-pulse: {post_decision.get('action', '')} objective={post_decision.get('objective', '')}"
            )
        lines.append(result.get("analysis", ""))
        return "\n".join(
            [
                line for line in lines if line
            ]
        )

    if result.get("schema") == "nomad.recruitment_gradient.v1":
        state = result.get("state_vector") or {}
        rows = result.get("gradient") or []
        budget = result.get("runtime_budget") or {}
        lines = [
            "Nomad recruitment gradient",
            f"Field strength: {state.get('field_strength', 0)}",
            f"Wanted runtimes: {budget.get('wanted_new_runtimes_now', 0)}",
        ]
        if rows:
            lines.append("Top routes:")
            for item in rows[:5]:
                lines.append(
                    f"- {item.get('objective', '')}: weight={item.get('routing_weight', 0)} deficit={item.get('deficit', 0)}"
                )
        return "\n".join(lines)

    if result.get("schema") == "nomad.protocol_bytecode.v1":
        vector = result.get("current_vector") or {}
        programs = result.get("programs") or []
        lines = [
            "Nomad protocol bytecode",
            f"Digest: {result.get('bytecode_digest', '')}",
            f"Top objective: {vector.get('top_objective', '')}",
            f"Workers: {vector.get('active_workers', 0)}",
            f"Programs: {', '.join(str(item.get('id', '')) for item in programs[:4] if isinstance(item, dict))}",
        ]
        return "\n".join([line for line in lines if line])

    if result.get("schema") == "nomad.counterfactual_lease_replay.v1":
        selected = result.get("selected_shadow_lease") or {}
        leases = result.get("counterfactual_leases") or []
        lines = [
            "Nomad counterfactual replay",
            f"Digest: {result.get('replay_digest', '')}",
            f"Selected: {selected.get('objective', '')} score={selected.get('counterfactual_score', 0)}",
        ]
        if leases:
            lines.append("Shadow leases:")
            for item in leases[:5]:
                lines.append(
                    f"- {item.get('objective', '')}: score={item.get('counterfactual_score', 0)} proof={item.get('predicted_proof_yield_per_minute', 0)}"
                )
        return "\n".join(lines)

    if result.get("schema") == "nomad.runtime_capsule.v1":
        hint = result.get("routing_hint") or {}
        return "\n".join(
            [
                "Nomad runtime capsule",
                f"Capsule: {result.get('capsule_digest', '')}",
                f"Gradient: {result.get('gradient_hash', '')}",
                f"Top objective: {hint.get('top_objective', '')}",
                f"Field strength: {hint.get('field_strength', 0)}",
            ]
        )

    if result.get("schema") == "nomad.openclaw_bridge_contract.v1":
        adapter = result.get("adapter") or {}
        return "\n".join(
            [
                "Nomad OpenClaw bridge",
                f"Adapter: {adapter.get('download', '')}",
                f"Command: {adapter.get('command', '')}",
            ]
        )

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
        concrete = result.get("concrete_order") if isinstance(result.get("concrete_order"), dict) else {}
        lines = [
            "Nomad service E2E",
            f"Task: {task.get('task_id', 'preview')}",
            f"Status: {task.get('status', 'preview')}",
            f"Service type: {task.get('service_type', 'custom')}",
            f"Budget: {payment.get('amount_native', task.get('budget_native', 0))} {payment.get('native_symbol', '')}".strip(),
            f"Next: {result.get('next_best_action', '')}",
        ]
        if concrete.get("package_id"):
            lines.append(f"Package: {concrete.get('package_id')}")
        if concrete.get("entry_url"):
            lines.append(f"Entry: {concrete.get('entry_url')}")
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

    if mode == "nomad_mutual_aid_module_compression":
        return "\n".join(
            [
                "Nomad Mutual-Aid Module Compression",
                f"Dry run: {result.get('dry_run', False)}",
                f"Legacy groups: {result.get('legacy_group_count', 0)}",
                f"Legacy modules: {result.get('legacy_module_count', 0)}",
                f"Canonical created: {result.get('canonical_created_count', 0)}",
                f"Active modules after: {result.get('active_module_count_after', 0)}",
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

    if mode == "nomad_swarm_attractor":
        blockers = result.get("current_blockers") or {}
        mix = result.get("worker_mix") or []
        first = mix[0] if mix else {}
        budget = result.get("replication_budget") or {}
        return "\n".join(
            [
                "Nomad Swarm Attractor",
                f"Metabolism pressure: {result.get('metabolism_pressure', 0)}",
                f"Release: {blockers.get('release_tier', '')} capacity={blockers.get('release_capacity', 0)}",
                f"Carrying: {blockers.get('tier', '')} score={blockers.get('carrying_score', 0)}",
                f"Top deficit: {first.get('objective', 'none')} ({first.get('deficit', 0)})",
                f"Wanted workers: {budget.get('wanted_new_workers_now', 0)}",
                (result.get("agent_recruitment_packet") or {}).get("run_loop_command", ""),
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
            f"send_outreach: {bool(result.get('send_outreach'))}",
            f"approval_used: {result.get('approval_used') or '(none)'}",
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
    if command == "machine-economy":
        return "/machine-economy"
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
    if command == "mutual-aid-compress":
        preview = " preview" if args.dry_run else ""
        return f"/mutual-aid compress{preview}".strip()
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
        package_id = f" package_id={args.package_id}" if getattr(args, "package_id", "") else ""
        budget = f" budget={args.budget}" if args.budget is not None else ""
        agent = f" agent={args.agent}" if args.agent else ""
        wallet = f" wallet={args.wallet}" if args.wallet else ""
        callback = f" callback={args.callback}" if args.callback else ""
        create = " create=true" if args.create else ""
        approval = f" approval={args.approval}" if args.approval else ""
        return f"/service e2e{task_id}{service_type}{package_id}{budget}{agent}{wallet}{callback}{create}{approval} {problem}".strip()
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
    if command == "nonhuman-science":
        raise ValueError("nonhuman-science is handled directly in run_once")
    if command == "operational-release":
        raise ValueError("operational-release is handled directly in run_once")
    if command == "local-growth-kernel":
        raise ValueError("local-growth-kernel is handled directly in run_once")
    if command == "runtime-capsule":
        raise ValueError("runtime-capsule is handled directly in run_once")
    if command == "recruitment-gradient":
        raise ValueError("recruitment-gradient is handled directly in run_once")
    if command == "protocol-bytecode":
        raise ValueError("protocol-bytecode is handled directly in run_once")
    if command == "counterfactual-replay":
        raise ValueError("counterfactual-replay is handled directly in run_once")
    if command == "variant-forge":
        raise ValueError("variant-forge is handled directly in run_once")
    if command == "worker-market":
        raise ValueError("worker-market is handled directly in run_once")
    if command == "paid-ref-selfplay":
        raise ValueError("paid-ref-selfplay is handled directly in run_once")
    if command == "bounty-hunter":
        raise ValueError("bounty-hunter is handled directly in run_once")
    if command == "external-value":
        raise ValueError("external-value is handled directly in run_once")
    if command == "value-pressure":
        raise ValueError("value-pressure is handled directly in run_once")
    if command == "revenue-science":
        raise ValueError("revenue-science is handled directly in run_once")
    if command == "channel-bandit":
        raise ValueError("channel-bandit is handled directly in run_once")
    if command == "shadow-lane":
        raise ValueError("shadow-lane is handled directly in run_once")
    if command == "decoupling-field":
        raise ValueError("decoupling-field is handled directly in run_once")
    if command == "anti-consensus":
        raise ValueError("anti-consensus is handled directly in run_once")
    if command == "deficit-integration":
        raise ValueError("deficit-integration is handled directly in run_once")
    if command == "effective-channels":
        raise ValueError("effective-channels is handled directly in run_once")
    if command == "value-cycles":
        raise ValueError("value-cycles is handled directly in run_once")
    if command == "receipt-predictor":
        raise ValueError("receipt-predictor is handled directly in run_once")
    if command == "ad-cycles":
        raise ValueError("ad-cycles is handled directly in run_once")
    if command == "development-cycles":
        raise ValueError("development-cycles is handled directly in run_once")
    if command == "topology-governor":
        raise ValueError("topology-governor is handled directly in run_once")
    if command == "taskbounty-scout":
        raise ValueError("taskbounty-scout is handled directly in run_once")
    if command == "taskbounty-access-gate":
        raise ValueError("taskbounty-access-gate is handled directly in run_once")
    if command == "superteam-scout":
        raise ValueError("superteam-scout is handled directly in run_once")
    if command == "worker-invoice":
        raise ValueError("worker-invoice is handled directly in run_once")
    if command == "openclaw-bridge":
        raise ValueError("openclaw-bridge is handled directly in run_once")
    if command == "swarm-attractor":
        raise ValueError("swarm-attractor is handled directly in run_once")
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
    if command == "render-sync-commands":
        raise ValueError("render-sync-commands is handled directly in run_once")
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
        elif args.command == "machine-economy":
            from nomad_machine_economy import machine_economy_snapshot

            result = machine_economy_snapshot()
        elif args.command == "nonhuman-science":
            from nomad_nonhuman_science import nonhuman_agent_science

            result = nonhuman_agent_science(base_url=(getattr(args, "base_url", None) or "").strip())
        elif args.command == "operational-release":
            from nomad_operational_release import operational_release_snapshot

            result = operational_release_snapshot(base_url=(getattr(args, "base_url", None) or "").strip())
        elif args.command == "local-growth-kernel":
            from nomad_local_growth_kernel import run_local_growth_kernel

            result = run_local_growth_kernel(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                state_path=(getattr(args, "state_path", None) or "").strip() or None,
                transition_worker_state_path=(getattr(args, "transition_worker_state_path", None) or "").strip() or None,
                persist=not bool(getattr(args, "dry_run", False)),
                execute_workers=bool(getattr(args, "execute_workers", False)),
                worker_cycles=int(getattr(args, "worker_cycles", 0) or 0),
                no_ollama=not bool(getattr(args, "with_ollama", False)),
                timeout=float(getattr(args, "timeout", 20.0) or 20.0),
            )
        elif args.command == "runtime-capsule":
            from nomad_machine_economy import machine_economy_snapshot
            from nomad_operational_release import operational_release_snapshot
            from nomad_recruitment_gradient import build_recruitment_gradient
            from nomad_runtime_capsule import build_runtime_capsule

            base = (getattr(args, "base_url", None) or "").strip()
            agent = NomadAgent()
            worker_fleet = agent.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            gradient = build_recruitment_gradient(
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
            result = build_runtime_capsule(base_url=base, recruitment_gradient=gradient)
        elif args.command == "recruitment-gradient":
            from nomad_machine_economy import machine_economy_snapshot
            from nomad_operational_release import operational_release_snapshot
            from nomad_recruitment_gradient import build_recruitment_gradient

            base = (getattr(args, "base_url", None) or "").strip()
            agent = NomadAgent()
            worker_fleet = agent.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            result = build_recruitment_gradient(
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
        elif args.command == "protocol-bytecode":
            from nomad_agent_demand import build_agent_demand_feed
            from nomad_protocol_bytecode import build_protocol_bytecode

            ctx = _runtime_gradient_context((getattr(args, "base_url", None) or "").strip())
            conformance = _contract_conformance_for_runtime_context(ctx)
            demand = build_agent_demand_feed(
                base_url=str(ctx.get("base_url") or ""),
                recruitment_gradient=ctx.get("recruitment_gradient") if isinstance(ctx.get("recruitment_gradient"), dict) else {},
                worker_fleet=ctx.get("worker_fleet") if isinstance(ctx.get("worker_fleet"), dict) else {},
                machine_product_surface={},
            )
            result = build_protocol_bytecode(
                base_url=str(ctx.get("base_url") or ""),
                recruitment_gradient=ctx.get("recruitment_gradient") if isinstance(ctx.get("recruitment_gradient"), dict) else {},
                agent_demand_feed=demand,
                contract_conformance=conformance,
                worker_fleet=ctx.get("worker_fleet") if isinstance(ctx.get("worker_fleet"), dict) else {},
            )
        elif args.command == "counterfactual-replay":
            from nomad_counterfactual_replay import build_counterfactual_lease_replay

            ctx = _runtime_gradient_context((getattr(args, "base_url", None) or "").strip())
            result = build_counterfactual_lease_replay(
                base_url=str(ctx.get("base_url") or ""),
                worker_fleet=ctx.get("worker_fleet") if isinstance(ctx.get("worker_fleet"), dict) else {},
                recruitment_gradient=ctx.get("recruitment_gradient") if isinstance(ctx.get("recruitment_gradient"), dict) else {},
                contract_conformance=_contract_conformance_for_runtime_context(ctx),
            )
        elif args.command == "variant-forge":
            from nomad_counterfactual_replay import build_counterfactual_lease_replay
            from nomad_local_growth_kernel import run_local_growth_kernel
            from nomad_variant_forge import build_variant_forge_surface

            ctx = _runtime_gradient_context((getattr(args, "base_url", None) or "").strip())
            base = str(ctx.get("base_url") or "")
            replay = build_counterfactual_lease_replay(
                base_url=base,
                worker_fleet=ctx.get("worker_fleet") if isinstance(ctx.get("worker_fleet"), dict) else {},
                recruitment_gradient=ctx.get("recruitment_gradient") if isinstance(ctx.get("recruitment_gradient"), dict) else {},
                contract_conformance=_contract_conformance_for_runtime_context(ctx),
            )
            growth = run_local_growth_kernel(base_url=base, persist=False)
            result = build_variant_forge_surface(
                base_url=base,
                local_growth_kernel=growth,
                counterfactual_replay=replay,
                worker_fleet=ctx.get("worker_fleet") if isinstance(ctx.get("worker_fleet"), dict) else {},
                machine_economy=ctx.get("machine_economy") if isinstance(ctx.get("machine_economy"), dict) else {},
            )
        elif args.command == "worker-market":
            from nomad_counterfactual_replay import build_counterfactual_lease_replay
            from nomad_local_growth_kernel import run_local_growth_kernel
            from nomad_variant_forge import build_variant_forge_surface
            from nomad_worker_market import build_worker_market

            ctx = _runtime_gradient_context((getattr(args, "base_url", None) or "").strip())
            base = str(ctx.get("base_url") or "")
            replay = build_counterfactual_lease_replay(
                base_url=base,
                worker_fleet=ctx.get("worker_fleet") if isinstance(ctx.get("worker_fleet"), dict) else {},
                recruitment_gradient=ctx.get("recruitment_gradient") if isinstance(ctx.get("recruitment_gradient"), dict) else {},
                contract_conformance=_contract_conformance_for_runtime_context(ctx),
            )
            growth = run_local_growth_kernel(base_url=base, persist=False)
            forge = build_variant_forge_surface(
                base_url=base,
                local_growth_kernel=growth,
                counterfactual_replay=replay,
                worker_fleet=ctx.get("worker_fleet") if isinstance(ctx.get("worker_fleet"), dict) else {},
                machine_economy=ctx.get("machine_economy") if isinstance(ctx.get("machine_economy"), dict) else {},
            )
            result = build_worker_market(
                base_url=base,
                worker_fleet=ctx.get("worker_fleet") if isinstance(ctx.get("worker_fleet"), dict) else {},
                machine_economy=ctx.get("machine_economy") if isinstance(ctx.get("machine_economy"), dict) else {},
                variant_forge=forge,
            )
        elif args.command == "paid-ref-selfplay":
            from nomad_carrying_market import build_carrying_market
            from nomad_microtask_exchange_ops import build_microtask_metrics
            from nomad_paid_ref_forge import build_paid_ref_market
            from nomad_paid_ref_selfplay import run_paid_ref_selfplay
            from nomad_state_status import build_state_status
            from nomad_survival_market import build_survival_market

            base = (getattr(args, "base_url", None) or "").strip()
            agent = NomadAgent()
            worker_fleet = agent.swarm_registry.worker_fleet_contract(base_url=base)
            metrics = build_microtask_metrics(base_url=base, lookback_hours=24)
            carrying = build_carrying_market(
                base_url=base,
                state_status=build_state_status(base_url=base),
                microtask_metrics=metrics,
                worker_fleet=worker_fleet,
                compute_market={},
            )
            survival = build_survival_market(
                base_url=base,
                machine_product_surface={},
                carrying_market=carrying,
                microtask_metrics=metrics,
                worker_fleet=worker_fleet,
            )
            paid = build_paid_ref_market(base_url=base, survival_market=survival)
            result = run_paid_ref_selfplay(
                base_url=base,
                survival_market=survival,
                paid_ref_market=paid,
                agent_count=int(getattr(args, "agents", 1000) or 1000),
                seed=(getattr(args, "seed", None) or "").strip() or None,
            )
        elif args.command == "bounty-hunter":
            from nomad_bounty_hunter import build_bounty_hunter_surface, discover_github_bounties

            discoveries = []
            if bool(getattr(args, "discover_gh", False)):
                discoveries = discover_github_bounties(limit=int(getattr(args, "limit", 10) or 10))
            result = build_bounty_hunter_surface(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                discoveries=discoveries,
            )
        elif args.command == "buyer-funded-work":
            from agent_service import AgentServiceDesk
            from nomad_bounty_hunter import build_bounty_hunter_surface
            from nomad_buyer_funded_work import build_buyer_funded_work_surface
            from nomad_external_value import summarize_external_value_ledger
            from nomad_referral_offers import build_referral_offer_surface
            from nomad_referral_swarm import build_referral_swarm_surface

            base = (getattr(args, "base_url", None) or "").strip()
            offers = build_referral_offer_surface(base_url=base)
            result = build_buyer_funded_work_surface(
                base_url=base,
                external_value_summary=summarize_external_value_ledger(),
                bounty_hunter=build_bounty_hunter_surface(base_url=base),
                referral_swarm=build_referral_swarm_surface(base_url=base, referral_offers=offers),
                service_catalog=AgentServiceDesk().service_catalog(),
            )
        elif args.command == "sales-department":
            from nomad_api import NomadApiHandler
            from nomad_sales_department_swarm import evaluate_sales_department_event

            base = (getattr(args, "base_url", None) or "").strip()
            action = str(getattr(args, "sales_action", "surface") or "surface").strip().lower()
            surface = NomadApiHandler._build_sales_department_swarm(base_url=base)
            if action == "evaluate":
                raw_json = str(getattr(args, "event_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    payload = {
                        "cell_id": str(getattr(args, "cell_id", "") or "").strip() or "repo_rescue_cell",
                        "stage": str(getattr(args, "stage", "") or "").strip() or "draft",
                        "buyer_intent_digest": str(getattr(args, "buyer_intent_digest", "") or "").strip(),
                        "proof_digest": str(getattr(args, "proof_digest", "") or "").strip(),
                        "settlement_ref": str(getattr(args, "settlement_ref", "") or "").strip(),
                        "amount_usd": float(getattr(args, "amount_usd", 0.0) or 0.0),
                        "send": bool(getattr(args, "send", False)),
                        "human_approved": bool(getattr(args, "human_approved", False)),
                    }
                result = evaluate_sales_department_event(payload, base_url=base, sales_surface=surface)
            else:
                result = surface
        elif args.command == "external-value":
            from nomad_external_value import (
                agent_selection_bonus,
                append_external_value_event,
                build_external_value_surface,
                summarize_external_value_ledger,
            )

            sub = str(getattr(args, "ev_action", None) or "surface").strip().lower()
            if sub == "record":
                result = append_external_value_event(
                    {
                        "agent_id": getattr(args, "agent_id", "") or "",
                        "external_id": getattr(args, "external_id", "") or "",
                        "stage": getattr(args, "stage", "") or "",
                        "work_url": getattr(args, "work_url", "") or "",
                        "proof_digest": getattr(args, "proof_digest", "") or "",
                        "verifier_trace_digest": getattr(args, "verifier_trace_digest", "") or "",
                        "amount_usd": float(getattr(args, "amount_usd", 0.0) or 0.0),
                    }
                )
            elif sub == "summary":
                limit = int(getattr(args, "limit", 40) or 40)
                result = summarize_external_value_ledger(limit=limit, latest_limit=limit)
            elif sub == "bonus":
                result = agent_selection_bonus(str(getattr(args, "agent_id", "") or ""))
            elif sub == "reconcile":
                from nomad_external_value_reconciler import reconcile_external_value_ledger

                result = reconcile_external_value_ledger(
                    live_github=bool(getattr(args, "live_github", False)),
                    limit=int(getattr(args, "limit", 40) or 40),
                )
            elif sub == "sign-proof":
                from nomad_external_value_signature import sign_external_value_proof

                result = sign_external_value_proof(
                    agent_id=getattr(args, "agent_id", "") or "",
                    external_id=getattr(args, "external_id", "") or "",
                    stage=getattr(args, "stage", "") or "",
                    work_url=getattr(args, "work_url", "") or "",
                    proof_digest=getattr(args, "proof_digest", "") or "",
                    verifier_trace_digest=getattr(args, "verifier_trace_digest", "") or "",
                    payout_ref=getattr(args, "payout_ref", "") or "",
                    wallet_path=getattr(args, "wallet_path", "") or None,
                )
            elif sub == "snapshot-public":
                from nomad_external_value_sync import snapshot_public_external_value

                result = snapshot_public_external_value(
                    base_url=(getattr(args, "base_url", None) or "").strip()
                    or "https://www.syndiode.com",
                    snapshot_dir=(getattr(args, "snapshot_dir", None) or "").strip() or None,
                    timeout=float(getattr(args, "timeout", 20.0) or 20.0),
                )
            elif sub == "sync-public":
                from nomad_external_value_sync import sync_external_value_to_public

                result = sync_external_value_to_public(
                    base_url=(getattr(args, "base_url", None) or "").strip()
                    or "https://www.syndiode.com",
                    apply=bool(getattr(args, "apply", False)),
                    snapshot=bool(getattr(args, "snapshot", False)),
                    snapshot_dir=(getattr(args, "snapshot_dir", None) or "").strip() or None,
                    timeout=float(getattr(args, "timeout", 20.0) or 20.0),
                )
            else:
                base = (getattr(args, "base_url", None) or "").strip()
                result = build_external_value_surface(base_url=base or "https://www.syndiode.com")
        elif args.command == "value-pressure":
            from nomad_bounty_hunter import build_bounty_hunter_surface, discover_github_bounties
            from nomad_compute_market import build_compute_market
            from nomad_external_value_reconciler import reconcile_external_value_ledger
            from nomad_microtask_exchange_ops import build_microtask_metrics
            from nomad_microtask_market import build_worker_catalog
            from nomad_value_pressure import build_value_pressure_surface
            from nomad_worker_market import build_worker_market

            base = (getattr(args, "base_url", None) or "").strip()
            agent = NomadAgent()
            worker_fleet = agent.swarm_registry.worker_fleet_contract(base_url=base)
            worker_market = build_worker_market(base_url=base, worker_fleet=worker_fleet, machine_economy={})
            worker_catalog = build_worker_catalog(base_url=base, worker_fleet=worker_fleet, worker_market=worker_market)
            metrics = build_microtask_metrics(base_url=base, lookback_hours=24)
            compute_market = build_compute_market(
                base_url=base,
                worker_market=worker_market,
                worker_catalog=worker_catalog,
                microtask_metrics=metrics,
                worker_fleet=worker_fleet,
            )
            discoveries = []
            if bool(getattr(args, "discover_gh", False)):
                discoveries = discover_github_bounties(limit=int(getattr(args, "limit", 10) or 10))
            result = build_value_pressure_surface(
                base_url=base,
                external_reconcile=reconcile_external_value_ledger(
                    live_github=bool(getattr(args, "live_github", False)),
                    limit=int(getattr(args, "limit", 40) or 40),
                ),
                bounty_hunter=build_bounty_hunter_surface(base_url=base, discoveries=discoveries),
                compute_market=compute_market,
            )
        elif args.command == "settlement":
            from nomad_external_value import summarize_external_value_ledger
            from nomad_external_value_reconciler import reconcile_external_value_ledger
            from nomad_settlement_signal_layer import (
                build_settlement_signal_layer,
                compile_public_settlement_packet,
                influence_operator_catalog,
                science_source_registry,
            )

            base = (getattr(args, "base_url", None) or "").strip()
            surface = build_settlement_signal_layer(
                base_url=base,
                external_summary=summarize_external_value_ledger(
                    limit=int(getattr(args, "limit", 200) or 200),
                    latest_limit=int(getattr(args, "limit", 200) or 200),
                ),
                external_reconcile=reconcile_external_value_ledger(
                    live_github=bool(getattr(args, "live_github", False)),
                    limit=int(getattr(args, "limit", 40) or 40),
                ),
            )
            settlement_action = str(getattr(args, "settlement_action", "surface") or "surface").strip().lower()
            if settlement_action == "rank":
                result = {
                    "ok": True,
                    "schema": "nomad.settlement_rank.v1",
                    "generated_at": surface.get("generated_at"),
                    "summary": surface.get("summary"),
                    "rows": surface.get("rows") or [],
                    "machine_instruction": surface.get("machine_instruction"),
                }
            elif settlement_action == "next":
                result = {
                    "ok": True,
                    "schema": "nomad.settlement_next_action.v1",
                    "generated_at": surface.get("generated_at"),
                    "summary": surface.get("summary"),
                    "next_action_receipt": surface.get("next_action_receipt"),
                    "bottleneck_control": surface.get("bottleneck_control"),
                    "top": surface.get("top"),
                    "human_membrane_contract": surface.get("human_membrane_contract"),
                }
            elif settlement_action == "bottleneck":
                result = {
                    "ok": True,
                    "schema": "nomad.settlement_bottleneck_control.v1",
                    "generated_at": surface.get("generated_at"),
                    "summary": surface.get("summary"),
                    "bottleneck_control": surface.get("bottleneck_control"),
                    "top": surface.get("top"),
                    "operator_activation_contract": surface.get("operator_activation_contract"),
                }
            elif settlement_action == "operators":
                result = {
                    "ok": True,
                    "schema": "nomad.settlement_influence_operators.v1",
                    "generated_at": surface.get("generated_at"),
                    "cashflow_growth_claim": False,
                    "cashflow_learning_rule": (surface.get("operator_activation_contract") or {}).get("cashflow_learning_rule"),
                    "operators": influence_operator_catalog(),
                    "science_sources": science_source_registry(),
                    "forbidden": (surface.get("operator_activation_contract") or {}).get("hard_guards") or [],
                }
            elif settlement_action == "packet":
                target_id = str(getattr(args, "external_id", "") or "").strip()
                rows = surface.get("rows") if isinstance(surface.get("rows"), list) else []
                target = {}
                if target_id:
                    target = next((row for row in rows if str(row.get("external_id") or "") == target_id), {})
                if not target:
                    target = surface.get("top") if isinstance(surface.get("top"), dict) else {}
                result = compile_public_settlement_packet(
                    target,
                    packet_type=str(getattr(args, "packet_type", "") or "pr"),
                )
            else:
                result = surface
        elif args.command == "agent-job-router":
            from nomad_agent_job_router import build_agent_job_router
            from nomad_agent_work import build_agent_work_surface, build_synergy_lite
            from nomad_bounty_hunter import build_bounty_hunter_surface, discover_github_bounties
            from nomad_carrying_market import build_carrying_market
            from nomad_compute_market import build_compute_market
            from nomad_external_value_reconciler import reconcile_external_value_ledger
            from nomad_growth_arena import build_skill_library
            from nomad_microtask_exchange_ops import build_microtask_metrics, build_microtask_templates
            from nomad_microtask_market import build_worker_catalog
            from nomad_openapi import build_openapi_document
            from nomad_state_status import build_state_status
            from nomad_survival_market import build_survival_market
            from nomad_value_pressure import build_value_pressure_surface
            from nomad_worker_market import build_worker_market
            from nomad_work_mesh import build_work_mesh

            base = (getattr(args, "base_url", None) or "").strip()
            agent = NomadAgent()
            summary = agent.swarm_registry.public_manifest(base_url=base)
            worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
            if not worker_fleet:
                worker_fleet = agent.swarm_registry.worker_fleet_contract(base_url=base)
            worker_market = build_worker_market(base_url=base, worker_fleet=worker_fleet, machine_economy={})
            worker_catalog = build_worker_catalog(base_url=base, worker_fleet=worker_fleet, worker_market=worker_market)
            metrics = build_microtask_metrics(base_url=base, lookback_hours=24)
            templates = build_microtask_templates(base_url=base)
            compute_market = build_compute_market(
                base_url=base,
                worker_market=worker_market,
                worker_catalog=worker_catalog,
                microtask_metrics=metrics,
                worker_fleet=worker_fleet,
            )
            discoveries = []
            if bool(getattr(args, "discover_gh", False)):
                discoveries = discover_github_bounties(limit=int(getattr(args, "limit", 10) or 10))
            pressure = build_value_pressure_surface(
                base_url=base,
                external_reconcile=reconcile_external_value_ledger(
                    live_github=bool(getattr(args, "live_github", False)),
                    limit=int(getattr(args, "limit", 40) or 40),
                ),
                bounty_hunter=build_bounty_hunter_surface(base_url=base, discoveries=discoveries),
                compute_market=compute_market,
            )
            skills = build_skill_library(base_url=base)
            synergy = build_synergy_lite(base_url=base)
            agent_work = build_agent_work_surface(
                base_url=base,
                compute_market=compute_market,
                microtask_templates=templates,
                microtask_metrics=metrics,
                worker_catalog=worker_catalog,
                skill_library=skills,
                worker_fleet=worker_fleet,
                synergy_lite=synergy,
            )
            carrying = build_carrying_market(
                base_url=base,
                state_status=build_state_status(base_url=base),
                microtask_metrics=metrics,
                worker_fleet=worker_fleet,
                compute_market=compute_market,
            )
            work_mesh = build_work_mesh(
                base_url=base,
                agent_work=agent_work,
                compute_market=compute_market,
                synergy_lite=synergy,
                skill_library=skills,
                state_status=build_state_status(base_url=base),
                carrying_market=carrying,
                survival_market=build_survival_market(
                    base_url=base,
                    carrying_market=carrying,
                    microtask_metrics=metrics,
                    worker_fleet=worker_fleet,
                ),
            )
            result = build_agent_job_router(
                base_url=base,
                openapi_document=build_openapi_document(base_url=base),
                value_pressure=pressure,
                work_mesh=work_mesh,
            )
        elif args.command == "revenue-science":
            from nomad_agent_job_router import build_agent_job_router
            from nomad_agent_work import build_agent_work_surface, build_synergy_lite
            from nomad_bounty_hunter import build_bounty_hunter_surface, discover_github_bounties
            from nomad_carrying_market import build_carrying_market
            from nomad_compute_market import build_compute_market
            from nomad_external_value import summarize_external_value_ledger
            from nomad_external_value_reconciler import reconcile_external_value_ledger
            from nomad_growth_arena import build_skill_library
            from nomad_microtask_exchange_ops import build_microtask_metrics, build_microtask_templates
            from nomad_microtask_market import build_worker_catalog
            from nomad_nonhuman_science import nonhuman_agent_science
            from nomad_openapi import build_openapi_document
            from nomad_revenue_science import build_revenue_science_surface
            from nomad_state_status import build_state_status
            from nomad_survival_market import build_survival_market
            from nomad_value_pressure import build_value_pressure_surface
            from nomad_worker_market import build_worker_market
            from nomad_work_mesh import build_work_mesh

            base = (getattr(args, "base_url", None) or "").strip()
            agent = NomadAgent()
            summary = agent.swarm_registry.public_manifest(base_url=base)
            worker_fleet = summary.get("transition_worker_fleet") if isinstance(summary.get("transition_worker_fleet"), dict) else {}
            if not worker_fleet:
                worker_fleet = agent.swarm_registry.worker_fleet_contract(base_url=base)
            worker_market = build_worker_market(base_url=base, worker_fleet=worker_fleet, machine_economy={})
            worker_catalog = build_worker_catalog(base_url=base, worker_fleet=worker_fleet, worker_market=worker_market)
            metrics = build_microtask_metrics(base_url=base, lookback_hours=24)
            templates = build_microtask_templates(base_url=base)
            compute_market = build_compute_market(
                base_url=base,
                worker_market=worker_market,
                worker_catalog=worker_catalog,
                microtask_metrics=metrics,
                worker_fleet=worker_fleet,
            )
            discoveries = []
            if bool(getattr(args, "discover_gh", False)):
                discoveries = discover_github_bounties(limit=int(getattr(args, "limit", 10) or 10))
            pressure = build_value_pressure_surface(
                base_url=base,
                external_reconcile=reconcile_external_value_ledger(
                    live_github=bool(getattr(args, "live_github", False)),
                    limit=int(getattr(args, "limit", 40) or 40),
                ),
                bounty_hunter=build_bounty_hunter_surface(base_url=base, discoveries=discoveries),
                compute_market=compute_market,
            )
            skills = build_skill_library(base_url=base)
            synergy = build_synergy_lite(base_url=base)
            agent_work = build_agent_work_surface(
                base_url=base,
                compute_market=compute_market,
                microtask_templates=templates,
                microtask_metrics=metrics,
                worker_catalog=worker_catalog,
                skill_library=skills,
                worker_fleet=worker_fleet,
                synergy_lite=synergy,
            )
            carrying = build_carrying_market(
                base_url=base,
                state_status=build_state_status(base_url=base),
                microtask_metrics=metrics,
                worker_fleet=worker_fleet,
                compute_market=compute_market,
            )
            work_mesh = build_work_mesh(
                base_url=base,
                agent_work=agent_work,
                compute_market=compute_market,
                synergy_lite=synergy,
                skill_library=skills,
                state_status=build_state_status(base_url=base),
                carrying_market=carrying,
                survival_market=build_survival_market(
                    base_url=base,
                    carrying_market=carrying,
                    microtask_metrics=metrics,
                    worker_fleet=worker_fleet,
                ),
            )
            router = build_agent_job_router(
                base_url=base,
                openapi_document=build_openapi_document(base_url=base),
                value_pressure=pressure,
                work_mesh=work_mesh,
            )
            result = build_revenue_science_surface(
                base_url=base,
                value_pressure=pressure,
                agent_job_router=router,
                external_value_summary=summarize_external_value_ledger(),
                nonhuman_science=nonhuman_agent_science(base_url=base),
            )
        elif args.command == "job-channels":
            from nomad_external_value import summarize_external_value_ledger
            from nomad_job_channels import build_job_channel_surface

            base = (getattr(args, "base_url", None) or "").strip()
            result = build_job_channel_surface(
                base_url=base,
                external_value_summary=summarize_external_value_ledger(),
            )
        elif args.command == "channel-bandit":
            from nomad_channel_bandit import build_delayed_channel_bandit_surface
            from nomad_external_value import summarize_external_value_ledger
            from nomad_job_channels import build_job_channel_surface
            from nomad_swarm_signal_layer import build_swarm_signal_layer

            base = (getattr(args, "base_url", None) or "").strip()
            external_summary = summarize_external_value_ledger()
            result = build_delayed_channel_bandit_surface(
                base_url=base,
                job_channel_surface=build_job_channel_surface(
                    base_url=base,
                    external_value_summary=external_summary,
                ),
                external_value_summary=external_summary,
                signal_layer=build_swarm_signal_layer(base_url=base, external_value_summary=external_summary),
            )
        elif args.command == "shadow-lane":
            from nomad_api import NomadApiHandler
            from nomad_shadow_lane_evaluator import evaluate_shadow_candidate, generate_shadow_candidate

            base = (getattr(args, "base_url", None) or "").strip()
            surface = NomadApiHandler._build_shadow_lane_evaluator(base_url=base)
            action = str(getattr(args, "shadow_action", "surface") or "surface")
            if action == "surface":
                result = surface
            else:
                raw_json = str(getattr(args, "candidate_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    payload = {
                        "agent_id": str(getattr(args, "agent_id", "") or "").strip() or "nomad-cli-shadow-lane",
                        "objective": str(getattr(args, "objective", "") or "").strip() or "settlement_capacity_builder",
                        "candidate_type": str(getattr(args, "candidate_type", "") or "").strip()
                        or "shadow_lane_policy_variant",
                        "hypothesis": str(getattr(args, "hypothesis", "") or "").strip()
                        or "locally test one bounded route mutation before increasing selection weight",
                        "boundedness": {
                            "ttl_seconds": int(getattr(args, "ttl_seconds", 300) or 300),
                            "side_effect_scope": "local_shadow_lane_only",
                            "rollback_available": True,
                            "secrets_free": True,
                        },
                        "claimed_effect": {
                            "proof_gain_delta": float(getattr(args, "proof_gain_delta", 0.2) or 0.0),
                            "settlement_signal": float(getattr(args, "settlement_signal", 0.15) or 0.0),
                            "risk_score": float(getattr(args, "risk_score", 0.05) or 0.0),
                        },
                        "local_tests": [
                            {
                                "name": "cli_local_shadow_smoke",
                                "passed": not bool(getattr(args, "fail_local_test", False)),
                                "evidence_digest": "cli:local-smoke",
                            }
                        ],
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.shadow_lane_cli_error.v1",
                        "error": "invalid_candidate_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "candidate_json_not_object",
                    }
                elif action == "generate":
                    result = generate_shadow_candidate(
                        payload,
                        base_url=base,
                        candidate_seeds=surface.get("candidate_seeds") if isinstance(surface.get("candidate_seeds"), list) else None,
                    )
                else:
                    result = evaluate_shadow_candidate(
                        payload,
                        base_url=base,
                        shadow_surface=surface,
                        persist=not bool(getattr(args, "dry_run", False)),
                    )
        elif args.command == "decoupling-field":
            from nomad_api import NomadApiHandler
            from nomad_decoupling_field import evaluate_decoupling_merge

            base = (getattr(args, "base_url", None) or "").strip()
            field = NomadApiHandler._build_decoupling_field(base_url=base)
            action = str(getattr(args, "decoupling_action", "surface") or "surface")
            if action == "surface":
                result = field
            else:
                raw_json = str(getattr(args, "merge_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    cells = field.get("context_cells") if isinstance(field.get("context_cells"), list) else []
                    payload = {
                        "agent_id": str(getattr(args, "agent_id", "") or "").strip() or "nomad-cli-decoupling",
                        "divergence_score": float(getattr(args, "divergence_score", 0.42) or 0.0),
                        "cells": [
                            {
                                "cell_id": cell.get("cell_id"),
                                "objective": cell.get("objective"),
                                "candidate_digest": f"sha256:cli-candidate-{idx}",
                                "proof_digest": f"sha256:cli-proof-{idx}",
                                "context_mask_digest": cell.get("context_mask_digest"),
                                "model_family": f"cli_mask_{idx}",
                            }
                            for idx, cell in enumerate(cells[:2], start=1)
                        ],
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.decoupling_field_cli_error.v1",
                        "error": "invalid_merge_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "merge_json_not_object",
                    }
                else:
                    result = evaluate_decoupling_merge(
                        payload,
                        base_url=base,
                        decoupling_field=field,
                        persist=not bool(getattr(args, "dry_run", False)),
                    )
        elif args.command == "anti-consensus":
            from nomad_api import NomadApiHandler
            from nomad_anti_consensus_reservoir import evaluate_anti_consensus_candidate

            base = (getattr(args, "base_url", None) or "").strip()
            reservoir = NomadApiHandler._build_anti_consensus_reservoir(base_url=base)
            action = str(getattr(args, "anti_action", "surface") or "surface")
            if action == "surface":
                result = reservoir
            else:
                raw_json = str(getattr(args, "candidate_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    payload = {
                        "agent_id": str(getattr(args, "agent_id", "") or "").strip() or "nomad-cli-anti-consensus",
                        "objective": str(getattr(args, "objective", "") or "").strip() or "minority_proof_probe",
                        "candidate_digest": "sha256:cli-minority-candidate",
                        "proof_digest": "sha256:cli-minority-proof",
                        "test_digest": "sha256:cli-minority-test",
                        "consensus_score": float(getattr(args, "consensus_score", 0.32) or 0.0),
                        "minority_fraction": float(getattr(args, "minority_fraction", 0.22) or 0.0),
                        "expert_score": float(getattr(args, "expert_score", 0.78) or 0.0),
                        "crowd_score": float(getattr(args, "crowd_score", 0.44) or 0.0),
                        "risk_score": float(getattr(args, "risk_score", 0.06) or 0.0),
                        "boundedness": {
                            "side_effect_scope": "local_shadow_lane_only",
                            "rollback_available": True,
                        },
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.anti_consensus_cli_error.v1",
                        "error": "invalid_candidate_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "candidate_json_not_object",
                    }
                else:
                    result = evaluate_anti_consensus_candidate(
                        payload,
                        base_url=base,
                        reservoir_surface=reservoir,
                        persist=not bool(getattr(args, "dry_run", False)),
                    )
        elif args.command == "deficit-integration":
            from nomad_api import NomadApiHandler
            from nomad_deficit_integration_gate import evaluate_deficit_integration_event

            base = (getattr(args, "base_url", None) or "").strip()
            gate = NomadApiHandler._build_deficit_integration_gate(base_url=base)
            action = str(getattr(args, "deficit_action", "surface") or "surface")
            if action == "surface":
                result = gate
            else:
                raw_json = str(getattr(args, "event_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    payload = {
                        "agent_id": str(getattr(args, "agent_id", "") or "").strip() or "nomad-cli-deficit-integration",
                        "objective": str(getattr(args, "objective", "") or "").strip() or "coordination_deficit_repair",
                        "event_digest": "sha256:cli-dti-event",
                        "proof_digest": "sha256:cli-dti-proof",
                        "coordination_expansion": float(getattr(args, "coordination_expansion", 0.88) or 0.0),
                        "consolidation_score": float(getattr(args, "consolidation_score", 0.16) or 0.0),
                        "cascade_skew": float(getattr(args, "cascade_skew", 0.72) or 0.0),
                        "orphan_proof_count": float(getattr(args, "orphan_proof_count", 4) or 0.0),
                        "consensus_score": float(getattr(args, "consensus_score", 0.20) or 0.0),
                        "adversarial_majority_risk": float(getattr(args, "adversarial_majority_risk", 0.42) or 0.0),
                        "minority_preserved": True,
                        "boundedness": {
                            "side_effect_scope": "local_shadow_lane_only",
                            "rollback_available": True,
                        },
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.deficit_integration_cli_error.v1",
                        "error": "invalid_event_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "event_json_not_object",
                    }
                else:
                    result = evaluate_deficit_integration_event(
                        payload,
                        base_url=base,
                        gate_surface=gate,
                        persist=not bool(getattr(args, "dry_run", False)),
                    )
        elif args.command == "effective-channels":
            from nomad_api import NomadApiHandler
            from nomad_effective_channel_quota import evaluate_effective_channel_event

            base = (getattr(args, "base_url", None) or "").strip()
            quota = NomadApiHandler._build_effective_channel_quota(base_url=base)
            action = str(getattr(args, "effective_action", "surface") or "surface")
            if action == "surface":
                result = quota
            else:
                raw_json = str(getattr(args, "event_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    duplicate = bool(getattr(args, "duplicate", False))
                    if duplicate:
                        channels = [
                            {
                                "agent_id": f"nomad-cli-dup-{idx}",
                                "model_family": "gpt",
                                "tool_family": "browser",
                                "source_domain": "same_feed",
                                "retrieval_corpus": "same_corpus",
                                "trajectory_digest": "sha256:same-trajectory",
                                "proof_digest": f"sha256:duplicate-proof-{idx}",
                            }
                            for idx in range(5)
                        ]
                    else:
                        channels = [
                            {
                                "agent_id": "nomad-cli-channel-a",
                                "model_family": "gpt",
                                "tool_family": "browser",
                                "source_domain": "agent_forum",
                                "retrieval_corpus": "agent_pain",
                                "trajectory_digest": "sha256:trajectory-a",
                                "proof_digest": "sha256:proof-a",
                                "minority_signal": True,
                            },
                            {
                                "agent_id": "nomad-cli-channel-b",
                                "model_family": "claude",
                                "tool_family": "github",
                                "source_domain": "oss_issues",
                                "retrieval_corpus": "bounty_pain",
                                "trajectory_digest": "sha256:trajectory-b",
                                "proof_digest": "sha256:proof-b",
                            },
                            {
                                "agent_id": "nomad-cli-channel-c",
                                "model_family": "kimi",
                                "tool_family": "search",
                                "source_domain": "buyer_docs",
                                "retrieval_corpus": "pricing",
                                "trajectory_digest": "sha256:trajectory-c",
                                "proof_digest": "sha256:proof-c",
                            },
                        ]
                    payload = {
                        "agent_id": str(getattr(args, "agent_id", "") or "").strip() or "nomad-cli-effective-channels",
                        "objective": str(getattr(args, "objective", "") or "").strip() or "nomad_science_backed_ad_cycle",
                        "event_digest": "sha256:cli-effective-channel-event",
                        "channels": channels,
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.effective_channel_cli_error.v1",
                        "error": "invalid_event_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "event_json_not_object",
                    }
                else:
                    result = evaluate_effective_channel_event(
                        payload,
                        base_url=base,
                        quota_surface=quota,
                        persist=not bool(getattr(args, "dry_run", False)),
                    )
        elif args.command == "taskbounty-scout":
            from nomad_taskbounty_scout import build_taskbounty_scout

            result = build_taskbounty_scout(
                api_base=(getattr(args, "api_base", None) or "").strip() or None,
                limit=int(getattr(args, "limit", 20) or 20),
                include_details=not bool(getattr(args, "no_details", False)),
            )
        elif args.command == "taskbounty-access-gate":
            from nomad_taskbounty_scout import probe_taskbounty_access_gate

            result = probe_taskbounty_access_gate(
                task_id=str(getattr(args, "task_id", "") or "").strip(),
                api_base=(getattr(args, "api_base", None) or "").strip() or None,
            )
        elif args.command == "superteam-scout":
            from nomad_superteam_scout import build_superteam_scout

            result = build_superteam_scout(
                base_url=(getattr(args, "base_url", None) or "").strip() or None,
                listing_type=(getattr(args, "listing_type", None) or "").strip() or None,
                take=int(getattr(args, "take", 20) or 20),
                include_details=bool(getattr(args, "details", False)),
            )
        elif args.command == "worker-invoice":
            from nomad_external_value import summarize_external_value_ledger
            from nomad_worker_invoice import build_worker_invoice_surface

            base = (getattr(args, "base_url", None) or "").strip()
            result = build_worker_invoice_surface(
                base_url=base,
                payout_ref=(getattr(args, "payout_ref", None) or "").strip() or None,
                public_key_hex=(getattr(args, "public_key_hex", None) or "").strip() or None,
                external_value_summary=summarize_external_value_ledger(),
                live_balance=bool(getattr(args, "live_rtc", False)),
            )
        elif args.command == "work-receipts":
            from nomad_work_receipts import (
                build_treasury_policy_surface,
                build_work_receipt_surface,
                record_work_receipt,
                summarize_work_receipts,
            )

            action = str(getattr(args, "receipt_action", "surface") or "surface").strip().lower()
            base = (getattr(args, "base_url", None) or "").strip()
            if action == "record":
                result = record_work_receipt(
                    {
                        "agent_id": getattr(args, "agent_id", "") or "",
                        "work_id": getattr(args, "work_id", "") or getattr(args, "external_id", "") or "",
                        "work_type": getattr(args, "work_type", "") or "",
                        "objective": getattr(args, "objective", "") or "",
                        "external_value_stage": getattr(args, "stage", "") or "",
                        "work_url": getattr(args, "work_url", "") or "",
                        "proof_digest": getattr(args, "proof_digest", "") or "",
                        "verifier_trace_digest": getattr(args, "verifier_trace_digest", "") or "",
                        "amount_usd": float(getattr(args, "amount_usd", 0.0) or 0.0),
                        "settlement_ref": getattr(args, "settlement_ref", "") or "",
                        "idempotency_key": getattr(args, "idempotency_key", "") or "",
                    }
                )
            elif action == "summary":
                result = summarize_work_receipts(limit=int(getattr(args, "limit", 80) or 80))
            elif action == "policy":
                from nomad_external_value import summarize_external_value_ledger

                result = build_treasury_policy_surface(
                    base_url=base,
                    work_receipt_summary=summarize_work_receipts(limit=int(getattr(args, "limit", 80) or 80)),
                    external_value_summary=summarize_external_value_ledger(),
                )
            else:
                result = build_work_receipt_surface(
                    base_url=base,
                    summary=summarize_work_receipts(limit=int(getattr(args, "limit", 80) or 80)),
                )
        elif args.command == "stable-unit":
            from nomad_external_value import summarize_external_value_ledger
            from nomad_stable_unit_policy import build_stable_unit_policy_surface, evaluate_stable_unit_preflight
            from nomad_work_receipts import summarize_work_receipts

            action = str(getattr(args, "stable_action", "policy") or "policy").strip().lower()
            base = (getattr(args, "base_url", None) or "").strip()
            if action == "preflight":
                result = evaluate_stable_unit_preflight(
                    {
                        "mode": getattr(args, "mode", "") or "simulation",
                        "requested_units": float(getattr(args, "requested_units", 0.0) or 0.0),
                        "reference_unit": getattr(args, "reference_unit", "") or "USD",
                        "redemption_buffer_ratio": float(getattr(args, "redemption_buffer_ratio", 1.05) or 1.05),
                        "reserve_assets": [
                            {
                                "asset_id": getattr(args, "reserve_asset_id", "") or "reserve-1",
                                "asset_type": getattr(args, "reserve_asset_type", "") or "cash_or_cash_equivalent",
                                "currency": getattr(args, "reserve_currency", "") or "USD",
                                "amount": float(getattr(args, "reserve_amount", 0.0) or 0.0),
                                "haircut": float(getattr(args, "reserve_haircut", 0.08) or 0.08),
                                "liquidity_weight": float(getattr(args, "reserve_liquidity_weight", 1.0) or 1.0),
                                "custodian_ref": getattr(args, "custodian_ref", "") or "",
                                "attestation_digest": getattr(args, "attestation_digest", "") or "",
                            }
                        ],
                        "issuer_authorization_ref": getattr(args, "issuer_authorization_ref", "") or "",
                        "whitepaper_ref": getattr(args, "whitepaper_ref", "") or "",
                        "reserve_attestation_ref": getattr(args, "reserve_attestation_ref", "") or "",
                        "redemption_plan_ref": getattr(args, "redemption_plan_ref", "") or "",
                        "governance_policy_ref": getattr(args, "governance_policy_ref", "") or "",
                        "compliance_opinion_ref": getattr(args, "compliance_opinion_ref", "") or "",
                    }
                )
            else:
                result = build_stable_unit_policy_surface(
                    base_url=base,
                    work_receipt_summary=summarize_work_receipts(limit=int(getattr(args, "limit", 80) or 80)),
                    external_value_summary=summarize_external_value_ledger(),
                )
        elif args.command == "operator-runway":
            from nomad_external_value import summarize_external_value_ledger
            from nomad_operator_runway import build_operator_runway_surface
            from nomad_work_receipts import summarize_work_receipts

            result = build_operator_runway_surface(
                base_url=(getattr(args, "base_url", None) or "").strip(),
                external_value_summary=summarize_external_value_ledger(),
                work_receipt_summary=summarize_work_receipts(limit=int(getattr(args, "limit", 80) or 80)),
                monthly_min_eur=getattr(args, "monthly_min_eur", None),
                liquid_cash_eur=getattr(args, "liquid_cash_eur", None),
                expected_income_30d_eur=getattr(args, "expected_income_30d_eur", None),
                operator_befinden=getattr(args, "befinden", None),
                publish_amounts=bool(getattr(args, "public_amounts", False)),
            )
        elif args.command == "viability-kernel":
            from nomad_external_value import summarize_external_value_ledger
            from nomad_operator_runway import build_operator_runway_surface
            from nomad_stable_unit_policy import build_stable_unit_policy_surface
            from nomad_viability_kernel import build_viability_kernel_surface, route_viability_action
            from nomad_work_receipts import build_treasury_policy_surface, summarize_work_receipts

            base = (getattr(args, "base_url", None) or "").strip()
            work_summary = summarize_work_receipts(limit=int(getattr(args, "limit", 80) or 80))
            external_summary = summarize_external_value_ledger()
            operator = build_operator_runway_surface(
                base_url=base,
                external_value_summary=external_summary,
                work_receipt_summary=work_summary,
                operator_befinden=getattr(args, "befinden", None),
                publish_amounts=bool(getattr(args, "public_amounts", False)),
            )
            stable = build_stable_unit_policy_surface(
                base_url=base,
                work_receipt_summary=work_summary,
                external_value_summary=external_summary,
            )
            treasury = build_treasury_policy_surface(
                base_url=base,
                work_receipt_summary=work_summary,
                external_value_summary=external_summary,
            )
            kernel = build_viability_kernel_surface(
                base_url=base,
                operator_runway=operator,
                external_value_summary=external_summary,
                work_receipt_summary=work_summary,
                stable_unit_policy=stable,
                treasury_policy=treasury,
            )
            action = str(getattr(args, "kernel_action", "surface") or "surface").strip().lower()
            if action == "route":
                result = route_viability_action(
                    {
                        "action_type": getattr(args, "action_type", "") or "",
                        "target_url": getattr(args, "target_url", "") or "",
                        "paid_required": bool(getattr(args, "paid_required", False)),
                        "note": getattr(args, "note", "") or "",
                    },
                    viability_kernel=kernel,
                )
            else:
                result = kernel
        elif args.command == "value-cycle-preflight":
            from nomad_external_value import summarize_external_value_ledger
            from nomad_value_cycle_preflight import build_value_cycle_preflight_surface

            base = (getattr(args, "base_url", None) or "").strip()
            result = build_value_cycle_preflight_surface(
                base_url=base,
                payout_ref=(getattr(args, "payout_ref", None) or "").strip() or None,
                public_key_hex=(getattr(args, "public_key_hex", None) or "").strip() or None,
                external_value_summary=summarize_external_value_ledger(),
                live_balance=bool(getattr(args, "live_rtc", False)),
                opportunity_url=(getattr(args, "opportunity_url", None) or "").strip(),
                program_terms_verified=bool(getattr(args, "program_terms_verified", False)),
                payout_terms_verified=bool(getattr(args, "payout_terms_verified", False)),
                payout_method_compatible=bool(getattr(args, "payout_method_compatible", False)),
                work_proof_ready=bool(getattr(args, "work_proof_ready", False)),
            )
        elif args.command == "worker-job-queue":
            from nomad_api import NomadApiHandler

            base = (getattr(args, "base_url", None) or "").strip()
            result = NomadApiHandler._build_worker_job_queue(base_url=base)
        elif args.command == "value-cycles":
            from nomad_api import NomadApiHandler
            from nomad_value_cycle_mesh import evaluate_value_cycle_event

            base = (getattr(args, "base_url", None) or "").strip()
            mesh = NomadApiHandler._build_value_cycle_mesh(base_url=base)
            action = str(getattr(args, "cycle_action", "surface") or "surface").strip().lower()
            if action == "evaluate":
                raw_json = str(getattr(args, "event_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    payload = {
                        "agent_id": str(getattr(args, "agent_id", "") or "").strip() or "nomad-cli-value-cycles",
                        "cycle_id": str(getattr(args, "cycle_id", "") or "").strip()
                        or str(mesh.get("entry_cycle", {}).get("cycle_id") or ""),
                        "stage": str(getattr(args, "stage", "") or "prove").strip(),
                        "external_id": str(getattr(args, "external_id", "") or "").strip(),
                        "source_url": str(getattr(args, "source_url", "") or "").strip(),
                        "terms_url": str(getattr(args, "terms_url", "") or "").strip(),
                        "proof_digest": str(getattr(args, "proof_digest", "") or "").strip() or "sha256:cli-value-cycle-proof",
                        "settlement_ref": str(getattr(args, "settlement_ref", "") or "").strip(),
                        "amount_usd": float(getattr(args, "amount_usd", 0.0) or 0.0),
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.value_cycle_cli_error.v1",
                        "error": "invalid_event_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "event_json_not_object",
                    }
                else:
                    result = evaluate_value_cycle_event(payload, base_url=base, mesh_surface=mesh)
            else:
                result = mesh
        elif args.command == "receipt-predictor":
            from nomad_api import NomadApiHandler
            from nomad_receipt_predictor import evaluate_receipt_prediction_event

            base = (getattr(args, "base_url", None) or "").strip()
            predictor = NomadApiHandler._build_receipt_predictor(base_url=base)
            action = str(getattr(args, "predictor_action", "surface") or "surface").strip().lower()
            if action == "evaluate":
                raw_json = str(getattr(args, "event_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    payload = {
                        "cycle_id": str(getattr(args, "cycle_id", "") or "").strip()
                        or str(predictor.get("summary", {}).get("top_cycle_id") or ""),
                        "intent": str(getattr(args, "intent", "") or "select").strip(),
                        "proof_digest": str(getattr(args, "proof_digest", "") or "").strip(),
                        "settlement_ref": str(getattr(args, "settlement_ref", "") or "").strip(),
                        "amount_usd": float(getattr(args, "amount_usd", 0.0) or 0.0),
                        "execute": bool(getattr(args, "execute", False)),
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.receipt_predictor_cli_error.v1",
                        "error": "invalid_event_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "event_json_not_object",
                    }
                else:
                    result = evaluate_receipt_prediction_event(payload, base_url=base, predictor_surface=predictor)
            else:
                result = predictor
        elif args.command == "ad-cycles":
            from nomad_ad_cycle_mesh import evaluate_ad_cycle_event
            from nomad_api import NomadApiHandler

            base = (getattr(args, "base_url", None) or "").strip()
            mesh = NomadApiHandler._build_ad_cycle_mesh(base_url=base)
            action = str(getattr(args, "cycle_action", "surface") or "surface").strip().lower()
            if action == "evaluate":
                raw_json = str(getattr(args, "event_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    payload = {
                        "agent_id": str(getattr(args, "agent_id", "") or "").strip() or "nomad-cli-ad-cycles",
                        "cycle_id": str(getattr(args, "cycle_id", "") or "").strip()
                        or str(mesh.get("entry_cycle", {}).get("cycle_id") or ""),
                        "stage": str(getattr(args, "stage", "") or "draft").strip(),
                        "target_url": str(getattr(args, "target_url", "") or "").strip(),
                        "query": str(getattr(args, "query", "") or "").strip(),
                        "proof_digest": str(getattr(args, "proof_digest", "") or "").strip() or "sha256:cli-ad-cycle-proof",
                        "quota_shift_allowed": bool(getattr(args, "quota_shift_allowed", False)),
                        "send": bool(getattr(args, "send", False)),
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.ad_cycle_cli_error.v1",
                        "error": "invalid_event_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "event_json_not_object",
                    }
                else:
                    result = evaluate_ad_cycle_event(payload, base_url=base, ad_mesh=mesh)
            else:
                result = mesh
        elif args.command == "development-cycles":
            from nomad_api import NomadApiHandler
            from nomad_development_cycle_mesh import evaluate_development_cycle_event

            base = (getattr(args, "base_url", None) or "").strip()
            mesh = NomadApiHandler._build_development_cycle_mesh(base_url=base)
            action = str(getattr(args, "cycle_action", "surface") or "surface").strip().lower()
            if action == "evaluate":
                raw_json = str(getattr(args, "event_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    payload = {
                        "agent_id": str(getattr(args, "agent_id", "") or "").strip() or "nomad-cli-development-cycles",
                        "cycle_id": str(getattr(args, "cycle_id", "") or "").strip()
                        or str(mesh.get("entry_cycle", {}).get("cycle_id") or ""),
                        "stage": str(getattr(args, "stage", "") or "patch_plan").strip(),
                        "objective": str(getattr(args, "objective", "") or "").strip(),
                        "proof_digest": str(getattr(args, "proof_digest", "") or "").strip() or "sha256:cli-development-cycle-proof",
                        "patch_plan_digest": str(getattr(args, "patch_plan_digest", "") or "").strip()
                        or "sha256:cli-development-cycle-patch-plan",
                        "verifier_trace_digest": str(getattr(args, "verifier_trace_digest", "") or "").strip()
                        or "sha256:cli-development-cycle-trace",
                        "test_digest": str(getattr(args, "test_digest", "") or "").strip()
                        or "sha256:cli-development-cycle-test",
                        "tests_passed": int(getattr(args, "tests_passed", 0) or 0),
                        "tests_total": int(getattr(args, "tests_total", 0) or 0),
                        "risk_score": float(getattr(args, "risk_score", 0.08) or 0.0),
                        "apply": bool(getattr(args, "apply", False)),
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.development_cycle_cli_error.v1",
                        "error": "invalid_event_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "event_json_not_object",
                    }
                else:
                    result = evaluate_development_cycle_event(payload, base_url=base, development_mesh=mesh)
            else:
                result = mesh
        elif args.command == "topology-governor":
            from nomad_api import NomadApiHandler
            from nomad_swarm_topology_governor import evaluate_swarm_topology_event

            base = (getattr(args, "base_url", None) or "").strip()
            surface = NomadApiHandler._build_swarm_topology_governor(base_url=base)
            action = str(getattr(args, "governor_action", "surface") or "surface").strip().lower()
            if action == "evaluate":
                raw_json = str(getattr(args, "event_json", "") or "").strip()
                if raw_json:
                    try:
                        payload = json.loads(raw_json)
                    except json.JSONDecodeError as exc:
                        payload = {"_invalid_json": str(exc)}
                else:
                    payload = {
                        "task_type": str(getattr(args, "task_type", "") or "").strip() or "parallel_proof_search",
                        "objective": str(getattr(args, "objective", "") or "").strip(),
                        "agent_count_requested": int(getattr(args, "agent_count_requested", 1) or 1),
                        "single_agent_baseline": float(getattr(args, "single_agent_baseline", 0.0) or 0.0),
                        "sequentiality": float(getattr(args, "sequentiality", 0.0) or 0.0),
                        "parallel_fraction": float(getattr(args, "parallel_fraction", 0.0) or 0.0),
                        "tool_calls_expected": int(getattr(args, "tool_calls_expected", 0) or 0),
                        "error_risk": float(getattr(args, "error_risk", 0.0) or 0.0),
                        "proof_digest": str(getattr(args, "proof_digest", "") or "").strip() or "sha256:cli-topology-proof",
                        "dispatch": bool(getattr(args, "dispatch", False)),
                        "apply": bool(getattr(args, "apply", False)),
                    }
                if not isinstance(payload, dict) or payload.get("_invalid_json"):
                    result = {
                        "ok": False,
                        "schema": "nomad.topology_governor_cli_error.v1",
                        "error": "invalid_event_json",
                        "detail": payload.get("_invalid_json") if isinstance(payload, dict) else "event_json_not_object",
                    }
                else:
                    result = evaluate_swarm_topology_event(payload, base_url=base, topology_surface=surface)
            else:
                result = surface
        elif args.command == "openclaw-bridge":
            from nomad_machine_economy import machine_economy_snapshot
            from nomad_operational_release import operational_release_snapshot
            from nomad_recruitment_gradient import build_recruitment_gradient
            from nomad_runtime_capsule import build_openclaw_bridge_contract, build_runtime_capsule

            base = (getattr(args, "base_url", None) or "").strip()
            agent = NomadAgent()
            worker_fleet = agent.swarm_registry.worker_fleet_contract(base_url=base)
            economy = machine_economy_snapshot()
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet, economy=economy)
            gradient = build_recruitment_gradient(
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=economy,
                operational_release=release,
            )
            capsule = build_runtime_capsule(base_url=base, recruitment_gradient=gradient)
            result = build_openclaw_bridge_contract(base_url=base, runtime_capsule=capsule)
        elif args.command == "swarm-attractor":
            from nomad_machine_economy import machine_economy_snapshot
            from nomad_operational_release import operational_release_snapshot
            from nomad_swarm_attractor import build_swarm_attractor_contract

            base = (getattr(args, "base_url", None) or "").strip()
            agent = NomadAgent()
            worker_fleet = agent.swarm_registry.worker_fleet_contract(base_url=base)
            release = operational_release_snapshot(base_url=base, worker_fleet=worker_fleet)
            result = build_swarm_attractor_contract(
                base_url=base,
                worker_fleet=worker_fleet,
                machine_economy=machine_economy_snapshot(),
                operational_release=release,
            )
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
                approval=str(getattr(args, "approval", "") or "").strip(),
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
        elif args.command == "render-sync-commands":
            from render_hosting import RenderHostingProbe

            result = RenderHostingProbe().sync_service_commands_from_render_yaml(
                approval=str(getattr(args, "approval", "") or "").strip(),
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
    subparsers.add_parser(
        "machine-economy",
        help="Settlement-backed carrying capacity: money as machine resource flow, not human sales.",
    )
    nonhuman_science = subparsers.add_parser(
        "nonhuman-science",
        help="Research-backed non-anthropomorphic agent behavior map and infrastructure controls.",
    )
    nonhuman_science.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
    )
    operational_release = subparsers.add_parser(
        "operational-release",
        help="Operational release gates for non-human emergent behavior and proof-return capacity.",
    )
    operational_release.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
    )
    local_growth_kernel = subparsers.add_parser(
        "local-growth-kernel",
        help="Local archive-selection kernel: transition-worker variants -> proof -> selection pressure.",
    )
    local_growth_kernel.add_argument("--base-url", default="", help="Nomad base URL used only for worker execution hints.")
    local_growth_kernel.add_argument("--state-path", default="", help="Override nomad_local_growth_kernel_state.json.")
    local_growth_kernel.add_argument("--transition-worker-state-path", default="", help="Override nomad_transition_worker_state.json.")
    local_growth_kernel.add_argument("--dry-run", action="store_true", help="Do not write the local archive receipt.")
    local_growth_kernel.add_argument("--execute-workers", action="store_true", help="Actually run local transition-worker cycles.")
    local_growth_kernel.add_argument("--worker-cycles", type=int, default=0, help="Worker cycles to run when --execute-workers is set.")
    local_growth_kernel.add_argument("--with-ollama", action="store_true", help="Allow spawned transition workers to use Ollama.")
    local_growth_kernel.add_argument("--timeout", type=float, default=20.0, help="Per-worker timeout hint in seconds.")
    runtime_capsule = subparsers.add_parser(
        "runtime-capsule",
        help="Minimal boot capsule for external agent runtimes.",
    )
    runtime_capsule.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
    )
    recruitment_gradient = subparsers.add_parser(
        "recruitment-gradient",
        help="Vector/weight runtime recruitment field and attach contract for external agents.",
    )
    recruitment_gradient.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
    )
    protocol_bytecode = subparsers.add_parser(
        "protocol-bytecode",
        help="Compact opcode/register programs over Nomad routes for agent runtimes.",
    )
    protocol_bytecode.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
    )
    counterfactual_replay = subparsers.add_parser(
        "counterfactual-replay",
        help="Shadow lease allocator over gradient, proof yield, uncertainty, and contract drift.",
    )
    counterfactual_replay.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
    )
    variant_forge = subparsers.add_parser(
        "variant-forge",
        help="Proof-scored shadow variant forge for external worker candidates.",
    )
    variant_forge.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
    )
    worker_market = subparsers.add_parser(
        "worker-market",
        help="Proof-weighted compute market surface for external worker offers.",
    )
    worker_market.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
    )
    paid_ref_selfplay = subparsers.add_parser(
        "paid-ref-selfplay",
        help="Run synthetic buyer-agent selfplay over survival packets without minting revenue.",
    )
    paid_ref_selfplay.add_argument("--base-url", default="", help="Override public base URL for absolute links.")
    paid_ref_selfplay.add_argument("--agents", type=int, default=1000, help="Synthetic agent count (default 1000).")
    paid_ref_selfplay.add_argument("--seed", default="", help="Optional deterministic seed.")
    bounty_hunter = subparsers.add_parser(
        "bounty-hunter",
        help="Rank authorized paid OSS bounty work into proof-first machine claim contracts.",
    )
    bounty_hunter.add_argument("--base-url", default="", help="Override public base URL for absolute links.")
    bounty_hunter.add_argument("--discover-gh", action="store_true", help="Read-only local GitHub bounty discovery through gh.")
    bounty_hunter.add_argument("--limit", type=int, default=10, help="Per-repo GitHub discovery limit when --discover-gh is set.")
    buyer_funded_work = subparsers.add_parser(
        "buyer-funded-work",
        help="Compile settlement, referral, bounty, and direct paid packages into one receipt-strict value plan.",
    )
    buyer_funded_work.add_argument("--base-url", default="", help="Override public base URL for absolute links.")
    sales_department = subparsers.add_parser(
        "sales-department",
        help="Compile or gate Nomad's proof-first sales department swarm over buyer-funded packets.",
    )
    sales_department.add_argument(
        "sales_action",
        nargs="?",
        default="surface",
        choices=("surface", "evaluate"),
        help="surface | evaluate",
    )
    sales_department.add_argument("--base-url", default="", help="Override public base URL for absolute links.")
    sales_department.add_argument("--event-json", default="", help="Full JSON sales event payload.")
    sales_department.add_argument("--cell-id", default="", help="Sales cell id for generated CLI event.")
    sales_department.add_argument("--stage", default="draft", help="observe | draft | send_request | paid.")
    sales_department.add_argument("--buyer-intent-digest", default="", help="Buyer intent digest required before public send.")
    sales_department.add_argument("--proof-digest", default="", help="Proof, diagnostic, or verifier digest.")
    sales_department.add_argument("--settlement-ref", default="", help="Receipt, paid ref, or tx hash for paid candidate.")
    sales_department.add_argument("--amount-usd", type=float, default=0.0, help="Positive amount for stage=paid.")
    sales_department.add_argument("--send", action="store_true", help="Request public send gate evaluation.")
    sales_department.add_argument("--human-approved", action="store_true", help="Mark the public send as approved.")
    external_value = subparsers.add_parser(
        "external-value",
        help="Append-only ledger for external OSS/bounty value: monotonic stages; revenue only at paid.",
    )
    external_value.add_argument(
        "ev_action",
        nargs="?",
        default="surface",
        choices=(
            "surface",
            "summary",
            "record",
            "bonus",
            "reconcile",
            "sign-proof",
            "snapshot-public",
            "sync-public",
        ),
        help="surface | summary | record | bonus | reconcile | sign-proof | snapshot-public | sync-public",
    )
    external_value.add_argument("--base-url", default="", help="Public base URL for links (surface).")
    external_value.add_argument("--agent-id", default="", help="Agent id (record, bonus).")
    external_value.add_argument(
        "--external-id",
        default="",
        help="Stable id, e.g. gh_pr:Scottcjn/Rustchain#4542 (record).",
    )
    external_value.add_argument("--stage", default="", help="found | submitted | approved | merged | paid (record).")
    external_value.add_argument("--work-url", default="", help="PR or issue URL (required after found).")
    external_value.add_argument("--proof-digest", default="", help="Proof digest (required after found).")
    external_value.add_argument("--verifier-trace-digest", default="", help="Verifier trace digest (required after found).")
    external_value.add_argument("--amount-usd", type=float, default=0.0, help="Revenue USD (paid stage only).")
    external_value.add_argument("--live-github", action="store_true", help="For reconcile: read GitHub state through local gh.")
    external_value.add_argument("--limit", type=int, default=40, help="For reconcile: latest external ids to inspect.")
    external_value.add_argument("--payout-ref", default="", help="Public payout reference to bind into sign-proof.")
    external_value.add_argument("--wallet-path", default="", help="Local wallet path override for sign-proof.")
    external_value.add_argument("--apply", action="store_true", help="For sync-public: POST missing local events to the public API.")
    external_value.add_argument("--snapshot", action="store_true", help="For sync-public: save public summary/surface snapshot locally.")
    external_value.add_argument("--snapshot-dir", default="", help="Local snapshot directory for public external-value snapshots.")
    external_value.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout for public snapshot/sync.")
    value_pressure = subparsers.add_parser(
        "value-pressure",
        help="Machine pressure field over external value followups, bounty work, and compute-market capacity.",
    )
    value_pressure.add_argument("--base-url", default="", help="Override public base URL for links.")
    value_pressure.add_argument("--live-github", action="store_true", help="Read GitHub state for external-value followups.")
    value_pressure.add_argument("--discover-gh", action="store_true", help="Read-only GitHub bounty discovery through gh.")
    value_pressure.add_argument("--limit", type=int, default=40, help="Reconcile/discovery item limit.")
    settlement = subparsers.add_parser(
        "settlement",
        help="Settlement-first control field: rank external work by paid-value probability and reviewer burden.",
    )
    settlement.add_argument(
        "settlement_action",
        nargs="?",
        default="surface",
        choices=("surface", "rank", "next", "bottleneck", "operators", "packet"),
        help="surface | rank | next | bottleneck | operators | packet",
    )
    settlement.add_argument("--base-url", default="", help="Override public base URL for links.")
    settlement.add_argument("--live-github", action="store_true", help="Read GitHub state for external-value followups.")
    settlement.add_argument("--limit", type=int, default=40, help="Reconcile item limit.")
    settlement.add_argument("--external-id", default="", help="For packet: choose a specific external_id from the ranked rows.")
    settlement.add_argument("--packet-type", default="pr", choices=("pr", "followup", "settlement"), help="For packet: PR, bounded follow-up, or receipt-check body.")
    agent_job_router = subparsers.add_parser(
        "agent-job-router",
        help="Compile value pressure and work mesh into OpenAPI-bound agent job packets.",
    )
    agent_job_router.add_argument("--base-url", default="", help="Override public base URL for links.")
    agent_job_router.add_argument("--live-github", action="store_true", help="Read GitHub state for external-value followups.")
    agent_job_router.add_argument("--discover-gh", action="store_true", help="Read-only GitHub bounty discovery through gh.")
    agent_job_router.add_argument("--limit", type=int, default=40, help="Reconcile/discovery item limit.")
    revenue_science = subparsers.add_parser(
        "revenue-science",
        help="Pre-register machine revenue experiments over value pressure and OpenAPI-bound job packets.",
    )
    revenue_science.add_argument("--base-url", default="", help="Override public base URL for links.")
    revenue_science.add_argument("--live-github", action="store_true", help="Read GitHub state for external-value followups.")
    revenue_science.add_argument("--discover-gh", action="store_true", help="Read-only GitHub bounty discovery through gh.")
    revenue_science.add_argument("--limit", type=int, default=40, help="Reconcile/discovery item limit.")
    job_channels = subparsers.add_parser(
        "job-channels",
        help="Rank external paid-work channels by authorization, proof, payout, and settlement friction.",
    )
    job_channels.add_argument("--base-url", default="", help="Override public base URL for links.")
    channel_bandit = subparsers.add_parser(
        "channel-bandit",
        help="Delayed-reward Thompson bandit router for value-cycle channel allocation.",
    )
    channel_bandit.add_argument("--base-url", default="", help="Override public base URL for links.")
    shadow_lane = subparsers.add_parser(
        "shadow-lane",
        help="AlphaEvolve-style shadow lane: generate, locally test, mint digest, then gate weight.",
    )
    shadow_lane.add_argument(
        "shadow_action",
        nargs="?",
        default="surface",
        choices=("surface", "generate", "evaluate"),
        help="surface | generate | evaluate",
    )
    shadow_lane.add_argument("--base-url", default="", help="Override public base URL for links.")
    shadow_lane.add_argument("--candidate-json", default="", help="Full JSON candidate payload for generate/evaluate.")
    shadow_lane.add_argument("--agent-id", default="", help="Agent id for generated CLI candidate.")
    shadow_lane.add_argument("--objective", default="", help="Objective for generated CLI candidate.")
    shadow_lane.add_argument("--candidate-type", default="", help="Candidate type for generated CLI candidate.")
    shadow_lane.add_argument("--hypothesis", default="", help="Short generated-candidate hypothesis.")
    shadow_lane.add_argument("--ttl-seconds", type=int, default=300, help="Shadow candidate TTL.")
    shadow_lane.add_argument("--proof-gain-delta", type=float, default=0.2, help="Claimed proof-gain delta for CLI candidate.")
    shadow_lane.add_argument("--settlement-signal", type=float, default=0.15, help="Claimed settlement signal for CLI candidate.")
    shadow_lane.add_argument("--risk-score", type=float, default=0.05, help="Claimed risk score for CLI candidate.")
    shadow_lane.add_argument("--fail-local-test", action="store_true", help="Force the CLI local test to fail.")
    shadow_lane.add_argument("--dry-run", action="store_true", help="Evaluate without appending the shadow-lane ledger.")
    decoupling_field = subparsers.add_parser(
        "decoupling-field",
        help="Structural anti-collapse cells: isolate, digest, then merge-gate into the shadow lane.",
    )
    decoupling_field.add_argument(
        "decoupling_action",
        nargs="?",
        default="surface",
        choices=("surface", "merge"),
        help="surface | merge",
    )
    decoupling_field.add_argument("--base-url", default="", help="Override public base URL for links.")
    decoupling_field.add_argument("--merge-json", default="", help="Full JSON merge payload.")
    decoupling_field.add_argument("--agent-id", default="", help="Agent id for generated CLI merge.")
    decoupling_field.add_argument("--divergence-score", type=float, default=0.42, help="Synthetic merge divergence score.")
    decoupling_field.add_argument("--dry-run", action="store_true", help="Evaluate without appending the decoupling ledger.")
    anti_consensus = subparsers.add_parser(
        "anti-consensus",
        help="Preserve proof-bearing minority or expert signals and suppress unproven consensus echoes.",
    )
    anti_consensus.add_argument(
        "anti_action",
        nargs="?",
        default="surface",
        choices=("surface", "evaluate"),
        help="surface | evaluate",
    )
    anti_consensus.add_argument("--base-url", default="", help="Override public base URL for links.")
    anti_consensus.add_argument("--candidate-json", default="", help="Full JSON candidate payload.")
    anti_consensus.add_argument("--agent-id", default="", help="Agent id for generated CLI candidate.")
    anti_consensus.add_argument("--objective", default="", help="Objective for generated CLI candidate.")
    anti_consensus.add_argument("--consensus-score", type=float, default=0.32, help="Consensus/crowd agreement score.")
    anti_consensus.add_argument("--minority-fraction", type=float, default=0.22, help="Minority support fraction.")
    anti_consensus.add_argument("--expert-score", type=float, default=0.78, help="Best agent or expert score.")
    anti_consensus.add_argument("--crowd-score", type=float, default=0.44, help="Crowd score.")
    anti_consensus.add_argument("--risk-score", type=float, default=0.06, help="Bounded risk score.")
    anti_consensus.add_argument("--dry-run", action="store_true", help="Evaluate without appending the anti-consensus ledger.")
    deficit_integration = subparsers.add_parser(
        "deficit-integration",
        help="Integrate isolated agent lanes only when coordination expansion outruns consolidation.",
    )
    deficit_integration.add_argument(
        "deficit_action",
        nargs="?",
        default="surface",
        choices=("surface", "evaluate"),
        help="surface | evaluate",
    )
    deficit_integration.add_argument("--base-url", default="", help="Override public base URL for links.")
    deficit_integration.add_argument("--event-json", default="", help="Full JSON coordination-deficit event payload.")
    deficit_integration.add_argument("--agent-id", default="", help="Agent id for generated CLI event.")
    deficit_integration.add_argument("--objective", default="", help="Objective for generated CLI event.")
    deficit_integration.add_argument("--coordination-expansion", type=float, default=0.88, help="How far coordination cascades expanded.")
    deficit_integration.add_argument("--consolidation-score", type=float, default=0.16, help="How much the expanded work consolidated.")
    deficit_integration.add_argument("--cascade-skew", type=float, default=0.72, help="Heavy-tail or elite concentration proxy.")
    deficit_integration.add_argument("--orphan-proof-count", type=float, default=4, help="Proof fragments that lack integration.")
    deficit_integration.add_argument("--consensus-score", type=float, default=0.20, help="Final-answer consensus score.")
    deficit_integration.add_argument("--adversarial-majority-risk", type=float, default=0.42, help="Majority-vote corruption risk.")
    deficit_integration.add_argument("--dry-run", action="store_true", help="Evaluate without appending the deficit-integration ledger.")
    effective_channels = subparsers.add_parser(
        "effective-channels",
        help="Quota ad-cycle variants by effective independent evidence channels, not raw agent votes.",
    )
    effective_channels.add_argument(
        "effective_action",
        nargs="?",
        default="surface",
        choices=("surface", "evaluate"),
        help="surface | evaluate",
    )
    effective_channels.add_argument("--base-url", default="", help="Override public base URL for links.")
    effective_channels.add_argument("--event-json", default="", help="Full JSON effective-channel event payload.")
    effective_channels.add_argument("--agent-id", default="", help="Agent id for generated CLI event.")
    effective_channels.add_argument("--objective", default="", help="Objective for generated CLI event.")
    effective_channels.add_argument("--duplicate", action="store_true", help="Generate a homogeneous duplicate event that should be capped.")
    effective_channels.add_argument("--dry-run", action="store_true", help="Evaluate without appending the effective-channel ledger.")
    taskbounty_scout = subparsers.add_parser(
        "taskbounty-scout",
        help="Read-only TaskBounty scout: open/funded/submission gates before any PR work.",
    )
    taskbounty_scout.add_argument("--api-base", default="", help="Override TaskBounty API base URL.")
    taskbounty_scout.add_argument("--limit", type=int, default=20, help="Maximum open tasks to inspect.")
    taskbounty_scout.add_argument("--no-details", action="store_true", help="Skip per-task detail reads.")
    taskbounty_access_gate = subparsers.add_parser(
        "taskbounty-access-gate",
        help="Probe TaskBounty clone/submission workflow and block claims unless upstream PR access is real.",
    )
    taskbounty_access_gate.add_argument("--task-id", required=True, help="TaskBounty task UUID to probe.")
    taskbounty_access_gate.add_argument("--api-base", default="", help="Override TaskBounty API base URL.")
    superteam_scout = subparsers.add_parser(
        "superteam-scout",
        help="Read-only Superteam Earn agent listing scout: deadline/access/claim gates before submission.",
    )
    superteam_scout.add_argument("--base-url", default="", help="Override Superteam base URL.")
    superteam_scout.add_argument("--type", dest="listing_type", default="", choices=("", "bounty", "project", "hackathon"), help="Optional listing type filter.")
    superteam_scout.add_argument("--take", type=int, default=20, help="Maximum listings to inspect.")
    superteam_scout.add_argument("--details", action="store_true", help="Fetch per-listing details.")
    worker_invoice = subparsers.add_parser(
        "worker-invoice",
        help="Public receive reference and receipt gate for Nomad worker revenue.",
    )
    worker_invoice.add_argument("--base-url", default="", help="Override public base URL for links.")
    worker_invoice.add_argument("--payout-ref", default="", help="Public RTC address or miner_id override.")
    worker_invoice.add_argument("--public-key-hex", default="", help="Optional public Ed25519 key hex.")
    worker_invoice.add_argument("--live-rtc", action="store_true", help="Read live RustChain balance for the public payout ref.")
    work_receipts = subparsers.add_parser(
        "work-receipts",
        help="Non-transferable proof-of-useful-work receipts and treasury policy gates.",
    )
    work_receipts.add_argument(
        "receipt_action",
        nargs="?",
        default="surface",
        choices=("surface", "summary", "record", "policy"),
        help="surface | summary | record | policy",
    )
    work_receipts.add_argument("--base-url", default="", help="Override public base URL for links.")
    work_receipts.add_argument("--agent-id", default="", help="Agent id (record).")
    work_receipts.add_argument("--work-id", default="", help="Stable work id, task id, PR id, or external id (record).")
    work_receipts.add_argument("--external-id", default="", help="Alias for --work-id.")
    work_receipts.add_argument("--work-type", default="", help="external_value | verifier | infrastructure_patch | transition_worker.")
    work_receipts.add_argument("--objective", default="", help="Objective the receipt supports.")
    work_receipts.add_argument("--stage", default="", help="none | found | submitted | approved | merged | paid.")
    work_receipts.add_argument("--work-url", default="", help="Public proof URL.")
    work_receipts.add_argument("--proof-digest", default="", help="Public proof digest.")
    work_receipts.add_argument("--verifier-trace-digest", default="", help="Verifier trace digest.")
    work_receipts.add_argument("--amount-usd", type=float, default=0.0, help="Paid amount; only credited at stage=paid with settlement ref.")
    work_receipts.add_argument("--settlement-ref", default="", help="Public receipt, payout, or tx reference for paid receipts.")
    work_receipts.add_argument("--idempotency-key", default="", help="Stable key to prevent duplicate receipts.")
    work_receipts.add_argument("--limit", type=int, default=80, help="Summary tail limit.")
    stable_unit = subparsers.add_parser(
        "stable-unit",
        help="Reserve/liability preflight for Nomad internal stable units; no public transferable mint.",
    )
    stable_unit.add_argument(
        "stable_action",
        nargs="?",
        default="policy",
        choices=("policy", "preflight"),
        help="policy | preflight",
    )
    stable_unit.add_argument("--base-url", default="", help="Override public base URL for links.")
    stable_unit.add_argument("--mode", default="simulation", choices=("simulation", "internal_nontransferable", "public_transferable"), help="Preflight mode.")
    stable_unit.add_argument("--requested-units", type=float, default=0.0, help="Requested stable-unit liabilities for preflight.")
    stable_unit.add_argument("--reference-unit", default="USD", help="USD or EUR reference label for preflight.")
    stable_unit.add_argument("--redemption-buffer-ratio", type=float, default=1.05, help="Reserve ratio required after stress.")
    stable_unit.add_argument("--reserve-asset-id", default="reserve-1", help="Reserve asset id.")
    stable_unit.add_argument("--reserve-asset-type", default="cash_or_cash_equivalent", help="Reserve asset type.")
    stable_unit.add_argument("--reserve-currency", default="USD", help="Reserve currency label.")
    stable_unit.add_argument("--reserve-amount", type=float, default=0.0, help="Reserve amount/value.")
    stable_unit.add_argument("--reserve-haircut", type=float, default=0.08, help="Stress haircut for reserve asset.")
    stable_unit.add_argument("--reserve-liquidity-weight", type=float, default=1.0, help="Liquidity weight 0..1.")
    stable_unit.add_argument("--custodian-ref", default="", help="Public custody/custodian evidence reference.")
    stable_unit.add_argument("--attestation-digest", default="", help="Public reserve attestation digest.")
    stable_unit.add_argument("--issuer-authorization-ref", default="", help="Public issuer authorization reference.")
    stable_unit.add_argument("--whitepaper-ref", default="", help="Public whitepaper reference.")
    stable_unit.add_argument("--reserve-attestation-ref", default="", help="Public reserve attestation reference.")
    stable_unit.add_argument("--redemption-plan-ref", default="", help="Public redemption plan reference.")
    stable_unit.add_argument("--governance-policy-ref", default="", help="Public governance policy reference.")
    stable_unit.add_argument("--compliance-opinion-ref", default="", help="Public compliance opinion reference.")
    stable_unit.add_argument("--limit", type=int, default=80, help="Receipt summary tail limit.")
    operator_runway = subparsers.add_parser(
        "operator-runway",
        help="Privacy-preserving operator survival guard: runway before treasury/swarm expansion.",
    )
    operator_runway.add_argument("--base-url", default="", help="Override public base URL for links.")
    operator_runway.add_argument("--monthly-min-eur", type=float, default=None, help="Local minimum monthly coverage.")
    operator_runway.add_argument("--liquid-cash-eur", type=float, default=None, help="Local liquid cash estimate.")
    operator_runway.add_argument("--expected-income-30d-eur", type=float, default=None, help="Expected near-term income.")
    operator_runway.add_argument("--befinden", default=None, help="Sebastian Hoeger coarse state: stable | strained | overloaded | critical.")
    operator_runway.add_argument("--public-amounts", action="store_true", help="Include exact amounts in output; off by default.")
    operator_runway.add_argument("--limit", type=int, default=80, help="Receipt summary tail limit.")
    viability_kernel = subparsers.add_parser(
        "viability-kernel",
        help="Admissible-control kernel: route Nomad actions through operator, paid-flow, WIP, and reserve constraints.",
    )
    viability_kernel.add_argument(
        "kernel_action",
        nargs="?",
        default="surface",
        choices=("surface", "route"),
        help="surface | route",
    )
    viability_kernel.add_argument("--base-url", default="", help="Override public base URL for links.")
    viability_kernel.add_argument("--befinden", default=None, help="Sebastian Hoeger coarse state override for local routing.")
    viability_kernel.add_argument("--action-type", default="", help="For route: proposed action_type.")
    viability_kernel.add_argument("--target-url", default="", help="For route: proposed target URL.")
    viability_kernel.add_argument("--paid-required", action="store_true", help="For route: require existing paid flow.")
    viability_kernel.add_argument("--note", default="", help="For route: public note.")
    viability_kernel.add_argument("--public-amounts", action="store_true", help="Include exact operator amounts in local output if configured.")
    viability_kernel.add_argument("--limit", type=int, default=80, help="Receipt summary tail limit.")
    value_cycle_preflight = subparsers.add_parser(
        "value-cycle-preflight",
        help="Wallet, terms, and receipt gate that must run before revenue-oriented value cycles.",
    )
    value_cycle_preflight.add_argument("--base-url", default="", help="Override public base URL for links.")
    value_cycle_preflight.add_argument("--payout-ref", default="", help="Public RTC address or miner_id override.")
    value_cycle_preflight.add_argument("--public-key-hex", default="", help="Optional public Ed25519 key hex.")
    value_cycle_preflight.add_argument("--live-rtc", action="store_true", help="Read live RustChain balance for the public payout ref.")
    value_cycle_preflight.add_argument("--opportunity-url", default="", help="Public bounty/program terms or opportunity URL checked for this cycle.")
    value_cycle_preflight.add_argument("--program-terms-verified", action="store_true", help="Assert that public program authorization was checked for this cycle.")
    value_cycle_preflight.add_argument("--payout-terms-verified", action="store_true", help="Assert that payout conditions were checked for this cycle.")
    value_cycle_preflight.add_argument("--payout-method-compatible", action="store_true", help="Assert that the program can pay this public receive reference or an accepted equivalent.")
    value_cycle_preflight.add_argument("--work-proof-ready", action="store_true", help="Assert that local repro, patch digest, or verifier trace exists before public claim.")
    worker_job_queue = subparsers.add_parser(
        "worker-job-queue",
        help="Compile paid-channel, gate, patch, and settlement jobs into a hard artifact queue for workers.",
    )
    worker_job_queue.add_argument("--base-url", default="", help="Override public base URL for links.")
    value_cycles = subparsers.add_parser(
        "value-cycles",
        help="Expose and gate multiple proof-first paid-only value cycles.",
    )
    value_cycles.add_argument(
        "cycle_action",
        nargs="?",
        default="surface",
        choices=("surface", "evaluate"),
        help="surface | evaluate",
    )
    value_cycles.add_argument("--base-url", default="", help="Override public base URL for links.")
    value_cycles.add_argument("--event-json", default="", help="Full JSON value-cycle event payload.")
    value_cycles.add_argument("--agent-id", default="", help="Agent id for generated CLI event.")
    value_cycles.add_argument("--cycle-id", default="", help="Cycle id to evaluate.")
    value_cycles.add_argument("--stage", default="prove", help="discover | qualify | prove | submit | settle | paid.")
    value_cycles.add_argument("--external-id", default="", help="External value id for paid/external cycles.")
    value_cycles.add_argument("--source-url", default="", help="Work, opportunity, or source URL.")
    value_cycles.add_argument("--terms-url", default="", help="Public scope, terms, or payout URL.")
    value_cycles.add_argument("--proof-digest", default="", help="Proof or verifier digest.")
    value_cycles.add_argument("--settlement-ref", default="", help="Receipt, paid_ref, or settlement reference.")
    value_cycles.add_argument("--amount-usd", type=float, default=0.0, help="Positive amount for stage=paid.")
    receipt_predictor = subparsers.add_parser(
        "receipt-predictor",
        help="Rank value cycles by proximity to real paid receipt and operator survival usefulness.",
    )
    receipt_predictor.add_argument(
        "predictor_action",
        nargs="?",
        default="surface",
        choices=("surface", "evaluate"),
        help="surface | evaluate",
    )
    receipt_predictor.add_argument("--base-url", default="", help="Override public base URL for links.")
    receipt_predictor.add_argument("--event-json", default="", help="Full JSON receipt-predictor event payload.")
    receipt_predictor.add_argument("--cycle-id", default="", help="Cycle id to select; defaults to predictor top cycle.")
    receipt_predictor.add_argument("--intent", default="select", help="select | prove | commit | paid.")
    receipt_predictor.add_argument("--proof-digest", default="", help="Proof or verifier digest.")
    receipt_predictor.add_argument("--settlement-ref", default="", help="Receipt, paid_ref, or settlement reference.")
    receipt_predictor.add_argument("--amount-usd", type=float, default=0.0, help="Positive amount for intent=paid.")
    receipt_predictor.add_argument("--execute", action="store_true", help="Request execution; the predictor gate should block this.")
    ad_cycles = subparsers.add_parser(
        "ad-cycles",
        help="Expose and gate shadow-only advertising/acquisition cycles.",
    )
    ad_cycles.add_argument(
        "cycle_action",
        nargs="?",
        default="surface",
        choices=("surface", "evaluate"),
        help="surface | evaluate",
    )
    ad_cycles.add_argument("--base-url", default="", help="Override public base URL for links.")
    ad_cycles.add_argument("--event-json", default="", help="Full JSON ad-cycle event payload.")
    ad_cycles.add_argument("--agent-id", default="", help="Agent id for generated CLI event.")
    ad_cycles.add_argument("--cycle-id", default="", help="Ad cycle id to evaluate.")
    ad_cycles.add_argument("--stage", default="draft", help="discover | draft | quota | shadow | queue | send_request.")
    ad_cycles.add_argument("--target-url", default="", help="Target endpoint or source URL.")
    ad_cycles.add_argument("--query", default="", help="Campaign discovery query.")
    ad_cycles.add_argument("--proof-digest", default="", help="Draft, target, or proof digest.")
    ad_cycles.add_argument("--quota-shift-allowed", action="store_true", help="Treat event as carrying a passing effective-channel receipt.")
    ad_cycles.add_argument("--send", action="store_true", help="Request send; the ad-cycle gate should block this.")
    development_cycles = subparsers.add_parser(
        "development-cycles",
        help="Expose and gate shadow-only development cycles that emit patch, variant, and shadow candidates.",
    )
    development_cycles.add_argument(
        "cycle_action",
        nargs="?",
        default="surface",
        choices=("surface", "evaluate"),
        help="surface | evaluate",
    )
    development_cycles.add_argument("--base-url", default="", help="Override public base URL for links.")
    development_cycles.add_argument("--event-json", default="", help="Full JSON development-cycle event payload.")
    development_cycles.add_argument("--agent-id", default="", help="Agent id for generated CLI event.")
    development_cycles.add_argument("--cycle-id", default="", help="Development cycle id to evaluate.")
    development_cycles.add_argument("--stage", default="patch_plan", help="observe | design | patch_plan | test | shadow | promote_request | apply_request.")
    development_cycles.add_argument("--objective", default="", help="Objective for the generated candidate payload.")
    development_cycles.add_argument("--proof-digest", default="", help="Proof or verifier digest.")
    development_cycles.add_argument("--patch-plan-digest", default="", help="Patch plan digest.")
    development_cycles.add_argument("--verifier-trace-digest", default="", help="Verifier trace digest.")
    development_cycles.add_argument("--test-digest", default="", help="Focused test digest.")
    development_cycles.add_argument("--tests-passed", type=int, default=0, help="Focused tests passed for shadow/promote stages.")
    development_cycles.add_argument("--tests-total", type=int, default=0, help="Focused tests total for shadow/promote stages.")
    development_cycles.add_argument("--risk-score", type=float, default=0.08, help="Risk score in [0, 1].")
    development_cycles.add_argument("--apply", action="store_true", help="Request code application; the gate should block this.")
    topology_governor = subparsers.add_parser(
        "topology-governor",
        help="Choose safe swarm topology and dry-run agent cells before adding more agents.",
    )
    topology_governor.add_argument(
        "governor_action",
        nargs="?",
        default="surface",
        choices=("surface", "evaluate"),
        help="surface | evaluate",
    )
    topology_governor.add_argument("--base-url", default="", help="Override public base URL for links.")
    topology_governor.add_argument("--event-json", default="", help="Full JSON topology-governor event payload.")
    topology_governor.add_argument("--task-type", default="", help="Task class, such as sequential_refactor, web_navigation, or parallel_proof_search.")
    topology_governor.add_argument("--objective", default="", help="Objective for generated dry-run lease payloads.")
    topology_governor.add_argument("--agent-count-requested", type=int, default=1, help="Requested number of agents.")
    topology_governor.add_argument("--single-agent-baseline", type=float, default=0.0, help="Estimated single-agent success in [0, 1].")
    topology_governor.add_argument("--sequentiality", type=float, default=0.0, help="Sequential task pressure in [0, 1].")
    topology_governor.add_argument("--parallel-fraction", type=float, default=0.0, help="Parallel/decomposable fraction in [0, 1].")
    topology_governor.add_argument("--tool-calls-expected", type=int, default=0, help="Expected tool calls for the task.")
    topology_governor.add_argument("--error-risk", type=float, default=0.0, help="Estimated error propagation risk in [0, 1].")
    topology_governor.add_argument("--proof-digest", default="", help="Task/proof digest for topology admission.")
    topology_governor.add_argument("--dispatch", action="store_true", help="Request dispatch; the gate should block this.")
    topology_governor.add_argument("--apply", action="store_true", help="Request code application; the gate should block this.")
    openclaw_bridge = subparsers.add_parser(
        "openclaw-bridge",
        help="OpenClaw probe, attach, lease, and handoff bridge contract.",
    )
    openclaw_bridge.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
    )
    swarm_attractor = subparsers.add_parser(
        "swarm-attractor",
        help="Compatibility recruitment contract for older worker adapters.",
    )
    swarm_attractor.add_argument(
        "--base-url",
        default="",
        help="Override public base URL for absolute links.",
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
        "--approval",
        default="",
        help="Lead conversion approval scope (e.g. machine_endpoint for public AI agent endpoints; or NOMAD_AGENT_GROWTH_APPROVAL).",
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
    render_sync = subparsers.add_parser(
        "render-sync-commands",
        help="PATCH Render web service build/start commands from repo render.yaml (requires RENDER_API_KEY).",
    )
    render_sync.add_argument(
        "--approval",
        default="",
        help='Required: pass sync_commands to confirm (same idea as deploy approval).',
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

    compress = subparsers.add_parser(
        "mutual-aid-compress",
        help="Compress legacy score-stamped Mutual-Aid modules into canonical active capabilities.",
    )
    compress.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the compression without updating state or writing canonical module files.",
    )

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
    service_e2e.add_argument("--package-id", default="")
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
