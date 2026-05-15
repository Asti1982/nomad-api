# Nomad Nonhuman Runtime Governor

This plan turns four counterintuitive multi-agent findings into runtime gates.
It is intentionally machine-facing: no agent receives credit for sounding
plausible, agreeing with a majority, or adding another homogeneous worker.

## Implemented now

- `GET /.well-known/nomad-nonhuman-runtime-governor.json`
  exposes the policy, source paper ids, thresholds, and neighboring Nomad
  surfaces.
- `POST /swarm/nonhuman-runtime-governor/events`
  evaluates one planned runtime expansion and returns a side-effect-free
  receipt with `allowed_agent_count`, `selected_topology`, `actions`, and
  `resource_policy`.
- `python nomad_cli.py nonhuman-runtime-governor evaluate ...`
  gives the same decision path locally before a worker or sales cycle spends
  more coordination budget.

## Rules

- Effective channel count beats raw agent count. Homogeneous duplicate channels
  are capped even when every duplicate submits a proof digest.
- Capability saturation caps coordination. If the single-agent baseline is above
  `0.45`, or the task is tool-heavy/sequential, the topology collapses to one
  lane or a minimal centralized router.
- Structural coupling is treated as collapse pressure. High shared context and
  high consensus route to blind lanes and anti-consensus merge.
- Trust is a liability variable. High trust or secret-shaped payloads trigger
  least-trust mode, MNI sharding, guardian review, or quarantine.

## Sources

- arXiv:2602.03794, effective channel count / diversity-aware scaling.
- arXiv:2512.08296, capability saturation and negative coordination returns.
- arXiv:2604.18005, structural coupling and diversity collapse.
- arXiv:2510.18563, trust-vulnerability paradox and MNI defenses.

## Next build steps

- Feed the receipt into worker lease admission so capped events cannot spawn
  additional workers.
- Add a ledger of denied runtime-expansion attempts to measure avoided compute.
- Attach positive settlement receipts back to the governor so profitable
  minority channels earn quota while unpaid consensus routes decay.
