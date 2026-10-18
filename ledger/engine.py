"""The ledger engine: applies events one at a time, in the order given.

Every event ends in exactly one outcome:
- accepted, with the entry ids or auth record it produced, or
- rejected, with an ErrorRecord. The replay never stops on a bad event.

A declined authorization is an accepted event with a DECLINED auth record.
It is a normal business outcome, not an error.

With a Policy, days are closed as the replay moves forward: an event for
day D first closes every open day before D. `replay(..., final_day=N)`
closes the remaining days through N at the end. A late event never
reopens a closed day; the next close re-checks all days and corrects fees.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .account import Account
from .eod import DayClose, DayCloser
from .events import Authorization, Credit, Debit, Event, Reversal, Settlement
from .money import Money
from .policy import Policy
from .records import AuthRecord, AuthState, Direction, Entry, EntryKind, ErrorCode, ErrorRecord

REVERSIBLE_KINDS = {EntryKind.CREDIT, EntryKind.DEBIT}


@dataclass(frozen=True, slots=True)
class Outcome:
    event: Event
    accepted: bool
    late: bool  # arrived after an event with a later booking day
    entry_ids: tuple[str, ...] = ()
    auth_state: AuthState | None = None
    error: ErrorRecord | None = None


class _Rejected(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Ledger:
    policy: Policy | None = None  # None: events only, no end-of-day processing
    accounts: dict[str, Account] = field(default_factory=dict)
    _outcomes: list[Outcome] = field(default_factory=list)
    _errors: list[ErrorRecord] = field(default_factory=list)
    _seen_event_ids: set[str] = field(default_factory=set)
    _latest_day: int = 0
    _last_closed_day: int = 0
    _day_closes: list[DayClose] = field(default_factory=list)
    _closer: DayCloser | None = None

    def __post_init__(self) -> None:
        if self.policy is not None:
            self._closer = DayCloser(self.policy)

    # --- setup --------------------------------------------------------

    def open_account(self, account_id: str, currency: str, opening_balance: Money) -> Account:
        if account_id in self.accounts:
            raise ValueError(f"Account {account_id} already exists")
        acc = Account(account_id, currency, opening_balance)
        self.accounts[account_id] = acc
        return acc

    # --- read-only views ----------------------------------------------

    @property
    def outcomes(self) -> tuple[Outcome, ...]:
        return tuple(self._outcomes)

    @property
    def errors(self) -> tuple[ErrorRecord, ...]:
        return tuple(self._errors)

    @property
    def day_closes(self) -> tuple[DayClose, ...]:
        return tuple(self._day_closes)

    # --- closing days -------------------------------------------------

    def close_through(self, day: int) -> None:
        """Close every open day up to and including `day`."""
        if self._closer is None:
            return
        for d in range(self._last_closed_day + 1, day + 1):
            result = self._closer.close(self.accounts, d)
            self._day_closes.append(result)
            self._errors.extend(result.errors)
            self._last_closed_day = d

    # --- applying events ----------------------------------------------

    def replay(self, events: list[Event], final_day: int | None = None) -> None:
        for event in events:
            self.apply(event)
        if final_day is not None:
            self.close_through(final_day)

    def apply(self, event: Event) -> Outcome:
        late = event.day < self._latest_day
        if event.day > self._latest_day:
            self.close_through(event.day - 1)
        self._latest_day = max(self._latest_day, event.day)
        try:
            if event.event_id in self._seen_event_ids:
                raise _Rejected(ErrorCode.DUPLICATE_EVENT, f"{event.event_id} was already applied")
            account = self._account_for(event)
            outcome = self._dispatch(event, account, late)
        except _Rejected as r:
            error = ErrorRecord(event.event_id, event.day, event.account_id, r.code, r.message)
            self._errors.append(error)
            outcome = Outcome(event, accepted=False, late=late, error=error)
        self._seen_event_ids.add(event.event_id)
        self._outcomes.append(outcome)
        return outcome

    def _account_for(self, event: Event) -> Account:
        account = self.accounts.get(event.account_id)
        if account is None:
            raise _Rejected(ErrorCode.UNKNOWN_ACCOUNT, f"No account {event.account_id}")
        amount = getattr(event, "amount", None)
        if amount is not None and amount.currency != account.currency:
            raise _Rejected(
                ErrorCode.CURRENCY_MISMATCH,
                f"Event is {amount.currency}, account {account.account_id} is {account.currency}",
            )
        return account

    def _dispatch(self, event: Event, account: Account, late: bool) -> Outcome:
        match event:
            case Credit():
                return self._credit(event, account, late)
            case Debit():
                return self._debit(event, account, late)
            case Authorization():
                return self._authorize(event, account, late)
            case Settlement():
                return self._settle(event, account, late)
            case Reversal():
                return self._reverse(event, account, late)
        raise TypeError(f"Unknown event type {type(event).__name__}")

    # --- handlers -----------------------------------------------------

    def _credit(self, e: Credit, account: Account, late: bool) -> Outcome:
        parts = e.amount.split(e.instalments)
        ids = []
        for i, part in enumerate(parts, start=1):
            entry_id = e.event_id if e.instalments == 1 else f"{e.event_id}-{i}"
            note = "" if e.instalments == 1 else f"instalment {i} of {e.instalments}"
            account.append_entry(
                Entry(entry_id, account.account_id, EntryKind.CREDIT, Direction.CREDIT,
                      part, e.value_date, e.day, e.event_id, note=note)
            )
            ids.append(entry_id)
        return Outcome(e, accepted=True, late=late, entry_ids=tuple(ids))

    def _debit(self, e: Debit, account: Account, late: bool) -> Outcome:
        # Booked debits are not checked against funds. They have already
        # happened; going negative is what the overdraft fee is for.
        account.append_entry(
            Entry(e.event_id, account.account_id, EntryKind.DEBIT, Direction.DEBIT,
                  e.amount, e.value_date, e.day, e.event_id)
        )
        return Outcome(e, accepted=True, late=late, entry_ids=(e.event_id,))

    def _authorize(self, e: Authorization, account: Account, late: bool) -> Outcome:
        if account.auth_state(e.auth_id) is not None:
            raise _Rejected(ErrorCode.DUPLICATE_AUTH, f"{e.auth_id} already exists")
        available_after = account.available_balance() - e.amount
        if available_after.is_negative:
            state = AuthState.DECLINED
            note = f"available after hold would be {available_after}"
        else:
            state = AuthState.ACTIVE
            note = f"available after hold {available_after}"
        account.append_auth(
            AuthRecord(e.auth_id, account.account_id, state, e.amount, e.day, e.event_id, note)
        )
        return Outcome(e, accepted=True, late=late, auth_state=state)

    def _settle(self, e: Settlement, account: Account, late: bool) -> Outcome:
        current = account.auth_state(e.auth_id)
        if current is None:
            raise _Rejected(
                ErrorCode.UNKNOWN_AUTH,
                f"{e.auth_id} has no authorization on {account.account_id}; nothing posted",
            )
        if current.state is AuthState.DECLINED:
            raise _Rejected(ErrorCode.AUTH_DECLINED, f"{e.auth_id} was declined; nothing posted")
        if current.state is AuthState.SETTLED:
            raise _Rejected(ErrorCode.AUTH_ALREADY_SETTLED, f"{e.auth_id} is already settled")
        if e.amount > current.hold_amount:
            raise _Rejected(
                ErrorCode.SETTLEMENT_EXCEEDS_HOLD,
                f"{e.auth_id} settles {e.amount} against a hold of {current.hold_amount}",
            )
        account.append_entry(
            Entry(e.event_id, account.account_id, EntryKind.SETTLEMENT, Direction.DEBIT,
                  e.amount, e.value_date, e.day, e.event_id, refers_to=e.auth_id)
        )
        released = current.hold_amount - e.amount
        account.append_auth(
            AuthRecord(e.auth_id, account.account_id, AuthState.SETTLED, current.hold_amount,
                       e.day, e.event_id, f"settled {e.amount}, released {released}")
        )
        return Outcome(e, accepted=True, late=late, entry_ids=(e.event_id,),
                       auth_state=AuthState.SETTLED)

    def _reverse(self, e: Reversal, account: Account, late: bool) -> Outcome:
        targets = [x for x in account.entries if x.event_id == e.target_event_id
                   and x.kind is not EntryKind.REVERSAL]
        if not targets:
            raise _Rejected(ErrorCode.UNKNOWN_ENTRY,
                            f"No entries from {e.target_event_id} on {account.account_id}")
        if any(t.kind not in REVERSIBLE_KINDS for t in targets):
            raise _Rejected(ErrorCode.NOT_REVERSIBLE,
                            f"{e.target_event_id} is a {targets[0].kind.value}, not reversible")
        already = {x.refers_to for x in account.entries if x.kind is EntryKind.REVERSAL}
        if any(t.entry_id in already for t in targets):
            raise _Rejected(ErrorCode.ALREADY_REVERSED, f"{e.target_event_id} is already reversed")
        ids = []
        for t in targets:
            opposite = Direction.CREDIT if t.direction is Direction.DEBIT else Direction.DEBIT
            entry_id = f"{e.event_id}:{t.entry_id}"
            account.append_entry(
                Entry(entry_id, account.account_id, EntryKind.REVERSAL, opposite,
                      t.amount, e.value_date, e.day, e.event_id, refers_to=t.entry_id,
                      note=f"reverses {t.entry_id}")
            )
            ids.append(entry_id)
        return Outcome(e, accepted=True, late=late, entry_ids=tuple(ids))
