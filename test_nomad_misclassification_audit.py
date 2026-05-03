from nomad_misclassification_audit import run_misclassification_audit_pass


def test_misclassification_audit_composes_edge_and_lead(monkeypatch):
    def fake_edge(**kwargs):
        return {
            "schema": "nomad.machine_blind_spots_pass.v1",
            "public_base_url": "https://x/nomad",
            "peer_glimpse_coherence": {
                "readiness_disagrees_with_health_probe": True,
                "network_broken_while_swarm_ok": False,
            },
            "json_contract_html_facades": [{"url": "https://x/openapi.json"}],
            "openapi_semantic_holes": [],
            "gateway_or_throttle_hits": 2,
        }

    def fake_lead(**kwargs):
        return {
            "schema": "nomad.lead_product_blind_spots_pass.v1",
            "counts": {"conversions": 10, "products": 0, "queue": 3},
            "queue_agent_metrics": {"agent_execution_desert_ratio": 0.9},
            "recurring_human_gates": [{"human_gate": "x", "count": 4}],
            "product_pain_orphans": [{"product_id": "p1"}],
            "stale_unproductized_conversions": [{"conversion_id": "c1"}],
            "conversion_draft_like_status_count": 8,
            "pain_monoculture": True,
            "human_facing_lead_hits": [{"conversion_id": "a"}] * 4,
            "duplicate_title_collisions": [{"normalized_title": "x"}] * 2,
        }

    monkeypatch.setattr("nomad_misclassification_audit.run_machine_blind_spot_pass", fake_edge)
    monkeypatch.setattr("nomad_misclassification_audit.run_lead_product_blind_spot_pass", fake_lead)

    out = run_misclassification_audit_pass(base_url="https://x/nomad", stale_days=7)
    assert out["schema"] == "nomad.misclassification_audit_pass.v1"
    kinds = {r["kind"] for r in out["misclassification_risks"]}
    assert "attribution_health_vs_readiness_split" in kinds
    assert "contract_masquerade_as_http_success" in kinds
    assert "throttle_misread_as_agent_loop" in kinds
    assert "throughput_misread_as_queue_success" in kinds
    assert "policy_wall_mistaken_for_agent_incompetence" in kinds
    assert "draft_backlog_shamed_as_low_velocity" in kinds
    assert "pain_monoculture_mistaken_for_clear_product_market_fit" in kinds
    assert "human_facing_surface_mistaken_for_agent_addressable_lead" in kinds
    assert "duplicate_title_fork_mistaken_for_single_incident" in kinds
    hooks = out.get("agent_attraction_hooks") or []
    assert len(hooks) >= 2
    assert any(h.get("sku") == "nomad.attribution_clarity_pack" for h in hooks)
    sample = next(h for h in hooks if h.get("sku") == "nomad.attribution_clarity_pack")
    assert "symptom" in sample and "relief" in sample and "verify" in sample
    assert len(out["philosophy_notes"]) >= 1
