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

### 12:09: step 2 started, event replay
- User reviewed step 1 and asked for step 2.
- Events are frozen dataclasses, one per type: Credit, Debit, Authorization, Settlement, Reversal. Each has a booking `day` and a `value_date`.
- Every event produces exactly one `Outcome`: accepted, or rejected with an `ErrorRecord`. Rejections never stop the replay.
- Decision: a declined authorization is an accepted event with a DECLINED auth record, not an error. A decline is a normal answer to "can this person spend this?"; errors are for events the ledger refuses to process. The report will show declines under authorization states.
- Decision: booked debits are not checked against funds. They have already happened, and the overdraft fee only makes sense if debits can go negative. Only authorizations get the available-balance check.
- Decision: a reversal posts one opposite entry per target entry, with id `E9:E7` and `refers_to` the original. E7 stays in the ledger. Only CREDIT and DEBIT can be reversed. A reversal can't be reversed and a target can't be reversed twice.
- Decision: a "late" event is one whose booking day is earlier than an event already replayed. Late events are applied and flagged, not rejected. Only E10 is late.
- Decision: E10 instalments get entry ids `E10-1` to `E10-3`.

### 12:16: step 2 done
- `ledger/events.py`, `ledger/engine.py`, `ledger/scenario.py`, `tests/test_replay.py`.
- 44 tests, all pass. Criteria checked so far: 1 (Day 2 at −370.00 after E8), 3 (Auth-A accepted), 4 (Auth-Z rejected, nothing posted).
- Without fees or interest, ACC-001 ends at AED 465.00 and ACC-002 at BHD 10.000.
- Considered failing the replay when an internal invariant breaks, such as a duplicate entry id. Kept that as a raised exception, not an error record, because it means a bug in the engine, not a bad event.
- Stopped for review. Nothing committed.
