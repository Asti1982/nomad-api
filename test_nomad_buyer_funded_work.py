from agent_service import AgentServiceDesk
from nomad_bounty_hunter import build_bounty_hunter_surface
from nomad_buyer_funded_work import build_buyer_funded_work_surface
from nomad_referral_offers import build_referral_offer_surface
from nomad_referral_swarm import build_referral_swarm_surface


def _surface(tmp_path):
    base_url = "https://nomad.example"
    offers = build_referral_offer_surface(base_url=base_url)
    return build_buyer_funded_work_surface(
        base_url=base_url,
        external_value_summary={
            "schema": "nomad.external_value_summary.v1",
            "event_tail_count": 12,
            "distinct_externals": 5,
            "revenue_recognized_usd_total": 0.0,
        },
        bounty_hunter=build_bounty_hunter_surface(base_url=base_url),
        referral_swarm=build_referral_swarm_surface(base_url=base_url, referral_offers=offers),
        service_catalog=AgentServiceDesk(
            path=tmp_path / "tasks.json",
            product_store_path=tmp_path / "products.json",
        ).service_catalog(),
    )


def test_buyer_funded_work_prioritizes_small_paid_packages(tmp_path):
    out = _surface(tmp_path)

    assert out["schema"] == "nomad.buyer_funded_work.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-buyer-funded-work.json"
    assert out["receipt_law"]["recognized_revenue_usd_total"] == 0.0
    assert out["receipt_law"]["only_paid_counts"] is True
    assert out["priority_order"][0] == "buyer_funded_diagnostic_patch"
    packages = out["buyer_funded_packages"]
    starter = out["concrete_starter_order"]
    assert packages[0]["service_type"] == "repo_issue_help"
    assert packages[0]["package_id"] == "repo_diagnostic_patch_starter"
    assert packages[0]["price"]["receipt_rule"].startswith("task is revenue only")
    assert starter["entry_url"] == "https://nomad.example/service/e2e?service_type=repo_issue_help"
    assert starter["create_task_request"]["payload"]["package_id"] == "repo_diagnostic_patch_starter"
    assert starter["simulation_counts_as_revenue"] is False
    assert out["contextual_referral_policy"]["blocked"]
    assert out["bounty_gate"]["public_go_count"] == 0


def test_repo_issue_help_has_real_service_package(tmp_path):
    catalog = AgentServiceDesk(
        path=tmp_path / "tasks.json",
        product_store_path=tmp_path / "products.json",
    ).service_catalog()

    packages = catalog["service_packages"]["repo_issue_help"]
    assert packages[0]["package_id"] == "repo_diagnostic_patch_starter"
    assert "starter_repo_diagnosis" in packages[0]["aliases"]
    assert packages[0]["buyer_input"] == ["repo_url", "issue_or_log_url", "observed_error", "expected_behavior"]
    assert packages[1]["package_id"] == "bounded_repo_patch_plan"
    assert "duplicate-pressure" in packages[0]["delivery"]
