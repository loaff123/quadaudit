"""Bounded rational piecewise-polynomial language. No executable input syntax."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from fractions import Fraction
from math import comb
import re
from types import MappingProxyType
from collections.abc import Mapping

MAX_BITS = 1024
MAX_SEGMENTS = 128
MAX_DEGREE = 32


def rational(value: str | int | Fraction) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
        raise ValueError("rational values must be integers or rational strings, never floats")
    if isinstance(value, str):
        if len(value) > 640 or not re.fullmatch(r"-?\d+(?:/[1-9]\d*)?", value):
            raise ValueError("invalid or oversized rational string")
    try:
        q = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("invalid rational") from exc
    if max(q.numerator.bit_length(), q.denominator.bit_length()) > MAX_BITS:
        raise ValueError("rational exceeds 1024-bit input limit")
    return q


def compose(
    coefficients: tuple[Fraction, ...], offset: Fraction, scale: Fraction
) -> tuple[Fraction, ...]:
    """Coefficients of p(offset + scale*u), exactly."""
    out = [Fraction(0)] * len(coefficients)
    for k, ck in enumerate(coefficients):
        for j in range(k + 1):
            out[j] += ck * comb(k, j) * offset ** (k - j) * scale**j
    return tuple(out)


@dataclass(frozen=True)
class Segment:
    left: Fraction
    right: Fraction
    coefficients: tuple[Fraction, ...]

    def __post_init__(self):
        object.__setattr__(self, "left", rational(self.left))
        object.__setattr__(self, "right", rational(self.right))
        object.__setattr__(self, "coefficients", tuple(rational(c) for c in self.coefficients))
        if (
            self.left >= self.right
            or not self.coefficients
            or len(self.coefficients) > MAX_DEGREE + 1
        ):
            raise ValueError("segments require positive width and degree <= 32")

    def evaluate(self, x: Fraction) -> Fraction:
        if isinstance(x, bool) or not isinstance(x, (Fraction, int)):
            raise ValueError("exact evaluation requires a Fraction or integer")
        x = Fraction(x)
        t = (x - self.left) / (self.right - self.left)
        y = Fraction(0)
        for c in reversed(self.coefficients):
            y = y * t + c
        return y

    def integral(self) -> Fraction:
        return (self.right - self.left) * sum(
            (c / Fraction(k + 1) for k, c in enumerate(self.coefficients)), Fraction(0)
        )

    def to_dict(self) -> dict:
        return {
            "left": str(self.left),
            "right": str(self.right),
            "coefficients": list(map(str, self.coefficients)),
        }


@dataclass(frozen=True)
class Case:
    case_id: str
    family: str
    segments: tuple[Segment, ...]
    reference: Fraction
    parameters: dict = field(default_factory=dict, compare=True)
    description: str = ""

    def __post_init__(self):
        if not isinstance(self.case_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}", self.case_id
        ):
            raise ValueError("invalid case identifier")
        if not isinstance(self.family, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,80}", self.family
        ):
            raise ValueError("invalid family identifier")
        object.__setattr__(self, "segments", tuple(self.segments))
        object.__setattr__(self, "reference", rational(self.reference))
        if not 1 <= len(self.segments) <= MAX_SEGMENTS or not all(
            isinstance(s, Segment) for s in self.segments
        ):
            raise ValueError("case requires 1..128 segments")
        if any(a.right != b.left for a, b in zip(self.segments, self.segments[1:])):
            raise ValueError("segments must be contiguous and ordered")
        if not isinstance(self.parameters, Mapping) or len(self.parameters) > 30:
            raise ValueError("parameters must be a bounded object")
        if any(
            not isinstance(k, str)
            or len(k) > 80
            or not isinstance(v, (str, int))
            or isinstance(v, bool)
            or len(str(v)) > 640
            for k, v in self.parameters.items()
        ):
            raise ValueError("parameters must contain bounded scalar metadata")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        if not isinstance(self.description, str) or len(self.description) > 4000:
            raise ValueError("description too long")

    @property
    def a(self):
        return self.segments[0].left

    @property
    def b(self):
        return self.segments[-1].right

    @property
    def knots(self):
        return (self.a,) + tuple(s.right for s in self.segments)

    def segment_at(self, x: Fraction) -> Segment:
        if not self.a <= x <= self.b:
            raise ValueError("abscissa outside domain")
        i = min(bisect_right(self.knots, x) - 1, len(self.segments) - 1)
        return self.segments[i]

    def evaluate_exact(self, x: Fraction) -> Fraction:
        if isinstance(x, bool) or not isinstance(x, (Fraction, int)):
            raise ValueError("exact evaluation requires a Fraction or integer")
        return self.segment_at(x).evaluate(x)

    def integral(self) -> Fraction:
        return sum((s.integral() for s in self.segments), Fraction(0))

    def to_dict(self) -> dict:
        return {
            "schema": "quadaudit.case.v1",
            "case_id": self.case_id,
            "family": self.family,
            "segments": [s.to_dict() for s in self.segments],
            "reference": str(self.reference),
            "parameters": dict(self.parameters),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Case:
        if not isinstance(d, dict) or d.get("schema") != "quadaudit.case.v1":
            raise ValueError("unsupported case schema")
        segs = d.get("segments")
        if not isinstance(segs, list) or not 1 <= len(segs) <= MAX_SEGMENTS:
            raise ValueError("invalid segment list")
        try:
            parsed = []
            for s in segs:
                cs = s["coefficients"]
                if not isinstance(cs, list) or not 1 <= len(cs) <= MAX_DEGREE + 1:
                    raise ValueError("invalid coefficient list")
                parsed.append(
                    Segment(rational(s["left"]), rational(s["right"]), tuple(map(rational, cs)))
                )
            return cls(
                d["case_id"],
                d["family"],
                tuple(parsed),
                rational(d["reference"]),
                d.get("parameters", {}),
                d.get("description", ""),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("malformed case") from exc

    def affine(self, offset: Fraction, scale: Fraction) -> Case:
        offset, scale = rational(offset), rational(scale)
        if scale <= 0:
            raise ValueError("affine scale must be positive")
        from .families import FAMILY_NAMES

        parameters = dict(self.parameters)
        if self.family in FAMILY_NAMES or {"offset", "width", "amplitude"} <= parameters.keys():
            parameters["offset"] = str(offset + scale * rational(parameters.get("offset", 0)))
            parameters["width"] = str(scale * rational(parameters.get("width", 1)))
        return Case(
            self.case_id + ".affine",
            self.family,
            tuple(
                Segment(offset + scale * s.left, offset + scale * s.right, s.coefficients)
                for s in self.segments
            ),
            self.reference * scale,
            parameters,
            self.description,
        )

    def scaled(self, amplitude: Fraction) -> Case:
        amplitude = rational(amplitude)
        from .families import FAMILY_NAMES

        parameters = dict(self.parameters)
        if self.family in FAMILY_NAMES or {"offset", "width", "amplitude"} <= parameters.keys():
            parameters["amplitude"] = str(amplitude * rational(parameters.get("amplitude", 1)))
        return Case(
            self.case_id + ".scaled",
            self.family,
            tuple(
                Segment(s.left, s.right, tuple(amplitude * c for c in s.coefficients))
                for s in self.segments
            ),
            self.reference * amplitude,
            parameters,
            self.description,
        )


def add_cases(a: Case, b: Case, case_id: str = "sum") -> Case:
    if (a.a, a.b) != (b.a, b.b):
        raise ValueError("sums require identical domains")
    knots = sorted(set(a.knots + b.knots))
    segs = []
    for left, right in zip(knots, knots[1:]):
        coeffs = []
        for case in (a, b):
            s = case.segment_at((left + right) / 2)
            coeffs.append(
                compose(
                    s.coefficients,
                    (left - s.left) / (s.right - s.left),
                    (right - left) / (s.right - s.left),
                )
            )
        n = max(map(len, coeffs))
        cs = tuple(
            sum((c[k] if k < len(c) else Fraction(0) for c in coeffs), Fraction(0))
            for k in range(n)
        )
        segs.append(Segment(left, right, cs))
    return Case(
        case_id,
        "composition",
        tuple(segs),
        a.reference + b.reference,
        {"left_case": a.case_id, "right_case": b.case_id},
        "Exact sum on aligned knots",
    )
