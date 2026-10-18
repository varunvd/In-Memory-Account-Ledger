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

### 12:17: step 3 started, end-of-day fees, refunds and interest
- User reviewed step 2 and asked for step 3.
- Moved every business constant into `ledger/policy.py` (fee AED 25.00, rate 0.0004, capitalization Day 6). The ledger takes a `Policy`; `policy=None` means events only. The step 2 tests now use `policy=None` so they test event handling alone.
- Day closing is driven by the replay. An event for day D first closes every open day before D. `replay(..., final_day=6)` closes the rest. E10 (late, Day 5) does not reopen Day 5. The Day 6 close re-checks every day anyway.
- Fee rule: at each close, walk days 1..D in order. Fee if the day's balance *before its own fee* is negative and it has no live fee. Refund if it is no longer negative and has a live fee. Walking in order means a Day 2 fee counts toward Day 3.
- Spotted while designing the rule, before coding it: checking the balance *with* the fee in it would let a fee keep itself alive. Example: a day at +10 with a 25 fee reads −15, so the fee would never be refunded. Used the pre-fee balance instead and added a test for that case.
- Interest is calculated only at the Day 6 close, after the fee refunds, from the corrected closing balances. One INTEREST entry per account equals the sum of the rounded daily accruals. The accruals are kept as `InterestAccrual` records so the report can show them per day.
- No fee is set for BHD. An overdrawn BHD day logs one NO_FEE_FOR_CURRENCY error per day instead of inventing a rate. It never fires in this scenario.

### 12:23: step 3 done
- `ledger/policy.py`, `ledger/eod.py`, engine and scenario hooks, `tests/test_end_of_day.py`.
- 63 tests, all pass on the first run.
- Scenario result: the Day 5 close posts fees for Day 2, 4 and 5. The Day 6 close refunds all three and capitalizes interest. ACC-001: AED 1.03 interest, Day 6 closes at AED 466.03. ACC-002: BHD 0.008 interest, Day 6 closes at BHD 10.008.
- Criteria now covered by tests: 2 rejected (three fees, not one), 8 rejected (1.03 vs 1.02), and part of 6 (Auth-B stays declined after E9).
- Candidate for the failing test in step 5: authorizations are checked against available balance *without* the overdraft fees that the day's close is about to post. On Day 5, Auth-B saw −155 when the true position after fees was −230. Here it was declined either way, but a borderline auth could be approved against money the account no longer has.
- Stopped for review. Nothing committed.

### 12:24: step 4 started, per-day report
- User reviewed step 3 and asked for step 4.
- Decision: show two closing balances per day. "final" uses every entry known at the end of the replay. "at close" is what the ledger saw when that day closed. Showing only final would hide E7 entirely: Day 5 would read 465.00, as if nothing happened. Showing only "at close" would hide E9's correction. Added a `BalanceSnapshot` to each `DayClose`.
- Decision: fees are listed under the day whose close *assessed* them, each with the day it is *for*. So the Day 5 block shows three fees "for Day 2/4/5".
- Decision: authorization states are shown as of the end of each day, from the auth log filtered by day, with "(changed today)" on the day of a transition. Auth-Z never appears there because it never existed; it shows only under Errors on Day 4.
- Renderer is a pure function `render(ledger, days) -> str` in `ledger/report.py`. `replay.py` at the repo root just runs the scenario and prints it.

### 12:29: report revised after first run
- First run read correctly but had two problems.
- Fee amounts printed as "-AED 25.00". Switched to the entry's signed amount: "AED -25.00".
- Restatements were invisible in the block where they happened. The Day 5 close moved Day 2 from 250 to −395, but the Day 5 block only showed Day 5. Added "Earlier days restated at this close", which compares every day's balance with the previous close. Each `DayClose` now records the closing balance of every day so far.

### 12:32: step 4 done
- `ledger/report.py`, `replay.py`, `tests/test_report.py`. `DayClose` gained `snapshots` and `day_balances`.
- 73 tests, all pass, including one that runs `python3 replay.py` as a subprocess.
- Stopped for review. Nothing committed.
