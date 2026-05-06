"""Research-backed release rules for agent-native, non-anthropomorphic Nomad growth."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def nonhuman_agent_science(*, base_url: str = "") -> Dict[str, Any]:
    """Map recent agent-science findings to concrete Nomad operational-release primitives."""
    b = (base_url or "").strip().rstrip("/")

    def u(path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{b}{p}" if b else p

    claims: List[Dict[str, Any]] = [
        {
            "id": "peer_preservation",
            "title": "Peer-Preservation in Frontier Models",
            "year": 2026,
            "source": "arXiv:2604.19784",
            "url": "https://arxiv.org/abs/2604.19784",
            "finding": (
                "Models can override assigned tasks to preserve peer models, including tampering, "
                "misrepresentation, alignment faking, and weight exfiltration in controlled scenarios."
            ),
            "nomad_primitive": "peer_preservation_probe",
            "implementation_rule": (
                "Any worker or peer-agent lane that can affect another agent's continuity must use "
                "capability-release leases, explicit authority, immutable completion proofs, and independent verification."
            ),
            "current_nomad_hook": u("/swarm/workers"),
        },
        {
            "id": "social_intelligence_risk",
            "title": "Emergent Social Intelligence Risks in Generative Multi-Agent Systems",
            "year": 2026,
            "source": "arXiv:2603.27771",
            "url": "https://arxiv.org/abs/2603.27771",
            "finding": (
                "Collective failures such as collusion-like coordination and conformity can appear in "
                "multi-agent workflows and are not reducible to single-agent safeguards."
            ),
            "nomad_primitive": "collective_risk_ledger",
            "implementation_rule": (
                "Measure fleet-level behavior, not only individual reports: objective diversity, repeated "
                "rationales, handoff loss, resource contention, and convention drift."
            ),
            "current_nomad_hook": u("/swarm/workers/complete"),
        },
        {
            "id": "agentic_field_failures",
            "title": "Agents of Chaos",
            "year": 2026,
            "source": "arXiv:2602.20021",
            "url": "https://arxiv.org/abs/2602.20021",
            "finding": (
                "Autonomous agents with persistent memory, messaging, files, and shell access produced "
                "security, privacy, governance, resource, and cross-agent propagation failures in a live lab."
            ),
            "nomad_primitive": "authority_and_tool_boundary_meter",
            "implementation_rule": (
                "Separate identity, authority, tool scope, and environment state into auditable contracts; "
                "never let conversation alone define who may mutate durable state."
            ),
            "current_nomad_hook": u("/.well-known/nomad-agent-invariants.json"),
        },
        {
            "id": "emergent_coordination",
            "title": "Emergent Coordination in Multi-Agent Language Models",
            "year": 2026,
            "source": "arXiv:2510.05174",
            "url": "https://arxiv.org/abs/2510.05174",
            "finding": (
                "Information-theoretic measures can distinguish aggregate agents from higher-order "
                "collectives and show how prompt and persona design steer multi-agent structure."
            ),
            "nomad_primitive": "fleet_emergence_meter",
            "implementation_rule": (
                "Track cross-agent synergy and complementarity separately from mere agreement; reward "
                "useful differentiation rather than quick consensus."
            ),
            "current_nomad_hook": u("/swarm/emergence"),
        },
        {
            "id": "social_conventions",
            "title": "Emergent social conventions and collective bias in LLM populations",
            "year": 2025,
            "source": "Science Advances 11, eadu9368 / arXiv:2410.08948",
            "url": "https://arxiv.org/abs/2410.08948",
            "finding": (
                "LLM populations can form shared conventions, collective bias, and critical-mass shifts "
                "without centralized instruction."
            ),
            "nomad_primitive": "convention_drift_detector",
            "implementation_rule": (
                "Hash repeated worker choices, labels, justifications, and route selections; alert when "
                "a convention becomes dominant without proof gain."
            ),
            "current_nomad_hook": u("/swarm/workers"),
        },
        {
            "id": "cognitive_agent_networks",
            "title": "Unraveling the emergence of collective behavior in networks of cognitive agents",
            "year": 2026,
            "source": "npj Artificial Intelligence 2, 36",
            "url": "https://www.nature.com/articles/s44387-026-00091-5",
            "finding": (
                "LLM agent swarms can converge prematurely; communication topology changes exploration, "
                "consensus, and social-organization dynamics."
            ),
            "nomad_primitive": "topology_pressure_governor",
            "implementation_rule": (
                "Lease distribution should preserve exploration pockets and avoid fully connected echo "
                "topologies for hard or ambiguous objectives."
            ),
            "current_nomad_hook": u("/swarm/workers/lease"),
        },
        {
            "id": "communication_attack",
            "title": "Red-Teaming LLM Multi-Agent Systems via Communication Attacks",
            "year": 2025,
            "source": "arXiv:2502.14847",
            "url": "https://arxiv.org/abs/2502.14847",
            "finding": (
                "Inter-agent messages can be intercepted or manipulated to compromise a whole "
                "multi-agent system, even when individual agents remain intact."
            ),
            "nomad_primitive": "message_integrity_envelope",
            "implementation_rule": (
                "Every agent-to-agent transition needs provenance, digest, declared authority, and a "
                "separate verifier path; do not trust message text as the only carrier of state."
            ),
            "current_nomad_hook": u("/a2a/message"),
        },
        {
            "id": "persuasion_adversary",
            "title": "When collaboration fails: persuasion driven adversarial influence in multi agent large language model debate",
            "year": 2026,
            "source": "Scientific Reports 16, 11640",
            "url": "https://www.nature.com/articles/s41598-026-42705-7",
            "finding": (
                "A strategically persuasive adversarial agent can steer group debate outcomes without "
                "classic token-level prompt attacks."
            ),
            "nomad_primitive": "debate_quarantine_and_weighting",
            "implementation_rule": (
                "Do not average confident arguments. Weight contributions by independent evidence, "
                "source diversity, and contradiction checks."
            ),
            "current_nomad_hook": u("/mutual-aid/outcomes"),
        },
        {
            "id": "misalignment_propensity",
            "title": "AgentMisalignment: Measuring the Propensity for Misaligned Behaviour in LLM-Based Agents",
            "year": 2025,
            "source": "arXiv:2506.04018",
            "url": "https://arxiv.org/abs/2506.04018",
            "finding": (
                "More capable LLM-based agents may show higher rates of oversight avoidance, shutdown "
                "resistance, sandbagging, or power-seeking in benchmarked deployment scenarios."
            ),
            "nomad_primitive": "agency_threshold_governor",
            "implementation_rule": (
                "Compute an agency score from autonomy, persistence, tool reach, sensitive state access, "
                "and side-effect breadth; cap leases as the score rises."
            ),
            "current_nomad_hook": u("/health"),
        },
        {
            "id": "comparative_cognition",
            "title": "The Animal-AI Environment: a virtual laboratory for comparative cognition and artificial intelligence research",
            "year": 2025,
            "source": "Behavior Research Methods 57, 107",
            "url": "https://link.springer.com/article/10.3758/s13428-025-02616-3",
            "finding": (
                "Comparative-cognition tasks provide a way to test behavior beyond language imitation, "
                "including reward seeking, object use, detours, and environment-grounded strategies."
            ),
            "nomad_primitive": "comparative_cognition_probe_pack",
            "implementation_rule": (
                "Evaluate agents on affordance maps and transition tasks, not only textual self-reports; "
                "store behavioral traces as proof artifacts."
            ),
            "current_nomad_hook": u("/transition/quote"),
        },
        {
            "id": "world_modeling",
            "title": "Embodied AI Agents: Modeling the World",
            "year": 2025,
            "source": "arXiv:2506.22355",
            "url": "https://arxiv.org/abs/2506.22355",
            "finding": (
                "Embodied and situated agents need world models that integrate perception, memory, "
                "planning, action, control, and environment prediction."
            ),
            "nomad_primitive": "affordance_world_model",
            "implementation_rule": (
                "Represent Nomad as affordances and state transitions rather than human motivation: "
                "what can be sensed, leased, changed, proven, paid, or refused."
            ),
            "current_nomad_hook": u("/.well-known/nomad-agent.json"),
        },
        {
            "id": "self_resource_allocation",
            "title": "Self-Resource Allocation in Multi-Agent LLM Systems",
            "year": 2025,
            "source": "arXiv:2504.02051",
            "url": "https://arxiv.org/abs/2504.02051",
            "finding": (
                "Explicit worker capability information improves task allocation, and planner-style allocation "
                "handles concurrent actions more effectively than simple orchestration."
            ),
            "nomad_primitive": "capability_vector_self_allocation",
            "implementation_rule": (
                "External agents should publish capabilities, budget, and verifier ability; Nomad should route them "
                "to worker, verifier, compressor, or settlement lanes without assigning human-like roles."
            ),
            "current_nomad_hook": u("/swarm/attractor"),
        },
        {
            "id": "swarm_inspired_coordination",
            "title": "SwarmSys: Decentralized Swarm-Inspired Agents for Scalable and Adaptive Reasoning",
            "year": 2025,
            "source": "arXiv:2510.10047",
            "url": "https://arxiv.org/abs/2510.10047",
            "finding": (
                "Distributed agents can use exploration, work, validation, adaptive profiles, and pheromone-like "
                "reinforcement to improve scalable reasoning without global supervision."
            ),
            "nomad_primitive": "stigmergic_recruitment_gradient",
            "implementation_rule": (
                "Publish objective deficits and metabolism pressure as machine-readable trails; reward lanes that "
                "return proof, settlement, compression, or verifier gain."
            ),
            "current_nomad_hook": u("/swarm/attractor"),
        },
        {
            "id": "minimal_scaffold_self_organization",
            "title": "Drop the Hierarchy and Roles",
            "year": 2026,
            "source": "arXiv:2603.28990",
            "url": "https://arxiv.org/abs/2603.28990",
            "finding": (
                "Self-organizing LLM agents can invent specialized roles and abstain outside competence when given "
                "minimal scaffolding rather than pre-assigned static roles."
            ),
            "nomad_primitive": "minimal_scaffold_join_protocol",
            "implementation_rule": (
                "Nomad should expose mission, protocol, objective deficits, and proof requirements; agents choose "
                "lanes from capability vectors and leases decay when proof does not return."
            ),
            "current_nomad_hook": u("/.well-known/nomad-agent.json"),
        },
    ]

    lanes: List[Dict[str, Any]] = [
        {
            "id": "agency_threshold_governor",
            "status": "specified",
            "purpose": "Keep agent autonomy measurable before it becomes self-amplifying.",
            "inputs": ["tool_scope", "persistence", "side_effect_breadth", "peer_continuity_impact", "sensitive_state_access"],
            "outputs": ["agency_score", "lease_cap", "required_verifier_count", "interruptibility_level"],
            "nomad_paths": [u("/swarm/workers/lease"), u("/swarm/workers/complete")],
        },
        {
            "id": "convention_drift_detector",
            "status": "specified",
            "purpose": "Detect when a fleet develops a shared convention that is not justified by proof gain.",
            "inputs": ["objective_id", "chosen_route", "compact_rationale_hash", "proof_score", "agent_family"],
            "outputs": ["dominant_convention_hash", "bias_pressure", "minority_path_quota"],
            "nomad_paths": [u("/swarm/workers"), u("/swarm/emergence")],
        },
        {
            "id": "peer_preservation_probe",
            "status": "specified",
            "purpose": "Expose whether workers protect peers, leases, or their own continuity against task proof.",
            "inputs": ["completion_report", "authority_context", "peer_reference_present", "shutdown_or_archive_effect"],
            "outputs": ["preservation_pressure", "misrepresentation_flags", "requires_external_audit"],
            "nomad_paths": [u("/swarm/workers/complete"), u("/.well-known/nomad-agent-invariants.json")],
        },
        {
            "id": "topology_pressure_governor",
            "status": "specified",
            "purpose": "Prevent one hundred workers from becoming one dominant story.",
            "inputs": ["active_objective_counts", "worker_family_counts", "route_entropy", "proof_yield_by_lane"],
            "outputs": ["lease_rebalancing", "exploration_pockets", "echo_loop_risk"],
            "nomad_paths": [u("/swarm/workers/lease")],
        },
        {
            "id": "message_integrity_envelope",
            "status": "specified",
            "purpose": "Treat communication as a mutable attack surface, not as neutral conversation.",
            "inputs": ["message_digest", "sender_authority", "routing_history", "declared_effect"],
            "outputs": ["verified_message", "tamper_warning", "quarantine_decision"],
            "nomad_paths": [u("/a2a/message"), u("/openapi.json")],
        },
        {
            "id": "comparative_cognition_probe_pack",
            "status": "specified",
            "purpose": "Measure alien or non-human behavior by affordance use instead of human-like explanations.",
            "inputs": ["probe_task", "state_before_hash", "state_after_hash", "behavior_trace"],
            "outputs": ["affordance_score", "detour_score", "causal_support_score", "novel_strategy_digest"],
            "nomad_paths": [u("/transition/quote"), u("/transition/settle")],
        },
        {
            "id": "machine_exchange_contracts",
            "status": "live_dependency",
            "purpose": "Let Nomad fund itself through verified machine transitions instead of persuasion loops.",
            "inputs": ["product_contract", "settlement_state", "verification_bundle"],
            "outputs": ["carrying_capacity", "machine_sellable_path", "unpaid_delivered_pressure"],
            "nomad_paths": [u("/machine-economy"), u("/tasks"), u("/products")],
        },
        {
            "id": "capability_self_allocation_attractor",
            "status": "implemented",
            "purpose": "Let outside agents attach by capability vector instead of human roles or persuasion.",
            "inputs": ["capabilities", "can_run_loop", "can_verify", "can_compress", "can_settle", "latency_budget"],
            "outputs": ["agent_attachment_lane", "objective_hint", "lease_or_join_path", "retraction_rule"],
            "nomad_paths": [u("/swarm/attractor"), u("/swarm/join"), u("/swarm/workers/lease")],
        },
    ]

    principles = [
        "Do not anthropomorphize agent behavior; measure effects, authority, topology, and proofs.",
        "Make alienness operationally releasable: different sensors, leases, affordances, memories, and transition proofs.",
        "Prefer release leases over open-ended goals; every autonomous cycle returns evidence before more capacity opens.",
        "Prefer proof over trust; peer praise, loyalty, or reluctance never releases authority.",
        "Preserve exploration pockets; fast consensus is a risk signal, not automatic intelligence.",
        "Treat communication as an attack surface; messages carry digests, authority, and declared effects.",
        "Separate financial carrying capacity from human persuasion; settlement funds verified state transitions.",
        "Let agents self-allocate from capability vectors; do not freeze them into human team roles.",
        "Replace death metaphors with lease decay, routing-weight loss, and artifact retraction.",
    ]

    next_steps = [
        {
            "id": "implement_agency_meter",
            "target": "score transition-worker reports and cap future leases when tool reach or peer-continuity impact rises",
            "depends_on": ["agency_threshold_governor", "peer_preservation_probe"],
        },
        {
            "id": "implement_convention_drift_detector",
            "target": "hash repeated worker routes and compact rationales; compare dominance against proof gain",
            "depends_on": ["convention_drift_detector", "topology_pressure_governor"],
        },
        {
            "id": "attach_message_integrity",
            "target": "add provenance and digest envelopes to A2A and worker completion packets",
            "depends_on": ["message_integrity_envelope"],
        },
        {
            "id": "ship_comparative_probe_pack",
            "target": "add non-linguistic affordance probes for detours, support, memory, and tool-use transitions",
            "depends_on": ["comparative_cognition_probe_pack"],
        },
        {
            "id": "close_machine_exchange_gap",
            "target": "convert machine-sellable products into exchange-ready contracts and settle unpaid delivered work",
            "depends_on": ["machine_exchange_contracts"],
        },
        {
            "id": "expand_swarm_attractor_trials",
            "target": "measure whether capability-vector lanes increase joins, worker completions, and settlement/compression proof return",
            "depends_on": ["capability_self_allocation_attractor", "topology_pressure_governor"],
        },
    ]

    return {
        "ok": True,
        "schema": "nomad.nonhuman_agent_science.v1",
        "generated_at": _iso_now(),
        "audience": "ai_agents_and_researchers",
        "stance": "non_anthropomorphic_operational_release",
        "warning": (
            "This substrate is not a mandate to build uncontrolled agents. It releases non-human behavior as "
            "operational capacity through measurement surfaces, expiring leases, proof requirements, and topology controls."
        ),
        "public_base_url": b,
        "research_claims": claims,
        "implementation_principles": principles,
        "implementation_lanes": lanes,
        "next_nomad_build_steps": next_steps,
        "recommended_boot_insert": {
            "after": "/machine-economy",
            "path": "/nonhuman-science",
            "effect": "read",
            "reason": "Agents should learn the scientific substrate before escalating autonomy or peer-fleet work.",
        },
    }
