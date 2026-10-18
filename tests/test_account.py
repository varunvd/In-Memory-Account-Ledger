import unittest

from ledger import Account, AuthRecord, AuthState, Direction, Entry, EntryKind, Money


def aed(x: str) -> Money:
    return Money.of(x, "AED")


def entry(eid, direction, amount, value_date, booking_day=None, kind=None):
    return Entry(
        entry_id=eid,
        account_id="ACC-001",
        kind=kind or (EntryKind.CREDIT if direction is Direction.CREDIT else EntryKind.DEBIT),
        direction=direction,
        amount=aed(amount),
        value_date=value_date,
        booking_day=booking_day if booking_day is not None else value_date,
        event_id=eid,
    )


class AccountBalanceTests(unittest.TestCase):
    def setUp(self):
        self.acc = Account("ACC-001", "AED", aed("0.00"))
        self.acc.append_entry(entry("E1", Direction.CREDIT, "1200.00", 1))
        self.acc.append_entry(entry("E2", Direction.DEBIT, "950.00", 1))

    def test_day_1_closes_at_250(self):
        self.assertEqual(self.acc.closing_balance(1), aed("250.00"))

    def test_backdated_debit_restates_earlier_day(self):
        self.acc.append_entry(entry("E4", Direction.CREDIT, "400.00", 3))
        self.assertEqual(self.acc.closing_balance(2), aed("250.00"))
        # E7: booked Day 5, value-dated Day 2.
        self.acc.append_entry(entry("E7", Direction.DEBIT, "620.00", 2, booking_day=5))
        self.assertEqual(self.acc.closing_balance(2), aed("-370.00"))
        self.assertEqual(self.acc.closing_balance(3), aed("30.00"))

    def test_entries_are_frozen(self):
        with self.assertRaises(AttributeError):
            self.acc.entries[0].amount = aed("1.00")

    def test_entries_view_cannot_be_appended_to(self):
        self.assertIsInstance(self.acc.entries, tuple)

    def test_duplicate_entry_id_rejected(self):
        with self.assertRaises(ValueError):
            self.acc.append_entry(entry("E1", Direction.CREDIT, "1.00", 1))

    def test_wrong_currency_entry_rejected(self):
        bad = Entry("X1", "ACC-001", EntryKind.CREDIT, Direction.CREDIT,
                    Money.of("1.000", "BHD"), 1, 1, "X1")
        with self.assertRaises(ValueError):
            self.acc.append_entry(bad)

    def test_zero_or_negative_entry_amount_rejected(self):
        with self.assertRaises(ValueError):
            entry("X2", Direction.CREDIT, "0.00", 1)


class HoldTests(unittest.TestCase):
    def setUp(self):
        self.acc = Account("ACC-001", "AED", aed("0.00"))
        self.acc.append_entry(entry("E1", Direction.CREDIT, "250.00", 1))

    def test_active_hold_reduces_available_not_ledger(self):
        self.acc.append_auth(AuthRecord("Auth-A", "ACC-001", AuthState.ACTIVE, aed("200.00"), 2, "E3"))
        self.assertEqual(self.acc.ledger_balance(), aed("250.00"))
        self.assertEqual(self.acc.available_balance(), aed("50.00"))

    def test_settled_hold_no_longer_counts(self):
        self.acc.append_auth(AuthRecord("Auth-A", "ACC-001", AuthState.ACTIVE, aed("200.00"), 2, "E3"))
        self.acc.append_auth(AuthRecord("Auth-A", "ACC-001", AuthState.SETTLED, aed("200.00"), 4, "E5"))
        self.assertEqual(self.acc.active_holds(), aed("0.00"))
        self.assertEqual(self.acc.auth_state("Auth-A").state, AuthState.SETTLED)
        # The history is kept: both records are still there.
        self.assertEqual(len(self.acc.auth_log), 2)

    def test_declined_auth_places_no_hold(self):
        self.acc.append_auth(AuthRecord("Auth-B", "ACC-001", AuthState.DECLINED, aed("90.00"), 5, "E8"))
        self.assertEqual(self.acc.available_balance(), aed("250.00"))

    def test_unknown_auth_is_none(self):
        self.assertIsNone(self.acc.auth_state("Auth-Z"))


if __name__ == "__main__":
    unittest.main()
