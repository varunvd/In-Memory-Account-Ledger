"""Money: exact decimal amounts tied to a currency and its precision.

Rules this module enforces:
- Amounts are Decimal, never float.
- Every amount is held at its currency's precision (AED 2 places, BHD 3 places).
- Rounding is ROUND_HALF_UP and happens only through `round_amount`.
- Money of different currencies cannot be combined.
- `split` divides an amount into parts that always sum back to the original.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Decimal places per currency. Only currencies listed here are accepted.
CURRENCY_PRECISION: dict[str, int] = {
    "AED": 2,
    "BHD": 3,
}

ROUNDING_MODE = ROUND_HALF_UP


class CurrencyMismatchError(ValueError):
    """Two amounts in different currencies were combined."""


class PrecisionError(ValueError):
    """An amount was given with more decimal places than its currency allows."""


def _quantum(currency: str) -> Decimal:
    try:
        places = CURRENCY_PRECISION[currency]
    except KeyError:
        raise ValueError(f"Unsupported currency: {currency!r}") from None
    return Decimal(1).scaleb(-places)  # AED -> 0.01, BHD -> 0.001


def round_amount(value: Decimal, currency: str) -> Decimal:
    """Round a raw Decimal to the currency's precision, half up."""
    return value.quantize(_quantum(currency), rounding=ROUNDING_MODE)


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError("Money amounts must not be float; pass a str or Decimal")
        amount = Decimal(self.amount)
        quantized = amount.quantize(_quantum(self.currency))
        if quantized != amount:
            # Refuse to silently round input. Rounding must be an explicit step.
            raise PrecisionError(
                f"{amount} has more precision than {self.currency} allows "
                f"({CURRENCY_PRECISION[self.currency]} places)"
            )
        # Normalise the stored exponent so 250 and 250.00 print the same way.
        object.__setattr__(self, "amount", quantized)

    # --- construction -------------------------------------------------

    @classmethod
    def of(cls, amount: str | int | Decimal, currency: str) -> Money:
        return cls(Decimal(amount), currency)

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(Decimal(0), currency)

    @classmethod
    def rounded(cls, raw: Decimal, currency: str) -> Money:
        """Build Money from a raw calculation result, rounding half up."""
        return cls(round_amount(raw, currency), currency)

    # --- arithmetic ---------------------------------------------------

    def _check(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError(f"Expected Money, got {type(other).__name__}")
        if other.currency != self.currency:
            raise CurrencyMismatchError(f"{self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.amount >= other.amount

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    @property
    def is_positive(self) -> bool:
        return self.amount > 0

    # --- splitting ----------------------------------------------------

    def split(self, parts: int) -> list[Money]:
        """Split into `parts` amounts that sum exactly to self.

        Works in minor units. Any leftover minor units go to the earliest
        parts, one each. BHD 10.000 / 3 -> 3.334, 3.333, 3.333.
        """
        if parts < 1:
            raise ValueError("parts must be at least 1")
        places = CURRENCY_PRECISION[self.currency]
        total_minor = int(self.amount.scaleb(places))
        base, remainder = divmod(abs(total_minor), parts)
        sign = -1 if total_minor < 0 else 1
        result = []
        for i in range(parts):
            minor = base + (1 if i < remainder else 0)
            result.append(Money(Decimal(sign * minor).scaleb(-places), self.currency))
        return result

    # --- display ------------------------------------------------------

    def __str__(self) -> str:
        return f"{self.currency} {self.amount:,}"


def total(amounts: list[Money], currency: str) -> Money:
    """Sum a list of Money, starting from zero in the given currency."""
    result = Money.zero(currency)
    for m in amounts:
        result = result + m
    return result
