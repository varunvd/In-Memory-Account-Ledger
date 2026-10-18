"""Step 3: end-of-day fees, fee refunds and interest."""

import unittest
from decimal import Decimal

from ledger.engine import Ledger
from ledger.events import Credit, Debit
from ledger.money import Money, round_amount
from ledger.policy import SCENARIO_POLICY
from ledger.records import AuthState, EntryKind, ErrorCode
from ledger.scenario import EVENTS, aed, bhd, build_ledger, run_scenario


def of_kind(account, kind):
    return [e for e in account.entries if e.kind is kind]


class ScenarioFeeTests(unittest.TestCase):
    def setUp(self):
        self.ledger = run_scenario()
        self.acc1 = self.ledger.accounts["ACC-001"]

    def test_e7_causes_three_fees_not_one(self):
        # Why criterion 2 is wrong: Day 2, Day 4 and Day 5 all close negative.
        fees = of_kind(self.acc1, EntryKind.OVERDRAFT_FEE)
        self.assertEqual([f.value_date for f in fees], [2, 4, 5])
        self.assertEqual({f.booking_day for f in fees}, {5})
        self.assertEqual({f.amount for f in fees}, {aed("25.00")})

    def test_e9_refunds_each_fee_on_its_own_value_date(self):
        fees = of_kind(self.acc1, EntryKind.OVERDRAFT_FEE)
        refunds = of_kind(self.acc1, EntryKind.FEE_REFUND)
        self.assertEqual([r.refers_to for r in refunds], [f.entry_id for f in fees])
        self.assertEqual([r.value_date for r in refunds], [2, 4, 5])
        self.assertEqual({r.booking_day for r in refunds}, {6})

    def test_fees_still_in_ledger_after_refund(self):
        # Append-only: the refund is new; the fee is not removed.
        self.assertEqual(len(of_kind(self.acc1, EntryKind.OVERDRAFT_FEE)), 3)

    def test_fees_posted_at_day_5_close_and_refunds_at_day_6_close(self):
        by_day = {c.day: c for c in self.ledger.day_closes}
        self.assertEqual([e.kind for e in by_day[5].fee_entries], [EntryKind.OVERDRAFT_FEE] * 3)
        self.assertEqual([e.kind for e in by_day[6].fee_entries], [EntryKind.FEE_REFUND] * 3)
        for day in (1, 2, 3, 4):
            self.assertEqual(by_day[day].fee_entries, ())

    def test_final_closing_balances(self):
        expected = {1: "250.00", 2: "250.00", 3: "650.00", 4: "465.00", 5: "465.00", 6: "466.03"}
        for day, amount in expected.items():
            self.assertEqual(self.acc1.closing_balance(day), aed(amount), f"Day {day}")

    def test_auth_b_stays_declined_after_e9(self):
        # Part of why criterion 6 is wrong: E9 cannot re-approve Auth-B.
        self.assertEqual(self.acc1.auth_state("Auth-B").state, AuthState.DECLINED)

    def test_only_error_is_auth_z(self):
        self.assertEqual([(e.event_id, e.code) for e in self.ledger.errors],
                         [("E6", ErrorCode.UNKNOWN_AUTH)])


class EndOfDay5StateTests(unittest.TestCase):
    """What the ledger looked like on Day 5, before E9 arrived."""

    def setUp(self):
        self.ledger = build_ledger()
        up_to_e8 = {"E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"}
        self.ledger.replay([e for e in EVENTS if e.event_id in up_to_e8])
        self.acc1 = self.ledger.accounts["ACC-001"]

    def test_day_2_is_minus_370_before_any_fee(self):
        # Criterion 1, with end-of-day processing switched on. Day 5 is
        # still open, so its close has not assessed any fee yet.
        self.assertEqual(of_kind(self.acc1, EntryKind.OVERDRAFT_FEE), [])
        self.assertEqual(self.acc1.closing_balance(2), aed("-370.00"))

    def test_after_day_5_close(self):
        self.ledger.close_through(5)
        self.assertEqual(self.acc1.closing_balance(2), aed("-395.00"))
        self.assertEqual(self.acc1.closing_balance(3), aed("5.00"))
        self.assertEqual(self.acc1.closing_balance(4), aed("-205.00"))
        self.assertEqual(self.acc1.closing_balance(5), aed("-230.00"))


class ScenarioInterestTests(unittest.TestCase):
    def setUp(self):
        self.ledger = run_scenario()
        close6 = next(c for c in self.ledger.day_closes if c.day == 6)
        self.accruals = {acc: [a for a in close6.accruals if a.account_id == acc]
                         for acc in ("ACC-001", "ACC-002")}
        self.interest = {e.account_id: e for e in close6.interest_entries}

    def test_acc_001_daily_accruals_on_corrected_history(self):
        got = [(a.day, str(a.accrued.amount)) for a in self.accruals["ACC-001"]]
        self.assertEqual(got, [(1, "0.10"), (2, "0.10"), (3, "0.26"),
                               (4, "0.19"), (5, "0.19"), (6, "0.19")])

    def test_acc_001_capitalizes_sum_of_rounded_accruals(self):
        self.assertEqual(self.interest["ACC-001"].amount, aed("1.03"))
        self.assertEqual(self.interest["ACC-001"].value_date, 6)

    def test_rounding_once_at_the_end_would_give_1_02(self):
        # Why criterion 8 is wrong: the rounded accruals sum to 1.03, the
        # exact sum rounds to 1.02. Discarding that cent breaks the rule
        # that the rounded accruals must sum to the capitalized total.
        exact = sum(a.raw for a in self.accruals["ACC-001"])
        self.assertEqual(exact, Decimal("1.018"))
        self.assertEqual(round_amount(exact, "AED"), Decimal("1.02"))
        rounded_sum = sum(a.accrued.amount for a in self.accruals["ACC-001"])
        self.assertEqual(rounded_sum, self.interest["ACC-001"].amount.amount)

    def test_acc_002_earns_on_day_5_and_6(self):
        got = [(a.day, str(a.accrued.amount)) for a in self.accruals["ACC-002"]]
        self.assertEqual(got, [(5, "0.004"), (6, "0.004")])
        self.assertEqual(self.interest["ACC-002"].amount, bhd("0.008"))
        self.assertEqual(self.ledger.accounts["ACC-002"].closing_balance(6), bhd("10.008"))

    def test_day_6_interest_paid_on_balance_before_the_credit(self):
        day6 = self.accruals["ACC-001"][-1]
        self.assertEqual(day6.base, aed("465.00"))


class FeeRuleEdgeTests(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger(policy=SCENARIO_POLICY)
        self.acc = self.ledger.open_account("A", "AED", aed("0.00"))

    def test_fee_cannot_justify_itself(self):
        # Day 1 closes at -10 and is charged. A backdated +20 makes it +10.
        # With the fee it would be -15, but the fee must not count toward
        # its own trigger, so it is refunded.
        self.ledger.apply(Debit("D1", 1, "A", aed("10.00"), 1))
        self.ledger.close_through(1)
        self.ledger.apply(Credit("C1", 2, "A", aed("20.00"), 1))
        self.ledger.close_through(2)
        self.assertEqual(len(of_kind(self.acc, EntryKind.FEE_REFUND)), 1)
        self.assertEqual(self.acc.closing_balance(1), aed("10.00"))

    def test_one_fee_per_day_across_repeated_closes(self):
        self.ledger.apply(Debit("D1", 1, "A", aed("10.00"), 1))
        self.ledger.close_through(3)
        fees = of_kind(self.acc, EntryKind.OVERDRAFT_FEE)
        self.assertEqual([f.value_date for f in fees], [1, 2, 3])

    def test_zero_balance_is_not_overdrawn(self):
        self.ledger.apply(Credit("C1", 1, "A", aed("10.00"), 1))
        self.ledger.apply(Debit("D1", 1, "A", aed("10.00"), 1))
        self.ledger.close_through(1)
        self.assertEqual(of_kind(self.acc, EntryKind.OVERDRAFT_FEE), [])

    def test_overdrawn_bhd_account_logs_one_error_and_no_fee(self):
        b = self.ledger.open_account("B", "BHD", bhd("0.000"))
        self.ledger.apply(Debit("D1", 1, "B", bhd("1.000"), 1))
        self.ledger.close_through(3)
        self.assertEqual(of_kind(b, EntryKind.OVERDRAFT_FEE), [])
        gaps = [e for e in self.ledger.errors if e.code is ErrorCode.NO_FEE_FOR_CURRENCY]
        self.assertEqual([(e.account_id, e.day) for e in gaps], [("B", 1), ("B", 2), ("B", 3)])

    def test_no_interest_on_negative_or_zero_days(self):
        self.ledger.apply(Debit("D1", 1, "A", aed("10.00"), 1))
        self.ledger.close_through(6)
        self.assertEqual(of_kind(self.acc, EntryKind.INTEREST), [])


if __name__ == "__main__":
    unittest.main()
