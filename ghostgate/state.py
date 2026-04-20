"""Wallet state -- velocity tracking and the freeze latch.

No state = no intelligence. This module is the "memory" layer of section 1.3
of the spec: spend totals, send history, and the global kill switch.

Kept in-memory for v1. A persistent adapter (SQLite / Redis / Postgres) can
drop in behind the same public interface later without touching the wallet
or the policies.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Tuple

from ghostgate.types import TxIntent


@dataclass
class _SendRecord:
    intent: TxIntent
    tx_hash: str
    sent_at: float  # unix seconds


class WalletState:
    """Mutable state the policy rules read from and the wallet writes to."""

    def __init__(self) -> None:
        self._sends: List[_SendRecord] = []
        self._frozen_reason: str | None = None
        self._frozen_at: float | None = None

    # --- freeze latch (spec 1.7) ----------------------------------------

    @property
    def frozen(self) -> bool:
        return self._frozen_reason is not None

    @property
    def frozen_reason(self) -> str | None:
        return self._frozen_reason

    @property
    def frozen_at(self) -> float | None:
        return self._frozen_at

    def freeze(self, reason: str) -> None:
        """Lock the wallet. Idempotent -- re-freezing keeps the first reason."""
        if self._frozen_reason is None:
            self._frozen_reason = reason
            self._frozen_at = time.time()

    def unfreeze(self) -> None:
        """Release the lock. Caller is responsible for auditing the override."""
        self._frozen_reason = None
        self._frozen_at = None

    # --- velocity metrics (spec 1.3) ------------------------------------

    def record_send(self, intent: TxIntent, tx_hash: str) -> None:
        """Append a successful send to the history."""
        self._sends.append(_SendRecord(intent=intent, tx_hash=tx_hash, sent_at=time.time()))

    def sends_in_window(self, seconds: float) -> int:
        """How many sends in the last `seconds`?"""
        cutoff = time.time() - seconds
        return sum(1 for s in self._sends if s.sent_at >= cutoff)

    def spent_in_window(self, seconds: float) -> int:
        """Total wei successfully sent in the last `seconds`."""
        cutoff = time.time() - seconds
        return sum(s.intent.value_wei for s in self._sends if s.sent_at >= cutoff)

    def distinct_recipients_in_window(self, seconds: float) -> int:
        cutoff = time.time() - seconds
        return len({s.intent.to.lower() for s in self._sends if s.sent_at >= cutoff})

    @property
    def total_sends(self) -> int:
        return len(self._sends)

    @property
    def sends(self) -> Tuple[_SendRecord, ...]:
        """Read-only snapshot of send history."""
        return tuple(self._sends)
