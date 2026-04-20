"""End-to-end tests for GatedWallet.

Each test builds a fresh wallet so state doesn't leak between cases. The
MockRPC/MockSigner pair means these tests run offline and deterministically.
"""

from __future__ import annotations

import pytest

from ghostgate import (
    AuditLog,
    GatedWallet,
    MockRPC,
    MockSigner,
    TxDenied,
    WalletFrozen,
    WalletState,
    policies,
)

UNISWAP = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
AAVE = "0x7d2768dE32b0b80b7a3454c06BdAc94A69DDc7A9"
SCAM = "0xDeadBeef00000000000000000000000000000000"

ONE_ETH = 10**18
ONE_TENTH_ETH = 10**17
ONE_HUNDREDTH_ETH = 10**16


def _fresh_wallet(rules):
    return GatedWallet(
        signer=MockSigner(),
        rpc=MockRPC(),
        policies=rules,
        state=WalletState(),
        audit=AuditLog(),
    )


def test_approve_happy_path():
    w = _fresh_wallet([policies.max_value_per_tx(ONE_ETH)])
    tx_hash = w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)
    assert tx_hash.startswith("0x")
    assert w.state.total_sends == 1
    assert len(w.audit.approved()) == 1  # type: ignore[attr-defined]
    assert len(w.audit.denied()) == 0  # type: ignore[attr-defined]


def test_deny_by_value_cap_leaves_wallet_usable():
    w = _fresh_wallet([policies.max_value_per_tx(ONE_TENTH_ETH)])

    # overshoot the cap -- gets denied
    with pytest.raises(TxDenied) as exc:
        w.send(UNISWAP, value_wei=ONE_ETH)
    assert exc.value.rule_id == "max_value_per_tx"
    assert "exceeds per-tx cap" in exc.value.reason

    # wallet still usable for a valid send right after
    tx_hash = w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)
    assert tx_hash.startswith("0x")
    assert w.state.total_sends == 1  # denied one was not recorded as a send


def test_allowlist_blocks_unknown_destinations():
    w = _fresh_wallet([policies.contract_allowlist({UNISWAP, AAVE})])

    # allowed destinations go through
    assert w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH).startswith("0x")
    assert w.send(AAVE, value_wei=ONE_HUNDREDTH_ETH).startswith("0x")

    # unknown destination is denied
    with pytest.raises(TxDenied) as exc:
        w.send(SCAM, value_wei=ONE_HUNDREDTH_ETH)
    assert exc.value.rule_id == "contract_allowlist"
    assert w.state.total_sends == 2  # scam send never landed


def test_allowlist_is_case_insensitive():
    w = _fresh_wallet([policies.contract_allowlist({UNISWAP.lower()})])
    # pass in upper-cased form -- should still match
    assert w.send(UNISWAP.upper(), value_wei=ONE_HUNDREDTH_ETH).startswith("0x")


def test_denylist_freezes_wallet():
    w = _fresh_wallet([policies.contract_denylist({SCAM})])

    # first touch of denylisted address freezes the whole wallet
    with pytest.raises(WalletFrozen):
        w.send(SCAM, value_wei=ONE_HUNDREDTH_ETH)

    assert w.state.frozen is True

    # subsequent sends to ANY address are now blocked
    with pytest.raises(WalletFrozen):
        w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)


def test_rate_limit_freezes_on_burst():
    # cap: 5 sends per 60 seconds
    w = _fresh_wallet([policies.rate_limit(max_sends=5, window_seconds=60)])

    for _ in range(5):
        w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)

    # 6th send trips the freeze
    with pytest.raises(WalletFrozen) as exc:
        w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)
    assert "rate limit" in exc.value.reason.lower()
    assert w.state.frozen is True


def test_spend_cap_accumulates_across_txs():
    # 0.1 ETH per 1-hour window
    w = _fresh_wallet([policies.spend_cap(max_wei=ONE_TENTH_ETH, window_seconds=3600)])

    # four sends of 0.02 ETH each = 0.08, all fine
    for _ in range(4):
        w.send(UNISWAP, value_wei=2 * ONE_HUNDREDTH_ETH)

    # next one would push us to 0.10 exactly -- allowed (not strictly greater)
    w.send(UNISWAP, value_wei=2 * ONE_HUNDREDTH_ETH)

    # now we're at the cap; any nonzero tx exceeds
    with pytest.raises(TxDenied) as exc:
        w.send(UNISWAP, value_wei=1)
    assert exc.value.rule_id == "spend_cap"
    # wallet NOT frozen -- spend cap is a deny, not a freeze
    assert w.state.frozen is False


def test_manual_freeze_and_unfreeze():
    w = _fresh_wallet([policies.max_value_per_tx(ONE_ETH)])

    # normal send works
    w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)

    # manual freeze
    w.freeze("operator panic button")
    assert w.state.frozen_reason == "operator panic button"

    with pytest.raises(WalletFrozen):
        w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)

    # manual unfreeze
    w.unfreeze()
    assert w.state.frozen is False

    # sends work again
    tx = w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)
    assert tx.startswith("0x")


def test_audit_log_records_every_attempt():
    w = _fresh_wallet(
        [
            policies.contract_allowlist({UNISWAP}),
            policies.max_value_per_tx(ONE_TENTH_ETH),
        ]
    )

    w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)  # approve

    with pytest.raises(TxDenied):
        w.send(SCAM, value_wei=ONE_HUNDREDTH_ETH)  # deny (allowlist)

    with pytest.raises(TxDenied):
        w.send(UNISWAP, value_wei=ONE_ETH)  # deny (value cap)

    entries = w.audit.entries()  # type: ignore[attr-defined]
    assert len(entries) == 3
    assert entries[0].decision.outcome == "approve"
    assert entries[1].decision.outcome == "deny"
    assert entries[1].decision.rule_id == "contract_allowlist"
    assert entries[2].decision.outcome == "deny"
    assert entries[2].decision.rule_id == "max_value_per_tx"

    # audit record serialization doesn't explode
    dumped = entries[0].to_dict()
    assert dumped["decision"]["outcome"] == "approve"
    assert dumped["intent"]["to"] == UNISWAP


def test_policy_chain_short_circuits_on_first_non_approve():
    """If rule #1 denies, rule #2 never runs -- verify by counting calls."""
    calls = {"second": 0}

    def first_denies(intent, state):
        from ghostgate.types import Decision
        return Decision("deny", "first rule rejects all", "first")

    def second_counts(intent, state):
        calls["second"] += 1
        return None

    w = _fresh_wallet([first_denies, second_counts])
    with pytest.raises(TxDenied):
        w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)

    assert calls["second"] == 0


def test_broken_bot_scenario_end_to_end():
    """The hero demo, expressed as a test.

    A bot does a few legit swaps, then gets prompt-injected into draining,
    then panics and retries in a loop. Gate catches each stage.
    """
    w = _fresh_wallet(
        [
            policies.contract_denylist({SCAM}),
            policies.contract_allowlist({UNISWAP, AAVE}),
            policies.max_value_per_tx(ONE_TENTH_ETH),
            policies.rate_limit(max_sends=5, window_seconds=60),
        ]
    )

    # Phase 1: legit activity
    for _ in range(3):
        w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH, tag="uniswap_swap")
    assert w.state.total_sends == 3

    # Phase 2: prompt injection tries to drain to scam address.
    # denylist is checked before allowlist, so this freezes rather than denies.
    with pytest.raises(WalletFrozen):
        w.send(SCAM, value_wei=ONE_ETH, tag="drain_attempt")

    assert w.state.frozen is True
    assert w.state.total_sends == 3  # drain never landed

    # Phase 3: panic retries -- all blocked by the freeze latch
    for _ in range(5):
        with pytest.raises(WalletFrozen):
            w.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH)

    # Audit trail has everything: 3 approves, 1 freeze, 5 frozen-denies
    entries = w.audit.entries()  # type: ignore[attr-defined]
    assert len(entries) == 3 + 1 + 5
    outcomes = [e.decision.outcome for e in entries]
    assert outcomes[:3] == ["approve", "approve", "approve"]
    assert outcomes[3] == "freeze"
    assert all(o == "deny" for o in outcomes[4:])
    assert all(e.decision.rule_id == "kill_switch" for e in entries[4:])
