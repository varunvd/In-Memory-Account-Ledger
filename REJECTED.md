# Rejected

Part 1 lists the acceptance criteria I refused and why. Part 2 lists approaches I dropped during design and the build.

Every refusal has a test in `tests/test_criteria.py`, in a class named with its verdict. The tests show what the ledger actually does and why the criterion's claim cannot hold.

## Verdicts at a glance

| # | Criterion | Verdict |
|---|---|---|
| 1 | Day 2 closing, at end of Day 5 before fees, is AED −370.00 | Accepted |
| 2 | E7 causes exactly one overdraft fee, on Day 2 | **Rejected** |
| 3 | The Day 4 settlement of Auth-A must be accepted | Accepted |
| 4 | A settlement for an unknown auth ID is rejected and no funds leave | Accepted, with a caveat |
| 5 | If Auth-B is approved, its hold reduces available but not ledger | Accepted, never triggers |
| 6 | After E9, all balances and fees return to their pre-E7 values | **Rejected** |
| 7 | The three BHD instalments in E10 are each BHD 3.334 | **Rejected** |
| 8 | If rounded accruals don't sum to the capitalized total, discard the remainder | **Rejected** |

---

## Part 1: Criteria refused

### Criterion 2: "E7 causes exactly one overdraft fee to be assessed, on Day 2"

**Refused. E7 causes three fees: Day 2, Day 4 and Day 5.**

E7 is a debit of AED 620.00, booked on Day 5 and value-dated Day 2. It lowers the closing balance of Day 2 *and every day after it*. A backdated entry doesn't stay in its own day.

At the Day 5 close, after E7 and before E9:

| Day | Working | Closing | Fee? |
|---|---|---|---|
| 2 | 250.00 − 620.00 | −370.00 | Yes, then −395.00 |
| 3 | −395.00 + 400.00 (E4) | 5.00 | No |
| 4 | 5.00 − 185.00 (E5) | −180.00 | Yes, then −205.00 |
| 5 | −205.00, no new entries | −205.00 | Yes, then −230.00 |

The criterion's author seems to have looked only at the day E7 is dated to. Day 3 escapes only because E4's AED 400.00 lands that day. It escapes by AED 5.00, which means any fee above AED 30.00 would have made it four fees. See NUMBERS.md.

**Evidence:** `C2_E7CausesExactlyOneFee_REJECTED`. The counterfactual test confirms that without E7 there are no fees at all, so all three are E7's.

### Criterion 6: "After E9, all balances and fees return to their pre-E7 values"

**Refused. Some things return; not all of them can.**

I compared the real replay against a counterfactual replay with E7 and E9 removed.

- **Closing ledger balances return.** They match on all six days. That only works because of the decision to refund E7's fees on their original dates. Without refunds, Day 6 would end AED 75.00 short.
- **Fees do not "return".** The ledger is append-only. The three fee entries still exist, with three refund entries beside them. The net effect is zero, but the records cannot be removed. The brief's own rule forbids that.
- **Available balance does not return.** Auth-B was checked on Day 5, after E7 had made the balance negative, and was declined. E9 arrives on Day 6 and cannot go back and approve it. In the counterfactual, Auth-B is approved and holds AED 90.00. The two available balances differ by exactly that hold.

The criterion assumes a reversal is an undo button. In a ledger that reacts to events in order, decisions made in the meantime stand. Authorization decisions in particular are final once given.

**Evidence:** `C6_E9RestoresEverything_REJECTED`. One test shows the part that holds, and two show the parts that don't.

### Criterion 7: "The three BHD instalments in E10 must each be BHD 3.334"

**Refused. Three times 3.334 is 10.002, not 10.000.**

E10 credits BHD 10.000 in three equal instalments. 10.000 / 3 = 3.3333…, which can't be written at three decimal places. Rounding every part up creates 0.002 BHD from nothing. That breaks the deposit's own total, and any reconciliation against the source would fail.

The ledger posts **3.334, 3.333, 3.333**. The leftover fils goes on the first instalment, and the parts sum to exactly 10.000. "Equal" can only mean as equal as the currency allows.

**Evidence:** `C7_EachInstalmentIs3_334_REJECTED`, and `test_three_times_3_334_is_not_10` in `tests/test_money.py`.

### Criterion 8: "If the rounded daily interest accruals do not sum to the capitalized total, the remainder is discarded"

**Refused. It contradicts a non-negotiable rule.**

The brief's rule: "The rounded daily accruals must sum exactly to the capitalized total." A remainder can only exist if the total is calculated some other way, such as rounding the exact sum once. Discarding the remainder then pays a total that disagrees with the daily records. That is exactly what the rule forbids.

For ACC-001:

| | Amount |
|---|---|
| Rounded daily accruals: 0.10 + 0.10 + 0.26 + 0.19 + 0.19 + 0.19 | AED 1.03 |
| Exact sum 1.018, rounded once | AED 1.02 |

Discarding the cent would pay 1.02 while the accrual records add up to 1.03. The ledger instead *defines* the capitalized total as the sum of the rounded accruals, so there is never a remainder.

Daily rounding can drift either way. At half the rate, the rounded days sum to 0.50 while the exact sum rounds to 0.51. A "discard" rule would then mean paying more than the records show. See NUMBERS.md.

**Evidence:** `C8_DiscardInterestRemainder_REJECTED`, and `InterestInvariantTests` in `tests/test_invariants.py`.

---

## Criteria accepted, briefly

- **Criterion 1:** 1,200.00 − 950.00 − 620.00 = −370.00. Auth-A's hold is not a ledger entry, so it doesn't count. "End of Day 5 and before any fee" is read as after Day 5's events and before Day 5's close. See AMBIGUITIES.md B9.
- **Criterion 3:** Auth-A is active with a hold of 200.00, and 185.00 is within it.
- **Criterion 4:** accepted, but the reasoning matters. It is consistent with the brief's rules, which never require honouring an unmatched settlement. "The funds must not leave the account" is true of the customer's account only. In reality the card network has likely paid the merchant already. See AMBIGUITIES.md A1.
- **Criterion 5:** true as a statement about holds, and tested in a variant where Auth-B is approved. In the real scenario Auth-B is declined, so the condition never fires.

---

## Part 2: Approaches abandoned

Listed roughly in the order they came up. Timings are in WORKLOG.md.

### During design, before any code

1. **Integer minor units (cents) for money.** I proposed this in the first design sketch. I switched to `Decimal` quantized to each currency, because two currencies with different precisions make integer units easy to mix up. `Decimal` keeps amounts readable and still exact. Floats were never considered.
2. **Explicit end-of-day marker events.** Also in the first sketch. Dropped because the brief's stream has none. Adding them would mean changing the given input. Day closes are inferred from day changes instead.
3. **An EXPIRED authorization state.** Dropped because the brief has no expiry rule, and Auth-B, the only unsettled authorization, is declined anyway.
4. **Force-posting the Auth-Z settlement, or parking it in an exceptions book.** These were options 2 and 3 for criterion 4. Rejected in favour of a plain rejection. See AMBIGUITIES.md A1.
5. **Keeping E7's fees after the reversal.** That would end Day 6 at AED 390.00 before interest. Rejected: E7 was a mistake, and the customer shouldn't pay for it.
6. **Paying interest on balances as known each night.** That would give AED 0.84. Rejected for corrected history, which gives 1.03, consistent with refunding the fees.
7. **pytest.** It isn't installed in this environment. I used the standard library's `unittest` so the suite runs with no installs.

### During the build

8. **Judging a day's overdraft on its balance including its own fee.** I spotted this while designing the fee rule, before coding it. It lets a fee keep itself alive: a day at +10 with a 25 fee reads −15, so it is never refunded. I switched to the pre-fee balance, and `test_fee_cannot_justify_itself` pins it.
9. **Step 2 tests running with fees switched on.** Once end-of-day processing was added, the event-only tests would have started seeing fees mid-replay. The ledger now takes an optional `Policy`, and those tests run with `policy=None`.
10. **A report with only final balances.** This was the plan for step 4 until I worked through it before writing the renderer. It would show Day 5 as AED 465.00, as if E7 never happened. I added an "at close" balance next to the final one before the first run.
11. **A report without restatements.** The first actual run showed the Day 5 close silently changing Days 2 to 4, visible only in each day's own block. I added "Earlier days restated at this close".
12. **Fee amounts printed as "-AED 25.00".** Changed to the entry's signed amount, "AED -25.00", after the first run.
13. **Choosing test events by comparing ID strings.** One test used `event_id <= "E8"`, which only works by accident of string ordering ("E10" < "E8"). Replaced with an explicit list.
14. **Using the scenario's Auth-B for the failing test.** Ruled out: Auth-B is declined with or without the pending fees, at −155 vs −230, so it can't show the bug. I built a minimal four-step case instead.
15. **Marking the failing test with `@unittest.expectedFailure`.** Rejected with the project owner's agreement. The brief asks for a failing test, and the decorator would make it pass. The README explains the one expected failure.
16. **A claim in the first draft of NUMBERS.md.** It said halving the interest rate closes the rounding gap. Checking it by calculation showed the gap flips direction instead: 0.50 vs 0.51. The text was corrected, and the corrected fact now strengthens the case against criterion 8.
