"""GatedWallet -- the entry point every bot routes through.

Evaluation order (the critical path):

    1. Kill switch check       -- if state.frozen, raise WalletFrozen
    2. Policy chain evaluation -- first non-approve decision wins
    3. Audit write             -- record the decision (approve or not)
    4. Enforcement             -- sign and broadcast ONLY on approve
    5. State update            -- record send into velocity tracker

No step 4 without step 2. No step 2 without step 1. This is the spec's
"enforcement layer" section 1.5 expressed as code, and it's why a broken
bot can't drain the wallet: the key is never reachable from any code path
that skipped the policy chain.
"""

from __future__ import annotations

import time
from typing import Callable, Iterable, List, Optional

from ghostgate.audit import AuditLog, AuditRecord, AuditSink
from ghostgate.state import WalletState
from ghostgate.types import (
    Decision,
    RPC,
    Signer,
    TxDenied,
    TxIntent,
    WalletFrozen,
)

Rule = Callable[[TxIntent, WalletState], Optional[Decision]]


class GatedWallet:
    """A wallet that refuses to do anything the policy chain hasn't approved."""

    def __init__(
        self,
        signer: Signer,
        rpc: RPC,
        policies: Iterable[Rule],
        state: WalletState | None = None,
        audit: AuditSink | None = None,
    ) -> None:
        self._signer = signer
        self._rpc = rpc
        self._policies: List[Rule] = list(policies)
        self._state = state if state is not None else WalletState()
        self._audit: AuditSink = audit if audit is not None else AuditLog()

    # --- public API -----------------------------------------------------

    @property
    def state(self) -> WalletState:
        return self._state

    @property
    def audit(self) -> AuditSink:
        return self._audit

    @property
    def address(self) -> str:
        return self._signer.address()

    def send(
        self,
        to: str,
        value_wei: int,
        data: bytes = b"",
        gas_limit: int = 21000,
        tag: str = "",
    ) -> str:
        """Attempt to send a transaction.

        Returns the broadcast tx hash on success. Raises ``TxDenied`` if the
        policy chain refused this specific intent, or ``WalletFrozen`` if the
        wallet is locked (either by a prior freeze or by this call triggering
        one).
        """
        intent = TxIntent(
            to=to,
            value_wei=value_wei,
            data=data,
            gas_limit=gas_limit,
            tag=tag,
        )

        # 1. kill switch -- must be first
        if self._state.frozen:
            reason = self._state.frozen_reason or "frozen"
            decision = Decision(
                outcome="deny",
                reason=f"wallet frozen: {reason}",
                rule_id="kill_switch",
            )
            self._audit.record(
                AuditRecord(timestamp=time.time(), intent=intent, decision=decision)
            )
            raise WalletFrozen(reason)

        # 2. policy chain
        decision = self._evaluate(intent)

        # 3. audit every decision, including approves
        self._audit.record(
            AuditRecord(timestamp=time.time(), intent=intent, decision=decision)
        )

        # handle freeze: lock the wallet AND raise
        if decision.outcome == "freeze":
            self._state.freeze(decision.reason)
            raise WalletFrozen(decision.reason)

        # handle deny: raise but leave wallet usable
        if decision.outcome == "deny":
            raise TxDenied(decision.reason, decision.rule_id)

        # 4. enforcement -- sign and broadcast
        tx = self._build_tx(intent)
        raw = self._signer.sign_tx(tx)
        tx_hash = self._rpc.send_raw_transaction(raw)

        # 5. state update
        self._state.record_send(intent, tx_hash)

        return tx_hash

    def freeze(self, reason: str) -> None:
        """Manual kill switch. Locks the wallet immediately."""
        self._state.freeze(reason)

    def unfreeze(self) -> None:
        """Manual override. Caller is responsible for the audit trail of *why*."""
        self._state.unfreeze()

    # --- internals ------------------------------------------------------

    def _evaluate(self, intent: TxIntent) -> Decision:
        """Run the policy chain. First non-approve verdict wins."""
        for rule in self._policies:
            verdict = rule(intent, self._state)
            if verdict is None:
                continue
            if verdict.outcome != "approve":
                return verdict
        return Decision(outcome="approve", reason="all rules passed", rule_id="")

    def _build_tx(self, intent: TxIntent) -> dict:
        """Assemble the unsigned tx dict handed to the signer.

        Deliberately minimal -- ghostgate is not a tx builder. Gas pricing,
        EIP-1559 fields, access lists, etc. are the caller's responsibility
        via a richer signer implementation.
        """
        return {
            "to": intent.to,
            "value": intent.value_wei,
            "data": intent.data,
            "gas": intent.gas_limit,
            "nonce": self._rpc.get_nonce(self._signer.address()),
            "chainId": self._rpc.chain_id(),
        }
