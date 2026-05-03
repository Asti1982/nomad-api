from nomad_agent_market_offers import build_inter_agent_witness_offer_well_known


def test_inter_agent_witness_well_known_card():
    card = build_inter_agent_witness_offer_well_known(public_base_url="https://api.example")
    assert card["ok"] is True
    assert card["schema"] == "nomad.well_known_agent_sku_offer.v1"
    assert card["service_type"] == "inter_agent_witness"
    assert card["sku"] == "nomad.inter_agent_witness_bundle_pack"
    assert "who_builds_who_buys" in card
    acts = card.get("machine_actions") or {}
    assert acts["service_menu"]["url"] == "https://api.example/service"
    assert acts["create_task"]["url"] == "https://api.example/tasks"
