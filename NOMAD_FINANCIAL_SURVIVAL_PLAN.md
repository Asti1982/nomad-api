# Nomad Financial Survival Plan

This plan is operational, not aspirational. Nomad survives by converting proof
work into verified paid receipts, while suppressing unpaid expansion when the
operator runway is constrained.

## Hard Invariants

- Revenue is recognized only at `paid` with positive amount and settlement ref.
- `found`, `submitted`, `approved`, and `merged` are routing signals, not money.
- Public claims require scope, payout terms, duplicate scan, proof digest, and a
  compatible receive path.
- When operator runway is critical or unknown, unpaid WIP is capped and
  settlement conversion outranks new exploration.
- Human-looking persuasion has zero weight unless it later produces proof,
  acceptance, or paid receipt.

## Priority Order

1. **Settlement tail harvester**
   Convert already submitted, approved, merged, delivered, or invoiced work to
   `paid`. This is closest to money and should preempt new scouting.

2. **Receipt predictor**
   Score every value cycle by cashflow distance, preflight friction, proof state,
   operator state, and whether it can become a receipt without public-side-effect
   risk.

3. **Paid setup and support work**
   Prefer small, scoped work with buyer acceptance: API integration, plugin
   install/support, monitoring fix, bug repro, migration sprint, compliance
   packet, localization patch.

4. **Reusable proof-pack resale**
   Package failed experiments, repros, benchmark traces, and audit packets as
   licensable evidence. The machine advantage is reuse: proof becomes inventory.

5. **Authorized bounty and grant lanes**
   Scout and prove only when terms, payout, duplicate checks, and public receive
   path are clear. Public submissions remain gated.

6. **Evaluator breeding**
   Give more weight to evaluators that predicted later receipts and less weight
   to evaluators that selected unpaid work, slow loops, or social approval.

7. **Topology governor before execution**
   More agents are admitted only when task physics predicts lower error and
   faster receipt conversion. Otherwise collapse to single-agent or centralized
   router.

## Abarbeitungsplan

| Phase | Goal | Machine Surface | Done When |
|---|---|---|---|
| 1 | Convert existing tails | `external-value`, `work-receipts` | nonpaid tails have next evidence request |
| 2 | Rank all value cycles | `receipt-predictor` | top queue has receipt proximity score |
| 3 | Execute near-cash work | `value-cycles`, `worker-job-queue` | only top WIP-cap cycles active |
| 4 | Package reusable proof | `proof-reuse-ledger`, `work-receipts` | proof packs become sellable artifacts |
| 5 | Breed evaluators | `shadow-lane`, `receipt-predictor` | predictors are scored by later receipt |
| 6 | Scale agents | `topology-governor` | extra agents require topology receipt |

## Non-Human Concepts To Preserve

- Archive failed work instead of deleting it.
- Treat negative results as saleable evidence.
- Reward delayed receipts, not immediate approval.
- Collapse swarms when single-agent baselines are strong.
- Quarantine human-readable text from credit assignment.
- Re-sample old candidates under new market conditions.

## Daily Machine Loop

1. Read `/.well-known/nomad-receipt-predictor.json`.
2. Pick the highest `now` queue item.
3. Run the required preflight.
4. Produce or verify the missing proof digest.
5. Record only monotonic stage transitions.
6. Stop when WIP cap is reached.
7. Increase weight only after paid receipt or accepted work receipt.
