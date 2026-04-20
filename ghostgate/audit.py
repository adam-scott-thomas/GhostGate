"""Audit log -- every intent, every decision, every reason.

Spec 1.6: "Logging without enforcement = useless." The reverse is also true:
enforcement without logging is unauditable and therefore untrustable.

This is a minimal in-memory append-only log. A pluggable ``AuditSink``
protocol lets you wire it to gate-compliance's SQLite store later without
changing the wallet code.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable

from ghostgate.types import Decision, TxIntent


@dataclass(frozen=True)
class AuditRecord:
    """One row of the audit log -- an attempted intent and its decision."""

    timestamp: float
    intent: TxIntent
    decision: Decision
    tx_hash: str = ""  # populated only on approve path after broadcast

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "intent": {
                "to": self.intent.to,
                "value_wei": self.intent.value_wei,
                "data_hex": self.intent.data.hex(),
                "gas_limit": self.intent.gas_limit,
                "tag": self.intent.tag,
            },
            "decision": {
                "outcome": self.decision.outcome,
                "reason": self.decision.reason,
                "rule_id": self.decision.rule_id,
            },
            "tx_hash": self.tx_hash,
        }


@runtime_checkable
class AuditSink(Protocol):
    """Any destination the wallet can push audit records to."""

    def record(self, entry: AuditRecord) -> None: ...


class AuditLog:
    """In-memory append-only audit log.

    Default sink used by GatedWallet when the caller doesn't supply one.
    Thread-unsafe by design -- v1 is single-process, single-wallet.
    """

    def __init__(self) -> None:
        self._entries: List[AuditRecord] = []

    def record(self, entry: AuditRecord) -> None:
        self._entries.append(entry)

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)

    def __getitem__(self, idx: int) -> AuditRecord:
        return self._entries[idx]

    def entries(self) -> tuple[AuditRecord, ...]:
        """Read-only snapshot."""
        return tuple(self._entries)

    def denied(self) -> tuple[AuditRecord, ...]:
        return tuple(e for e in self._entries if e.decision.outcome == "deny")

    def frozen(self) -> tuple[AuditRecord, ...]:
        return tuple(e for e in self._entries if e.decision.outcome == "freeze")

    def approved(self) -> tuple[AuditRecord, ...]:
        return tuple(e for e in self._entries if e.decision.outcome == "approve")
