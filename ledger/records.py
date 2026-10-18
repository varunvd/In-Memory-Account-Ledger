"""Immutable records the ledger appends. Nothing here is ever edited or deleted.

- Entry: one posted movement of money on an account.
- AuthRecord: one step in an authorization's life (approved, declined, settled).
- ErrorRecord: an event the ledger refused, with a reason code.

Days are plain integers: Day 1 .. Day 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .money import Money


class Direction(Enum):
    CREDIT = "CREDIT"  # money into the customer's account
    DEBIT = "DEBIT"  # money out of the customer's account


class EntryKind(Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    SETTLEMENT = "SETTLEMENT"
    REVERSAL = "REVERSAL"
    OVERDRAFT_FEE = "OVERDRAFT_FEE"
    FEE_REFUND = "FEE_REFUND"
    INTEREST = "INTEREST"


@dataclass(frozen=True, slots=True)
class Entry:
    entry_id: str
    account_id: str
    kind: EntryKind
    direction: Direction
    amount: Money  # always positive; direction carries the sign
    value_date: int  # the day the money counts for
    booking_day: int  # the day the ledger learned about it
    event_id: str | None  # source event, None for system entries like fees
    refers_to: str | None = None  # entry or auth this one relates to
    note: str = ""

    def __post_init__(self) -> None:
        if not self.amount.is_positive:
            raise ValueError(f"Entry amount must be positive, got {self.amount}")

    @property
    def signed_amount(self) -> Money:
        return self.amount if self.direction is Direction.CREDIT else -self.amount


class AuthState(Enum):
    ACTIVE = "ACTIVE"  # approved, hold in place
    DECLINED = "DECLINED"  # refused, no hold ever placed
    SETTLED = "SETTLED"  # settlement posted, hold released


@dataclass(frozen=True, slots=True)
class AuthRecord:
    auth_id: str
    account_id: str
    state: AuthState
    hold_amount: Money  # the amount originally requested
    day: int
    event_id: str
    note: str = ""


class ErrorCode(Enum):
    UNKNOWN_ACCOUNT = "UNKNOWN_ACCOUNT"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    INSUFFICIENT_AVAILABLE = "INSUFFICIENT_AVAILABLE"
    DUPLICATE_AUTH = "DUPLICATE_AUTH"
    UNKNOWN_AUTH = "UNKNOWN_AUTH"
    AUTH_DECLINED = "AUTH_DECLINED"
    AUTH_ALREADY_SETTLED = "AUTH_ALREADY_SETTLED"
    SETTLEMENT_EXCEEDS_HOLD = "SETTLEMENT_EXCEEDS_HOLD"
    UNKNOWN_ENTRY = "UNKNOWN_ENTRY"
    NOT_REVERSIBLE = "NOT_REVERSIBLE"
    ALREADY_REVERSED = "ALREADY_REVERSED"
    DUPLICATE_EVENT = "DUPLICATE_EVENT"


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    event_id: str
    day: int
    account_id: str
    code: ErrorCode
    message: str
