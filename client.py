import os
import json
from dotenv import load_dotenv

from settings import get_chain_config

load_dotenv()

try:
    from web3 import Web3
except ImportError:  # pragma: no cover - handled at runtime
    Web3 = None


PLACEHOLDER_VALUES = {
    "",
    "your_private_key_here",
    "your_agent_wallet_address_here",
    "0x...",
}


class ArbiterWeb3:
    def __init__(self):
        if Web3 is None:
            raise RuntimeError("web3 is not installed. Run 'python -m pip install web3'.")

        chain = get_chain_config()
        rpc_url = chain.rpc_url
        private_key = os.getenv("AGENT_PRIVATE_KEY")
        if not rpc_url:
            raise RuntimeError("RPC_URL is not configured.")
        if not private_key or private_key.lower() in PLACEHOLDER_VALUES:
            raise RuntimeError("AGENT_PRIVATE_KEY is not configured.")

        self.chain_id = chain.chain_id
        self.network_name = chain.name
        self.native_symbol = chain.native_symbol
        self.explorer_tx_base = chain.explorer_tx_base
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.account = self.w3.eth.account.from_key(private_key)
        contract_address = os.getenv("CONTRACT_ADDRESS") or ""
        self.contract_address = (
            contract_address
            if contract_address.lower() not in PLACEHOLDER_VALUES
            and Web3.is_address(contract_address)
            else ""
        )
        self.address = self.account.address

    @classmethod
    def is_configured(cls) -> bool:
        if Web3 is None:
            return False
        private_key = os.getenv("AGENT_PRIVATE_KEY") or ""
        rpc_url = os.getenv("RPC_URL") or get_chain_config().rpc_url or ""
        configured = bool(
            rpc_url
            and private_key
            and private_key.lower() not in PLACEHOLDER_VALUES
        )
        if not configured:
            return False
        try:
            timeout_seconds = float(os.getenv("RPC_CONNECT_TIMEOUT_SECONDS", "1.0"))
            provider = Web3.HTTPProvider(
                rpc_url,
                request_kwargs={"timeout": timeout_seconds},
            )
            return bool(Web3(provider).is_connected())
        except Exception:
            return False
        
    def record_arbitrage(self, deal_data: dict) -> str:
        """
        Records a found deal on-chain. 
        In a full ERC-8004 implementation, this would call 'reportFinding'.
        """
        try:
            tx = self.build_record_transaction(deal_data)
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.account.key)
            raw_tx = getattr(signed_tx, "raw_transaction", None) or getattr(
                signed_tx, "rawTransaction"
            )
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            return self.w3.to_hex(tx_hash)
        except Exception as e:
            print(f"[Blockchain Error] {e}")
            return ""

    def build_record_transaction(self, deal_data: dict) -> dict:
        nonce = self.w3.eth.get_transaction_count(self.account.address)

        # We keep the payload small and deterministic so it can be reconstructed later.
        call_data = self.w3.to_hex(text=json.dumps(deal_data, sort_keys=True))

        return {
            'nonce': nonce,
            'to': self.contract_address or self.account.address,
            'value': 0,
            'gas': 150000,
            'gasPrice': self.w3.eth.gas_price,
            'data': call_data,
            'chainId': self.chain_id,
        }

    def get_balance(self):
        balance_wei = self.w3.eth.get_balance(self.account.address)
        return self.w3.from_wei(balance_wei, 'ether')
