import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def env_first(*keys: str, default: str = "") -> str:
    for key in keys:
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return default


@dataclass(frozen=True)
class ChainConfig:
    name: str
    rpc_url: str
    chain_id: int
    native_symbol: str
    explorer_tx_base: str


def get_chain_config() -> ChainConfig:
    chain_id = int(env_first("EVM_CHAIN_ID", "CHAIN_ID", "BASE_CHAIN_ID", default="97"))
    explorer_raw = os.getenv("BLOCK_EXPLORER_TX_BASE")
    explorer = (
        explorer_raw.strip()
        if explorer_raw is not None
        else "https://testnet.bscscan.com/tx/"
    )
    return ChainConfig(
        name=env_first("NETWORK_NAME", default="BSC Testnet"),
        rpc_url=env_first(
            "RPC_URL",
            default="https://data-seed-prebsc-1-s1.binance.org:8545",
        ),
        chain_id=chain_id,
        native_symbol=env_first("NATIVE_SYMBOL", default="TBNB"),
        explorer_tx_base=(explorer.rstrip("/") + "/") if explorer else "",
    )


def get_project_token_address() -> str:
    return env_first("NOMAD_TOKEN_ADDRESS", "ARBIT_TOKEN_ADDRESS")


def get_project_token_symbol() -> str:
    return env_first("NOMAD_TOKEN_SYMBOL", "ARBIT_TOKEN_SYMBOL", default="NOMAD")


def get_project_token_decimals() -> int:
    return int(env_first("NOMAD_TOKEN_DECIMALS", "ARBIT_TOKEN_DECIMALS", default="18"))


def get_wrapped_native_token_address() -> str:
    return env_first("WRAPPED_NATIVE_TOKEN_ADDRESS", "WETH_TOKEN_ADDRESS")
