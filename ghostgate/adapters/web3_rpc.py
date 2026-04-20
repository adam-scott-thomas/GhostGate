"""Web3RPC -- adapts a web3.py Web3 instance to ghostgate's RPC protocol.

Usage:

    from web3 import Web3
    from ghostgate.adapters import Web3RPC

    w3 = Web3(Web3.HTTPProvider(os.environ["RPC_URL"]))
    rpc = Web3RPC(w3)

ghostgate's RPC protocol is deliberately narrow: chain_id, get_nonce,
send_raw_transaction. Nothing else. That keeps the adapter tiny and makes
it trivial to swap for a different backend (ethers-js via a subprocess,
custom JSON-RPC client, an archive node with rate-limiting, etc.).
"""

from __future__ import annotations

from typing import Any


class Web3RPC:
    """Wraps a ``web3.Web3`` instance as a ghostgate RPC.

    Duck-typed -- any object with a ``.eth`` attribute exposing
    ``chain_id``, ``get_transaction_count(address)``, and
    ``send_raw_transaction(raw)`` works. No hard import on web3.py.
    """

    def __init__(self, w3: Any) -> None:
        if not hasattr(w3, "eth"):
            raise TypeError(
                "Web3RPC requires an object with a .eth attribute; "
                f"got {type(w3).__name__}. Install web3 via "
                "`pip install 'ghostgate[web3]'`."
            )
        eth = w3.eth
        for method in ("get_transaction_count", "send_raw_transaction"):
            if not hasattr(eth, method):
                raise TypeError(
                    f"Web3RPC requires w3.eth.{method}; got {type(eth).__name__}"
                )
        self._w3 = w3

    def chain_id(self) -> int:
        # web3.py exposes chain_id as a property, not a method
        return int(self._w3.eth.chain_id)

    def get_nonce(self, address: str) -> int:
        return int(self._w3.eth.get_transaction_count(address))

    def send_raw_transaction(self, raw: bytes) -> str:
        tx_hash = self._w3.eth.send_raw_transaction(raw)
        # web3.py returns HexBytes; .hex() produces "0x..." string
        if hasattr(tx_hash, "hex"):
            return tx_hash.hex() if tx_hash.hex().startswith("0x") else f"0x{tx_hash.hex()}"
        return str(tx_hash)
