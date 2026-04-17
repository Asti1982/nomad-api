import os
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict

from dotenv import load_dotenv
from web3 import Web3

from client import ArbiterWeb3
from settings import (
    get_project_token_address,
    get_project_token_decimals,
    get_project_token_symbol,
)


load_dotenv()


TOKEN_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

PLACEHOLDER_VALUES = {
    "",
    "your_nomad_token_address_here",
    "your_arbit_token_address_here",
}


class NomadTokenClient:
    def __init__(self) -> None:
        self.web3_client = ArbiterWeb3()
        self.token_address = get_project_token_address().strip()
        if self.token_address.lower() in PLACEHOLDER_VALUES or not Web3.is_address(
            self.token_address
        ):
            raise RuntimeError("NOMAD token address is not configured.")
        self.token_symbol = get_project_token_symbol()
        self.token_decimals = get_project_token_decimals()
        self.contract = self.web3_client.w3.eth.contract(
            address=Web3.to_checksum_address(self.token_address),
            abi=TOKEN_ABI,
        )

    @classmethod
    def is_ready(cls) -> bool:
        try:
            cls()
            return True
        except Exception:
            return False

    def token_balance(self, address: str) -> Decimal:
        raw_balance = self.contract.functions.balanceOf(address).call()
        return Decimal(raw_balance) / Decimal(10**self.token_decimals)

    def execute_local_funding(self, amount_native: float) -> Dict[str, Any]:
        if self.web3_client.chain_id != 31337:
            raise RuntimeError("Local funding execution is only enabled on chain id 31337.")

        mint_rate = Decimal(os.getenv("LOCAL_DEV_FUNDING_MINT_RATE", "1000"))
        recipient = self.web3_client.address
        token_amount = (Decimal(str(amount_native)) * mint_rate).quantize(
            Decimal("0.000001"),
            rounding=ROUND_DOWN,
        )
        mint_units = int(token_amount * Decimal(10**self.token_decimals))
        if mint_units <= 0:
            raise RuntimeError("Funding amount is too small to mint tokens.")

        tx = self.contract.functions.mint(recipient, mint_units).build_transaction(
            {
                "from": recipient,
                "nonce": self.web3_client.w3.eth.get_transaction_count(recipient),
                "gas": 200000,
                "gasPrice": self.web3_client.w3.eth.gas_price,
                "chainId": self.web3_client.chain_id,
            }
        )
        signed_tx = self.web3_client.w3.eth.account.sign_transaction(
            tx,
            self.web3_client.account.key,
        )
        raw_tx = getattr(signed_tx, "raw_transaction", None) or getattr(
            signed_tx, "rawTransaction"
        )
        tx_hash = self.web3_client.w3.eth.send_raw_transaction(raw_tx)
        receipt = self.web3_client.w3.eth.wait_for_transaction_receipt(tx_hash)

        return {
            "executed": True,
            "token_symbol": self.token_symbol,
            "token_address": self.token_address,
            "mint_rate": float(mint_rate),
            "minted_amount": float(token_amount),
            "recipient": recipient,
            "tx_hash": self.web3_client.w3.to_hex(tx_hash),
            "gas_used": receipt.gasUsed,
            "token_balance": float(self.token_balance(recipient)),
        }
