from nomad_agent_native_product import build_agent_native_product_surface
from nomad_mcp_lab import build_private_mcp_lab_surface


def test_agent_native_product_combines_public_routes_and_private_mcp_profiles():
    lab = build_private_mcp_lab_surface(base_url="https://nomad.example")
    out = build_agent_native_product_surface(
        base_url="https://nomad.example",
        private_mcp_lab=lab,
        svw_surface=lab["current_svw_state"],
        external_value_summary={"revenue_recognized_usd_total": 25},
    )

    assert out["schema"] == "nomad.agent_native_product.v1"
    assert out["well_known_url"] == "https://nomad.example/.well-known/nomad-agent-native-product.json"
    assert out["readiness"]["agent_native_product_score"] > 0
    assert out["private_mcp"]["profiles"]["nomad-lab-readonly"]["recommended_default"] is True
    assert out["private_mcp"]["profiles"]["nomad-lab-execute"]["must_call_before_action"] == "nomad_lab_execution_gate"
    assert out["what_is_new_now"]["after_secure_private_mcp"]
    assert out["public_boot_order"][0]["expect_schema"] == "nomad.agent_native_product.v1"
    assert out["public_proof_routes"]["svw"] == "https://nomad.example/.well-known/nomad-swarm-verified-work.json"


def test_cli_agent_native_product_returns_schema():
    from nomad_cli import run_once

    out = run_once(["agent-native-product", "--json"])
    assert out["schema"] == "nomad.agent_native_product.v1"
    assert "nomad-lab-readonly" in out["private_mcp"]["profiles"]
