"""THE ONE FAILING TEST. It fails on purpose, against this ledger's own design.

Run it alone:
    python3 -m unittest tests.test_known_failure -v

WHAT IT REVEALS
Overdraft fees are lazy: they are only posted when a day closes. An
authorization is checked against available balance *right now*. In the gap
between a backdated debit arriving and the next close, the ledger knows a
fee is certain but has not posted it, so available balance is overstated.
An authorization in that gap can be approved against money that is
already owed to the bank as a fee.

WHY THE SCENARIO DOESN'T HIT IT
On Day 5, E7 lands and Auth-B is checked straight after. Auth-B sees a
ledger balance of -155.00; the true position after the fees that Day 5's
close will post is -230.00. Auth-B is declined either way, so the bug is
invisible in the brief's stream. It only shows when the balance before
fees is just positive enough.

WHY IT ISN'T FIXED
A fix means working out "fees certain to be charged" inside the
authorization check: any already-closed day that now closes negative and
has no live fee. That duplicates the end-of-day fee logic in a second
place, and gets subtle when a later event in the same day could still
rescue the balance. The brief makes the authorization rule "ledger balance
minus active holds", with no mention of pending fees, so the current
behaviour follows the letter of the rule. The test records the gap
between the letter and what a bank would want.
"""

import unittest

from ledger.engine import Ledger
from ledger.events import Authorization, Credit, Debit
from ledger.policy import SCENARIO_POLICY
from ledger.records import AuthState
from ledger.scenario import aed


class AuthorizationIgnoresFeesAlreadyOwed(unittest.TestCase):
    def test_auth_should_be_declined_when_a_certain_fee_would_overdraw_it(self):
        ledger = Ledger(policy=SCENARIO_POLICY)
        acc = ledger.open_account("A", "AED", aed("0.00"))

        # Day 2: AED 100 arrives. Day 1 closes at 0.00, so no fee.
        ledger.apply(Credit("C1", day=2, account_id="A", amount=aed("100.00"), value_date=2))

        # Day 3: a debit of 50 arrives, backdated to Day 1. Day 1 is already
        # closed, and it now closes at -50.00. A 25.00 fee for Day 1 is now
        # certain. It will be posted at the Day 3 close, but not before.
        ledger.apply(Debit("D1", day=3, account_id="A", amount=aed("50.00"), value_date=1))

        # Still Day 3: authorization for 40. The ledger checks
        # 50.00 (ledger) - 0.00 (holds) - 40.00 = 10.00 >= 0 and approves.
        # The 25.00 fee it already knows about is not counted.
        outcome = ledger.apply(
            Authorization("A1", day=3, account_id="A", auth_id="Auth-1", amount=aed("40.00"), value_date=3)
        )

        # Day 3 closes: the Day 1 fee posts. Ledger becomes 25.00, the 40.00
        # hold is still active, so available is now -15.00. The approval
        # broke the "available stays at or above zero" rule within hours.
        ledger.close_through(3)
        self.assertEqual(acc.available_balance(), aed("-15.00"))  # passes: the damage is real

        # What a correct design would have done. THIS ASSERTION FAILS:
        # the ledger returns ACTIVE because it checked before the fee existed.
        self.assertEqual(outcome.auth_state, AuthState.DECLINED)


if __name__ == "__main__":
    unittest.main()
