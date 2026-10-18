"""Account: an append-only store of entries and authorization records.

Balances are never stored. They are always computed from the entries,
so a backdated entry automatically changes every later day's balance.
"""

from __future__ import annotations

from .money import Money, total
from .records import AuthRecord, AuthState, Entry


class Account:
    def __init__(self, account_id: str, currency: str, opening_balance: Money) -> None:
        if opening_balance.currency != currency:
            raise ValueError("Opening balance currency must match the account currency")
        self.account_id = account_id
        self.currency = currency
        self.opening_balance = opening_balance
        self._entries: list[Entry] = []
        self._entry_ids: set[str] = set()
        self._auth_log: list[AuthRecord] = []

    # --- appending (the only way state changes) -----------------------

    def append_entry(self, entry: Entry) -> None:
        if entry.account_id != self.account_id:
            raise ValueError(f"Entry {entry.entry_id} belongs to {entry.account_id}")
        if entry.amount.currency != self.currency:
            raise ValueError(
                f"Entry {entry.entry_id} is {entry.amount.currency}, account is {self.currency}"
            )
        if entry.entry_id in self._entry_ids:
            raise ValueError(f"Duplicate entry id {entry.entry_id}")
        self._entries.append(entry)
        self._entry_ids.add(entry.entry_id)

    def append_auth(self, record: AuthRecord) -> None:
        if record.account_id != self.account_id:
            raise ValueError(f"Auth {record.auth_id} belongs to {record.account_id}")
        if record.hold_amount.currency != self.currency:
            raise ValueError(f"Auth {record.auth_id} currency does not match the account")
        self._auth_log.append(record)

    # --- read-only views ----------------------------------------------

    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(self._entries)

    @property
    def auth_log(self) -> tuple[AuthRecord, ...]:
        return tuple(self._auth_log)

    def find_entry(self, entry_id: str) -> Entry | None:
        for e in self._entries:
            if e.entry_id == entry_id:
                return e
        return None

    # --- balances -----------------------------------------------------

    def ledger_balance(self, as_of: int | None = None) -> Money:
        """Opening balance plus every entry with value_date <= as_of.

        With as_of=None, every entry posted so far counts.
        """
        included = [
            e.signed_amount for e in self._entries if as_of is None or e.value_date <= as_of
        ]
        return self.opening_balance + total(included, self.currency)

    def closing_balance(self, day: int) -> Money:
        """The closing ledger balance for a day, given everything known now."""
        return self.ledger_balance(as_of=day)

    # --- authorizations -----------------------------------------------

    def auth_state(self, auth_id: str) -> AuthRecord | None:
        """The latest record for an auth, or None if the ledger never saw it."""
        latest = None
        for r in self._auth_log:
            if r.auth_id == auth_id:
                latest = r
        return latest

    def auth_ids(self) -> list[str]:
        """Every auth id seen, in first-seen order."""
        seen: list[str] = []
        for r in self._auth_log:
            if r.auth_id not in seen:
                seen.append(r.auth_id)
        return seen

    def active_holds(self) -> Money:
        held = []
        for auth_id in self.auth_ids():
            latest = self.auth_state(auth_id)
            if latest is not None and latest.state is AuthState.ACTIVE:
                held.append(latest.hold_amount)
        return total(held, self.currency)

    def available_balance(self) -> Money:
        """Ledger balance (all posted entries) minus active holds."""
        return self.ledger_balance() - self.active_holds()
