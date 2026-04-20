"""Built-in policy rules.

Each factory returns a callable ``(intent, state) -> Decision | None``.
Returning ``None`` means "this rule has no opinion, keep evaluating" --
only a non-None, non-approve Decision halts the chain.

All the policies here are deterministic and side-effect-free. No network
calls, no randomness, no wall-clock dependency beyond what ``WalletState``
already exposes.
"""

from __future__ import annotations

from typing import Iterable, Set

from ghostgate.state import WalletState
from ghostgate.types import Decision, TxIntent


def max_value_per_tx(max_wei: int) -> "typing.Callable":  # noqa: F821
    """Deny any single transaction above ``max_wei`` in value."""

    def rule(intent: TxIntent, state: WalletState) -> Decision | None:
        if intent.value_wei > max_wei:
            return Decision(
                outcome="deny",
                reason=f"value {intent.value_wei} wei exceeds per-tx cap {max_wei} wei",
                rule_id="max_value_per_tx",
            )
        return None

    return rule


def contract_allowlist(allowed: Iterable[str]) -> "typing.Callable":  # noqa: F821
    """Deny any transaction whose ``to`` is not in the allowlist.

    Addresses are compared case-insensitively (EIP-55 checksum casing is
    irrelevant at the policy layer).
    """
    allowed_set: Set[str] = {a.lower() for a in allowed}

    def rule(intent: TxIntent, state: WalletState) -> Decision | None:
        if intent.to.lower() not in allowed_set:
            return Decision(
                outcome="deny",
                reason=f"destination {intent.to} not in allowlist",
                rule_id="contract_allowlist",
            )
        return None

    return rule


def contract_denylist(blocked: Iterable[str]) -> "typing.Callable":  # noqa: F821
    """Freeze the wallet if the bot ever tries to touch a known-bad address.

    Deny-list hits are treated as freeze events, not plain denials, because
    the fact that the bot even attempted the call is itself evidence of
    compromise or prompt injection.
    """
    blocked_set: Set[str] = {a.lower() for a in blocked}

    def rule(intent: TxIntent, state: WalletState) -> Decision | None:
        if intent.to.lower() in blocked_set:
            return Decision(
                outcome="freeze",
                reason=f"attempted send to denylisted address {intent.to}",
                rule_id="contract_denylist",
            )
        return None

    return rule


def rate_limit(max_sends: int, window_seconds: float) -> "typing.Callable":  # noqa: F821
    """Freeze on more than ``max_sends`` successful sends per ``window_seconds``.

    Freeze (not deny) because sustained rapid-fire is the signature of a
    runaway loop, and the safe default is to stop everything until a human
    looks at it.
    """

    def rule(intent: TxIntent, state: WalletState) -> Decision | None:
        count = state.sends_in_window(window_seconds)
        if count >= max_sends:
            return Decision(
                outcome="freeze",
                reason=(
                    f"rate limit exceeded: {count} sends in last "
                    f"{window_seconds:.0f}s (cap {max_sends})"
                ),
                rule_id="rate_limit",
            )
        return None

    return rule


def spend_cap(max_wei: int, window_seconds: float) -> "typing.Callable":  # noqa: F821
    """Deny if this tx would push total spend over ``max_wei`` in the window.

    Uses a rolling window. Unlike ``rate_limit``, this is a deny (not freeze)
    because hitting the spend cap is a normal business condition, not an
    anomaly -- the bot should back off and try again later.
    """

    def rule(intent: TxIntent, state: WalletState) -> Decision | None:
        already_spent = state.spent_in_window(window_seconds)
        if already_spent + intent.value_wei > max_wei:
            return Decision(
                outcome="deny",
                reason=(
                    f"spend cap hit: {already_spent} + {intent.value_wei} "
                    f"> {max_wei} wei in last {window_seconds:.0f}s"
                ),
                rule_id="spend_cap",
            )
        return None

    return rule


def require_nonempty_data_for_contract_calls() -> "typing.Callable":  # noqa: F821
    """Placeholder for the "calldata sanity" rule -- currently advisory only.

    Right now it always returns None. The shape is here so tests can cover
    the "policies with richer context" path without blocking on a real ABI
    decoder. v0.3 will add calldata pattern matching (approve(max_uint256),
    setApprovalForAll, etc.) behind this same factory.
    """

    def rule(intent: TxIntent, state: WalletState) -> Decision | None:
        return None

    return rule
