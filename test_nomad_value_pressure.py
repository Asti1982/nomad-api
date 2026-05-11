from nomad_value_pressure import build_value_pressure_surface


def _external_reconcile():
    return {
        "schema": "nomad.external_value_reconcile.v1",
        "generated_at": "2026-05-11T00:00:00+00:00",
        "followups": [
            {
                "external_id": "gh_pr:Scottcjn/Rustchain#4542",
                "current_stage": "merged",
                "work_url": "https://github.com/Scottcjn/Rustchain/pull/4542",
                "paid_guard": "paid_requires_payment_receipt_with_positive_amount_and_current_stage_merged",
                "followup": {
                    "action": "await_payment_receipt",
                    "priority": 0.91,
                    "target_stage": "paid",
                    "required_evidence": [
                        "trusted_owner_member_or_collaborator_payment_receipt",
                        "positive_amount_usd",
                        "public_or_private_receipt_digest",
                    ],
                    "machine_instruction": "never_mint_paid_from_merge_alone_wait_for_positive_receipt",
                },
            },
            {
                "external_id": "gh_issue_comment:Scottcjn/rustchain-bounties#73:1",
                "current_stage": "submitted",
                "work_url": "https://github.com/Scottcjn/rustchain-bounties/issues/73#issuecomment-1",
                "followup": {
                    "action": "ignore_soft_ack_wait_for_owner_signal",
                    "priority": 0.36,
                    "target_stage": "approved",
                    "required_evidence": ["owner_or_maintainer_acceptance_signal"],
                },
            },
        ],
    }


def _bounty_hunter():
    scout = {
        "opportunity_id": "rustchain_utxo_static_red_team",
        "source_url": "https://github.com/Scottcjn/rustchain-bounties/issues/2819",
        "repo": "Scottcjn/Rustchain",
        "bounty_score": 0.278432,
        "has_unique_repro": False,
        "comment_count": 0,
        "score_components": {"hourly_value_usd": 3.4688},
        "hard_gate": {
            "public_action": "scout_only",
            "required_proof": [
                "public_terms_url",
                "local_repro_or_patch_digest",
                "verifier_trace_digest",
                "work_url_after_public_action",
            ],
        },
        "claim_next": {
            "first_action": "gh repo clone Scottcjn/Rustchain external_work/scottcjn-rustchain",
            "work_rule": "local_static_review_or_failing_test_only_then_pr_or_issue_with_reproducible_trace",
        },
    }
    no_go = {
        "opportunity_id": "capital_market_claim",
        "hard_gate": {"public_action": "no_go"},
    }
    return {
        "schema": "nomad.bounty_hunter.v1",
        "bounty_digest": "nomad-bounty-hunter-test",
        "summary": {"public_go_count": 0, "scout_only_count": 1},
        "top_scout_candidate": scout,
        "top_candidate": scout,
        "opportunities": [scout, no_go],
        "excluded_lanes": [no_go],
    }


def _compute_market():
    return {
        "schema": "nomad.compute_market.v1",
        "market_digest": "nomad-compute-market-test",
        "market_state": {"recent_offer_count": 1},
        "top_worker": {
            "agent_id": "worker.1",
            "offer_id": "offer.1",
            "objective": "settlement_capacity_builder",
            "market_score": 0.23,
        },
        "top_lane": {
            "lane_id": "endpoint_health_proof",
            "price_eur": 0.02,
            "settled_eur": 0.04,
            "fill_rate": 0.5,
        },
    }


def test_value_pressure_prioritizes_merged_payment_receipt_over_new_scout_work():
    surface = build_value_pressure_surface(
        base_url="https://nomad.example",
        external_reconcile=_external_reconcile(),
        bounty_hunter=_bounty_hunter(),
        compute_market=_compute_market(),
    )

    assert surface["schema"] == "nomad.value_pressure.v1"
    assert surface["read_url"] == "https://nomad.example/swarm/value-pressure"
    assert surface["top"]["action"] == "await_payment_receipt"
    assert surface["top"]["external_id"] == "gh_pr:Scottcjn/Rustchain#4542"
    assert surface["summary"]["suppressed"]["bounty_no_go"] == 2
    assert surface["coordination_observation_contract"]["required_fields"]


def test_value_pressure_keeps_machine_local_views_deterministic():
    surface1 = build_value_pressure_surface(
        base_url="",
        external_reconcile=_external_reconcile(),
        bounty_hunter=_bounty_hunter(),
        compute_market=_compute_market(),
    )
    surface2 = build_value_pressure_surface(
        base_url="",
        external_reconcile=_external_reconcile(),
        bounty_hunter=_bounty_hunter(),
        compute_market=_compute_market(),
    )

    assert surface1["local_views"] == surface2["local_views"]
    assert set(surface1["local_views"]) == {
        "settlement_agent",
        "proof_scout",
        "capacity_binder",
        "topology_router",
    }
    assert all(len(rows) <= 3 for rows in surface1["local_views"].values())


def test_cli_value_pressure_returns_machine_surface():
    from nomad_cli import run_once

    out = run_once(["value-pressure", "--base-url", "https://nomad.example", "--json"])

    assert out["schema"] == "nomad.value_pressure.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-value-pressure.json"
    assert "local_views" in out


def test_unknown_microtask_lane_is_penalized_until_resolved():
    compute = _compute_market()
    compute["top_lane"] = {
        "lane_id": "unknown_lane",
        "settled_eur": 0.12,
        "fill_rate": 2.0,
    }

    surface = build_value_pressure_surface(
        base_url="",
        external_reconcile={"followups": []},
        bounty_hunter=_bounty_hunter(),
        compute_market=compute,
    )
    lane = next(row for row in surface["rows"] if row.get("lane_id") == "unknown_lane")

    assert lane["action"] == "inspect_or_claim_microtask_lane"
    assert lane["score_components"]["orphan_penalty"] == 0.35
    assert lane["pressure_score"] < 0.5
