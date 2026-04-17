import os
import re
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

from settings import (
    get_chain_config,
    get_project_token_address,
    get_project_token_decimals,
    get_project_token_symbol,
    get_wrapped_native_token_address,
)

load_dotenv()


PLACEHOLDER_VALUES = {
    "",
    "your_private_key_here",
    "your_agent_wallet_address_here",
    "your_0x_api_key_here",
    "your_arbit_token_address_here",
    "your_weth_token_address_here",
    "your_nomad_token_address_here",
    "your_wbnb_token_address_here",
}


class TreasuryAgent:
    def __init__(self) -> None:
        self.chain = get_chain_config()
        self.chain_id = self.chain.chain_id
        self.rpc_url = self.chain.rpc_url
        self.network_name = self.chain.name
        self.native_symbol = self.chain.native_symbol
        self.explorer_tx_base = self.chain.explorer_tx_base
        self.agent_address = (os.getenv("AGENT_ADDRESS") or "").strip()
        self.contract_address = (os.getenv("CONTRACT_ADDRESS") or "").strip()
        self.zerox_api_key = (os.getenv("ZEROX_API_KEY") or "").strip()
        self.zerox_base = (os.getenv("ZEROX_API_BASE") or "https://api.0x.org").rstrip(
            "/"
        )
        self.project_token_address = get_project_token_address().strip()
        self.wrapped_native_token_address = get_wrapped_native_token_address().strip()
        self.project_token_symbol = get_project_token_symbol()
        self.project_token_decimals = get_project_token_decimals()
        self.project_token_address = self.project_token_address or ""
        self.token_split_bps = int(os.getenv("FUNDING_SPLIT_TOKEN_BPS", "7000"))
        self.reserve_split_bps = int(os.getenv("FUNDING_SPLIT_RESERVE_BPS", "3000"))

    def build_funding_plan(self, query: str) -> Dict[str, Any]:
        amount_native = self._parse_amount_native(query)
        wallet_summary = self.get_wallet_summary()

        token_allocation = None
        reserve_allocation = None
        quote = None
        if amount_native is not None:
            token_allocation = round(amount_native * self.token_split_bps / 10000, 6)
            reserve_allocation = round(amount_native * self.reserve_split_bps / 10000, 6)
            quote = self.get_token_quote(token_allocation)

        contract_address = ""
        if self.contract_address and self.contract_address.lower() not in PLACEHOLDER_VALUES:
            contract_address = self.contract_address

        return {
            "wallet": wallet_summary,
            "network": self.network_name,
            "chain_id": self.chain_id,
            "native_symbol": self.native_symbol,
            "explorer_tx_base": self.explorer_tx_base,
            "project_token_symbol": self.project_token_symbol,
            "project_token_address": (
                ""
                if self.project_token_address.lower() in PLACEHOLDER_VALUES
                else self.project_token_address
            ),
            "amount_native": amount_native,
            "token_allocation_native": token_allocation,
            "reserve_allocation_native": reserve_allocation,
            "amount_eth": amount_native,
            "token_allocation_eth": token_allocation,
            "reserve_allocation_eth": reserve_allocation,
            "quote": quote,
            "token_split_pct": round(self.token_split_bps / 100, 2),
            "reserve_split_pct": round(self.reserve_split_bps / 100, 2),
            "contract_address": contract_address,
        }

    def get_wallet_summary(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "address": "",
            "native_balance": None,
            "native_balance_eth": None,
            "configured": False,
            "rpc_url": self.rpc_url,
        }

        if self.agent_address and self.agent_address.lower() not in PLACEHOLDER_VALUES:
            summary["address"] = self.agent_address
            summary["configured"] = True

        try:
            from client import ArbiterWeb3

            if ArbiterWeb3.is_configured():
                client = ArbiterWeb3()
                summary["address"] = client.address
                balance = round(float(client.get_balance()), 6)
                summary["native_balance"] = balance
                summary["native_balance_eth"] = balance
                summary["configured"] = True
        except Exception as exc:
            summary["warning"] = str(exc)

        try:
            from nomad_token_client import NomadTokenClient

            if summary.get("address") and NomadTokenClient.is_ready():
                token_client = NomadTokenClient()
                summary["project_token_symbol"] = token_client.token_symbol
                summary["project_token_address"] = token_client.token_address
                summary["project_token_balance"] = round(
                    float(token_client.token_balance(summary["address"])),
                    6,
                )
        except Exception:
            pass

        return summary

    def maybe_execute_local_funding(self, plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        amount_native = plan.get("amount_native")
        token_allocation = plan.get("token_allocation_native")
        if self.chain_id != 31337 or amount_native is None or token_allocation is None:
            return None

        try:
            from nomad_token_client import NomadTokenClient

            if not NomadTokenClient.is_ready():
                return {
                    "executed": False,
                    "message": "Local NOMAD token is not deployed yet.",
                }
            token_client = NomadTokenClient()
            execution = token_client.execute_local_funding(token_allocation)
            execution["reserve_stays_native"] = plan.get("reserve_allocation_native")
            return execution
        except Exception as exc:
            return {
                "executed": False,
                "message": f"Local funding execution failed: {exc}",
            }

    def get_token_quote(self, sell_amount_eth: Optional[float]) -> Optional[Dict[str, Any]]:
        if sell_amount_eth is None or sell_amount_eth <= 0:
            return None
        if (
            self.zerox_api_key.lower() in PLACEHOLDER_VALUES
            or self.project_token_address.lower() in PLACEHOLDER_VALUES
            or self.wrapped_native_token_address.lower() in PLACEHOLDER_VALUES
        ):
            return {
                "available": False,
                "message": (
                    "0x quote is not configured yet. Set ZEROX_API_KEY, "
                    "WRAPPED_NATIVE_TOKEN_ADDRESS and NOMAD_TOKEN_ADDRESS to enable live quotes."
                ),
            }

        wallet = self.get_wallet_summary()
        taker = wallet.get("address")
        if not taker:
            return {
                "available": False,
                "message": "Agent wallet address is not configured yet.",
            }

        sell_amount_wei = str(int(sell_amount_eth * 10**18))
        response = requests.get(
            f"{self.zerox_base}/swap/allowance-holder/price",
            params={
                "chainId": self.chain_id,
                "sellToken": self.wrapped_native_token_address,
                "buyToken": self.project_token_address,
                "sellAmount": sell_amount_wei,
                "taker": taker,
            },
            headers={
                "0x-api-key": self.zerox_api_key,
                "0x-version": "v2",
            },
            timeout=20,
        )
        if not response.ok:
            return {
                "available": False,
                "message": f"0x quote failed with status {response.status_code}.",
            }

        payload = response.json()
        buy_amount_raw = payload.get("buyAmount")
        buy_amount = None
        if buy_amount_raw:
            buy_amount = round(
                int(buy_amount_raw) / (10**self.project_token_decimals),
                6,
            )

        route = payload.get("route") or {}
        fills = route.get("fills") or []
        return {
            "available": bool(payload.get("liquidityAvailable", True)),
            "estimated_buy_amount": buy_amount,
            "buy_symbol": self.project_token_symbol,
            "sell_amount_native": sell_amount_eth,
            "sell_symbol": self.native_symbol,
            "route_sources": sorted(
                {fill.get("source", "Unknown") for fill in fills if fill.get("source")}
            ),
        }

    def _parse_amount_native(self, query: str) -> Optional[float]:
        symbol = re.escape(self.native_symbol.lower())
        match = re.search(
            rf"(\d+(?:[.,]\d+)?)\s*(?:eth|weth|bnb|tbnb|{symbol})",
            query,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        return float(match.group(1).replace(",", "."))
