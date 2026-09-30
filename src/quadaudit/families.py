"""Original rational constructions for seven classical polynomial archetypes.

Coordinates use x = offset + width*t, 0 <= t <= 1.  References are
family identities, not values produced by integrating stored coefficients.
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction as F
from math import comb, factorial

from .model import Case, Segment, rational

FAMILY_NAMES = (
    "power",
    "beta",
    "legendre",
    "chebyshev_even",
    "staircase",
    "hinge",
    "cardinal_bspline",
)
MAX_FAMILY_DEGREE = 16
MAX_FAMILY_SEGMENTS = 64
_COMMON = {"offset", "width", "amplitude"}
_SPECIFIC = {
    "power": {"n"},
    "beta": {"p", "q", "support_left", "support_right"},
    "legendre": {"n"},
    "chebyshev_even": {"n"},
    "staircase": {"breaks", "heights"},
    "hinge": {"m", "c"},
    "cardinal_bspline": {"degree", "support_left", "support_right"},
}
_DESCRIPTIONS = {
    "power": "Power control: amplitude*t^n on the affine unit interval.",
    "beta": "Beta-polynomial profile, optionally restricted to an explicit compact support.",
    "legendre": "Shifted Legendre polynomial: amplitude*P_n(2*t-1), with zero signed area.",
    "chebyshev_even": "Even shifted Chebyshev polynomial: amplitude*T_(2*n)(2*t-1).",
    "staircase": "Rational rectangle sum with right-hand values at interior knots.",
    "hinge": "Truncated-power hinge: amplitude*max(t-c,0)^m.",
    "cardinal_bspline": "Cardinal B-spline profile with explicit zero regions outside support.",
}


def _integer(value, name, lower, upper):
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in [{lower}, {upper}]")
    return value


def _rational_list(value, name):
    if not isinstance(value, str) or len(value) > 640:
        raise ValueError(f"{name} must be a bounded comma-separated rational string")
    try:
        return tuple(rational(v) for v in value.split(","))
    except ValueError as exc:
        raise ValueError(f"invalid {name}") from exc


def _parameters(family, parameters):
    if family not in FAMILY_NAMES:
        raise ValueError(f"unknown family: {family}")
    if not isinstance(parameters, Mapping) or set(parameters) - (_COMMON | _SPECIFIC[family]):
        raise ValueError("unknown family parameters")
    p = dict(parameters)
    for name, default in [("offset", 0), ("width", 1), ("amplitude", 1)]:
        p[name] = str(rational(p.get(name, default)))
    if F(p["width"]) <= 0:
        raise ValueError("width must be positive")
    required = _SPECIFIC[family] - {"support_left", "support_right"}
    if not required <= p.keys():
        raise ValueError("missing family parameters")
    if family in ("power", "legendre", "chebyshev_even"):
        p["n"] = _integer(
            p["n"],
            "n",
            0 if family == "power" else 1,
            8 if family == "chebyshev_even" else MAX_FAMILY_DEGREE,
        )
    if family == "beta":
        p["p"] = _integer(p["p"], "p", 1, MAX_FAMILY_DEGREE - 1)
        p["q"] = _integer(p["q"], "q", 1, MAX_FAMILY_DEGREE - 1)
        if p["p"] + p["q"] > MAX_FAMILY_DEGREE:
            raise ValueError("beta degree exceeds 16")
    if family == "hinge":
        p["m"] = _integer(p["m"], "m", 1, MAX_FAMILY_DEGREE)
        p["c"] = str(rational(p["c"]))
        if not 0 < F(p["c"]) < 1:
            raise ValueError("hinge requires 0 < c < 1")
    if family == "cardinal_bspline":
        p["degree"] = _integer(p["degree"], "degree", 1, MAX_FAMILY_DEGREE)
    if family in ("beta", "cardinal_bspline"):
        for name, default in [("support_left", 0), ("support_right", 1)]:
            p[name] = str(rational(p.get(name, default)))
        if not 0 <= F(p["support_left"]) < F(p["support_right"]) <= 1:
            raise ValueError("support must have positive width inside [0, 1]")
    if family == "staircase":
        breaks = _rational_list(p["breaks"], "breaks")
        heights = _rational_list(p["heights"], "heights")
        if not 1 <= len(heights) <= MAX_FAMILY_SEGMENTS or len(breaks) != len(heights) + 1:
            raise ValueError("staircase requires 1..64 heights and one more breakpoint")
        if breaks[0] != 0 or breaks[-1] != 1 or any(a >= b for a, b in zip(breaks, breaks[1:])):
            raise ValueError("staircase breakpoints must strictly partition [0, 1]")
        p["breaks"] = ",".join(map(str, breaks))
        p["heights"] = ",".join(map(str, heights))
    return p


def _identity(family, p):
    """Reference from a closed-form family identity in normalized coordinates."""
    if family == "power":
        area = F(1, p["n"] + 1)
    elif family == "beta":
        area = (F(p["support_right"]) - F(p["support_left"])) * F(
            factorial(p["p"]) * factorial(p["q"]), factorial(p["p"] + p["q"] + 1)
        )
    elif family == "legendre":
        area = F(0)
    elif family == "chebyshev_even":
        area = F(1, 1 - 4 * p["n"] ** 2)
    elif family == "staircase":
        breaks = tuple(map(F, p["breaks"].split(",")))
        heights = tuple(map(F, p["heights"].split(",")))
        area = sum(
            ((right - left) * height for left, right, height in zip(breaks, breaks[1:], heights)),
            F(0),
        )
    elif family == "hinge":
        area = (1 - F(p["c"])) ** (p["m"] + 1) / (p["m"] + 1)
    elif family == "cardinal_bspline":
        area = (F(p["support_right"]) - F(p["support_left"])) / (p["degree"] + 1)
    else:
        raise ValueError(f"unknown family: {family}")
    return F(p["amplitude"]) * F(p["width"]) * area


def family_reference(case: Case) -> F:
    """Independently compute the claimed family's area from its scalar parameters."""
    return _identity(case.family, _parameters(case.family, case.parameters))


def _linear_multiply(poly, intercept, slope):
    out = [F(0)] * (len(poly) + 1)
    for k, value in enumerate(poly):
        out[k] += intercept * value
        out[k + 1] += slope * value
    return out


def _orthogonal_coefficients(n, legendre):
    # Three-term recurrences in t; tests use distinct closed polynomial formulas.
    older, previous = [F(1)], [F(-1), F(2)]
    if n == 0:
        return tuple(older)
    for k in range(2, n + 1):
        current = _linear_multiply(previous, F(-1), F(2))
        first = F(2 * k - 1, k) if legendre else F(2)
        second = F(k - 1, k) if legendre else F(1)
        current = [first * value for value in current]
        for j, value in enumerate(older):
            current[j] -= second * value
        older, previous = previous, current
    return tuple(previous)


def build_case(family: str, parameters: Mapping, case_id: str | None = None) -> Case:
    """Build a bounded exact case; all numeric inputs are integers/rational strings.

    Common parameters are offset=0, width=1, amplitude=1.  The compact-support
    families also accept support_left=0 and support_right=1 in normalized t.
    Family-specific parameters are n; p,q; m,c; degree; or breaks,heights.
    """
    p = _parameters(family, parameters)
    pieces = []
    if family == "power":
        pieces.append((F(0), F(1), (F(0),) * p["n"] + (F(1),)))
    elif family == "beta":
        coefficients = [F(0)] * (p["p"] + p["q"] + 1)
        for k in range(p["q"] + 1):
            coefficients[p["p"] + k] = F((-1) ** k * comb(p["q"], k))
        pieces.append((F(p["support_left"]), F(p["support_right"]), tuple(coefficients)))
    elif family in ("legendre", "chebyshev_even"):
        degree = p["n"] if family == "legendre" else 2 * p["n"]
        pieces.append((F(0), F(1), _orthogonal_coefficients(degree, family == "legendre")))
    elif family == "staircase":
        breaks = tuple(map(F, p["breaks"].split(",")))
        heights = tuple(map(F, p["heights"].split(",")))
        pieces.extend(
            (left, right, (height,)) for left, right, height in zip(breaks, breaks[1:], heights)
        )
    elif family == "hinge":
        c = F(p["c"])
        pieces = [(F(0), c, (F(0),)), (c, F(1), (F(0),) * p["m"] + ((1 - c) ** p["m"],))]
    elif family == "cardinal_bspline":
        d = p["degree"]
        left, right = F(p["support_left"]), F(p["support_right"])
        h = (right - left) / (d + 1)
        # N_d(u) = 1/d! sum_j (-1)^j C(d+1,j) (u-j)_+^d.
        # On the kth unit span, u=k+v. Expand only the active truncated terms.
        for k in range(d + 1):
            coefficients = tuple(
                sum(
                    (
                        F((-1) ** j * comb(d + 1, j) * comb(d, r), factorial(d))
                        * F(k - j) ** (d - r)
                        for j in range(k + 1)
                    ),
                    F(0),
                )
                for r in range(d + 1)
            )
            pieces.append((left + k * h, left + (k + 1) * h, coefficients))
    if pieces[0][0] > 0:
        pieces.insert(0, (F(0), pieces[0][0], (F(0),)))
    if pieces[-1][1] < 1:
        pieces.append((pieces[-1][1], F(1), (F(0),)))
    offset, width, amplitude = (F(p[k]) for k in ("offset", "width", "amplitude"))
    segments = tuple(
        Segment(
            offset + width * left,
            offset + width * right,
            tuple(amplitude * c for c in coefficients),
        )
        for left, right, coefficients in pieces
    )
    return Case(case_id or family, family, segments, _identity(family, p), p, _DESCRIPTIONS[family])
