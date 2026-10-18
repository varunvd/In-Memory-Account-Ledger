# Worklog

Times are local (UTC+04) and taken from the system clock when each entry was written.
The design discussion before the first timestamp was not timed, so it is logged without times rather than with invented ones.

## 2026-10-18

### Before 12:06 (untimed): design discussion
- Read the brief and the 8 acceptance criteria.
- First pass: criteria 2, 6, 7, 8 look wrong. Criteria 1, 3, 5 look right. Criterion 4 (reject unknown-auth settlement) is a policy choice.
- Criterion 4: considered three options: reject, force-post, or park in an exceptions book. Chose reject. Reason: nothing in the rules says unmatched settlements must be honoured. The real-world force-post caveat goes in AMBIGUITIES.md.
- Partial settlement (Auth-A 185 vs 200 hold): release the whole hold, post 185.
- Backdated E7: re-evaluate every affected day. It causes fees on Day 2, 4 and 5, not one.
- E9 reversal: refund the three fees with new entries, dated to the same value date as each fee.
- Interest: computed at end of Day 6 from the corrected history. AED 1.03, not 1.02.
- Accepted defaults for the small items: BHD split 3.334/3.333/3.333, ROUND_HALF_UP, fee dated to the negative day, no invented FX rate for an AED fee on a BHD account.

### 12:06: step 1 started, core ledger
- Repo has only a README stub. Python 3.13.2. pytest not installed.
- Decision: use stdlib `unittest` so the suite runs with no installs.
- Money as `Decimal` at currency precision, not integer minor units. Decimal with `quantize` keeps AED and BHD readable and still exact. `Money` refuses input with extra precision instead of rounding it silently.
- Balances are never stored. They are computed from entries filtered by value_date, so backdated entries restate later days for free.
- Authorization state is an append-only log of `AuthRecord`s. Current state is the latest record. This keeps "no record is ever mutated" true for holds as well as entries.

### 12:07: step 1 code written
- `ledger/money.py`, `ledger/records.py`, `ledger/account.py`, `ledger/__init__.py`.

### 12:08: step 1 smoke check
- Added `tests/test_money.py` and `tests/test_account.py`, built from the scenario's own numbers.
- Ran `python3 -m unittest discover -s tests -t .`: 22 tests, all pass.
- Confirmed: Day 2 restates to AED −370.00 after the backdated E7. BHD 10.000 splits 3.334/3.333/3.333. 0.186 rounds to 0.19.
- Open point for step 2: `available_balance` counts every posted entry, whatever its value date. Fine for this stream, where nothing is future-dated. Logged for AMBIGUITIES.md.
- Stopped for the user's review. Nothing committed.
