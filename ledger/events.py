"""Incoming events. Each one is a frozen record of something that happened.

`day` is the booking day: when the event reached the ledger.
`value_date` is the day the money counts for. The two can differ (E7, E9).
"""

from __future__ import annotations

from dataclasses import dataclass

from .money import Money


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    day: int
    account_id: str


@dataclass(frozen=True, slots=True)
class Credit(Event):
    amount: Money
    value_date: int
    instalments: int = 1  # E10 arrives as three equal instalments


@dataclass(frozen=True, slots=True)
class Debit(Event):
    amount: Money
    value_date: int


@dataclass(frozen=True, slots=True)
class Authorization(Event):
    auth_id: str
    amount: Money
    value_date: int


@dataclass(frozen=True, slots=True)
class Settlement(Event):
    auth_id: str
    amount: Money
    value_date: int


@dataclass(frozen=True, slots=True)
class Reversal(Event):
    target_event_id: str
    value_date: int
