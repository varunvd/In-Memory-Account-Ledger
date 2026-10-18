"""The six-day scenario from the brief: two accounts and events E1 to E10.

Events are listed in the replay order the brief gives. E10 is booked on
Day 5 but comes after E9 (Day 6), so it replays late on purpose.
"""

from __future__ import annotations

from .engine import Ledger
from .events import Authorization, Credit, Debit, Event, Reversal, Settlement
from .money import Money

WINDOW_DAYS = range(1, 7)  # Day 1 .. Day 6


def aed(x: str) -> Money:
    return Money.of(x, "AED")


def bhd(x: str) -> Money:
    return Money.of(x, "BHD")


ACCOUNTS: list[tuple[str, str, Money]] = [
    ("ACC-001", "AED", aed("0.00")),
    ("ACC-002", "BHD", bhd("0.000")),
]

EVENTS: list[Event] = [
    Credit("E1", day=1, account_id="ACC-001", amount=aed("1200.00"), value_date=1),
    Debit("E2", day=1, account_id="ACC-001", amount=aed("950.00"), value_date=1),
    Authorization("E3", day=2, account_id="ACC-001", auth_id="Auth-A", amount=aed("200.00"), value_date=2),
    Credit("E4", day=3, account_id="ACC-001", amount=aed("400.00"), value_date=3),
    Settlement("E5", day=4, account_id="ACC-001", auth_id="Auth-A", amount=aed("185.00"), value_date=4),
    Settlement("E6", day=4, account_id="ACC-001", auth_id="Auth-Z", amount=aed("180.00"), value_date=4),
    Debit("E7", day=5, account_id="ACC-001", amount=aed("620.00"), value_date=2),
    Authorization("E8", day=5, account_id="ACC-001", auth_id="Auth-B", amount=aed("90.00"), value_date=5),
    Reversal("E9", day=6, account_id="ACC-001", target_event_id="E7", value_date=2),
    Credit("E10", day=5, account_id="ACC-002", amount=bhd("10.000"), value_date=5, instalments=3),
]


def build_ledger() -> Ledger:
    ledger = Ledger()
    for account_id, currency, opening in ACCOUNTS:
        ledger.open_account(account_id, currency, opening)
    return ledger
