"""Tests for Azure Scout integration with Nomad infrastructure discovery."""

from azure_scout import AzureScout, scout_free_azure
from infra_scout import InfrastructureScout


def test_azure_scout_basic():
    scout = AzureScout()
    options = scout.free_options()

    assert len(options) > 0
    assert all("id" in option for option in options)
    assert all("free_score" in option for option in options)


def test_azure_scout_activation_request():
    scout = AzureScout()
    request = scout.activation_request("azure-functions-free")

    assert request["ok"] is True
    assert "steps" in request
    assert len(request["steps"]) > 0
    assert request["option_name"]


def test_infra_scout_azure_integration():
    scout = InfrastructureScout()
    azure_options = [option for option in scout.options if "azure" in option.tags]
    activation = scout.activation_request(category="azure")

    assert len(azure_options) > 0
    assert activation["mode"] == "activation_request"
    assert activation["category"] == "compute"


def test_free_azure_summary():
    result = scout_free_azure()

    assert result["provider"] == "Azure"
    assert len(result["options"]) > 0
    assert "recommended_path" in result
