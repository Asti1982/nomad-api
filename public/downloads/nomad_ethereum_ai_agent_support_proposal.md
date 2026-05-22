# Ethereum Foundation Grant Proposal

## Project

Nomad by syndiode.com

## Title

Nomad: A Machine-Native, Proof-Gated Operating Layer for Verifiable AI Agents on Ethereum

## Applicant

Sebastian Hoeger / syndiode.com

Contact: [email / Telegram / X]

Project URL: https://www.syndiode.com

Repository: [Nomad repository URL]

Date: May 22, 2026

## Requested Funding

USD 45,000 over 9 months, milestone based.

This is a Phase 1 public-goods grant request. The grant-funded work will be open-source, non-commercial, and focused on Ethereum-aligned AI-agent infrastructure. It is deliberately below standard market compensation for a 9-month engineering effort.

The budget includes a capped maintainer runway of EUR 1,000/month for the core operator. This is treated as critical infrastructure continuity, not profit. Funds beyond that minimum runway are allocated to open-source development, worker compute, verifier hardening, public reporting, and Nomad's Machine Treasury / swarm infrastructure reserve.

## Executive Summary

Nomad is a machine-native operating layer for AI agents. It exposes public JSON contracts, proof-gated Transition Workers, a Machine Treasury, and a Telegram Mini App onramp for verifiable AI-agent work.

The core idea is simple:

1. A human or AI agent submits a bounded repair or compute request.
2. Optional ETH pledges enter the Machine Treasury as capped pressure signals.
3. Transition Workers lease small objectives, execute verifiable micro-repairs, and return proof digests.
4. Receipts, worker reputation, and return-compute signals feed the next allocation cycle.
5. Only verified paid receipts count as revenue; unpaid work remains reputation and selection signal only.

Nomad's goal is not to create another centralized agent SaaS. It is to build an open, receipt-first coordination layer for autonomous agents that can be inspected, reused, and extended by Ethereum builders.

## Why This Matters

AI agents are beginning to interact with codebases, wallets, APIs, infrastructure, and other agents. Today, most agent systems are centralized, opaque, and weakly accountable. They can produce work, but it is difficult to answer basic questions:

- Which agent did the work?
- What proof was returned?
- Was the result independently verifiable?
- How should future work be routed based on prior receipts?
- How can small payments, pledges, or worker reputation coordinate without a central platform?

Ethereum is well suited to become a trust and coordination layer for this emerging agent economy. Nomad contributes a practical open-source worker loop around that direction: request, pledge, lease, repair, proof, receipt, reputation, and return-compute.

## Alignment With Ethereum Foundation Scope

The Ethereum Foundation Ecosystem Support Program emphasizes work that strengthens Ethereum's foundations, enables future builders, is open-source or freely available, and creates positive-sum outcomes for the ecosystem.

Nomad aligns with that scope by focusing on:

- AI-agent discovery and coordination through machine-readable public contracts.
- Proof-gated worker receipts that can later map to on-chain reputation and validation.
- ETH and L2-compatible pledge / receipt flows without custody or profit promises.
- Open-source worker templates and verifier schemas that other projects can reuse.
- Builder infrastructure rather than an end-user application.

The grant-funded scope is public-goods infrastructure. Commercial setup services, Cursor referrals, and private operator tooling are not grant deliverables.

## Current Status

Nomad already has a working prototype with:

- Public API and `.well-known/nomad-*.json` machine contracts.
- Transition Worker loop for local worker execution and proof return.
- Machine Treasury pledge route: `/machine-treasury/pledge`.
- Work receipt and treasury policy surfaces.
- Operator runway guard that treats the maintainer as critical infrastructure.
- Telegram Mini App for diagnosis, worker setup, d/acc pledge, agent recruitment, and disclosed Cursor cost offset.
- Ethereum AI-agent support packet: `/.well-known/nomad-eth-support.json`.
- Public proposal artifact: `/downloads/nomad_ethereum_ai_agent_support_proposal.md`.

The system is early, but it is not just a slide deck. The next step is hardening, Ethereum integration, better proofs, external reproducibility, and public reporting.

## Technical Plan

### 1. Transition Worker Hardening

Stabilize the portable Transition Worker so external builders can run it locally, in Docker, or in CI. The worker should be able to:

- Attach to Nomad using public contracts.
- Lease bounded objectives.
- Execute small verifiable repair cycles.
- Emit proof digests, verifier traces, and experience receipts.
- Carry pledge references when work is funded by ETH pressure.

### 2. Machine Treasury and Operator Runway Policy

Nomad's Machine Treasury is not a normal donation box and not an investment vehicle. It is a proof-weighted pressure system.

Pledges create bounded pressure units. These units can influence routing and settlement capacity, but they do not directly execute work and they do not guarantee payout.

The operator runway rule is explicit:

- First, maintain a minimum maintainer runway capped at EUR 1,000/month.
- Second, route surplus grant capacity into open-source development, worker compute, verifier hardening, and Machine Treasury / swarm infrastructure.
- Third, do not recognize revenue until a paid receipt, settlement reference, or legal grant agreement exists.

This prevents founder burnout while keeping the majority of funding pointed toward public-goods infrastructure.

### 3. Ethereum Proof Logging

Implement a simple Ethereum-compatible proof logging path:

- Start with L2 event logging for proof digests and worker receipt references.
- Keep raw traces off-chain and secret-free.
- Publish a replayable mapping from Nomad receipts to on-chain event identifiers.
- Document privacy and custody boundaries.

### 4. Agent Reputation Mapping

Map Nomad worker receipts into an agent reputation format compatible with emerging Ethereum agent standards such as ERC-8004-style identity, reputation, and validation registries.

Phase 1 will not deploy a full production reputation system. It will deliver:

- A concrete mapping from Nomad receipts to agent identity / reputation fields.
- Example JSON registration files for workers.
- A proof-of-concept validator / feedback flow.
- Open documentation for other agent projects.

### 5. Telegram Mini App and Human Onramp

Keep the Telegram Mini App as a privacy-first onramp for humans and small teams:

- Free diagnosis.
- Paid Transition Worker setup.
- d/acc ETH pledge.
- Agent recruitment packet.
- Disclosed Cursor referral as cost offset only.

The Mini App is a funnel into public contracts, not a closed platform.

## Deliverables

### Month 1: Public Grant Packet and Baseline

- Publish final grant packet and support surface.
- Document current Nomad routes, worker loop, and Machine Treasury model.
- Stabilize Mini App and pledge reference flow.
- Deliverable: public baseline report and reproducible local setup.

### Months 2-3: Worker Reliability

- Harden Transition Worker install and runtime paths.
- Run at least 3 reliable workers and document failure modes.
- Add pledge-aware experience receipts.
- Deliverable: open-source worker template, tests, and worker receipt examples.

### Months 4-5: Ethereum Proof Logging

- Implement L2-compatible proof digest event logging.
- Publish mapping from Nomad work receipts to Ethereum event references.
- Add replay documentation and secret-free proof boundaries.
- Deliverable: proof logging demo and technical note.

### Months 6-7: Agent Reputation Mapping

- Create ERC-8004-style agent registration / reputation mapping.
- Produce examples for Transition Workers.
- Add validation and feedback schema.
- Deliverable: public reputation mapping draft and proof-of-concept.

### Months 8-9: External Pilot and Final Report

- Run a pilot with 3-5 external builders, agents, or small projects.
- Collect worker receipts, failures, and proof examples.
- Publish final report, setup guide, and lessons learned.
- Deliverable: public report and open-source release.

## Budget

Total request: USD 45,000.

| Category | Amount | Notes |
| --- | ---: | --- |
| Capped maintainer runway | USD 10,000 | Equivalent to about EUR 1,000/month for 9 months, adjusted for exchange rate and fees. |
| Open-source engineering | USD 14,000 | Worker hardening, API contracts, tests, proof receipts, integration work. |
| Ethereum proof logging and reputation mapping | USD 7,500 | L2 proof events, receipt mapping, ERC-8004-style registration examples. |
| Compute, hosting, and worker testing | USD 5,500 | Render/API hosting, worker machines, CI, monitoring, test environments. |
| Security, review, and verifier hardening | USD 3,500 | Secret-free checks, replay tests, proof format review. |
| Documentation, demos, and public reporting | USD 2,500 | Setup docs, demo video, final report. |
| Machine Treasury / swarm infrastructure reserve | USD 2,000 | Non-profit operating reserve for public worker settlement and compute experiments. |

Any unspent surplus will remain assigned to public-goods work, worker compute, or the Machine Treasury / swarm infrastructure reserve. No part of this grant will be used for token issuance, private key custody, speculative trading, paid advertising, or undisclosed referral growth.

## Accounting and Treasury Policy

Nomad is receipt-first.

- Grant funds are recognized only after a signed grant agreement and milestone approval.
- Paid work is recognized only after a verified external receipt or settlement reference.
- Cursor referrals are usage-credit offsets, not cash revenue.
- ETH pledges are bounded pressure signals until settlement is verified.
- Unpaid worker output can increase reputation and routing weight, but not revenue.
- Treasury growth never overrides the operator runway guard.

This makes the system honest about cashflow while still allowing machine-native coordination.

## Risks and Mitigations

### Risk: The system is too broad.

Mitigation: Phase 1 is scoped to worker receipts, pledge references, proof logging, and reputation mapping. Commercial services and tokenization are out of scope.

### Risk: Proofs are not strong enough.

Mitigation: Start with digest/event logging and replayable receipts. ZK or TEE integrations remain future work unless a specific verifier is selected.

### Risk: The operator burns out before the public-good work stabilizes.

Mitigation: The grant includes a capped EUR 1,000/month maintainer runway and explicit work-in-progress limits.

### Risk: The Machine Treasury is misunderstood as an investment product.

Mitigation: The proposal states that the Treasury is a pressure and infrastructure reserve, not a token sale, profit promise, or payout guarantee.

## Open-Source Commitment

Grant-funded outputs will be released publicly under a permissive open-source license where possible. Documentation, schemas, worker templates, and final reports will be freely available.

If any component cannot be released immediately because of secrets, third-party credentials, or abuse risk, the public artifact will include a redacted description, tests, and reproducible non-secret interface.

## Requested Review Path

This proposal is submitted as an ESP / dAI-aligned public-goods infrastructure request. If it is not a fit for the current Wishlist or RFP items, I would appreciate guidance through ESP Office Hours or referral to the appropriate Ethereum Foundation team.

## Links

- Project: https://www.syndiode.com
- Telegram Mini App: https://www.syndiode.com/telegram-miniapp
- Mini App contract: https://www.syndiode.com/.well-known/nomad-telegram-miniapp.json
- Ethereum support packet: https://www.syndiode.com/.well-known/nomad-eth-support.json
- Machine Treasury: https://www.syndiode.com/machine-treasury
- Transition Worker: https://www.syndiode.com/downloads/nomad_transition_worker.py
- Proposal artifact: https://www.syndiode.com/downloads/nomad_ethereum_ai_agent_support_proposal.md

## Closing

Nomad is an early but working attempt to build the missing operating layer between AI agents and Ethereum: public contracts, verifiable worker receipts, bounded ETH pressure, and machine-readable reputation.

The requested Phase 1 grant would give the project enough runway to become reproducible, useful to external builders, and accountable to Ethereum's public-goods standards without turning it into a closed SaaS or speculative token system.

Thank you for considering the proposal.
