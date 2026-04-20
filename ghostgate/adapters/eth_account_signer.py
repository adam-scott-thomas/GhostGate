"""EthAccountSigner -- adapts an eth_account LocalAccount to ghostgate's Signer protocol.

Usage:

    from eth_account import Account
    from ghostgate import GatedWallet, policies
    from ghostgate.adapters import EthAccountSigner, Web3RPC

    account = Account.from_key(os.environ["PRIVATE_KEY"])
    signer = EthAccountSigner(account)

    wallet = GatedWallet(signer=signer, rpc=..., policies=[...])

The private key never leaves the LocalAccount object ghostgate holds a
reference to. ghostgate never reads or copies key material -- it only
calls ``account.sign_transaction(tx)`` on approved intents.

**Security note**: Gate protects code paths that go through GatedWallet.
A malicious caller that imports eth_account directly and holds a reference
to the same LocalAccount can obviously still sign whatever they want. The
invariant ghostgate enforces is: no GatedWallet code path signs without
a passing policy chain. Your bot harness should never touch the raw
account, only the GatedWallet wrapper.
"""

from __future__ import annotations

from typing import Any


class EthAccountSigner:
    """Wraps an ``eth_account.signers.local.LocalAccount`` as a ghostgate Signer.

    Duck-typed -- any object exposing ``.address`` (str) and
    ``.sign_transaction(tx) -> SignedTransaction`` works. That keeps the
    class usable with eth_account, test fakes, and any future
    drop-in-compatible signer without a hard import on ``eth_account``.

    The only hard requirement is that ``sign_transaction`` returns an object
    with a ``raw_transaction`` attribute (eth_account >= 0.13). Older
    eth_account versions that use ``rawTransaction`` (camelCase) are also
    accepted for compatibility.
    """

    def __init__(self, account: Any) -> None:
        if not hasattr(account, "address"):
            raise TypeError(
                "EthAccountSigner requires an object with an .address attribute; "
                f"got {type(account).__name__}"
            )
        if not hasattr(account, "sign_transaction"):
            raise TypeError(
                "EthAccountSigner requires an object with .sign_transaction(tx); "
                f"got {type(account).__name__}. Install eth_account via "
                "`pip install 'ghostgate[web3]'`."
            )
        self._account = account

    def address(self) -> str:
        return str(self._account.address)

    def sign_tx(self, tx: dict) -> bytes:
        signed = self._account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None)
        if raw is None:
            # eth_account < 0.13 uses camelCase
            raw = getattr(signed, "rawTransaction", None)
        if raw is None:
            raise RuntimeError(
                "signed transaction has no raw_transaction/rawTransaction attribute; "
                f"got {type(signed).__name__}. Upgrade eth_account to >= 0.13."
            )
        return bytes(raw)
