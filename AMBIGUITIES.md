# Ambiguities

Every place the brief was silent, unclear, or open to two readings, and how each was resolved.

Each entry gives the question, the options considered, the resolution, and where it is enforced. Items marked **(user)** were decided with the project owner during design. The rest are my defaults, which the owner accepted.

---

## Authorizations and settlements

### A1. A settlement with no matching authorization (E6, Auth-Z) (user)

- **Question:** the brief's criterion says to reject it and keep the funds in the account. In real card processing, a settlement with no authorization (a "force-post") is still a network obligation. Offline terminals on planes and at toll booths produce them. By the time it arrives, the network has usually paid the merchant already.
- **Options:**
  1. Reject it, log an error, post nothing.
  2. Force-post it as a debit flagged as unmatched.
  3. Leave the customer account alone and park the amount in a separate exceptions book.
- **Resolution:** option 1. Nothing in the brief's rules says unmatched settlements must be honoured, so the criterion is not wrong by those rules.
- **The caveat:** "the funds must not leave the account" is true of the customer's account only. In reality the bank may already be out AED 180.00 and would recover it by chargeback, outside this ledger. Only the error record tracks the 180. No balance anywhere reflects it. Option 3 would close that gap but needs a book the brief doesn't define.
- **Enforced:** `_settle` in `ledger/engine.py`. Tests: `C4_UnknownAuthSettlementRejected_ACCEPTED`.

### A2. Settling for less than the hold (Auth-A: 185 against 200) (user)

- **Question:** what happens to the unused AED 15.00?
- **Resolution:** post the settled amount and release the whole hold. The AED 15.00 is available again. The authorization becomes SETTLED and can't be settled twice.
- **Not modelled:** multiple partial settlements against one hold, which some card schemes allow.
- **Enforced:** `_settle`. The report's Day 4 block shows "settled AED 185.00, released AED 15.00".

### A3. Settling for more than the hold

- **Question:** the brief doesn't say. Real schemes allow some overshoot, for example for restaurant tips.
- **Resolution:** reject with `SETTLEMENT_EXCEEDS_HOLD`. Any tolerance would be an invented number. It doesn't occur in the scenario.

### A4. Settling against an authorization that exists but isn't active

- **Question:** criterion 4 covers IDs "not present in the ledger". What about a declined authorization like Auth-B, or one already settled?
- **Resolution:** reject both, with separate codes: `AUTH_DECLINED` and `AUTH_ALREADY_SETTLED`. A declined authorization never placed a hold, so there is nothing to settle against.

### A5. Is a declined authorization an error?

- **Question:** the report must show "authorization states" and "errors". Auth-B fits both readings.
- **Resolution:** a decline is a normal answer to "can this person spend this?", so it is an authorization state, not an error. Errors are for events the ledger refused to process. Auth-B appears as DECLINED under authorization states, and the Errors section stays empty for Day 5.

### A6. Which balance an authorization is checked against

- **Question:** "available balance = ledger balance minus active holds". But ledger balance as of which value date? And should fees that are certain but not yet posted count?
- **Resolution:** all entries posted so far, whatever their value date, minus active holds. Pending fees are **not** counted, following the letter of the rule.
- **Consequence:** this is a real gap. `tests/test_known_failure.py` shows an authorization approved against money already owed as a fee. Available balance then goes to −15.00 at the close. The scenario doesn't hit it, because Auth-B is declined either way.
- **Not modelled:** future-dated entries. None occur in the stream. If one did, the available check would count money that hasn't arrived yet.

### A7. Holds that are never settled

- **Question:** "Auth-B is never settled inside the window." Should holds expire?
- **Resolution:** no expiry, because the brief gives no rule. The point is moot here: Auth-B was declined, so no hold exists. Had it been approved, it would still show ACTIVE at the end of Day 6.

### A8. Duplicate authorization IDs

- **Resolution:** a second authorization with an ID already seen on the account is rejected as `DUPLICATE_AUTH`. It doesn't occur in the scenario.

---

## Backdated events, fees and reversals

### B1. Backdated events and days that are already closed

- **Question:** E7 arrives on Day 5 but is value-dated Day 2. Day 2 is already closed. Does the ledger go back and re-judge it?
- **Resolution:** yes. Every day close re-checks every day from Day 1. Balances are never stored; they are computed from entries filtered by value date, so a backdated entry restates later days automatically.
- **Enforced:** `DayCloser.close` in `ledger/eod.py`.

### B2. "Booked with value_date equal to the day assessed" (user)

- **Question:** the fee for Day 2 is worked out at the Day 5 close. Is it dated Day 2, the day judged, or Day 5, the day the work happened?
- **Resolution:** Day 2. The fee belongs to the day that went negative. The entry keeps `booking_day=5`, so both facts are recorded. The report lists it under the Day 5 close as "for Day 2".
- **Consequence:** a Day 2 fee lowers Day 3's balance. Days are walked in order, so it counts.

### B3. How many fees E7 causes (user)

- **Question:** criterion 2 says one. The arithmetic says otherwise.
- **Resolution:** three, on Day 2, Day 4 and Day 5. See REJECTED.md.

### B4. Is a day judged before or after its own fee?

- **Question:** a day at +10.00 with a 25.00 fee reads −15.00. If the fee counts toward its own trigger, it can never be refunded.
- **Resolution:** a day is judged on its balance excluding its own fee and refunds. Earlier days' fees still count.
- **Enforced:** `DayCloser.pre_fee_closing`. Test: `test_fee_cannot_justify_itself`.

### B5. Fees after the backdated debit is reversed (user)

- **Question:** E9 cancels E7. The three fees existed only because of E7. Keep them or refund them?
- **Options:** refund them, so ACC-001 ends Day 6 at 465.00 before interest. Or keep them, ending at 390.00.
- **Resolution:** refund them. E7 was a mistake, and the customer shouldn't pay for it. The ledger is append-only, so a refund is a new FEE_REFUND entry pointing at the fee. The fee itself stays.

### B6. What date a fee refund carries

- **Question:** date each refund Day 6, when it happened, or the same day as the fee it cancels?
- **Resolution:** the same day as the fee. Days 2 to 5 then read exactly as they would have without E7. Dating them Day 6 would leave Days 2 to 5 short by the fees, and would wrongly cut interest on those days.

### B7. What can be reversed

- **Question:** the brief has one reversal, of a debit.
- **Resolution:** only CREDIT and DEBIT entries can be reversed, once each. Reversing a settlement, a fee or another reversal is rejected. A settlement has its own lifecycle through the authorization, and fees are corrected by refunds.
- **Enforced:** `_reverse`. Tests cover reversing twice, reversing a settlement, and reversing an unknown event.

### B8. The reversal's value date

- **Question:** E9 says "value_date Day 2", matching E7. Should a reversal always copy its target's date?
- **Resolution:** use the date the event gives. Here they match. A reversal dated differently from its target would leave a window where both count, and the ledger allows that.

### B9. Criterion 1's "evaluated at end of Day 5 and before any fee is assessed"

- **Question:** the end of Day 5 is exactly when the Day 5 close assesses fees. So "end of Day 5" and "before any fee" pull against each other.
- **Resolution:** read it as after every Day 5 event is applied, before the Day 5 close runs. At that point Day 2 is AED −370.00. After the close, it is −395.00, because of its own fee.
- **Test:** `C1_Day2ClosingIsMinus370_ACCEPTED`.

---

## Interest

### C1. Interest on which version of history (user)

- **Question:** E7 and E9 rewrite Days 2 to 5. Should interest use each day's balance as known that night, or the corrected final history?
- **Options:** as known that night gives AED 0.84, because Day 5 looked negative. Corrected history gives AED 1.03.
- **Resolution:** corrected history. It is consistent with refunding E7's fees. And because interest is only paid at the end of Day 6, the corrected history is fully known by then.
- **Consequence:** daily accrual records are created at the Day 6 close, not each night.

### C2. Is Day 6 interest paid on the balance before or after the capitalization credit?

- **Resolution:** before. Otherwise the interest would earn interest on itself on the same day.

### C3. Does interest compound daily?

- **Question:** "0.04% per day on the closing ledger balance". Does each accrual join the balance the next day?
- **Resolution:** no. Accruals aren't ledger entries until they're capitalized, so they're not in the closing balance. "Capitalize as a single credit at end of Day 6" says they join the balance only then.

### C4. What "rounded" means and when rounding happens

- **Resolution:** each daily accrual is rounded half up to the currency's precision. The capitalized total is defined as the sum of those. That is the only way to make "the rounded daily accruals must sum exactly to the capitalized total" true by construction. See NUMBERS.md for the rounding mode.

### C5. Interest on the BHD account

- **Resolution:** same rule and same rate. ACC-002 earns BHD 0.004 on Day 5 and on Day 6, for a total of 0.008. Day 5 counts because E10, although it arrived late, is value-dated Day 5.

---

## Money and currencies

### D1. AED overdraft fee on a BHD account

- **Question:** the fee is stated as AED 25.00. ACC-002 is in BHD.
- **Options:** convert at some rate, apply BHD 25.000, or apply no fee.
- **Resolution:** no fee is configured for BHD. Converting needs an exchange rate the brief doesn't give, and BHD 25.000 is worth about ten times AED 25.00. If a BHD account closes negative, the ledger logs a `NO_FEE_FOR_CURRENCY` error once per day and charges nothing. ACC-002 never goes negative, so it never fires in the scenario.
- **Test:** `test_overdrawn_bhd_account_logs_one_error_and_no_fee`.

### D2. Where the leftover fils goes in E10's split (user)

- **Question:** 10.000 / 3 does not divide evenly. Criterion 7's 3.334 × 3 is 10.002.
- **Resolution:** 3.334, 3.333, 3.333. The extra fils goes on the first instalment. See NUMBERS.md and REJECTED.md.

### D3. E10's instalments: one event or three?

- **Resolution:** one event, three entries (`E10-1` to `E10-3`), all booked Day 5 and value-dated Day 5. Reversing E10 would reverse all three together.

### D4. Is the opening balance an entry?

- **Resolution:** no. It is a field on the account. Both opening balances are zero, so this changes nothing here. It keeps the entries list to things that happened in the window.

---

## The event stream and replay

### E1. E10 arrives out of order (user)

- **Question:** E10 is booked on Day 5 but listed after E9, a Day 6 event. The brief says "replayed in this order".
- **Options:** sort events by day first, reject E10 as late, or apply it as listed.
- **Resolution:** apply it in the order given, with its own dates, and flag it LATE in the report. Sorting would ignore the brief's instruction. Rejecting it would lose a real deposit.
- **Consequence:** E10 lands after the Day 5 close has run. The report's Day 5 block shows ACC-002 "at close BHD 0.000" but "final BHD 10.000". The Day 6 close's restated section shows the change.

### E2. When a day closes

- **Question:** the stream has no end-of-day events.
- **Resolution:** the first event of a later day closes every open day before it. After the last event, the remaining days are closed through Day 6. A late event never reopens a closed day. The next close re-checks everything instead.

### E3. Should booked debits be checked against funds?

- **Question:** only authorizations have an explicit funds rule.
- **Resolution:** no. A booked debit has already happened. The overdraft fee exists only because debits can take an account negative. E7 must post for the scenario to make sense at all.

### E4. Duplicate event IDs

- **Resolution:** a repeated event ID is rejected as `DUPLICATE_EVENT`. It doesn't occur in the scenario.

### E5. What "append-only" covers

- **Question:** "No event record is ever mutated or deleted." Does that cover authorization state too?
- **Resolution:** yes. Authorization state is a log of `AuthRecord`s, and the current state is the latest one. Nothing is updated in place. `tests/test_invariants.py` snapshots every account after every event and close, and checks that each snapshot is a prefix of the next.

### E6. Events outside the window

- **Not modelled:** an event before Day 1 or after Day 6 is not rejected. None exist in the stream.

---

## Criteria wording

### F1. Criterion 5 is conditional and never triggers

- **Question:** "If Auth-B is approved, its hold reduces available balance but not ledger balance." Auth-B is declined.
- **Resolution:** accepted. The statement is true of how holds work, and it is tested in a variant without E7, where Auth-B is approved. In the real scenario the condition never fires.

### F2. "Pre-E7 values" in criterion 6

- **Question:** pre-E7 could mean the Day 4 position before E7 arrived, or a world where E7 never happened.
- **Resolution:** compared against a counterfactual replay with E7 and E9 removed. Closing ledger balances match on every day. Available balance and authorization outcomes don't, and the fee records remain. See REJECTED.md.

### F3. "Fee assessments" per day in the report

- **Question:** list fees under the day they're for, or the day they were assessed?
- **Resolution:** under the close that assessed them, each labelled with the day it is for. Listing them by value date would make Day 2 show a fee that didn't exist when Day 2 closed.
