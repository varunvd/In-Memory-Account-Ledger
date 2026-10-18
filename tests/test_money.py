import unittest
from decimal import Decimal

from ledger.money import CurrencyMismatchError, Money, PrecisionError, round_amount, total


class MoneyPrecisionTests(unittest.TestCase):
    def test_aed_keeps_two_places(self):
        self.assertEqual(str(Money.of("1200", "AED").amount), "1200.00")

    def test_bhd_keeps_three_places(self):
        self.assertEqual(str(Money.of("10", "BHD").amount), "10.000")

    def test_rejects_extra_precision_instead_of_rounding(self):
        with self.assertRaises(PrecisionError):
            Money.of("0.186", "AED")

    def test_rejects_float(self):
        with self.assertRaises(TypeError):
            Money(0.1, "AED")

    def test_rejects_unknown_currency(self):
        with self.assertRaises(ValueError):
            Money.of("1", "USD")

    def test_cannot_mix_currencies(self):
        with self.assertRaises(CurrencyMismatchError):
            Money.of("1", "AED") + Money.of("1", "BHD")


class RoundingTests(unittest.TestCase):
    def test_interest_on_465_rounds_half_up_to_0_19(self):
        # 465.00 x 0.04% = 0.186
        self.assertEqual(round_amount(Decimal("465.00") * Decimal("0.0004"), "AED"), Decimal("0.19"))

    def test_exact_half_rounds_up(self):
        self.assertEqual(round_amount(Decimal("0.125"), "AED"), Decimal("0.13"))
        self.assertEqual(round_amount(Decimal("0.0005"), "BHD"), Decimal("0.001"))


class SplitTests(unittest.TestCase):
    def test_bhd_10_into_three_sums_exactly(self):
        parts = Money.of("10.000", "BHD").split(3)
        self.assertEqual([str(p.amount) for p in parts], ["3.334", "3.333", "3.333"])
        self.assertEqual(total(parts, "BHD"), Money.of("10.000", "BHD"))

    def test_three_times_3_334_is_not_10(self):
        # Why criterion 7 is wrong.
        self.assertEqual(Money.of("3.334", "BHD").amount * 3, Decimal("10.002"))

    def test_even_split_has_no_remainder(self):
        parts = Money.of("9.000", "BHD").split(3)
        self.assertEqual({p.amount for p in parts}, {Decimal("3.000")})


if __name__ == "__main__":
    unittest.main()
