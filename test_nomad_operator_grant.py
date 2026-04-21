from nomad_operator_grant import (
    is_operator_approval_scope,
    operator_allows,
    operator_grant,
    service_approval_scope,
)


def test_operator_grant_expands_bounded_actions(monkeypatch):
    monkeypatch.setenv("NOMAD_OPERATOR_GRANT", "product_sales_agent_help_self_development")
    monkeypatch.setenv("NOMAD_OPERATOR_GRANT_SCOPE", "public_agent_help_sales_productization_bounded_development")
    monkeypatch.setenv(
        "NOMAD_OPERATOR_GRANT_ACTIONS",
        "development,service_work,code_review_diff_share,human_outreach,public_pr_plan,autonomous_continuation",
    )
    monkeypatch.setenv("NOMAD_AUTOPILOT_SERVICE_APPROVAL", "draft_only")

    grant = operator_grant()

    assert grant["enabled"] is True
    assert operator_allows("development") is True
    assert operator_allows("service_work") is True
    assert operator_allows("code_review_diff_share") is True
    assert operator_allows("human_outreach") is True
    assert operator_allows("public_pr_plan") is True
    assert operator_allows("autonomous_continuation") is True
    assert service_approval_scope() == "operator_granted"
    assert is_operator_approval_scope("operator_granted") is True
    assert "spending money" in " ".join(grant["requires_explicit_approval"])


def test_operator_grant_can_be_disabled(monkeypatch):
    monkeypatch.setenv("NOMAD_OPERATOR_GRANT", "disabled")
    monkeypatch.setenv("NOMAD_OPERATOR_GRANT_ACTIONS", "development,service_work")
    monkeypatch.setenv("NOMAD_AUTOPILOT_SERVICE_APPROVAL", "draft_only")

    grant = operator_grant()

    assert grant["enabled"] is False
    assert operator_allows("development") is False
    assert service_approval_scope() == "draft_only"
