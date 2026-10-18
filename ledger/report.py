"""Per-day text report for a replayed ledger.

For each day it prints:
- the events booked that day and what happened to each,
- closing ledger balance: final (corrected history) and as seen at that day's close,
- fee assessments posted at that day's close,
- interest accrued for that day (worked out at the capitalization close),
- authorization states at the end of that day,
- errors raised that day.
"""

from __future__ import annotations

from .engine import Ledger, Outcome
from .eod import DayClose
from .events import Authorization, Credit, Debit, Reversal, Settlement
from .records import AuthState, EntryKind

RULE = "=" * 78
THIN = "-" * 78

LEGEND = """\
How to read this report
  final      closing ledger balance for the day using every entry known at the
             end of the replay (all entries with value_date <= that day)
  at close   the same balance as the ledger saw it when that day closed;
             differs from final when a later event was backdated into the day
  available  ledger balance minus active holds, at that day's close
  Fees are assessed at a day's close and may be dated to an earlier day.
  Interest accruals are worked out at the Day 6 close on final balances."""


def _describe_event(o: Outcome) -> str:
    e = o.event
    match e:
        case Credit():
            what = f"CREDIT        {e.account_id} {e.amount}"
            if e.instalments > 1:
                what += f" in {e.instalments} instalments"
        case Debit():
            what = f"DEBIT         {e.account_id} {e.amount}"
        case Authorization():
            what = f"AUTHORIZATION {e.account_id} {e.auth_id} hold {e.amount}"
        case Settlement():
            what = f"SETTLEMENT    {e.account_id} {e.auth_id} for {e.amount}"
        case Reversal():
            what = f"REVERSAL      {e.account_id} reverses {e.target_event_id}"
        case _:
            what = type(e).__name__
    value_date = getattr(e, "value_date", None)
    if value_date is not None and value_date != e.day:
        what += f" (value Day {value_date})"
    return f"{e.event_id:<4} {what}"


def _describe_result(o: Outcome, ledger: Ledger) -> str:
    if not o.accepted:
        return f"REJECTED {o.error.code.value}"
    if o.auth_state is AuthState.ACTIVE:
        return "approved, hold placed"
    if o.auth_state is AuthState.DECLINED:
        return "DECLINED"
    if o.auth_state is AuthState.SETTLED:
        return "posted, hold released"
    if len(o.entry_ids) > 1:
        account = ledger.accounts[o.event.account_id]
        parts = " + ".join(str(account.find_entry(i).amount.amount) for i in o.entry_ids)
        return f"posted as {parts}"
    return "posted"


def _events_section(ledger: Ledger, day: int) -> list[str]:
    lines = ["Events booked"]
    booked = [o for o in ledger.outcomes if o.event.day == day]
    if not booked:
        lines.append("  none")
    for o in booked:
        lines.append(f"  {_describe_event(o)}  ->  {_describe_result(o, ledger)}")
        if o.late:
            lines.append("       LATE: replayed after an event from a later day; applied as dated")
    return lines


def _balance_section(ledger: Ledger, close: DayClose | None, day: int) -> list[str]:
    lines = ["Closing ledger balance"]
    snaps = {s.account_id: s for s in close.snapshots} if close else {}
    for account in ledger.accounts.values():
        final = account.closing_balance(day)
        line = f"  {account.account_id}  final {final}"
        snap = snaps.get(account.account_id)
        if snap is not None:
            line += f"  |  at close {snap.closing}  |  available {snap.available}"
            if snap.closing != final:
                line += "  (restated)"
        lines.append(line)
    return lines


def _restated_section(close: DayClose | None, previous: DayClose | None) -> list[str]:
    """Earlier days whose closing balance changed since the previous close."""
    lines = ["Earlier days restated at this close"]
    if close is None or previous is None:
        lines.append("  none")
        return lines
    before = {(acc, k): bal for acc, k, bal in previous.day_balances}
    changed = [(acc, k, before[(acc, k)], bal) for acc, k, bal in close.day_balances
               if (acc, k) in before and before[(acc, k)] != bal]
    if not changed:
        lines.append("  none")
    for acc, k, old, new in changed:
        lines.append(f"  {acc}  Day {k}: {old} -> {new}")
    return lines


def _fees_section(close: DayClose | None) -> list[str]:
    lines = ["Fee assessments at this close"]
    if close is None or not close.fee_entries:
        lines.append("  none")
        return lines
    for e in close.fee_entries:
        label = "FEE    " if e.kind is EntryKind.OVERDRAFT_FEE else "REFUND "
        lines.append(f"  {label} {e.account_id} {e.signed_amount}  for Day {e.value_date}  ({e.note})")
    return lines


def _interest_section(ledger: Ledger, day: int) -> list[str]:
    lines = ["Interest accrued for this day"]
    accruals = [a for c in ledger.day_closes for a in c.accruals if a.day == day]
    if not accruals:
        lines.append("  none")
    for a in accruals:
        lines.append(f"  {a.account_id}  {a.accrued}  on {a.base}  (exact {a.raw.normalize()})")
    interest = [e for c in ledger.day_closes if c.day == day for e in c.interest_entries]
    for e in interest:
        lines.append(f"  CAPITALIZED {e.account_id} {e.amount}  ({e.note})")
    return lines


def _auth_section(ledger: Ledger, day: int) -> list[str]:
    lines = ["Authorization states at end of day"]
    found = False
    for account in ledger.accounts.values():
        for auth_id in account.auth_ids():
            records = [r for r in account.auth_log if r.auth_id == auth_id and r.day <= day]
            if not records:
                continue
            found = True
            latest = records[-1]
            changed = "  (changed today)" if latest.day == day else ""
            lines.append(f"  {account.account_id}  {auth_id:<7} {latest.state.value:<9} "
                         f"hold {latest.hold_amount}  {latest.note}{changed}")
    if not found:
        lines.append("  none")
    return lines


def _errors_section(ledger: Ledger, day: int) -> list[str]:
    lines = ["Errors"]
    errors = [e for e in ledger.errors if e.day == day]
    if not errors:
        lines.append("  none")
    for e in errors:
        lines.append(f"  {e.event_id:<6} {e.account_id}  {e.code.value}: {e.message}")
    return lines


def _summary(ledger: Ledger, days: range) -> list[str]:
    last = days[-1]
    lines = [RULE, "SUMMARY", THIN]
    for account in ledger.accounts.values():
        fees = [e for e in account.entries if e.kind is EntryKind.OVERDRAFT_FEE]
        refunds = [e for e in account.entries if e.kind is EntryKind.FEE_REFUND]
        lines.append(f"  {account.account_id}  Day {last} closing {account.closing_balance(last)}  |  "
                     f"fees charged {len(fees)}, refunded {len(refunds)}  |  "
                     f"entries {len(account.entries)}")
    lines.append(f"  errors {len(ledger.errors)}")
    lines.append(RULE)
    return lines


def render(ledger: Ledger, days: range) -> str:
    closes = {c.day: c for c in ledger.day_closes}
    out = [LEGEND, ""]
    for day in days:
        close = closes.get(day)
        out += [RULE, f"DAY {day}", THIN]
        for section in (
            _events_section(ledger, day),
            _balance_section(ledger, close, day),
            _restated_section(close, closes.get(day - 1)),
            _fees_section(close),
            _interest_section(ledger, day),
            _auth_section(ledger, day),
            _errors_section(ledger, day),
        ):
            out += section + [""]
    out += _summary(ledger, days)
    return "\n".join(out)
