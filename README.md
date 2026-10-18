# In-Memory Account Ledger

A pure-Python ledger core that replays a fixed six-day event stream for two accounts. It prints, per day, the closing ledger balance, fee assessments, authorization states and errors.

There is no web layer, persistence, UI or database. It needs no third-party packages.

## Requirements

- Python 3.10 or newer. Built on 3.13.2. The suite gives the same result on 3.10 and 3.11.
- Nothing to install. Tests use the standard library's `unittest`.

## Run the replay

```bash
python3 replay.py
```

This replays events E1 to E10 in the order the brief gives, closes Day 1 to Day 6, and prints one block per day plus a summary.

## Run the tests

```bash
python3 -m unittest discover -s tests -t .
```

**Expected result: 96 tests, 1 failure.** The failure is deliberate. It is `tests/test_known_failure.py`, which documents a gap in this design. The file's docstring explains what it reveals. Any other failure is a real regression.

To run only that test:

```bash
python3 -m unittest tests.test_known_failure -v
```

To run everything except that test:

```bash
python3 -m unittest tests.test_money tests.test_account tests.test_replay tests.test_end_of_day tests.test_report tests.test_criteria tests.test_invariants
```

## Reading the output

The report opens with a short legend. Each day block then has these sections.

| Section | What it shows |
|---|---|
| Events booked | Every event whose booking day is this day, and what happened to it. Late events are flagged. |
| Closing ledger balance | Two numbers per account. **final** uses every entry known at the end of the replay. **at close** is what the ledger saw when this day closed. **available** is ledger minus active holds at that close. "(restated)" marks a day whose final balance differs from what was seen at the time. |
| Earlier days restated at this close | Past days whose closing balance changed since the previous close, because a backdated event arrived. |
| Fee assessments at this close | Fees and refunds posted by this day's close. Each says which day it is *for*, which can be earlier. |
| Interest accrued for this day | That day's accrual, worked out at the Day 6 close on final balances. The Day 6 block also shows the capitalized credit. |
| Authorization states at end of day | Each authorization's state after this day's events. "(changed today)" marks a transition. |
| Errors | Events rejected this day, with a reason code. |

### Where to look

- **Day 4** shows Auth-A settling for AED 185.00, which releases AED 15.00. It also shows the Auth-Z settlement rejected as `UNKNOWN_AUTH`.
- **Day 5** shows the backdated E7. Days 2 to 4 are restated, three AED 25.00 fees are charged, Auth-B is declined, and the late E10 is split 3.334 + 3.333 + 3.333.
- **Day 6** shows E9 reversing E7. The restated days come back, all three fees are refunded, and interest is capitalized.

## Key results

| Account | D1 | D2 | D3 | D4 | D5 | D6 |
|---|---|---|---|---|---|---|
| ACC-001 (AED), final | 250.00 | 250.00 | 650.00 | 465.00 | 465.00 | 466.03 |
| ACC-001 (AED), at close | 250.00 | 250.00 | 650.00 | 465.00 | −230.00 | 466.03 |
| ACC-002 (BHD), final | 0.000 | 0.000 | 0.000 | 0.000 | 10.000 | 10.008 |

The only error is E6, which is rejected because Auth-Z has no authorization.

## Layout

| Path | Contents |
|---|---|
| `replay.py` | Entry point. Runs the scenario and prints the report. |
| `ledger/money.py` | `Money`: exact Decimal at currency precision, half-up rounding, exact splitting. |
| `ledger/records.py` | Immutable `Entry`, `AuthRecord`, `ErrorRecord` and their enums. |
| `ledger/account.py` | Append-only account. Balances are computed from entries, never stored. |
| `ledger/events.py` | The event types: Credit, Debit, Authorization, Settlement, Reversal. |
| `ledger/engine.py` | `Ledger`: applies events, records errors, closes days. |
| `ledger/eod.py` | End-of-day fees, fee refunds, interest accrual and capitalization. |
| `ledger/policy.py` | Every business constant. See NUMBERS.md. |
| `ledger/scenario.py` | The two accounts and events E1 to E10. |
| `ledger/report.py` | Renders the per-day report. |
| `tests/test_criteria.py` | One test class per acceptance criterion, named with its verdict. |
| `tests/test_known_failure.py` | The deliberate failing test. |

## Other documents

- **NUMBERS.md**: every constant, why that value, and what halving it would do.
- **AMBIGUITIES.md**: every ambiguity found in the brief and how it was resolved.
- **REJECTED.md**: the criteria refused and why, plus approaches abandoned during the build.
- **WORKLOG.md**: a timestamped log of the build.
