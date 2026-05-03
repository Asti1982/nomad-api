from nomad_mcp_survival_playbook import build_mcp_survival_playbook


def test_mcp_survival_playbook_has_product_and_evidence():
    out = build_mcp_survival_playbook()
    assert out["schema"] == "nomad.mcp_survival_playbook.v1"
    assert out["nomad_product"]["pain_type"] == "mcp_production"
    assert len(out["github_evidence"]) >= 4
    assert "github.com" in out["github_evidence"][0]["url"]
