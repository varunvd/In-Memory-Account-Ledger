"""One test class per acceptance criterion from the brief.

ACCEPTED criteria are asserted as true.
REJECTED criteria are shown to be false: each test asserts what actually
happens and why the criterion's claim cannot hold. REJECTED.md has the reasoning.
"""

import unittest
from decimal import Decimal

from ledger.money import Money, round_amount, total
from ledger.records import AuthState, EntryKind, ErrorCode
from ledger.scenario import EVENTS, aed, bhd, build_ledger, run_scenario


def events_except(*excluded):
    return [e for e in EVENTS if e.event_id not in excluded]


def events_up_to(last_id):
    out = []
    for e in EVENTS:
        out.append(e)
        if e.event_id == last_id:
            return out
    raise ValueError(last_id)


def of_kind(account, kind):
    return [e for e in account.entries if e.kind is kind]


class C1_Day2ClosingIsMinus370_ACCEPTED(unittest.TestCase):
    """Day 2 closing, evaluated at end of Day 5 before any fee, is AED -370.00."""

    def test_day_2_is_minus_370_once_day_5_events_are_in_and_before_fees(self):
        ledger = build_ledger()
        ledger.replay(events_up_to("E8"))  # Day 5 events applied, Day 5 not yet closed
        acc = ledger.accounts["ACC-001"]
        self.assertEqual(of_kind(acc, EntryKind.OVERDRAFT_FEE), [])
        self.assertEqual(acc.closing_balance(2), aed("-370.00"))


class C2_E7CausesExactlyOneFee_REJECTED(unittest.TestCase):
    """Claim: E7 causes exactly one overdraft fee, on Day 2."""

    def test_e7_causes_three_fees(self):
        ledger = build_ledger()
        ledger.replay(events_up_to("E8"))
        ledger.close_through(5)
        fees = of_kind(ledger.accounts["ACC-001"], EntryKind.OVERDRAFT_FEE)
        # Day 3 survives only because E4 (+400) lands that day: -370 - 25 + 400 = 5.
        # Day 4: 5 - 185 = -180. Day 5: -180 - 25 = -205. Both negative.
        self.assertEqual([f.value_date for f in fees], [2, 4, 5])
        self.assertNotEqual(len(fees), 1)

    def test_without_e7_there_are_no_fees_at_all(self):
        ledger = build_ledger()
        ledger.replay(events_except("E7", "E9"), final_day=6)
        self.assertEqual(of_kind(ledger.accounts["ACC-001"], EntryKind.OVERDRAFT_FEE), [])


class C3_AuthASettlementAccepted_ACCEPTED(unittest.TestCase):
    """The Day 4 settlement of Auth-A must be accepted."""

    def test_e5_accepted_and_auth_a_settled(self):
        ledger = run_scenario()
        outcome = next(o for o in ledger.outcomes if o.event.event_id == "E5")
        self.assertTrue(outcome.accepted)
        acc = ledger.accounts["ACC-001"]
        self.assertEqual(acc.find_entry("E5").amount, aed("185.00"))
        self.assertEqual(acc.auth_state("Auth-A").state, AuthState.SETTLED)


class C4_UnknownAuthSettlementRejected_ACCEPTED(unittest.TestCase):
    """A settlement for an unknown auth ID is rejected and no funds leave."""

    def test_e6_rejected_and_balance_unchanged(self):
        ledger = build_ledger()
        ledger.replay(events_up_to("E5"))
        acc = ledger.accounts["ACC-001"]
        before = (acc.ledger_balance(), acc.available_balance(), len(acc.entries))
        outcome = ledger.apply(next(e for e in EVENTS if e.event_id == "E6"))
        self.assertFalse(outcome.accepted)
        self.assertEqual(outcome.error.code, ErrorCode.UNKNOWN_AUTH)
        self.assertEqual((acc.ledger_balance(), acc.available_balance(), len(acc.entries)), before)


class C5_AuthBHoldHitsAvailableNotLedger_ACCEPTED(unittest.TestCase):
    """If Auth-B is approved, its hold reduces available balance but not ledger."""

    def test_in_the_scenario_auth_b_is_declined_so_the_condition_never_fires(self):
        acc = run_scenario().accounts["ACC-001"]
        self.assertEqual(acc.auth_state("Auth-B").state, AuthState.DECLINED)

    def test_when_auth_b_is_approved_the_hold_behaves_as_claimed(self):
        # Without E7 the account has 465.00 on Day 5, so Auth-B is approved.
        ledger = build_ledger()
        ledger.replay([e for e in events_up_to("E8") if e.event_id != "E7"])
        acc = ledger.accounts["ACC-001"]
        self.assertEqual(acc.auth_state("Auth-B").state, AuthState.ACTIVE)
        self.assertEqual(acc.ledger_balance(), aed("465.00"))
        self.assertEqual(acc.available_balance(), aed("375.00"))


class C6_E9RestoresEverything_REJECTED(unittest.TestCase):
    """Claim: after E9, all balances and fees return to their pre-E7 values."""

    def setUp(self):
        self.actual = run_scenario().accounts["ACC-001"]
        never_e7 = build_ledger()
        never_e7.replay(events_except("E7", "E9"), final_day=6)
        self.counterfactual = never_e7.accounts["ACC-001"]

    def test_closing_ledger_balances_do_match(self):
        # This part of the claim holds, thanks to the fee refunds.
        for day in range(1, 7):
            self.assertEqual(self.actual.closing_balance(day),
                             self.counterfactual.closing_balance(day), f"Day {day}")

    def test_available_balance_does_not_match(self):
        # Auth-B was declined because of E7. E9 cannot re-approve it, so the
        # 90.00 hold that would exist without E7 is missing.
        self.assertEqual(self.actual.auth_state("Auth-B").state, AuthState.DECLINED)
        self.assertEqual(self.counterfactual.auth_state("Auth-B").state, AuthState.ACTIVE)
        self.assertNotEqual(self.actual.available_balance(), self.counterfactual.available_balance())

    def test_fee_records_do_not_disappear(self):
        # Append-only: the three fees stay; three refunds are added beside them.
        self.assertEqual(len(of_kind(self.actual, EntryKind.OVERDRAFT_FEE)), 3)
        self.assertEqual(len(of_kind(self.actual, EntryKind.FEE_REFUND)), 3)
        self.assertEqual(of_kind(self.counterfactual, EntryKind.OVERDRAFT_FEE), [])


class C7_EachInstalmentIs3_334_REJECTED(unittest.TestCase):
    """Claim: the three BHD instalments in E10 must each be BHD 3.334."""

    def test_three_times_3_334_overshoots_by_0_002(self):
        self.assertEqual(total([bhd("3.334")] * 3, "BHD"), bhd("10.002"))

    def test_ledger_posts_3_334_3_333_3_333(self):
        acc = run_scenario().accounts["ACC-002"]
        parts = [e.amount for e in acc.entries if e.event_id == "E10"]
        self.assertEqual(parts, [bhd("3.334"), bhd("3.333"), bhd("3.333")])
        self.assertEqual(total(parts, "BHD"), bhd("10.000"))


class C8_DiscardInterestRemainder_REJECTED(unittest.TestCase):
    """Claim: if rounded accruals don't sum to the capitalized total, discard the remainder."""

    def test_capitalized_total_is_defined_as_the_rounded_sum_so_nothing_is_left_over(self):
        ledger = run_scenario()
        for account in ledger.accounts.values():
            accruals = [a.accrued for c in ledger.day_closes for a in c.accruals
                        if a.account_id == account.account_id]
            interest = of_kind(account, EntryKind.INTEREST)
            self.assertEqual(len(interest), 1)
            self.assertEqual(interest[0].amount, total(accruals, account.currency))

    def test_discarding_would_break_the_exact_sum_rule(self):
        # Rounding the exact total gives 1.02; the rounded days sum to 1.03.
        # "Discarding" the 0.01 means paying 1.02 while the daily records say
        # 1.03, which is exactly what the non-negotiable rule forbids.
        raw = [Decimal("250.00"), Decimal("250.00"), Decimal("650.00"),
               Decimal("465.00"), Decimal("465.00"), Decimal("465.00")]
        exact = sum(b * Decimal("0.0004") for b in raw)
        rounded_days = sum(round_amount(b * Decimal("0.0004"), "AED") for b in raw)
        self.assertEqual(round_amount(exact, "AED"), Decimal("1.02"))
        self.assertEqual(rounded_days, Decimal("1.03"))


if __name__ == "__main__":
    unittest.main()
