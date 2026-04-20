"""Core data types and exceptions for ghostgate.

Everything that crosses a module boundary lives here so downstream code
(policies, audit sinks, adapters) can import types without pulling in the
whole wallet machinery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

Outcome = Literal["approve", "deny", "freeze"]


@dataclass(frozen=True)
class TxIntent:
    """An intent to send a transaction -- not yet signed, not yet broadcast.

    The wallet evaluates intents through the policy chain before any signing
    happens. This is the only object a policy rule ever sees.
    """

    to: str
    value_wei: int
    data: bytes = b""
    gas_limit: int = 21000
    # Free-form tag space for callers that want to annotate intents
    # (e.g. "uniswap_swap", "withdraw", "mint") -- policies can inspect.
    tag: str = ""


@dataclass(frozen=True)
class Decision:
    """A policy rule's verdict on a single intent.

    `outcome` is one of:
      - "approve" -- let the intent through to signing
      - "deny"    -- reject this intent, but the wallet stays usable
      - "freeze"  -- reject this intent AND lock the wallet against all
                    further sends until explicitly unfrozen

    `rule_id` identifies which policy produced the decision, so audit logs
    can attribute denials to specific rules.
    """

    outcome: Outcome
    reason: str = ""
    rule_id: str = ""


class GateError(Exception):
    """Base for all ghostgate enforcement exceptions."""


class TxDenied(GateError):
    """The policy chain denied this specific transaction.

    The wallet is still usable for subsequent intents -- only this one was
    blocked. Typical causes: value cap, allowlist miss, suspicious calldata.
    """

    def __init__(self, reason: str, rule_id: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.rule_id = rule_id


class WalletFrozen(GateError):
    """The wallet is locked. All subsequent sends will fail until unfrozen.

    Freeze is the kill switch. It is reached either by a policy returning
    outcome="freeze" or by explicit manual intervention via
    ``WalletState.freeze(reason)``.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# --- duck-typed adapters ------------------------------------------------

@runtime_checkable
class Signer(Protocol):
    """Anything that can turn a transaction dict into signed bytes.

    ghostgate never touches private key material directly. Implementations
    hold the key in whatever way the operator trusts (env var, KMS, HSM,
    hardware wallet) and expose only ``sign_tx``.
    """

    def address(self) -> str: ...

    def sign_tx(self, tx: dict) -> bytes: ...


@runtime_checkable
class RPC(Protocol):
    """Anything that can broadcast a signed transaction and read chain state.

    Kept deliberately narrow -- ghostgate only needs nonce, chain id, and
    broadcast. No balance queries, no log filters, no event subscriptions.
    """

    def chain_id(self) -> int: ...

    def get_nonce(self, address: str) -> int: ...

    def send_raw_transaction(self, raw: bytes) -> str: ...


Rule = "typing.Callable[[TxIntent, WalletState], Decision | None]"  # noqa: F821
