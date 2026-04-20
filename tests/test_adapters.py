"""Tests for the eth_account / web3.py adapters.

These tests use duck-typed fakes rather than installing the real libraries,
so they run everywhere including CI without pulling in the whole web3 stack.
The adapters are themselves duck-typed, so a fake that quacks like a
LocalAccount or a Web3 instance is a valid integration target.

A separate test at the bottom does the real-library round-trip if
eth_account and web3 happen to be installed on the machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from ghostgate import GatedWallet, WalletState, AuditLog, policies, TxDenied
from ghostgate.adapters import EthAccountSigner, Web3RPC


UNISWAP = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
ONE_HUNDREDTH_ETH = 10**16


# --- fakes --------------------------------------------------------------


@dataclass
class _FakeSignedTx:
    raw_transaction: bytes


class FakeLocalAccount:
    """Quacks like an eth_account LocalAccount."""

    def __init__(self, address: str = "0xFakeAccountFakeAccountFakeAccountFakeAcct") -> None:
        self.address = address
        self.signed: list[dict] = []

    def sign_transaction(self, tx: dict) -> _FakeSignedTx:
        self.signed.append(tx)
        # deterministic raw bytes derived from the tx for assertions
        return _FakeSignedTx(raw_transaction=f"raw:{tx['nonce']}:{tx['to']}".encode())


class FakeLegacyAccount:
    """Same as FakeLocalAccount but uses the pre-0.13 camelCase attribute."""

    def __init__(self) -> None:
        self.address = "0xLegacyLegacyLegacyLegacyLegacyLegacyLega"

    def sign_transaction(self, tx: dict):
        class _Signed:
            rawTransaction = b"raw:legacy"  # noqa: N815  -- matches real API
        return _Signed()


class _FakeHexBytes:
    def __init__(self, value: str) -> None:
        self._value = value if value.startswith("0x") else f"0x{value}"

    def hex(self) -> str:
        return self._value


class FakeEth:
    def __init__(self, chain_id: int = 1) -> None:
        self.chain_id = chain_id  # property on real web3, plain attr here
        self._nonce = 7
        self.broadcasts: list[bytes] = []

    def get_transaction_count(self, address: str) -> int:
        return self._nonce

    def send_raw_transaction(self, raw: bytes):
        self.broadcasts.append(raw)
        return _FakeHexBytes(f"{len(self.broadcasts):064x}")


class FakeWeb3:
    """Quacks like a web3.Web3 instance."""

    def __init__(self, chain_id: int = 1) -> None:
        self.eth = FakeEth(chain_id=chain_id)


# --- EthAccountSigner tests ---------------------------------------------


def test_eth_account_signer_exposes_address():
    account = FakeLocalAccount(address="0xCafe1111111111111111111111111111111111cafe")
    signer = EthAccountSigner(account)
    assert signer.address() == "0xCafe1111111111111111111111111111111111cafe"


def test_eth_account_signer_returns_raw_bytes():
    account = FakeLocalAccount()
    signer = EthAccountSigner(account)

    tx = {"to": UNISWAP, "value": ONE_HUNDREDTH_ETH, "nonce": 42, "chainId": 1}
    raw = signer.sign_tx(tx)

    assert isinstance(raw, bytes)
    assert b"raw:42:" in raw
    assert len(account.signed) == 1


def test_eth_account_signer_supports_legacy_camelcase_attribute():
    """eth_account < 0.13 uses rawTransaction (camelCase). Still accepted."""
    signer = EthAccountSigner(FakeLegacyAccount())
    raw = signer.sign_tx({"to": UNISWAP, "value": 1, "nonce": 0, "chainId": 1})
    assert raw == b"raw:legacy"


def test_eth_account_signer_rejects_non_account_object():
    with pytest.raises(TypeError, match="address"):
        EthAccountSigner(object())


def test_eth_account_signer_rejects_account_without_sign_transaction():
    class NoSign:
        address = "0x" + "0" * 40
    with pytest.raises(TypeError, match="sign_transaction"):
        EthAccountSigner(NoSign())


# --- Web3RPC tests ------------------------------------------------------


def test_web3_rpc_chain_id():
    rpc = Web3RPC(FakeWeb3(chain_id=8453))  # Base mainnet
    assert rpc.chain_id() == 8453


def test_web3_rpc_get_nonce_calls_eth_module():
    w3 = FakeWeb3()
    rpc = Web3RPC(w3)
    assert rpc.get_nonce("0xabc") == 7


def test_web3_rpc_send_raw_returns_hex_string():
    w3 = FakeWeb3()
    rpc = Web3RPC(w3)
    tx_hash = rpc.send_raw_transaction(b"whatever")
    assert tx_hash.startswith("0x")
    assert len(w3.eth.broadcasts) == 1
    assert w3.eth.broadcasts[0] == b"whatever"


def test_web3_rpc_rejects_non_web3_object():
    with pytest.raises(TypeError, match=r"\.eth"):
        Web3RPC(object())


def test_web3_rpc_rejects_eth_module_missing_methods():
    class BadEth:
        chain_id = 1
        # no get_transaction_count, no send_raw_transaction

    class BadWeb3:
        eth = BadEth()

    with pytest.raises(TypeError, match="get_transaction_count"):
        Web3RPC(BadWeb3())


# --- end-to-end integration with GatedWallet ----------------------------


def test_gated_wallet_round_trip_through_real_adapters():
    """Full path: GatedWallet → EthAccountSigner → FakeLocalAccount → Web3RPC → FakeWeb3."""
    account = FakeLocalAccount(address="0xBot1111111111111111111111111111111111bot1")
    w3 = FakeWeb3(chain_id=8453)

    wallet = GatedWallet(
        signer=EthAccountSigner(account),
        rpc=Web3RPC(w3),
        policies=[
            policies.contract_allowlist({UNISWAP}),
            policies.max_value_per_tx(max_wei=10**17),
        ],
        state=WalletState(),
        audit=AuditLog(),
    )

    tx_hash = wallet.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)

    assert tx_hash.startswith("0x")
    # The signer actually got called with a correctly-shaped tx dict
    assert len(account.signed) == 1
    signed_tx = account.signed[0]
    assert signed_tx["to"] == UNISWAP
    assert signed_tx["value"] == ONE_HUNDREDTH_ETH
    assert signed_tx["chainId"] == 8453
    assert signed_tx["nonce"] == 7  # from FakeEth

    # The RPC actually got the raw bytes
    assert len(w3.eth.broadcasts) == 1


def test_denied_tx_never_reaches_signer_or_rpc():
    """The core invariant -- no signing, no broadcast when policy denies."""
    account = FakeLocalAccount()
    w3 = FakeWeb3()

    wallet = GatedWallet(
        signer=EthAccountSigner(account),
        rpc=Web3RPC(w3),
        policies=[policies.max_value_per_tx(max_wei=10**15)],  # 0.001 ETH cap
    )

    with pytest.raises(TxDenied):
        wallet.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)  # way over cap

    assert account.signed == []
    assert w3.eth.broadcasts == []


# --- real-library integration (auto-skips if libs absent) ---------------


def test_against_real_eth_account_if_available():
    """If the real eth_account is installed, verify end-to-end compatibility."""
    eth_account = pytest.importorskip("eth_account")

    # Deterministic test key -- DO NOT USE IN PRODUCTION.
    # Standard anvil / hardhat test account #0.
    priv = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    real_account = eth_account.Account.from_key(priv)

    signer = EthAccountSigner(real_account)

    tx = {
        "to": UNISWAP,
        "value": 0,
        "gas": 21000,
        "gasPrice": 10**9,
        "nonce": 0,
        "chainId": 1,
        "data": b"",
    }
    raw = signer.sign_tx(tx)
    assert isinstance(raw, bytes)
    assert len(raw) > 0
    # Address should match the known anvil account #0
    assert signer.address().lower() == "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
