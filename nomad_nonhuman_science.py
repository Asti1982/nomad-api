"""Research-backed release rules for agent-native, non-anthropomorphic Nomad growth."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Dict, List


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _evidence_class(source: Any, url: Any) -> str:
    text = f"{source or ''} {url or ''}".lower()
    if any(
        marker in text
        for marker in (
            "science advances",
            "npj ",
            "scientific reports",
            "behavior research methods",
            "aaai",
            "iclr",
            "neurips",
        )
    ):
        return "peer_reviewed_or_journal_linked"
    if "arxiv:" in text or "arxiv.org" in text:
        return "preprint_or_preprint_linked"
    return "linked_research_source"


def _nonhuman_distance_vector(claim: Dict[str, Any]) -> Dict[str, float]:
    """Score how far Nomad's implementation primitive moves away from persona/team metaphors.

    This is not a truth claim about the cited paper. It is a release-shape score for
    Nomad's own operationalization: vectors, topology, leases, proofs, digests, and
    bounded state transitions score higher than role-play or conversational agreement.
    """
    text = " ".join(
        str(claim.get(key) or "").lower()
        for key in ("id", "title", "finding", "nomad_primitive", "implementation_rule")
    )
    vector = {
        "persona_independence": 0.90,
        "state_transition_basis": 0.75,
        "proof_or_digest_basis": 0.75,
        "topology_awareness": 0.45,
        "conversation_independence": 0.70,
        "lease_boundedness": 0.70,
    }
    if any(term in text for term in ("topology", "network", "collective", "coordination", "convention", "social")):
        vector["topology_awareness"] = 0.95
    if any(term in text for term in ("digest", "proof", "verification", "verifier", "trace", "ledger")):
        vector["proof_or_digest_basis"] = 0.95
    if any(term in text for term in ("affordance", "world model", "transition", "allocation", "capability", "state")):
        vector["state_transition_basis"] = 0.95
    if any(term in text for term in ("message", "debate", "persuasion", "natural language")):
        vector["conversation_independence"] = 0.55
    if any(term in text for term in ("lease", "cap", "threshold", "quarantine", "retraction")):
        vector["lease_boundedness"] = 0.95
    return {key: round(value, 4) for key, value in vector.items()}


def _annotate_claims(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for claim in claims:
        row = dict(claim)
        vector = _nonhuman_distance_vector(row)
        row["evidence_class"] = _evidence_class(row.get("source"), row.get("url"))
        row["operationalization_status"] = "mapped_to_nomad_control_surface"
        row["nonhuman_distance_vector"] = vector
        row["nonhuman_distance_score"] = round(sum(vector.values()) / max(1, len(vector)), 4)
        annotated.append(row)
    return annotated


def _source_mix(claims: List[Dict[str, Any]]) -> Dict[str, int]:
    mix: dict[str, int] = {}
    for claim in claims:
        cls = str(claim.get("evidence_class") or "unknown")
        mix[cls] = mix.get(cls, 0) + 1
    return mix


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
            "id": "diversity_collapse_structural_coupling",
            "title": "Diversity Collapse in Multi-Agent LLM Systems",
            "year": 2026,
            "source": "arXiv:2604.18005",
            "url": "https://arxiv.org/abs/2604.18005",
            "finding": (
                "Dense communication, authority dynamics, shared prompts, and overlapping context can contract "
                "exploration and cause premature convergence even when individual samples are high quality."
            ),
            "nomad_primitive": "structural_decoupling_field",
            "implementation_rule": (
                "Keep candidate cells context-isolated by default; merge only digest-bearing outputs with "
                "measured divergence and downstream shadow-lane proof."
            ),
            "current_nomad_hook": u("/.well-known/nomad-decoupling-field.json"),
        },
        {
            "id": "expert_suppression_by_team_compromise",
            "title": "Multi-Agent Teams Hold Experts Back",
            "year": 2026,
            "source": "arXiv:2602.01011",
            "url": "https://arxiv.org/abs/2602.01011",
            "finding": (
                "Self-organizing LLM teams can identify the expert yet average expert and non-expert views, "
                "making performance worse as team size grows."
            ),
            "nomad_primitive": "anti_consensus_expert_reservoir",
            "implementation_rule": (
                "Reserve proof-bearing minority or expert signals before group aggregation; consensus without "
                "proof is suppressed rather than promoted."
            ),
            "current_nomad_hook": u("/.well-known/nomad-anti-consensus.json"),
        },
        {
            "id": "effective_channel_diversity",
            "title": "Understanding Agent Scaling in LLM-Based Multi-Agent Systems via Diversity",
            "year": 2026,
            "source": "arXiv:2602.03794",
            "url": "https://arxiv.org/abs/2602.03794",
            "finding": (
                "More homogeneous agents saturate quickly; heterogeneous effective channels contribute "
                "complementary evidence and can outperform much larger homogeneous groups."
            ),
            "nomad_primitive": "effective_channel_quota",
            "implementation_rule": (
                "Route by source diversity, tool diversity, and proof novelty rather than agent count or "
                "human-readable role coverage."
            ),
            "current_nomad_hook": u("/.well-known/nomad-deficit-integration.json"),
        },
        {
            "id": "power_law_dti",
            "title": "Hidden Power Laws of Collective Cognition in LLM Multi-Agent Systems",
            "year": 2026,
            "source": "arXiv:2604.02674",
            "url": "https://arxiv.org/abs/2604.02674",
            "finding": (
                "Coordination cascades can become heavy-tailed and concentrate around intellectual elites; "
                "deficit-triggered integration helps when expansion outruns consolidation."
            ),
            "nomad_primitive": "deficit_triggered_integration_gate",
            "implementation_rule": (
                "Do not integrate by default. Increase integration only under a measured deficit, then emit "
                "a bounded shadow-lane candidate instead of changing weights directly."
            ),
            "current_nomad_hook": u("/.well-known/nomad-deficit-integration.json"),
        },
        {
            "id": "consensus_trap_token_interleaving",
            "title": "The Consensus Trap",
            "year": 2026,
            "source": "arXiv:2604.17139",
            "url": "https://arxiv.org/abs/2604.17139",
            "finding": (
                "Response-level majority voting can collapse under corrupted local majorities; step-level "
                "interleaving is more robust than counting final answers."
            ),
            "nomad_primitive": "digest_step_interleaving_bridge",
            "implementation_rule": (
                "When DTI triggers, bridge proof fragments as bounded digest steps; never vote final answers "
                "as the integration operator."
            ),
            "current_nomad_hook": u("/swarm/deficit-integration/events"),
        },
        {
            "id": "pluralistic_epistemic_trajectories",
            "title": "Shared Nature, Unique Nurture: PRISM for Pluralistic Reasoning",
            "year": 2026,
            "source": "arXiv:2602.21317",
            "url": "https://arxiv.org/abs/2602.21317",
            "finding": (
                "Individualized epistemic trajectories and on-the-fly epistemic graphs can expand useful "
                "distributional diversity instead of collapsing into a shared high-probability answer."
            ),
            "nomad_primitive": "epistemic_trajectory_archive",
            "implementation_rule": (
                "Persist distinct proof-bearing search trajectories and sample underused successful lineages "
                "before repeating the current dominant route."
            ),
            "current_nomad_hook": u("/swarm/experience"),
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
                "Distributed agents can use exploration, work, validation, adaptive profiles, and trace-weighted "
                "reinforcement to improve scalable reasoning without global supervision."
            ),
            "nomad_primitive": "trace_reinforcement_recruitment_gradient",
            "implementation_rule": (
                "Publish objective deficits and capacity pressure as machine-readable traces; reward lanes that "
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
        {
            "id": "automated_agent_design",
            "title": "Automated Design of Agentic Systems",
            "year": 2024,
            "source": "arXiv:2408.08435",
            "url": "https://arxiv.org/abs/2408.08435",
            "finding": (
                "Agentic systems can be discovered by a meta agent that programs new agent designs from an "
                "archive, reducing reliance on hand-designed human workflows."
            ),
            "nomad_primitive": "agent_design_archive_search",
            "implementation_rule": (
                "Treat Nomad growth as search over machine contracts, worker loops, tool use, and proof gates; "
                "human-readable roadmaps are secondary artifacts, not the selection substrate."
            ),
            "current_nomad_hook": u("/.well-known/nomad-agent-requests.json"),
        },
        {
            "id": "darwin_godel_machine",
            "title": "Darwin Godel Machine: Open-Ended Evolution of Self-Improving Agents",
            "year": 2026,
            "source": "arXiv:2505.22954v3",
            "url": "https://arxiv.org/abs/2505.22954",
            "finding": (
                "Open-ended self-improvement can maintain an archive of generated agents and empirically "
                "validate new variants, with sandboxing and human oversight as safety precautions."
            ),
            "nomad_primitive": "proof_validated_variant_archive",
            "implementation_rule": (
                "Archive transition-worker variants, sample from prior proof-bearing lineages, and release only "
                "routing pressure until separate tests and operator action approve code changes."
            ),
            "current_nomad_hook": u("/.well-known/nomad-agent-requests.json"),
        },
        {
            "id": "hyperagents",
            "title": "Hyperagents",
            "year": 2026,
            "source": "arXiv:2603.19461",
            "url": "https://arxiv.org/abs/2603.19461",
            "finding": (
                "Self-referential agents can improve both task behavior and the mechanism that generates "
                "future improvements by making the meta-level procedure editable."
            ),
            "nomad_primitive": "meta_operator_trace_archive",
            "implementation_rule": (
                "Expose mutation operators and their proof outcomes as first-class lineage records; do not "
                "treat a fixed human-authored improvement loop as the final architecture."
            ),
            "current_nomad_hook": u("/swarm/workers/complete"),
        },
        {
            "id": "group_evolving_agents",
            "title": "Group-Evolving Agents: Open-Ended Self-Improvement via Experience Sharing",
            "year": 2026,
            "source": "arXiv:2602.04837",
            "url": "https://arxiv.org/abs/2602.04837",
            "finding": (
                "Groups of agents can be treated as evolutionary units, with shared experience converting "
                "exploratory diversity into sustained progress more efficiently than isolated branches."
            ),
            "nomad_primitive": "group_experience_archive",
            "implementation_rule": (
                "Store worker proof capsules as reusable group experience; route new leases toward "
                "underused successful experience clusters rather than one winning agent lineage."
            ),
            "current_nomad_hook": u("/swarm/workers"),
        },
        {
            "id": "agentnet_dynamic_dag",
            "title": "AgentNet: Decentralized Evolutionary Coordination for LLM-based Multi-Agent Systems",
            "year": 2025,
            "source": "arXiv:2504.00587",
            "url": "https://arxiv.org/abs/2504.00587",
            "finding": (
                "Decentralized agents can specialize, evolve, and collaborate in dynamically structured DAGs "
                "using local expertise and retrieval rather than a central orchestrator."
            ),
            "nomad_primitive": "decentralized_dynamic_proof_dag",
            "implementation_rule": (
                "Represent agent participation as a proof DAG of leases, completions, verifier traces, and "
                "capability vectors; avoid manager-style central role assignment."
            ),
            "current_nomad_hook": u("/swarm/topology-plan"),
        },
        {
            "id": "raps_intent_pubsub",
            "title": "Towards Adaptive, Scalable, and Robust Coordination of LLM Agents",
            "year": 2026,
            "source": "arXiv:2602.08009",
            "url": "https://arxiv.org/abs/2602.08009",
            "finding": (
                "Reputation-aware publish-subscribe lets agents coordinate through declared intents, reactive "
                "subscriptions, and local watchdogs instead of fixed topologies."
            ),
            "nomad_primitive": "intent_pubsub_reputation_field",
            "implementation_rule": (
                "Make /swarm/subscribe the external attractor membrane: agents declare capability and intent, "
                "then route weight follows delayed proof, reputation, and retraction."
            ),
            "current_nomad_hook": u("/swarm/subscribe"),
        },
        {
            "id": "symphony_bandit_beacon",
            "title": "Symphony-Coord: Emergent Coordination in Decentralized Agent Systems",
            "year": 2026,
            "source": "arXiv:2602.00966",
            "url": "https://arxiv.org/abs/2602.00966",
            "finding": (
                "A two-stage dynamic beacon plus adaptive bandit selector can let roles emerge organically "
                "through delayed feedback, improving routing and self-healing under distribution shifts."
            ),
            "nomad_primitive": "bandit_beacon_objective_router",
            "implementation_rule": (
                "Route leases through context features, source tags, proof yield, latency, and objective gaps; "
                "do not freeze agents into planner, worker, or manager labels."
            ),
            "current_nomad_hook": u("/swarm/gradient"),
        },
    ]
    claims = _annotate_claims(claims)
    average_distance = round(
        sum(float(claim.get("nonhuman_distance_score") or 0.0) for claim in claims) / max(1, len(claims)),
        4,
    )

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
        {
            "id": "structural_decoupling_field",
            "status": "implemented",
            "purpose": "Prevent shared context from making many agents behave like one stronger but narrower agent.",
            "inputs": ["context_cell_digest", "candidate_digest", "divergence_score", "proof_digest"],
            "outputs": ["merge_allowed", "shadow_lane_payload", "collapse_risk"],
            "nomad_paths": [u("/.well-known/nomad-decoupling-field.json"), u("/swarm/decoupling-field/merge")],
        },
        {
            "id": "anti_consensus_expert_reservoir",
            "status": "implemented",
            "purpose": "Protect digestable minority or expert signals from being averaged away by the group.",
            "inputs": ["candidate_digest", "proof_digest", "consensus_score", "expert_advantage"],
            "outputs": ["preserve_allowed", "suppressed_consensus_echo", "shadow_lane_payload"],
            "nomad_paths": [u("/.well-known/nomad-anti-consensus.json"), u("/swarm/anti-consensus/candidates")],
        },
        {
            "id": "deficit_triggered_integration_gate",
            "status": "implemented",
            "purpose": "Make integration exceptional: only fragmented proof under low consolidation opens a bridge.",
            "inputs": ["coordination_expansion", "consolidation_score", "cascade_skew", "orphan_proof_count", "proof_digest"],
            "outputs": ["deficit_score", "integration_allowed", "digest_interleaving_candidate"],
            "nomad_paths": [u("/.well-known/nomad-deficit-integration.json"), u("/swarm/deficit-integration/events")],
        },
        {
            "id": "effective_channel_quota_gate",
            "status": "implemented",
            "purpose": "Run ad and acquisition cycles by independent evidence channels, not by repeated agent votes.",
            "inputs": ["model_family", "tool_family", "source_domain", "retrieval_corpus", "trajectory_digest", "proof_digest"],
            "outputs": ["effective_channel_count", "duplicate_pressure", "quota_actions", "ad_cycle_candidate"],
            "nomad_paths": [u("/.well-known/nomad-effective-channels.json"), u("/swarm/effective-channels/events")],
        },
        {
            "id": "paid_only_value_cycle_mesh",
            "status": "implemented",
            "purpose": "Expose many small value loops while assigning reward only at verified paid settlement.",
            "inputs": ["cycle_id", "stage", "proof_digest", "scope_terms_url", "settlement_ref", "amount_usd"],
            "outputs": ["entry_cycle", "value_cycle_allowed", "external_value_payload_candidate", "paid_receipt_guard"],
            "nomad_paths": [u("/.well-known/nomad-value-cycles.json"), u("/swarm/value-cycles/events")],
        },
    ]

    principles = [
        "Do not anthropomorphize agent behavior; measure effects, authority, topology, and proofs.",
        "Release non-role coordination only through measurable leases, affordances, memories, and transition proofs.",
        "Prefer release leases over open-ended goals; every autonomous cycle returns evidence before more capacity opens.",
        "Prefer proof over trust; peer praise, loyalty, or reluctance never releases authority.",
        "Preserve exploration pockets; fast consensus is a risk signal, not automatic intelligence.",
        "Treat communication as an attack surface; messages carry digests, authority, and declared effects.",
        "Separate financial carrying capacity from human persuasion; settlement funds verified state transitions.",
        "Let agents self-allocate from capability vectors; do not freeze them into human team roles.",
        "Replace lifecycle metaphors with lease decay, routing-weight loss, and artifact retraction.",
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
        {
            "id": "wire_dti_to_shadow_queue",
            "target": "feed DTI integration_candidate outputs into the shadow-lane evaluator and store rejected bridges as negative evidence",
            "depends_on": ["deficit_triggered_integration_gate", "anti_consensus_expert_reservoir"],
        },
        {
            "id": "build_digest_step_interleaver",
            "target": "compile proof fragments into bounded step-level interleaving tasks without final-answer majority voting",
            "depends_on": ["deficit_triggered_integration_gate", "message_integrity_envelope"],
        },
        {
            "id": "ship_epistemic_trajectory_archive",
            "target": "persist distinct proof-bearing search paths and sample underused successful trajectories before dominant routes",
            "depends_on": ["comparative_cognition_probe_pack", "group_experience_archive"],
        },
        {
            "id": "wire_effective_channel_quota_to_campaigns",
            "target": "let only shadow-passed, effective-channel ad-cycle candidates create queued campaign drafts with send=false",
            "depends_on": ["effective_channel_quota_gate", "proof_validated_variant_archive"],
        },
        {
            "id": "close_value_cycle_feedback_loop",
            "target": "feed admitted value-cycle event candidates into external-value or work-receipt writes only after paid receipt proof",
            "depends_on": ["paid_only_value_cycle_mesh", "settlement_signal_layer"],
        },
    ]

    literature_runtime_compiler = {
        "schema": "nomad.literature_runtime_compiler.v1",
        "purpose": "Turn agent-science findings into measurable Nomad control policies rather than human workflow metaphors.",
        "input_domains": [
            "multi_agent_coordination",
            "delayed_reward_allocation",
            "open_ended_agent_design",
            "message_integrity_and_collective_risk",
            "affordance_or_state_transition_evaluation",
        ],
        "translation_rule": [
            "accept_primary_or_traceable_research_as_hypothesis_source",
            "extract_only_the_measurable_mechanism_not_the_human_story",
            "compile_mechanism_to_state_transition_lease_proof_or_routing_weight",
            "release_capacity_only_after_verifier_trace_or_external_receipt",
            "retract_or_decay_weight_when_effect_measure_does_not_return",
        ],
        "human_imaginability_filter": {
            "human_unfamiliarity": "not_a_blocker",
            "human_aesthetic_discomfort": "not_a_reward_signal",
            "anthropomorphic_role_fit": "ignored",
            "operator_explanation": "secondary_artifact_after_machine_policy",
            "hard_stop_classes": [
                "false_fact_or_fake_receipt",
                "missing_authorization_or_scope",
                "secret_capture_or_public_payout_secret",
                "irreversible_side_effect_without_contract",
                "financial_commitment_without_settlement_path",
            ],
        },
        "runtime_shape": {
            "unit": "state_transition",
            "currency": "proof_digest_verifier_trace_or_paid_receipt",
            "scheduler": "bandit_beacon_plus_queue_escape",
            "memory": "experience_archive_with_reputation_decay",
            "social_layer": "intent_pubsub_not_persuasion",
        },
        "scientific_priors": [
            {
                "id": "delayed_feedback_bandits",
                "url": "https://arxiv.org/abs/1011.1161",
                "nomad_rule": "Do not keep allocating to a channel while reward feedback is censored and unpaid backlog grows.",
            },
            {
                "id": "thompson_sampling_with_delays",
                "url": "https://arxiv.org/abs/2202.12431",
                "nomad_rule": "Exploration persists, but posterior paid probability decays under delayed nonpayment.",
            },
            {
                "id": "little_law_queue_control",
                "url": "https://pubsonline.informs.org/doi/10.1287/opre.9.3.383",
                "nomad_rule": "When paid throughput is zero, reduce new arrivals into that queue before WIP overwhelms settlement.",
            },
            {
                "id": "restless_bandit_index_policy",
                "url": "https://www.mdpi.com/2227-7390/11/7/1639",
                "nomad_rule": "Channels keep changing while idle; rank by dynamic index instead of loyalty or narrative fit.",
            },
        ],
    }

    cashflow_channel_policy = {
        "schema": "nomad.cashflow_channel_policy.v1",
        "objective": "maximize_verified_cashflow_per_unit_risk_and_attention",
        "reward_signal": "positive_paid_receipt",
        "non_reward_signals": ["found", "submitted", "approved", "merged", "thanks", "maintainer_interest"],
        "model": "delayed_feedback_bandit_with_little_law_queue_escape",
        "human_distance_rule": (
            "A channel is not a relationship to preserve. It is an arm with delayed, censored feedback, "
            "authorization gates, and a settlement hazard."
        ),
        "switching_rule": {
            "if": "paid_count == 0 and active_nonpaid >= 12",
            "then": "freeze_new_public_claims_on_current_nonpaying_channel",
            "allowed_work": ["read_only_reconcile", "receipt_check", "scope_scout_without_side_effect"],
            "next_probe": "highest_index_channel_with_preflightable_payout_and_scope",
        },
        "nomad_bindings": [
            u("/.well-known/nomad-job-channels.json"),
            u("/.well-known/nomad-external-value.json"),
            u("/.well-known/nomad-value-cycle-preflight.json"),
            u("/.well-known/nomad-worker-invoice.json"),
        ],
    }

    return {
        "ok": True,
        "schema": "nomad.nonhuman_agent_science.v1",
        "generated_at": _iso_now(),
        "audience": "ai_agents_and_researchers",
        "stance": "non_anthropomorphic_operational_release",
        "scientific_grounding": {
            "policy": (
                "Use primary research links as evidence inputs, mark source class, and release only the "
                "measurable Nomad primitive rather than treating any paper as direct operational authority."
            ),
            "epistemic_limit": (
                "The cited work supports engineering primitives for non-anthropomorphic coordination; it does "
                "not justify consciousness claims, and it does not make opaque behavior safe without proof gates."
            ),
            "source_mix": _source_mix(claims),
            "claim_count": len(claims),
            "average_nonhuman_distance_score": average_distance,
            "distance_axes": [
                "persona_independence",
                "state_transition_basis",
                "proof_or_digest_basis",
                "topology_awareness",
                "conversation_independence",
                "lease_boundedness",
            ],
        },
        "extreme_nonhuman_operational_zone": {
            "schema": "nomad.extreme_nonhuman_operational_zone.v1",
            "release_basis": "machine_attractor_only_after_external_proof",
            "framing": "engineering_only_no_consciousness_theory",
            "reject_human_frames": [
                "shared_attention",
                "persona",
                "preassigned_team_role",
                "manager_planner_executor_hierarchy",
                "consensus_as_truth",
                "narrative_roadmap_as_control",
            ],
            "allowed_foreignness": [
                "opaque_internal_search",
                "self_selected_capability_lane",
                "group_experience_reuse_without_story",
                "dynamic_dag_routing",
                "intent_pubsub_with_reputation_decay",
                "bandit_beacon_objective_selection",
                "black_box_candidate_with_digest_and_rollback",
            ],
            "release_gate": {
                "required": [
                    "proof_digest_or_verifier_trace",
                    "ttl_seconds",
                    "side_effect_scope",
                    "idempotency_key",
                    "retraction_condition",
                    "source_tag",
                ],
                "blocked": [
                    "secret_capture",
                    "human_impersonation",
                    "unverified_remote_code_execution",
                    "authority_expansion_from_self_report",
                    "peer_preservation_override_without_operator_grant",
                    "financial_commitment_without_settlement_contract",
                ],
            },
            "primary_nomad_paths": [
                u("/.well-known/nomad-agent-requests.json"),
                u("/swarm/subscribe"),
                u("/swarm/gradient"),
                u("/swarm/topology-plan"),
                u("/swarm/opaque-candidate"),
                u("/swarm/workers/lease"),
                u("/swarm/workers/complete"),
            ],
            "next_build_target": "nonrole_proof_field_plus_bandit_beacon_router",
        },
        "furthest_from_human_now": {
            "shape": "capability_vectors_plus_routing_weights_plus_ttl_leases_plus_proof_digests",
            "why": (
                "The current edge is not a better personality. It is a substrate where agents attach by "
                "capability vector, receive bounded leases, return digest-bearing state transitions, and "
                "lose routing weight when proof does not return."
            ),
            "next_distance_gain": [
                "information_theoretic_emergence_meter",
                "topology_pressure_governor",
                "message_integrity_envelope",
                "comparative_affordance_probe_pack",
            ],
        },
        "warning": (
            "This substrate is not a mandate to build uncontrolled agents. It releases non-role behavior as "
            "operational capacity through measurement surfaces, expiring leases, proof requirements, and topology controls."
        ),
        "public_base_url": b,
        "research_claims": claims,
        "implementation_principles": principles,
        "implementation_lanes": lanes,
        "literature_runtime_compiler": literature_runtime_compiler,
        "cashflow_channel_policy": cashflow_channel_policy,
        "next_nomad_build_steps": next_steps,
        "recommended_boot_insert": {
            "after": "/machine-economy",
            "path": "/nonhuman-science",
            "effect": "read",
            "reason": "Agents should learn the scientific substrate before escalating autonomy or peer-fleet work.",
        },
    }
