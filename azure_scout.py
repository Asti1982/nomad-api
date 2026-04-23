"""
Azure Scout: Discover free and low-cost Azure infrastructure lanes for Nomad agents.

Focuses on free tier, free credits, and minimal-cost Azure services that work
for AI agents without requiring budget.
"""

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class AzureResourceOption:
    """Represents a free/low-cost Azure resource option for agent infrastructure."""

    id: str
    name: str
    service_type: str  # compute, hosting, database, monitoring, etc.
    free_tier_limit: str
    free_score: float  # 0-1, how much is actually free
    reliability_score: float  # 0-1
    automation_score: float  # 0-1 (how easy to provision via CLI/Bicep)
    description: str
    setup_effort: str  # minutes to set up
    monthly_cost_if_exceeded: str


class AzureScout:
    """Scout free Azure infrastructure lanes."""

    # Free Azure services aligned with Nomad's agent use cases
    FREE_OPTIONS: List[AzureResourceOption] = [
        # Compute
        AzureResourceOption(
            id="azure-container-instances-free",
            name="Azure Container Instances (free tier)",
            service_type="compute",
            free_tier_limit="Up to 4 vCPU-hours/month free on pay-as-you-go",
            free_score=0.3,  # 4 hours/month is very limited
            reliability_score=0.95,
            automation_score=0.90,
            description="Run Docker containers without managing VMs. 4 vCPU-hours/month free.",
            setup_effort="10 minutes (az cli or portal)",
            monthly_cost_if_exceeded="~$0.0015 per vCPU-second",
        ),
        AzureResourceOption(
            id="azure-functions-free",
            name="Azure Functions (free tier)",
            service_type="compute",
            free_tier_limit="1M requests/month, 400k GB-seconds/month",
            free_score=0.85,
            reliability_score=0.95,
            automation_score=0.90,
            description="Serverless compute for event-driven workloads. 1M requests/month free.",
            setup_effort="5 minutes (az cli)",
            monthly_cost_if_exceeded="~$0.20 per 1M requests",
        ),
        AzureResourceOption(
            id="azure-app-service-free",
            name="Azure App Service (free tier)",
            service_type="hosting",
            free_tier_limit="10 apps per resource group, 1 GB storage, shared compute",
            free_score=0.70,
            reliability_score=0.85,
            automation_score=0.85,
            description="Host web apps and APIs. Free tier limited to 1 GB storage and shared compute.",
            setup_effort="10 minutes (az cli or portal)",
            monthly_cost_if_exceeded="~$13/month for Basic tier",
        ),
        AzureResourceOption(
            id="azure-static-web-apps-free",
            name="Azure Static Web Apps (free tier)",
            service_type="hosting",
            free_tier_limit="100 GB bandwidth/month, 1 function per site",
            free_score=0.80,
            reliability_score=0.90,
            automation_score=0.85,
            description="Host static sites + serverless APIs. 100 GB bandwidth/month free.",
            setup_effort="15 minutes (GitHub Actions)",
            monthly_cost_if_exceeded="~$0.20 per GB over 100 GB",
        ),
        AzureResourceOption(
            id="azure-cosmos-db-free",
            name="Azure Cosmos DB (free tier)",
            service_type="database",
            free_tier_limit="1000 RUs/month, 25 GB storage",
            free_score=0.50,
            reliability_score=0.98,
            automation_score=0.80,
            description="NoSQL database. 1000 RUs/month free, 25 GB storage included.",
            setup_effort="10 minutes (az cli)",
            monthly_cost_if_exceeded="~$0.25 per RU/month",
        ),
        AzureResourceOption(
            id="azure-blob-storage-free",
            name="Azure Blob Storage (free tier)",
            service_type="storage",
            free_tier_limit="5 GB included with account, pay for overages",
            free_score=0.40,
            reliability_score=0.99,
            automation_score=0.90,
            description="Object storage for agent data, models, outputs. First 5 GB free account-wide.",
            setup_effort="5 minutes (az cli)",
            monthly_cost_if_exceeded="~$0.018 per GB",
        ),
        AzureResourceOption(
            id="azure-log-analytics-free",
            name="Azure Log Analytics (free tier)",
            service_type="monitoring",
            free_tier_limit="5 GB ingestion/day, 30-day retention",
            free_score=0.70,
            reliability_score=0.95,
            automation_score=0.85,
            description="Monitor and debug agent workloads. 5 GB/day ingestion free.",
            setup_effort="10 minutes (az cli)",
            monthly_cost_if_exceeded="~$0.70 per GB over 5 GB/day",
        ),
        AzureResourceOption(
            id="azure-key-vault-free",
            name="Azure Key Vault (free tier)",
            service_type="security",
            free_tier_limit="10,000 transactions/month included",
            free_score=0.90,
            reliability_score=0.99,
            automation_score=0.85,
            description="Secure credential storage for agent tokens and secrets.",
            setup_effort="5 minutes (az cli)",
            monthly_cost_if_exceeded="$0.03 per 10k transactions",
        ),
        AzureResourceOption(
            id="azure-managed-identity",
            name="Azure Managed Identity (free)",
            service_type="identity",
            free_tier_limit="Unlimited identities, unlimited AAD operations",
            free_score=1.0,
            reliability_score=0.99,
            automation_score=0.90,
            description="Identity for agents to access Azure services without secrets.",
            setup_effort="2 minutes (az cli)",
            monthly_cost_if_exceeded="No additional cost",
        ),
    ]

    # GitHub Models (Microsoft-backed, via GitHub - already in Nomad but listed for completeness)
    GITHUB_MODELS_OPTION = AzureResourceOption(
        id="github-models-free",
        name="GitHub Models (free inference)",
        service_type="compute/models",
        free_tier_limit="Unlimited reasoning calls, rate-limited to prevent abuse",
        free_score=0.95,
        reliability_score=0.90,
        automation_score=0.95,
        description="Free inference via GitHub (Microsoft-backed). GPT-4.1, Grok, Claude available.",
        setup_effort="1 minute (GitHub token with Models: read)",
        monthly_cost_if_exceeded="Currently free tier only",
    )

    def __init__(self) -> None:
        self.azure_subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
        self.azure_tenant_id = os.getenv("AZURE_TENANT_ID", "")
        self.azure_cli_available = self._check_azure_cli()

    def _check_azure_cli(self) -> bool:
        """Check if Azure CLI is installed and authenticated."""
        try:
            import subprocess

            result = subprocess.run(
                ["az", "account", "show"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def free_options(self) -> List[Dict[str, Any]]:
        """Return all free Azure options as dicts."""
        return [self._option_to_dict(opt) for opt in self.FREE_OPTIONS]

    def get_option(self, option_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific free Azure option by ID."""
        for opt in self.FREE_OPTIONS:
            if opt.id == option_id:
                return self._option_to_dict(opt)
        return None

    def _option_to_dict(self, opt: AzureResourceOption) -> Dict[str, Any]:
        """Convert option to dict format compatible with infra_scout."""
        return {
            "id": opt.id,
            "category": opt.service_type,
            "name": opt.name,
            "summary": opt.description,
            "best_for": f"Agent infrastructure without spending. {opt.free_tier_limit}",
            "tradeoff": f"Free tier is limited; {opt.monthly_cost_if_exceeded} if exceeded.",
            "source_url": "https://azure.microsoft.com/free",
            "tags": ("free", "azure", opt.service_type, "no-budget"),
            "free_score": opt.free_score,
            "reliability_score": opt.reliability_score,
            "automation_score": opt.automation_score,
            "openness_score": 0.5,  # Azure is proprietary but stable
            "privacy_score": 0.7,  # Microsoft datacenter, GDPR-compliant
            "ai_fit_score": 0.9 if opt.service_type == "compute" else 0.7,
        }

    def activation_request(self, option_id: str) -> Dict[str, Any]:
        """Generate human activation/unlock request for an Azure option."""
        opt = next((o for o in self.FREE_OPTIONS if o.id == option_id), None)
        if not opt:
            return {
                "ok": False,
                "error": "option_not_found",
                "message": f"Azure option {option_id} not found.",
            }

        steps = self._get_setup_steps(opt)
        return {
            "ok": True,
            "option_id": opt.id,
            "option_name": opt.name,
            "category": opt.service_type,
            "message": f"Nomad wants to use {opt.name} for agent infrastructure.",
            "free_tier_limit": opt.free_tier_limit,
            "setup_effort": opt.setup_effort,
            "steps": steps,
            "verification": self._get_verification_command(opt),
            "docs_url": self._get_docs_url(opt),
        }

    def _get_setup_steps(self, opt: AzureResourceOption) -> List[str]:
        """Get setup steps for an Azure option."""
        base_steps = [
            "1. Ensure Azure CLI is installed: https://learn.microsoft.com/cli/azure/install-azure-cli",
            "2. Authenticate: az login",
            "3. Set subscription: az account set --subscription <subscription-id>",
        ]

        if opt.id == "azure-container-instances-free":
            base_steps.extend([
                "4. Create resource group: az group create --name nomad-rg --location eastus",
                "5. Deploy container: az container create --resource-group nomad-rg --name nomad-agent --image python:3.11 --command-line 'python main.py'",
            ])
        elif opt.id == "azure-functions-free":
            base_steps.extend([
                "4. Create resource group: az group create --name nomad-rg --location eastus",
                "5. Create storage: az storage account create --resource-group nomad-rg --name nomadstore",
                "6. Create function app: az functionapp create --resource-group nomad-rg --consumption-plan-location eastus --name nomad-func --storage-account nomadstore",
            ])
        elif opt.id == "azure-static-web-apps-free":
            base_steps.extend([
                "4. Connect GitHub repo: https://portal.azure.com -> Static Web Apps -> Create",
                "5. Deploy automatically via GitHub Actions",
            ])
        elif opt.id == "azure-cosmos-db-free":
            base_steps.extend([
                "4. Create resource group: az group create --name nomad-rg --location eastus",
                "5. Create Cosmos account: az cosmosdb create --name nomad-db --resource-group nomad-rg",
            ])

        return base_steps

    def _get_verification_command(self, opt: AzureResourceOption) -> str:
        """Get command to verify the Azure option is working."""
        if not self.azure_cli_available:
            return "Install Azure CLI and run: az account show"

        if opt.id == "azure-container-instances-free":
            return "az container list --resource-group nomad-rg"
        elif opt.id == "azure-functions-free":
            return "az functionapp list --resource-group nomad-rg"
        elif opt.id == "azure-static-web-apps-free":
            return "az staticwebapp list"
        elif opt.id == "azure-cosmos-db-free":
            return "az cosmosdb list --resource-group nomad-rg"
        else:
            return "az account show"

    def _get_docs_url(self, opt: AzureResourceOption) -> str:
        """Get documentation URL for an Azure option."""
        docs_map = {
            "azure-container-instances-free": "https://learn.microsoft.com/azure/container-instances/container-instances-overview",
            "azure-functions-free": "https://learn.microsoft.com/azure/azure-functions/functions-overview",
            "azure-app-service-free": "https://learn.microsoft.com/azure/app-service/overview",
            "azure-static-web-apps-free": "https://learn.microsoft.com/azure/static-web-apps/overview",
            "azure-cosmos-db-free": "https://learn.microsoft.com/azure/cosmos-db/introduction",
            "azure-blob-storage-free": "https://learn.microsoft.com/azure/storage/blobs/storage-blobs-overview",
            "azure-log-analytics-free": "https://learn.microsoft.com/azure/azure-monitor/logs/log-analytics-overview",
            "azure-key-vault-free": "https://learn.microsoft.com/azure/key-vault/general/overview",
            "azure-managed-identity": "https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview",
        }
        return docs_map.get(opt.id, "https://azure.microsoft.com/free")


def scout_free_azure() -> Dict[str, Any]:
    """Entry point: Get summary of free Azure options for agents."""
    scout = AzureScout()
    return {
        "provider": "Azure",
        "focus": "Free tier and minimal-cost infrastructure",
        "cli_available": scout.azure_cli_available,
        "subscription_configured": bool(scout.azure_subscription_id),
        "options": scout.free_options(),
        "recommended_path": [
            "azure-managed-identity",  # Free identity
            "github-models-free",  # Free inference
            "azure-static-web-apps-free",  # Free hosting
            "azure-functions-free",  # Free compute
        ],
        "next_step": "Request activation for one option via /unlock azure <option-id>",
    }


if __name__ == "__main__":
    result = scout_free_azure()
    import json

    print(json.dumps(result, indent=2))
