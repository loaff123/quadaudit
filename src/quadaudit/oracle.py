"""Exact adjudication: represented results against exact mathematical references."""

from dataclasses import dataclass
from fractions import Fraction as F
from math import comb
from .model import Case, rational


@dataclass(frozen=True)
class Reference:
    lower: F | None
    upper: F | None
    validated: bool = True
    provenance: str = "exact rational antiderivative"

    def __post_init__(self):
        if self.validated:
            if self.lower is None or self.upper is None:
                raise ValueError("validated reference requires finite rational endpoints")
            object.__setattr__(self, "lower", rational(self.lower))
            object.__setattr__(self, "upper", rational(self.upper))
            if self.lower > self.upper:
                raise ValueError("reversed reference enclosure")


def audit_case(case: Case) -> dict:
    # Deliberately independent of Segment.integral and compose: expand into x powers.
    total = F(0)
    for s in case.segments:
        for k, c in enumerate(s.coefficients):
            for j in range(k + 1):
                global_c = c * comb(k, j) * (-s.left) ** (k - j) / (s.right - s.left) ** k
                total += global_c * (s.right ** (j + 1) - s.left ** (j + 1)) / F(j + 1)
    direct = case.integral()
    return {
        "valid": total == direct == case.reference,
        "local_integral": str(direct),
        "global_integral": str(total),
        "claimed_reference": str(case.reference),
    }


def adjudicate(
    value: F | None, reference: Reference, tolerance: F, estimated_error: F | None = None
) -> dict:
    tolerance = rational(tolerance)
    if tolerance < 0:
        raise ValueError("tolerance must be nonnegative")
    out = {
        "accuracy": "unscorable",
        "estimate": "missing",
        "error_lower": None,
        "error_upper": None,
        "zero_estimate": None,
        "tolerance": str(tolerance),
    }
    if estimated_error is not None and not isinstance(estimated_error, F):
        raise ValueError("estimate must be rational or absent")
    if estimated_error is not None and estimated_error < 0:
        out["estimate"] = "invalid"
    if value is None or not reference.validated:
        return out
    if not isinstance(value, F):
        raise ValueError("result must be an exact represented rational")
    lower = max(reference.lower - value, value - reference.upper, F(0))
    upper = max(abs(value - reference.lower), abs(value - reference.upper))
    out.update(
        error_lower=str(lower),
        error_upper=str(upper),
        accuracy="accurate"
        if upper <= tolerance
        else "inaccurate"
        if lower > tolerance
        else "unresolved",
    )
    if estimated_error is not None:
        if not isinstance(estimated_error, F):
            raise ValueError("estimate must be rational or absent")
        out["estimate"] = (
            "invalid"
            if estimated_error < 0
            else "underestimated"
            if estimated_error < lower
            else "sufficient"
            if estimated_error >= upper
            else "unresolved"
        )
        if estimated_error == 0:
            out["zero_estimate"] = (
                "exact_zero_error"
                if upper == 0
                else "confirmed_nonzero_error"
                if lower > 0
                else "unresolved_error"
            )
    return out


def nearest_binary(
    value: F, precision: int, min_exponent: int | None = None, max_abs: F | None = None
) -> F:
    """Nearest-even binary p-bit value; optional subnormal spacing and finite cap."""
    if value == 0:
        return F(0)
    sign = 1 if value > 0 else -1
    magnitude = abs(value)
    exponent = magnitude.numerator.bit_length() - magnitude.denominator.bit_length()
    if F(2) ** exponent > magnitude:
        exponent -= 1
    spacing_exponent = exponent - precision + 1
    if min_exponent is not None:
        spacing_exponent = max(spacing_exponent, min_exponent)
    unit = F(2) ** spacing_exponent
    result = round(magnitude / unit) * unit
    if max_abs is not None:
        result = min(result, max_abs)
    return sign * result
