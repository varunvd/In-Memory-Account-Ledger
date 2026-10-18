"""Every business constant in one place. NUMBERS.md explains each value.

The ledger takes a Policy instead of hardcoding numbers, so tests can run
event handling alone (policy=None) or with end-of-day processing.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .money import Money


@dataclass(frozen=True)
class Policy:
    # Flat overdraft fee, keyed by currency. A currency with no entry has
    # no fee; an overdrawn account in that currency is logged as an error.
    overdraft_fee: dict[str, Money]
    # Simple daily rate on positive closing balances. 0.04% = 0.0004.
    daily_interest_rate: Decimal
    # The day accrued interest is credited as one entry.
    capitalization_day: int


SCENARIO_POLICY = Policy(
    overdraft_fee={"AED": Money.of("25.00", "AED")},
    daily_interest_rate=Decimal("0.0004"),
    capitalization_day=6,
)
