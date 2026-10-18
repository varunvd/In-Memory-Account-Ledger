"""Event replay on its own: policy=None turns off end-of-day fees and interest.

End-of-day behaviour is tested in test_end_of_day.py.
"""

import unittest

from ledger.events import Authorization, Credit, Debit, Reversal, Settlement
from ledger.records import AuthState, EntryKind, ErrorCode
from ledger.scenario import EVENTS, aed, bhd, build_ledger


def outcome_for(ledger, event_id):
    return next(o for o in ledger.outcomes if o.event.event_id == event_id)


class ScenarioReplayTests(unittest.TestCase):
    def setUp(self):
        self.ledger = build_ledger(policy=None)
        self.ledger.replay(EVENTS)
        self.acc1 = self.ledger.accounts["ACC-001"]
        self.acc2 = self.ledger.accounts["ACC-002"]

    def test_every_event_has_exactly_one_outcome(self):
        self.assertEqual([o.event.event_id for o in self.ledger.outcomes],
                         [e.event_id for e in EVENTS])

    def test_auth_a_approved_then_settled_releasing_15(self):
        self.assertEqual(outcome_for(self.ledger, "E3").auth_state, AuthState.ACTIVE)
        self.assertTrue(outcome_for(self.ledger, "E5").accepted)  # criterion 3
        latest = self.acc1.auth_state("Auth-A")
        self.assertEqual(latest.state, AuthState.SETTLED)
        self.assertIn("released AED 15.00", latest.note)

    def test_auth_z_settlement_rejected_and_nothing_posted(self):
        o = outcome_for(self.ledger, "E6")
        self.assertFalse(o.accepted)
        self.assertEqual(o.error.code, ErrorCode.UNKNOWN_AUTH)
        self.assertIsNone(self.acc1.find_entry("E6"))  # criterion 4: funds stay

    def test_auth_b_declined_because_e7_made_balance_negative(self):
        o = outcome_for(self.ledger, "E8")
        self.assertTrue(o.accepted)
        self.assertEqual(o.auth_state, AuthState.DECLINED)
        self.assertEqual(self.acc1.active_holds(), aed("0.00"))

    def test_e9_posts_an_opposite_entry_and_keeps_e7(self):
        e7 = self.acc1.find_entry("E7")
        rev = self.acc1.find_entry("E9:E7")
        self.assertIsNotNone(e7)  # append-only: E7 is still there
        self.assertEqual(rev.kind, EntryKind.REVERSAL)
        self.assertEqual(rev.signed_amount, aed("620.00"))
        self.assertEqual(rev.value_date, 2)

    def test_e10_flagged_late_and_split_exactly(self):
        o = outcome_for(self.ledger, "E10")
        self.assertTrue(o.late)
        amounts = [str(self.acc2.find_entry(i).amount.amount) for i in o.entry_ids]
        self.assertEqual(amounts, ["3.334", "3.333", "3.333"])
        self.assertEqual(self.acc2.ledger_balance(), bhd("10.000"))

    def test_only_late_event_is_e10(self):
        self.assertEqual([o.event.event_id for o in self.ledger.outcomes if o.late], ["E10"])

    def test_closing_balances_before_fees_and_interest(self):
        expected = {1: "250.00", 2: "250.00", 3: "650.00", 4: "465.00", 5: "465.00", 6: "465.00"}
        for day, amount in expected.items():
            self.assertEqual(self.acc1.closing_balance(day), aed(amount), f"Day {day}")

    def test_only_error_is_auth_z(self):
        self.assertEqual([(e.event_id, e.code) for e in self.ledger.errors],
                         [("E6", ErrorCode.UNKNOWN_AUTH)])


class CriterionOneTests(unittest.TestCase):
    def test_day_2_closes_at_minus_370_at_end_of_day_5(self):
        ledger = build_ledger(policy=None)
        ledger.replay([e for e in EVENTS if e.event_id in {"E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"}])
        self.assertEqual(ledger.accounts["ACC-001"].closing_balance(2), aed("-370.00"))


class ErrorPathTests(unittest.TestCase):
    def setUp(self):
        self.ledger = build_ledger(policy=None)
        self.ledger.apply(Credit("C1", 1, "ACC-001", aed("100.00"), 1))

    def code_of(self, event):
        o = self.ledger.apply(event)
        self.assertFalse(o.accepted)
        return o.error.code

    def test_duplicate_event_id(self):
        self.assertEqual(self.code_of(Credit("C1", 1, "ACC-001", aed("1.00"), 1)),
                         ErrorCode.DUPLICATE_EVENT)

    def test_unknown_account(self):
        self.assertEqual(self.code_of(Credit("X", 1, "ACC-999", aed("1.00"), 1)),
                         ErrorCode.UNKNOWN_ACCOUNT)

    def test_currency_mismatch(self):
        self.assertEqual(self.code_of(Credit("X", 1, "ACC-001", bhd("1.000"), 1)),
                         ErrorCode.CURRENCY_MISMATCH)

    def test_duplicate_auth(self):
        self.ledger.apply(Authorization("A1", 1, "ACC-001", "Auth-1", aed("10.00"), 1))
        self.assertEqual(self.code_of(Authorization("A2", 1, "ACC-001", "Auth-1", aed("10.00"), 1)),
                         ErrorCode.DUPLICATE_AUTH)

    def test_auth_exactly_to_zero_is_approved(self):
        o = self.ledger.apply(Authorization("A1", 1, "ACC-001", "Auth-1", aed("100.00"), 1))
        self.assertEqual(o.auth_state, AuthState.ACTIVE)

    def test_settle_declined_auth(self):
        self.ledger.apply(Authorization("A1", 1, "ACC-001", "Auth-1", aed("500.00"), 1))
        self.assertEqual(self.code_of(Settlement("S1", 2, "ACC-001", "Auth-1", aed("10.00"), 2)),
                         ErrorCode.AUTH_DECLINED)

    def test_settle_twice(self):
        self.ledger.apply(Authorization("A1", 1, "ACC-001", "Auth-1", aed("50.00"), 1))
        self.ledger.apply(Settlement("S1", 2, "ACC-001", "Auth-1", aed("50.00"), 2))
        self.assertEqual(self.code_of(Settlement("S2", 2, "ACC-001", "Auth-1", aed("1.00"), 2)),
                         ErrorCode.AUTH_ALREADY_SETTLED)

    def test_settle_above_hold(self):
        self.ledger.apply(Authorization("A1", 1, "ACC-001", "Auth-1", aed("50.00"), 1))
        self.assertEqual(self.code_of(Settlement("S1", 2, "ACC-001", "Auth-1", aed("50.01"), 2)),
                         ErrorCode.SETTLEMENT_EXCEEDS_HOLD)

    def test_reverse_unknown_event(self):
        self.assertEqual(self.code_of(Reversal("R1", 2, "ACC-001", "NOPE", 2)),
                         ErrorCode.UNKNOWN_ENTRY)

    def test_reverse_twice(self):
        self.ledger.apply(Reversal("R1", 2, "ACC-001", "C1", 1))
        self.assertEqual(self.code_of(Reversal("R2", 2, "ACC-001", "C1", 1)),
                         ErrorCode.ALREADY_REVERSED)

    def test_reverse_settlement_not_allowed(self):
        self.ledger.apply(Authorization("A1", 1, "ACC-001", "Auth-1", aed("50.00"), 1))
        self.ledger.apply(Settlement("S1", 2, "ACC-001", "Auth-1", aed("50.00"), 2))
        self.assertEqual(self.code_of(Reversal("R1", 2, "ACC-001", "S1", 2)),
                         ErrorCode.NOT_REVERSIBLE)

    def test_rejected_event_changes_nothing(self):
        before = self.ledger.accounts["ACC-001"].entries
        self.code_of(Debit("X", 1, "ACC-001", bhd("1.000"), 1))
        self.assertEqual(self.ledger.accounts["ACC-001"].entries, before)


if __name__ == "__main__":
    unittest.main()
