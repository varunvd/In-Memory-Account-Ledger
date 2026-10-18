"""End-of-day processing: overdraft fees, fee refunds, interest.

At the close of day D, for every account and every day k from 1 to D:
- Work out k's closing balance *before k's own fee*, using everything
  known now. Backdated entries (E7, E9) change this after the fact.
- Negative and no live fee for k: post a fee, value-dated k.
- Not negative and a live fee for k: post a refund, value-dated k.
Days are walked in order, so a fee on day k counts toward day k+1.

On the capitalization day, after fees are settled, daily interest is
worked out from the corrected closing balances and credited as one entry.
The credit equals the sum of the *rounded* daily accruals, exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .account import Account
from .money import Money, total
from .policy import Policy
from .records import Direction, Entry, EntryKind, ErrorCode, ErrorRecord

FEE_KINDS = {EntryKind.OVERDRAFT_FEE, EntryKind.FEE_REFUND}


@dataclass(frozen=True, slots=True)
class InterestAccrual:
    account_id: str
    day: int
    base: Money  # closing ledger balance the interest is paid on
    raw: Decimal  # base x rate, unrounded
    accrued: Money  # raw rounded half up to the currency's precision


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    """An account's position as the ledger saw it when a day closed."""

    account_id: str
    closing: Money  # that day's closing ledger balance, after the close's own entries
    available: Money  # ledger balance minus active holds at that moment


@dataclass(frozen=True, slots=True)
class DayClose:
    day: int
    fee_entries: tuple[Entry, ...]  # fees and refunds posted at this close
    accruals: tuple[InterestAccrual, ...]
    interest_entries: tuple[Entry, ...]
    errors: tuple[ErrorRecord, ...]
    snapshots: tuple[BalanceSnapshot, ...] = ()
    # Closing balance of every day 1..day as seen at this close:
    # (account_id, day, closing). Comparing two closes shows restatements.
    day_balances: tuple[tuple[str, int, Money], ...] = ()


class DayCloser:
    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self._reported_fee_gaps: set[tuple[str, int]] = set()

    def close(self, accounts: dict[str, Account], day: int) -> DayClose:
        fee_entries: list[Entry] = []
        accruals: list[InterestAccrual] = []
        interest_entries: list[Entry] = []
        errors: list[ErrorRecord] = []
        for account in accounts.values():
            for k in range(1, day + 1):
                fee_entries.extend(self._reconcile_fee(account, k, day, errors))
            if day == self.policy.capitalization_day:
                acc_accruals, entry = self._capitalize(account, day)
                accruals.extend(acc_accruals)
                if entry is not None:
                    interest_entries.append(entry)
        snapshots = tuple(
            BalanceSnapshot(a.account_id, a.closing_balance(day), a.available_balance())
            for a in accounts.values()
        )
        day_balances = tuple(
            (a.account_id, k, a.closing_balance(k))
            for a in accounts.values() for k in range(1, day + 1)
        )
        return DayClose(day, tuple(fee_entries), tuple(accruals),
                        tuple(interest_entries), tuple(errors), snapshots, day_balances)

    # --- fees ---------------------------------------------------------

    @staticmethod
    def pre_fee_closing(account: Account, k: int) -> Money:
        """Day k's closing balance, leaving out day k's own fee and refunds.

        Earlier days' fees still count: they really did reduce the balance.
        """
        amounts = [
            e.signed_amount for e in account.entries
            if e.value_date <= k and not (e.value_date == k and e.kind in FEE_KINDS)
        ]
        return account.opening_balance + total(amounts, account.currency)

    @staticmethod
    def live_fees(account: Account, k: int) -> list[Entry]:
        """Fees value-dated k that have not been refunded."""
        refunded = {e.refers_to for e in account.entries if e.kind is EntryKind.FEE_REFUND}
        return [e for e in account.entries
                if e.kind is EntryKind.OVERDRAFT_FEE and e.value_date == k
                and e.entry_id not in refunded]

    def _reconcile_fee(self, account: Account, k: int, closing_day: int,
                       errors: list[ErrorRecord]) -> list[Entry]:
        negative = self.pre_fee_closing(account, k).is_negative
        live = self.live_fees(account, k)
        seq = sum(1 for e in account.entries if e.kind in FEE_KINDS) + 1

        if negative and not live:
            fee = self.policy.overdraft_fee.get(account.currency)
            if fee is None:
                if (account.account_id, k) not in self._reported_fee_gaps:
                    self._reported_fee_gaps.add((account.account_id, k))
                    errors.append(ErrorRecord(
                        f"EOD-D{closing_day}", closing_day, account.account_id,
                        ErrorCode.NO_FEE_FOR_CURRENCY,
                        f"Day {k} closed negative but no overdraft fee is set for "
                        f"{account.currency}; no fee charged",
                    ))
                return []
            entry = Entry(
                f"{account.account_id}:FEE:D{k}:{seq}", account.account_id,
                EntryKind.OVERDRAFT_FEE, Direction.DEBIT, fee,
                value_date=k, booking_day=closing_day, event_id=None,
                note=f"Day {k} closed negative",
            )
            account.append_entry(entry)
            return [entry]

        if not negative and live:
            posted = []
            for i, fee_entry in enumerate(live):
                entry = Entry(
                    f"{account.account_id}:REFUND:D{k}:{seq + i}", account.account_id,
                    EntryKind.FEE_REFUND, Direction.CREDIT, fee_entry.amount,
                    value_date=k, booking_day=closing_day, event_id=None,
                    refers_to=fee_entry.entry_id,
                    note=f"Day {k} no longer closes negative",
                )
                account.append_entry(entry)
                posted.append(entry)
            return posted

        return []

    # --- interest -----------------------------------------------------

    def _capitalize(self, account: Account, day: int) -> tuple[list[InterestAccrual], Entry | None]:
        if any(e.kind is EntryKind.INTEREST for e in account.entries):
            return [], None  # already capitalized
        rate = self.policy.daily_interest_rate
        accruals = []
        for k in range(1, day + 1):
            base = account.closing_balance(k)  # before the interest entry exists
            if not base.is_positive:
                continue
            raw = base.amount * rate
            accruals.append(InterestAccrual(account.account_id, k, base, raw,
                                            Money.rounded(raw, account.currency)))
        capitalized = total([a.accrued for a in accruals], account.currency)
        if not capitalized.is_positive:
            return accruals, None
        entry = Entry(
            f"{account.account_id}:INTEREST:D{day}", account.account_id,
            EntryKind.INTEREST, Direction.CREDIT, capitalized,
            value_date=day, booking_day=day, event_id=None,
            note=f"sum of {len(accruals)} rounded daily accruals",
        )
        account.append_entry(entry)
        return accruals, entry
