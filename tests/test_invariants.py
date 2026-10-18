"""Properties that must hold for the whole replay, not just specific numbers."""

import unittest

from ledger.money import total
from ledger.records import EntryKind
from ledger.report import render
from ledger.scenario import EVENTS, WINDOW_DAYS, build_ledger, run_scenario


class AppendOnlyTests(unittest.TestCase):
    def test_every_earlier_state_is_a_prefix_of_every_later_state(self):
        # Snapshot each account's entries and auth log after every event and
        # every day close. A mutation or deletion anywhere breaks the prefix.
        ledger = build_ledger()
        snapshots = []

        def snap():
            snapshots.append({a.account_id: (a.entries, a.auth_log) for a in ledger.accounts.values()})

        for event in EVENTS:
            ledger.apply(event)
            snap()
        ledger.close_through(6)
        snap()

        for earlier, later in zip(snapshots, snapshots[1:]):
            for account_id, (entries, auths) in earlier.items():
                later_entries, later_auths = later[account_id]
                self.assertEqual(later_entries[:len(entries)], entries)
                self.assertEqual(later_auths[:len(auths)], auths)

    def test_outcomes_and_errors_are_read_only_views(self):
        ledger = run_scenario()
        self.assertIsInstance(ledger.outcomes, tuple)
        self.assertIsInstance(ledger.errors, tuple)
        self.assertIsInstance(ledger.day_closes, tuple)


class DeterminismTests(unittest.TestCase):
    def test_two_replays_produce_identical_reports(self):
        self.assertEqual(render(run_scenario(), WINDOW_DAYS), render(run_scenario(), WINDOW_DAYS))


class FeeInvariantTests(unittest.TestCase):
    def test_at_most_one_live_fee_per_account_per_day(self):
        ledger = run_scenario()
        for account in ledger.accounts.values():
            refunded = {e.refers_to for e in account.entries if e.kind is EntryKind.FEE_REFUND}
            for day in WINDOW_DAYS:
                live = [e for e in account.entries if e.kind is EntryKind.OVERDRAFT_FEE
                        and e.value_date == day and e.entry_id not in refunded]
                self.assertLessEqual(len(live), 1, f"{account.account_id} Day {day}")

    def test_every_refund_points_at_a_fee_and_no_fee_is_refunded_twice(self):
        ledger = run_scenario()
        for account in ledger.accounts.values():
            fee_ids = {e.entry_id for e in account.entries if e.kind is EntryKind.OVERDRAFT_FEE}
            targets = [e.refers_to for e in account.entries if e.kind is EntryKind.FEE_REFUND]
            self.assertTrue(set(targets) <= fee_ids)
            self.assertEqual(len(targets), len(set(targets)))

    def test_no_live_fee_on_a_day_that_finally_closes_non_negative(self):
        ledger = run_scenario()
        acc = ledger.accounts["ACC-001"]
        refunded = {e.refers_to for e in acc.entries if e.kind is EntryKind.FEE_REFUND}
        live = [e for e in acc.entries if e.kind is EntryKind.OVERDRAFT_FEE and e.entry_id not in refunded]
        self.assertEqual(live, [])


class InterestInvariantTests(unittest.TestCase):
    def test_capitalized_interest_equals_sum_of_rounded_accruals_for_every_account(self):
        ledger = run_scenario()
        accruals = [a for c in ledger.day_closes for a in c.accruals]
        for account in ledger.accounts.values():
            mine = [a.accrued for a in accruals if a.account_id == account.account_id]
            posted = [e.amount for e in account.entries if e.kind is EntryKind.INTEREST]
            self.assertEqual(total(posted, account.currency), total(mine, account.currency))

    def test_accruals_only_on_positive_days(self):
        ledger = run_scenario()
        for c in ledger.day_closes:
            for a in c.accruals:
                self.assertTrue(a.base.is_positive)


if __name__ == "__main__":
    unittest.main()
