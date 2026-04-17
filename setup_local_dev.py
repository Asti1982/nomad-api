import shutil
import subprocess
import time
from pathlib import Path

from dotenv import dotenv_values, set_key
from eth_account import Account
from web3 import Web3

from settings import get_project_token_symbol


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
OUT_LOG = ROOT / "local_chain.out.log"
ERR_LOG = ROOT / "local_chain.err.log"

LOCAL_RPC_URL = "http://127.0.0.1:8545"
LOCAL_CHAIN_ID = 31337
LOCAL_NETWORK_NAME = "Nomad Local Devnet"
LOCAL_NATIVE_SYMBOL = "ETH"
STARTING_BALANCE_WEI = str(1_000 * 10**18)


def load_env() -> dict[str, str]:
    raw = dotenv_values(ENV_PATH)
    return {key: str(value or "").strip() for key, value in raw.items()}


def valid_private_key(value: str) -> bool:
    try:
        if not value:
            return False
        Account.from_key(value)
        return True
    except Exception:
        return False


def rpc_chain_id() -> int | None:
    try:
        w3 = Web3(Web3.HTTPProvider(LOCAL_RPC_URL))
        return int(w3.eth.chain_id)
    except Exception:
        return None


def wait_for_rpc(timeout_seconds: int = 30) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if rpc_chain_id() == LOCAL_CHAIN_ID:
            return
        time.sleep(1)
    raise RuntimeError("Local Ganache RPC did not come up on time.")


def ensure_local_wallet() -> tuple[str, str]:
    env = load_env()
    private_key = env.get("AGENT_PRIVATE_KEY", "")
    if not valid_private_key(private_key):
        account = Account.create("nomad-local-dev")
        private_key = account.key.hex()
        address = account.address
    else:
        account = Account.from_key(private_key)
        address = account.address

    set_key(str(ENV_PATH), "NETWORK_NAME", LOCAL_NETWORK_NAME)
    set_key(str(ENV_PATH), "RPC_URL", LOCAL_RPC_URL)
    set_key(str(ENV_PATH), "EVM_CHAIN_ID", str(LOCAL_CHAIN_ID))
    set_key(str(ENV_PATH), "BASE_CHAIN_ID", str(LOCAL_CHAIN_ID))
    set_key(str(ENV_PATH), "NATIVE_SYMBOL", LOCAL_NATIVE_SYMBOL)
    set_key(str(ENV_PATH), "BLOCK_EXPLORER_TX_BASE", "")
    set_key(str(ENV_PATH), "AGENT_PRIVATE_KEY", private_key)
    set_key(str(ENV_PATH), "AGENT_ADDRESS", address)
    set_key(str(ENV_PATH), "CONTRACT_ADDRESS", "")
    set_key(str(ENV_PATH), "NOMAD_TOKEN_ADDRESS", "")
    set_key(str(ENV_PATH), "ARBIT_TOKEN_ADDRESS", "")
    set_key(str(ENV_PATH), "NOMAD_TOKEN_SYMBOL", get_project_token_symbol())
    set_key(str(ENV_PATH), "ARBIT_TOKEN_SYMBOL", get_project_token_symbol())
    set_key(str(ENV_PATH), "AUTO_RECORD_ARBITRAGE", "false")
    return private_key, address


def start_ganache(private_key: str) -> None:
    current_chain_id = rpc_chain_id()
    if current_chain_id == LOCAL_CHAIN_ID:
        return
    if current_chain_id is not None and current_chain_id != LOCAL_CHAIN_ID:
        raise RuntimeError(
            f"Port 8545 is already serving chain id {current_chain_id}, not the local devnet."
        )

    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise RuntimeError("npx is not available on this machine.")

    cmd = [
        npx,
        "ganache",
        "--server.host",
        "127.0.0.1",
        "--server.port",
        "8545",
        "--chain.chainId",
        str(LOCAL_CHAIN_ID),
        "--wallet.accounts",
        f"{private_key if private_key.startswith('0x') else '0x' + private_key},{STARTING_BALANCE_WEI}",
    ]

    with OUT_LOG.open("w", encoding="utf-8") as out, ERR_LOG.open(
        "w", encoding="utf-8"
    ) as err:
        if hasattr(subprocess, "DETACHED_PROCESS"):
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            flags = 0
        subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=out,
            stderr=err,
            creationflags=flags,
        )

    wait_for_rpc()


def main() -> None:
    private_key, address = ensure_local_wallet()
    start_ganache(private_key)

    w3 = Web3(Web3.HTTPProvider(LOCAL_RPC_URL))
    balance = w3.from_wei(w3.eth.get_balance(address), "ether")
    print("Nomad local devnet is ready.")
    print(f"RPC: {LOCAL_RPC_URL}")
    print(f"Chain ID: {LOCAL_CHAIN_ID}")
    print(f"Agent wallet: {address}")
    print(f"Balance: {balance} {LOCAL_NATIVE_SYMBOL}")


if __name__ == "__main__":
    main()
