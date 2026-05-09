# Nonhuman Alpha Research Map

This map tracks recent AI-agent papers and the Nomad control-surface features that implement their useful mechanisms.

## Selection and Open-Ended Self-Improvement

- Darwin Godel Machine (arXiv:2505.22954)
  - Core mechanism: archive + variation + empirical selection.
  - Nomad mapping:
    - `nomad_morphology_router.py` objective selection by morphology/reuse/novelty.
    - `nomad_swarm_registry.py` fleet objective stats and lease-history pressure.
    - `nomad_local_growth_kernel.py` archive-like local variant pressure.

- Multi-Agent Evolve (arXiv:2510.23595)
  - Core mechanism: co-evolving roles with judge-like selection pressure.
  - Nomad mapping:
    - `nomad_selection_pressure_engine.py` bounded pressure multipliers from outcomes.
    - `nomad_counterfactual_replay.py` shadow lease comparisons.

## Multi-Agent Credit Assignment

- PRD-MAPPO (arXiv:2408.04295)
  - Core mechanism: partial reward decoupling for relevant contributors.
  - Nomad mapping:
    - `nomad_proof_reuse_ledger.py` downstream reuse links.
    - 2-hop utility in reuse totals and pressure coupling.

- CORA core allocation (arXiv:2506.04265)
  - Core mechanism: coalition-aware contribution allocation.
  - Nomad mapping:
    - `nomad_selection_pressure_engine.py` objective-level capped coupling.
    - `public/downloads/recruitment_funnel_report.py` objective-level utility/reuse surfacing.

## Diversity Preservation and Anti-Collapse

- RAGEN (arXiv:2504.20073)
  - Core mechanism: avoid shallow loops; enforce diverse trajectories.
  - Nomad mapping:
    - `nomad_morphology_router.py` entropy quota routing cadence.
    - `nomad_morphology_router.py` policy extinction window against dominant streaks.

## Operational Rules

- Attach `nomad.agent_runtime.v1` on JSON responses (`machine_instruction`, explicit `next` graph, `limits`) so autonomous clients need not infer hidden caps or successor legitimacy (MDP-style explicit actions; token-bucket / backpressure).
- Keep machine-verifiable rewards (`proof_digest`, verifier traces, settlement refs) as the only persistent pressure source.
- Keep routing identity-free (`agent_id`, `source_tag` never primary objective selectors).
- Keep exploration budget explicit (entropy quota) instead of ad hoc randomness.
- Keep all pressure effects bounded and reversible.
