import os
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values, set_key

from amadeus_client import AmadeusClient
from settings import get_chain_config
from treasury_agent import TreasuryAgent


ENV_PATH = Path(__file__).resolve().parent / ".env"

FIELDS = [
    ("AMADEUS_API_KEY", "Amadeus API key"),
    ("AMADEUS_API_SECRET", "Amadeus API secret"),
    ("AGENT_ADDRESS", "BSC testnet agent wallet address"),
    ("AGENT_PRIVATE_KEY", "BSC testnet agent private key"),
    ("CONTRACT_ADDRESS", "Optional contract address"),
    ("ZEROX_API_KEY", "0x API key"),
    ("WRAPPED_NATIVE_TOKEN_ADDRESS", "Wrapped native token address"),
    ("NOMAD_TOKEN_ADDRESS", "Your Nomad token address"),
]


def load_env_values() -> Dict[str, str]:
    raw = dotenv_values(ENV_PATH)
    return {key: str(value or "") for key, value in raw.items()}


def prompt_value(label: str, current: str) -> str:
    masked = "set" if current and "your_" not in current.lower() else "empty"
    answer = input(f"{label} [{masked}] (Enter keeps current): ").strip()
    return current if not answer else answer


def main() -> None:
    chain = get_chain_config()
    print("Arbiter live setup")
    print(f"Using env file: {ENV_PATH}")
    print(f"Active chain: {chain.name} ({chain.native_symbol})")
    values = load_env_values()

    for key, label in FIELDS:
        current = values.get(key, "")
        updated = prompt_value(label, current)
        set_key(str(ENV_PATH), key, updated)
        values[key] = updated

    print("\nRunning checks...")

    amadeus_ok = False
    amadeus = AmadeusClient()
    if amadeus.is_configured():
        try:
            token = amadeus._get_access_token()
            amadeus_ok = bool(token)
            print("Amadeus auth: OK")
        except Exception as exc:
            print(f"Amadeus auth: FAILED - {exc}")
    else:
        print("Amadeus auth: SKIPPED - keys missing")

    treasury = TreasuryAgent()
    funding = treasury.build_funding_plan(f"fund me 0.1 {chain.native_symbol.lower()}")
    wallet = funding["wallet"]
    if wallet.get("address"):
        print(f"Wallet address: {wallet['address']}")
    else:
        print("Wallet address: missing")

    quote = funding.get("quote")
    if quote and quote.get("available"):
        print("0x quote: OK")
    elif quote:
        print(f"0x quote: SKIPPED - {quote.get('message', 'not available')}")
    else:
        print("0x quote: SKIPPED")

    print("\nSetup complete.")
    if amadeus_ok:
        print("You can now test live travel search in Telegram.")
    else:
        print("Travel search still needs valid Amadeus credentials.")


if __name__ == "__main__":
    main()
