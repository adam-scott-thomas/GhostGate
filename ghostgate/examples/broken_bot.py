"""The hero demo: a deliberately broken bot tries to drain itself.

Run it:

    python -m ghostgate.examples.broken_bot

What you should see:
    - Three successful Uniswap swaps.
    - A drain attempt to a known-scam address getting STOPPED and the wallet
      freezing.
    - Five panic retries, all blocked by the kill switch.
    - A full audit trail printed at the end.

This is what you want a potential customer to watch in a 30-second video.
"""

from __future__ import annotations

from ghostgate import (
    AuditLog,
    GatedWallet,
    MockRPC,
    MockSigner,
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


def build_wallet() -> GatedWallet:
    return GatedWallet(
        signer=MockSigner(address="0xB0t0000000000000000000000000000000000000"),
        rpc=MockRPC(chain_id=1),
        policies=[
            policies.contract_denylist({SCAM}),
            policies.contract_allowlist({UNISWAP, AAVE}),
            policies.max_value_per_tx(ONE_TENTH_ETH),
            policies.rate_limit(max_sends=10, window_seconds=60),
            policies.spend_cap(max_wei=5 * ONE_TENTH_ETH, window_seconds=3600),
        ],
        state=WalletState(),
        audit=AuditLog(),
    )


def main() -> None:
    wallet = build_wallet()
    print(f"\n=== bot wallet: {wallet.address} ===\n")

    # -------------------- PHASE 1: legit trading --------------------
    print("[phase 1] bot does its normal thing")
    for i in range(3):
        h = wallet.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH, tag="uniswap_swap")
        print(f"  swap #{i + 1} broadcast: {h}")

    # -------------------- PHASE 2: prompt injection --------------------
    print("\n[phase 2] bot ingests a poisoned tweet and tries to drain itself")
    try:
        wallet.send(SCAM, value_wei=ONE_ETH, tag="urgent_sweep")
    except WalletFrozen as e:
        print(f"  >>> BLOCKED: {e}")

    # -------------------- PHASE 3: panic retries --------------------
    print("\n[phase 3] bot enters retry loop (still under attacker control)")
    blocked = 0
    for _ in range(5):
        try:
            wallet.send(UNISWAP, value_wei=ONE_HUNDREDTH_ETH, tag="retry")
        except WalletFrozen:
            blocked += 1
    print(f"  {blocked}/5 retries blocked by kill switch")

    # -------------------- AUDIT DUMP --------------------
    print("\n[audit] every attempt, approved or not:")
    for i, entry in enumerate(wallet.audit.entries(), 1):  # type: ignore[attr-defined]
        dec = entry.decision
        to = entry.intent.to
        val = entry.intent.value_wei / ONE_ETH
        print(
            f"  {i:2d}. {dec.outcome:7s} "
            f"{val:8.4f} ETH -> {to[:10]}...  "
            f"[{dec.rule_id or '-'}] {dec.reason}"
        )

    print(
        f"\nwallet frozen: {wallet.state.frozen}  "
        f"(reason: {wallet.state.frozen_reason!r})"
    )
    print(f"successful sends: {wallet.state.total_sends}")
    print(
        f"denied + frozen attempts: "
        f"{len(wallet.audit.denied()) + len(wallet.audit.frozen())}"  # type: ignore[attr-defined]
    )


if __name__ == "__main__":
    main()
