from pathlib import Path

from dotenv import set_key
from solcx import compile_standard, install_solc

from client import ArbiterWeb3
from settings import get_project_token_symbol


SOLC_VERSION = "0.8.20"
ENV_PATH = Path(__file__).resolve().parent / ".env"
CONTRACT_PATH = Path(__file__).resolve().parent / "NomadToken.sol"


def compile_contract() -> tuple[list[dict], str]:
    source = CONTRACT_PATH.read_text(encoding="utf-8")
    install_solc(SOLC_VERSION)
    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {"NomadToken.sol": {"content": source}},
            "settings": {
                "outputSelection": {"*": {"*": ["abi", "evm.bytecode"]}}
            },
        },
        solc_version=SOLC_VERSION,
    )

    contract_data = compiled["contracts"]["NomadToken.sol"]["NomadToken"]
    abi = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]
    return abi, bytecode


def deploy() -> None:
    client = ArbiterWeb3()
    abi, bytecode = compile_contract()
    contract = client.w3.eth.contract(abi=abi, bytecode=bytecode)

    token_name = "Nomad Token"
    token_symbol = get_project_token_symbol()
    initial_supply = 1_000_000 * 10**18
    recipient = client.address

    tx = contract.constructor(
        token_name,
        token_symbol,
        initial_supply,
        recipient,
    ).build_transaction(
        {
            "from": client.address,
            "nonce": client.w3.eth.get_transaction_count(client.address),
            "gas": 2_500_000,
            "gasPrice": client.w3.eth.gas_price,
            "chainId": client.chain_id,
        }
    )

    signed_tx = client.w3.eth.account.sign_transaction(tx, client.account.key)
    raw_tx = getattr(signed_tx, "raw_transaction", None) or getattr(
        signed_tx, "rawTransaction"
    )
    tx_hash = client.w3.eth.send_raw_transaction(raw_tx)
    receipt = client.w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = receipt.contractAddress

    set_key(str(ENV_PATH), "NOMAD_TOKEN_ADDRESS", contract_address)
    set_key(str(ENV_PATH), "ARBIT_TOKEN_ADDRESS", contract_address)

    print("Nomad token deployed.")
    print(f"Contract: {contract_address}")
    tx_hex = client.w3.to_hex(tx_hash)
    if client.explorer_tx_base:
        print(f"Tx: {client.explorer_tx_base}{tx_hex}")
    else:
        print(f"Tx hash: {tx_hex}")


if __name__ == "__main__":
    deploy()
