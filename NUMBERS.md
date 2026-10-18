# Numbers

Every constant in the ledger, where it lives, why it has that value, and what halving it would do.

"Given" means the brief fixes the value. "Chosen" means the brief is silent and I picked it.

All "what halving does" results come from rerunning the scenario with the changed value, not from estimates.

## Business constants

These live in `ledger/policy.py` and `ledger/money.py`.

### Overdraft fee: AED 25.00 (given)

- **Where:** `SCENARIO_POLICY.overdraft_fee["AED"]`.
- **Why:** the brief fixes it.
- **Halved to AED 12.50:** the same three days are charged, Day 2, Day 4 and Day 5. The Day 5 close shows AED −192.50 instead of −230.00. After E9's refunds, every final balance is unchanged.
- **The sensitive threshold is AED 30.00, not half.** After E7, Day 3 closes at −370 − fee + 400 = 30 − fee. At AED 25, Day 3 survives by AED 5.00. Any fee above AED 30.00 makes Day 3 negative too and adds a fourth fee. A rerun at AED 300 confirmed fees on Day 2, 3, 4 and 5. The criterion 2 tests pin the three-fee result, so a fee change that crosses 30 would fail them loudly.
- **Fee in other currencies: none.** No BHD fee is configured. Converting AED 25 into BHD would mean inventing an exchange rate. See AMBIGUITIES.md.

### Daily interest rate: 0.0004 (given as 0.04% per day)

- **Where:** `SCENARIO_POLICY.daily_interest_rate`.
- **Why:** 0.04% written as a fraction is 0.0004. It is not 0.004; that would be 0.4%.
- **Halved to 0.0002:** ACC-001 capitalizes AED 0.50 instead of 1.03, and ACC-002 capitalizes BHD 0.004 instead of 0.008. The rounding gap does not go away; it flips direction. 465 × 0.0002 = 0.093, which rounds *down* to 0.09. The rounded days sum to 0.50, but the exact sum of 0.509 rounds to 0.51. At the given rate the customer gains a cent from daily rounding; at half the rate they lose one. **Daily rounding can drift either way, which is why the total must be defined as the sum of the rounded days rather than reconciled to the exact sum.**
- **Stored as `Decimal("0.0004")`,** never as a float, so 465.00 × rate is exactly 0.186.

### Capitalization day: Day 6 (given)

- **Where:** `SCENARIO_POLICY.capitalization_day`.
- **Why:** the brief says accruals capitalize at the end of Day 6.
- **Halved to Day 3:** interest is paid before E7 and E9 happen. ACC-001 gets AED 0.46 for Days 1 to 3 only. ACC-002 gets nothing, because its money arrives on Day 5. Capitalizing at the end of the window is what lets interest use corrected history.

### Currency precision: AED 2 places, BHD 3 places (given)

- **Where:** `CURRENCY_PRECISION` in `ledger/money.py`.
- **Why:** the brief says so, and it matches ISO 4217. The fils is 1/100 of a dirham and 1/1000 of a dinar.
- **Halved, AED to 1 place:** daily interest would round to 0.1, 0.1, 0.3, 0.2, 0.2 and 0.2, which is 1.1. That's 8% more than the exact 1.018.
- **Halved, BHD to 1 or 2 places:** at 2 places, the daily 0.004 interest rounds to 0.00, so ACC-002 earns nothing. At 2 places, E10 splits as 3.34 + 3.33 + 3.33. That still sums correctly, but it isn't a legal BHD amount.
- **Input that is too precise is refused, not rounded.** `Money.of("0.186", "AED")` raises an error. Rounding only happens through `Money.rounded`, so every rounding is a deliberate call.

### Rounding mode: half up (chosen)

- **Where:** `ROUNDING_MODE` in `ledger/money.py`.
- **Why:** the brief says "rounded" without a mode. Half up is what people expect on a statement. Banker's rounding (half even) is the main alternative.
- **Does it matter here? No.** No exact half occurs anywhere in this scenario. The only rounding that changes a value is 0.186 → 0.19, which both modes agree on. A test covers the 0.125 → 0.13 case in case the data changes.

### Where rounding happens: each daily accrual (chosen, forced by the rules)

- **Why:** the brief says the rounded daily accruals must sum exactly to the capitalized total. So each day is rounded on its own, and the total is defined as their sum.
- **The alternative:** rounding once at the end gives AED 1.02 instead of 1.03. That's why criterion 8 is rejected.

### Instalment split remainder: extra minor unit goes to the first instalment (chosen)

- **Where:** `Money.split` in `ledger/money.py`.
- **Why:** BHD 10.000 / 3 leaves one fils over. It has to go somewhere so the parts sum exactly. Putting it first is the common convention and is deterministic. The result is 3.334, 3.333, 3.333.
- **Number of instalments, 3:** given by E10.

## Thresholds

### Overdraft trigger: strictly below zero (chosen)

- **Where:** `pre_fee_closing(...).is_negative` in `ledger/eod.py`.
- **Why:** the brief says "negative". Zero is not negative. This matches the authorization rule, where zero is an allowed result. A test covers a zero balance getting no fee.

### Authorization limit: available after the hold must be at or above zero (given)

- **Where:** `_authorize` in `ledger/engine.py`.
- **Why:** the brief says "remains at or above zero". An authorization that brings available to exactly 0.00 is approved, and a test covers that edge.

### Settlement tolerance over the hold: 0 (chosen)

- **Where:** `_settle` in `ledger/engine.py`.
- **Why:** the brief gives no tolerance. Real card schemes allow some overshoot, for example for tips, but any percentage would be an invented number. A settlement of 50.01 against a 50.00 hold is rejected. The scenario never settles above its hold.

### Fees per account per day: at most 1 live fee (given)

- **Why:** the brief says "once per day per account". Re-closing a day never adds a second fee. An invariant test checks this across the whole replay.

### Interest base: positive closing balances only (given)

- **Why:** the brief says "positive balances only". Zero and negative days accrue nothing. ACC-002 earns nothing on Days 1 to 4, when its balance is 0.000.

## Time and window

| Constant | Value | Given or chosen | Why |
|---|---|---|---|
| Window | Day 1 to Day 6 | Given | `WINDOW_DAYS` in `ledger/scenario.py`. |
| Hold expiry | Never | Chosen | The brief has no expiry rule. Any number of days would be invented. With Auth-B declined, no hold is open at the end, so it doesn't matter here. |
| Late threshold | Booking day earlier than the latest seen | Chosen | The simplest definition that flags E10, the only out-of-order event. |
| Day close trigger | First event of a later day, or end of stream | Chosen | The stream has no explicit end-of-day events. |

## Minor constants

| Constant | Value | Where | Why |
|---|---|---|---|
| Report width | 78 characters | `RULE` in `ledger/report.py` | Fits a standard 80-column terminal. |
| Subprocess timeout in tests | 30 seconds | `tests/test_report.py` | The script runs in well under a second. 30 s only catches a hang without being flaky on slow machines. |
| Decimal context precision | Python default, 28 digits | Implicit | The largest product is 1,200 × 0.0004. 28 digits is far more than enough. |
