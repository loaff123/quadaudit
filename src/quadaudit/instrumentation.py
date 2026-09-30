"""Scalar-point accounting, atomic vector budget enforcement, bounded evidence."""

from fractions import Fraction as F
import math


class BudgetExceeded(RuntimeError):
    """A request was rejected before exceeding the evaluation cap."""


def mp_fraction(value) -> F:
    from mpmath.libmp import to_rational

    if value._mpf_[3] < 0:
        raise ValueError("nonfinite mpmath number")
    # Version-pinned adapter boundary; this preserves the stored binary number exactly.
    return F(*to_rational(value._mpf_))


def round_mpf(value: F, ctx):
    from mpmath.libmp import from_rational

    return ctx.make_mpf(from_rational(value.numerator, value.denominator, ctx.prec, "n"))


def represented(value) -> F:
    if isinstance(value, F):
        return value
    if hasattr(value, "_mpf_"):
        return mp_fraction(value)
    if not math.isfinite(float(value)):
        raise ValueError("nonfinite number")
    return F.from_float(float(value))


class BudgetCounter:
    def __init__(self, budget: int, trace_limit: int = 0):
        for value, lo, hi in ((budget, 1, 1000000), (trace_limit, 0, 10000)):
            if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
                raise ValueError("invalid budget or trace limit")
        self.budget = budget
        self.trace_limit = trace_limit
        self.evaluations = 0
        self.completed = 0
        self.attempted = 0
        self.calls = 0
        self.denied_batch = 0
        self.unique = set()
        self.trace = []

    def reserve(self, n: int):
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError("request size must be a nonnegative integer")
        self.calls += 1
        self.attempted += n
        if self.evaluations + n > self.budget:
            self.denied_batch = n
            raise BudgetExceeded(f"{n} requested with {self.budget - self.evaluations} remaining")

    def _evaluate(self, x, fn, exact=None):
        self.evaluations += 1
        xr = represented(x)
        self.unique.add(xr)
        y = fn(x)
        self.completed += 1
        if len(self.trace) < self.trace_limit:
            try:
                yr = represented(y)
            except (ValueError, OverflowError):
                yr = None
            error = abs(yr - exact(xr)) if exact and yr is not None else None

            def bounded_text(q):
                if q is None or max(q.numerator.bit_length(), q.denominator.bit_length()) > 4096:
                    return None
                return str(q)

            error_text = bounded_text(error)
            self.trace.append(
                {
                    "x": bounded_text(xr),
                    "y": bounded_text(yr),
                    "value_display": str(y) if yr is None else None,
                    "callback_error": error_text,
                    "callback_error_status": (
                        "omitted_size_limit"
                        if error is not None and error_text is None
                        else "recorded"
                        if error is not None
                        else "unavailable"
                    ),
                    "rational_text_limit_bits": 4096,
                }
            )
        return y

    def call_scalar(self, x, fn, exact=None):
        self.reserve(1)
        return self._evaluate(x, fn, exact)

    def call_array(self, x, fn, exact=None):
        import numpy as np

        x = np.asarray(x)
        self.reserve(x.size)
        values = [self._evaluate(v, fn, exact) for v in x.flat]
        return np.asarray(values, dtype=float).reshape(x.shape)

    def to_dict(self):
        return {
            "budget": self.budget,
            "evaluations": self.evaluations,
            "completed_evaluations": self.completed,
            "evaluation_semantics": "charged scalar callback invocations started; completed values counted separately",
            "attempted_evaluations": self.attempted,
            "callback_calls": self.calls,
            "unique_abscissae": len(self.unique),
            "denied_batch": self.denied_batch,
            "unused_budget": self.budget - self.evaluations,
            "trace_limit": self.trace_limit,
            "trace_truncated": self.evaluations > len(self.trace),
        }
