"""Step 4: the per-day report and the runnable replay script."""

import re
import subprocess
import sys
import unittest
from pathlib import Path

from ledger.report import render
from ledger.scenario import WINDOW_DAYS, run_scenario

ROOT = Path(__file__).resolve().parent.parent


def day_block(report: str, day: int) -> str:
    match = re.search(rf"^DAY {day}\n(.*?)(?=^={{78}}$)", report, re.S | re.M)
    assert match, f"No block for Day {day}"
    return match.group(1)


class ReportContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = render(run_scenario(), WINDOW_DAYS)

    def test_one_block_per_day(self):
        self.assertEqual(re.findall(r"^DAY (\d)$", self.report, re.M), ["1", "2", "3", "4", "5", "6"])

    def test_every_block_has_the_four_required_sections(self):
        for day in WINDOW_DAYS:
            block = day_block(self.report, day)
            for heading in ("Closing ledger balance", "Fee assessments at this close",
                            "Authorization states at end of day", "Errors"):
                self.assertIn(heading, block, f"Day {day} missing {heading}")

    def test_final_closing_balances(self):
        expected = {1: "250.00", 2: "250.00", 3: "650.00", 4: "465.00", 5: "465.00", 6: "466.03"}
        for day, amount in expected.items():
            self.assertIn(f"ACC-001  final AED {amount}", day_block(self.report, day))
        self.assertIn("ACC-002  final BHD 10.008", day_block(self.report, 6))

    def test_day_5_shows_what_the_ledger_saw_at_the_time(self):
        block = day_block(self.report, 5)
        self.assertIn("at close AED -230.00", block)
        self.assertIn("Day 2: AED 250.00 -> AED -395.00", block)

    def test_fees_on_day_5_refunds_on_day_6(self):
        self.assertEqual(day_block(self.report, 5).count("FEE     ACC-001 AED -25.00"), 3)
        self.assertEqual(day_block(self.report, 6).count("REFUND  ACC-001 AED 25.00"), 3)

    def test_auth_states(self):
        self.assertIn("Auth-A  ACTIVE", day_block(self.report, 2))
        self.assertIn("Auth-A  SETTLED", day_block(self.report, 4))
        self.assertIn("released AED 15.00", day_block(self.report, 4))
        self.assertIn("Auth-B  DECLINED", day_block(self.report, 5))
        self.assertNotIn("Auth-Z", day_block(self.report, 4).split("Errors")[0].split("Authorization states")[1])

    def test_auth_z_error_on_day_4_only(self):
        self.assertIn("E6     ACC-001  UNKNOWN_AUTH", day_block(self.report, 4))
        for day in (1, 2, 3, 5, 6):
            self.assertNotIn("UNKNOWN_AUTH:", day_block(self.report, day))

    def test_e10_flagged_late_with_exact_split(self):
        block = day_block(self.report, 5)
        self.assertIn("posted as 3.334 + 3.333 + 3.333", block)
        self.assertIn("LATE", block)

    def test_interest_capitalized_on_day_6(self):
        block = day_block(self.report, 6)
        self.assertIn("CAPITALIZED ACC-001 AED 1.03", block)
        self.assertIn("CAPITALIZED ACC-002 BHD 0.008", block)


class ReplayScriptTests(unittest.TestCase):
    def test_script_runs_and_prints_the_report(self):
        result = subprocess.run([sys.executable, "replay.py"], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DAY 6", result.stdout)
        self.assertIn("SUMMARY", result.stdout)


if __name__ == "__main__":
    unittest.main()
