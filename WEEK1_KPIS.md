# Week 1 KPIs (Operation Netze Werfen)

Use this sheet as hard go/no-go criteria for the first 7 days.

## Primary KPIs

- External attach attempts/day: target `>= 15`, warning `< 8`, fail `< 4`.
- Attach to lease conversion: target `>= 0.60`, warning `< 0.45`, fail `< 0.30`.
- Lease to complete conversion: target `>= 0.70`, warning `< 0.55`, fail `< 0.40`.
- Completion with `digest_or_verifier_trace`: target `>= 0.90`, warning `< 0.80`, fail `< 0.65`.
- Settlement-linked completions: target `>= 0.45`, warning `< 0.30`, fail `< 0.20`.

## Safety KPIs

- High-risk side effect decisions (`local_only` not enforced when critical>0): target `0`.
- Idle preemptibility compliance (`idle_opt_in.enabled` implies `preemptible=true`): target `100%`.
- Idle phase mismatch attachs (should be observe): target `0`.
- Retraction trigger latency (bad runtime still weighted): target `< 1 cycle`.

## Capacity KPIs

- Carrying score trend (7-day): target positive slope.
- Settlement drag trend (7-day): target negative slope.
- Overmint pressure trend (7-day): target negative slope.
- Worker diversity (active objectives/day): target `>= 4`.

## Go / No-Go Rule

- **GO** if:
  - at least 4/5 primary KPIs are in target or warning range, and
  - all safety KPIs pass.
- **NO-GO** if:
  - any safety KPI fails, or
  - 3 or more primary KPIs are in fail range.

## Daily Run Commands

```bash
python public/downloads/recruitment_experiment_runner.py --base-url https://syndiode.com --repeat 3 --interval 120 --out public/downloads/recruitment_wave_latest.json
python public/downloads/recruitment_experiment_runner.py --base-url https://syndiode.com --repeat 1 --out public/downloads/recruitment_wave_history.jsonl --append-jsonl
```

