"""Mock signer and RPC for tests and demos.

No real crypto, no real network. These exist so the broken-bot demo and
the test suite can exercise the full enforcement path without pulling in
eth_account, web3.py, or a live node.

A real production wiring would replace these with:

    from eth_account import Account
    from web3 import Web3

    signer = EthAccountSigner(Account.from_key(os.environ["PRIVATE_KEY"]))
    rpc = Web3RPC(Web3(Web3.HTTPProvider(os.environ["RPC_URL"])))

...and GatedWallet would not know the difference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


class MockSigner:
    """A signer that pretends to sign transactions.

    ``sign_tx`` returns deterministic bytes derived from the tx dict so tests
    can assert on the signed output without needing real ECDSA.
    """

    def __init__(self, address: str = "0xCafeBabe0000000000000000000000000000CAFE") -> None:
        self._address = address

    def address(self) -> str:
        return self._address

    def sign_tx(self, tx: dict) -> bytes:
        return f"signed:{sorted(tx.items())}".encode("utf-8")


class MockRPC:
    """An RPC that records broadcasts instead of sending them.

    Every ``send_raw_transaction`` call appends to ``sent`` and returns a
    synthetic tx hash. Nonce is auto-incremented per call.
    """

    def __init__(self, chain_id: int = 1) -> None:
        self._chain_id = chain_id
        self._nonce = 0
        self.sent: List[bytes] = []

    def chain_id(self) -> int:
        return self._chain_id

    def get_nonce(self, address: str) -> int:
        n = self._nonce
        self._nonce += 1
        return n

    def send_raw_transaction(self, raw: bytes) -> str:
        self.sent.append(raw)
        return f"0x{len(self.sent):064x}"
