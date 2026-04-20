"""ghostgate -- enforcement layer between bot intent and on-chain execution.

Gate doesn't decide what to do. It decides what is allowed to happen.
"""

from ghostgate.types import (
    Decision,
    GateError,
    TxDenied,
    TxIntent,
    WalletFrozen,
)
from ghostgate.state import WalletState
from ghostgate.audit import AuditLog, AuditRecord
from ghostgate.wallet import GatedWallet
from ghostgate import policies
from ghostgate.mock import MockRPC, MockSigner

__all__ = [
    "Decision",
    "GateError",
    "TxDenied",
    "TxIntent",
    "WalletFrozen",
    "WalletState",
    "AuditLog",
    "AuditRecord",
    "GatedWallet",
    "policies",
    "MockRPC",
    "MockSigner",
]

__version__ = "0.2.0"
