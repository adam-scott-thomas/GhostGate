"""Production adapters -- real eth_account / web3.py integration.

These are opt-in. The core package has zero runtime dependencies and works
fine with MockSigner / MockRPC out of the box. Install the adapters via:

    pip install 'ghostgate[web3]'

...and then:

    from ghostgate.adapters import EthAccountSigner, Web3RPC

Imports here are lazy so that importing ``ghostgate.adapters`` does not
crash on a machine that has only the core package installed. Each adapter
raises a clear ImportError at construction time if its backing library is
missing.
"""

from __future__ import annotations

__all__ = ["EthAccountSigner", "Web3RPC"]


def __getattr__(name: str):
    if name == "EthAccountSigner":
        from ghostgate.adapters.eth_account_signer import EthAccountSigner
        return EthAccountSigner
    if name == "Web3RPC":
        from ghostgate.adapters.web3_rpc import Web3RPC
        return Web3RPC
    raise AttributeError(f"module 'ghostgate.adapters' has no attribute {name!r}")
