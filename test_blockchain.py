import pytest

from client import ArbiterWeb3


@pytest.mark.skipif(not ArbiterWeb3.is_configured(), reason="Blockchain client not configured")
def test_get_balance():
    client = ArbiterWeb3()
    balance = client.get_balance()
    assert float(balance) >= 0


@pytest.mark.skipif(not ArbiterWeb3.is_configured(), reason="Blockchain client not configured")
def test_build_record_transaction():
    client = ArbiterWeb3()
    tx = client.build_record_transaction(
        {"route": "BER-LIS", "price": 199.0, "provider": "test"}
    )
    assert tx["chainId"] > 0
    assert tx["value"] == 0
    assert tx["data"].startswith("0x")
    assert tx["gas"] >= 150000
