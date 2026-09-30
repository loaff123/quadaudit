"""Thin native solver contracts; return, accuracy, applicability remain separate."""

from __future__ import annotations
from dataclasses import dataclass, asdict
from fractions import Fraction as F
import math
import time
import sys
import warnings
from .model import Case, rational
from .oracle import Reference, adjudicate, audit_case, nearest_binary
from .instrumentation import BudgetCounter, BudgetExceeded, represented, round_mpf

METHODS = ("scipy_quad", "scipy_tanhsinh", "mpmath_tanhsinh")


@dataclass(frozen=True)
class RunConfig:
    method: str = "scipy_quad"
    track: str = "blind"
    tolerance: str = "1/100000000"
    budget: int = 4096
    trace_limit: int = 0
    precision: int = 80
    maxlevel: int = 10
    maxdegree: int = 8
    callback_mode: str = "exact_rounded"

    def __post_init__(self):
        if self.method not in METHODS or self.track not in ("blind", "split"):
            raise ValueError("unknown method or track")
        tol = rational(self.tolerance)
        if tol <= 0 or not math.isfinite(float(tol)) or float(tol) == 0:
            raise ValueError(
                "tolerance must be finite positive and binary64-representable as nonzero"
            )
        object.__setattr__(self, "tolerance", str(tol))
        for name, lo, hi in [
            ("budget", 1, 1000000),
            ("trace_limit", 0, 10000),
            ("precision", 20, 512),
            ("maxlevel", 2, 15),
            ("maxdegree", 1, 12),
        ]:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
                raise ValueError(f"{name} outside supported range {lo}..{hi}")
        if self.callback_mode not in ("exact_rounded", "native_horner"):
            raise ValueError("unknown callback mode")


def target_diagnostics(case: Case, config: RunConfig) -> dict:
    is_mp = config.method.startswith("mpmath")
    precision = config.precision if is_mp else 53
    nearest = nearest_binary(
        case.reference,
        precision,
        min_exponent=None if is_mp else -1074,
        max_abs=None if is_mp else F.from_float(sys.float_info.max),
    )
    lower = abs(nearest - case.reference)
    tau = rational(config.tolerance)
    return {
        "output_precision_bits": precision,
        "closest_representable_error": str(lower),
        "target_attainable": lower <= tau,
        "zero_meets_target": abs(case.reference) <= tau,
        "method": "nearest output-grid value to exact reference; no solver behavior inferred",
    }


def empty_result(case: Case, config: RunConfig) -> dict:
    return {
        "schema": "quadaudit.result.v1",
        "target_diagnostics": target_diagnostics(case, config),
        "case_id": case.case_id,
        "family": case.family,
        "method": config.method,
        "track": config.track,
        "config": asdict(config),
        "applicability": "exploratory"
        if config.method == "scipy_tanhsinh" and config.track == "blind" and len(case.segments) > 1
        else "in_contract",
        "applicability_note": "Blind multi-segment SciPy tanhsinh runs conservatively excluded from in-contract summaries."
        if config.method == "scipy_tanhsinh" and config.track == "blind" and len(case.segments) > 1
        else "",
        "outcome": "pending",
        "native_success": None,
        "value": None,
        "error_estimate": None,
        "adjudication": adjudicate(
            None, Reference(case.reference, case.reference), rational(config.tolerance)
        ),
        "work": {},
        "pieces": [],
        "trace": [],
        "warnings": [],
        "versions": {},
        "elapsed_seconds": None,
    }


def run_case(case: Case, config: RunConfig) -> dict:
    result = empty_result(case, config)
    counter = BudgetCounter(config.budget, config.trace_limit)
    started = time.perf_counter()
    tau = rational(config.tolerance)
    callback_precisions = set()
    try:
        if not audit_case(case)["valid"]:
            result.update(
                outcome="invalid_reference",
                message="Independent algebra audit rejected the stored reference",
            )
            return result
        is_mp = config.method.startswith("mpmath")
        ctx = None
        if is_mp:
            import mpmath

            ctx = mpmath.mp.clone()
            ctx.prec = config.precision
            result["versions"]["mpmath"] = mpmath.__version__

            def convert(x):
                return round_mpf(x, ctx)
        else:
            import scipy
            import scipy.integrate as integrate

            result["versions"]["scipy"] = scipy.__version__
            convert = float
        for x in case.knots:
            if represented(convert(x)) != x:
                result.update(
                    outcome="unsupported",
                    message="A rational breakpoint is not exactly representable at solver precision",
                )
                return result
        intervals = list(case.segments) if config.track == "split" else [None]
        values = []
        estimates = []
        successes = []
        for seg in intervals:
            left, right = (seg.left, seg.right) if seg else (case.a, case.b)
            exact = seg.evaluate if seg else case.evaluate_exact

            def raw(x):
                callback_precisions.add(ctx.prec if is_mp else 53)
                xr = represented(x)
                if not left <= xr <= right:
                    raise ValueError("solver sampled outside declared interval")
                if config.callback_mode == "exact_rounded":
                    y = exact(xr)
                    return round_mpf(y, ctx) if is_mp else float(y)
                s = seg or case.segment_at(xr)
                t = (x - convert(s.left)) / convert(s.right - s.left)
                y = convert(F(0))
                for c in reversed(s.coefficients):
                    y = y * t + convert(c)
                return y

            f = (
                (lambda x: counter.call_array(x, raw, exact))
                if config.method == "scipy_tanhsinh"
                else (lambda x: counter.call_scalar(x, raw, exact))
            )
            piece_tau = tau / len(intervals)
            native_tol = float(piece_tau)
            piece = {
                "left": str(left),
                "right": str(right),
                "tolerance_allocation": str(piece_tau),
                "native_atol_exact": str(F.from_float(native_tol)) if not is_mp else None,
                "endpoint_policy": "local_polynomial_extension" if seg else "right_branch",
            }
            before = counter.evaluations
            with warnings.catch_warnings(record=True) as captured:
                warnings.simplefilter("always")
                if config.method == "scipy_quad":
                    out = integrate.quad(
                        f,
                        float(left),
                        float(right),
                        epsabs=native_tol,
                        epsrel=0,
                        limit=200,
                        full_output=1,
                    )
                    val, err, info = out[:3]
                    ok = len(out) == 3
                    piece.update(
                        native_status="success" if ok else "warning",
                        native_message=out[3] if not ok else "",
                        native_nfev=int(info["neval"]),
                        native_settings={"limit": 200, "epsrel": 0, "epsabs": native_tol},
                    )
                elif config.method == "scipy_tanhsinh":
                    out = integrate.tanhsinh(
                        f,
                        float(left),
                        float(right),
                        atol=native_tol,
                        rtol=0,
                        minlevel=2,
                        maxlevel=config.maxlevel,
                    )
                    val, err, ok = float(out.integral), float(out.error), bool(out.success)
                    piece.update(
                        native_status=int(out.status),
                        native_nfev=int(out.nfev),
                        native_settings={
                            "atol": native_tol,
                            "rtol": 0,
                            "minlevel": 2,
                            "maxlevel": config.maxlevel,
                        },
                    )
                else:
                    val, err = ctx.quad(
                        f,
                        [convert(left), convert(right)],
                        method="tanh-sinh",
                        error=True,
                        maxdegree=config.maxdegree,
                    )
                    ok = None
                    piece.update(
                        native_status="returned_no_success_flag",
                        native_nfev=None,
                        native_settings={
                            "precision_bits": config.precision,
                            "maxdegree": config.maxdegree,
                            "stopping_policy": "mpmath native precision-driven criterion; no requested atol",
                        },
                    )
                result["warnings"].extend(str(w.message) for w in captured)
            piece["evaluations"] = counter.evaluations - before
            try:
                q = represented(val)
            except (ValueError, OverflowError):
                result.update(outcome="nonfinite", message="Nonfinite solver value")
                piece.update(value_display=str(val), error_display=str(err))
                result["pieces"].append(piece)
                return result
            try:
                e = represented(err)
                valid_estimate = e >= 0
            except (ValueError, OverflowError):
                e = None
                valid_estimate = False
            piece.update(
                value=str(q),
                error_estimate=str(e) if e is not None else None,
                error_display=str(err),
                estimate_valid=valid_estimate,
                native_success=ok,
            )
            result["pieces"].append(piece)
            values.append(q)
            estimates.append(e)
            successes.append(ok)
        exact_sum = sum(values, F(0))
        # The wrapper returns an explicitly rounded sum; estimate aggregation is an exact sum.
        q = represented(round_mpf(exact_sum, ctx)) if is_mp else F.from_float(float(exact_sum))
        estimate_valid = all(e is not None and e >= 0 for e in estimates)
        e = sum(estimates, F(0)) if estimate_valid else None
        result.update(
            outcome="returned",
            value=str(q),
            error_estimate=str(e) if e is not None else None,
            native_success=None if is_mp else all(successes),
            aggregation={
                "policy": "exact sum of represented pieces, then round once",
                "rounding_error": str(abs(q - exact_sum)),
                "estimate_policy": "exact sum of native estimated errors; not a certified bound",
            },
            adjudication=adjudicate(q, Reference(case.reference, case.reference), tau, e),
        )
        if not estimate_valid:
            result["adjudication"]["estimate"] = "invalid"
    except ImportError as exc:
        result.update(outcome="unsupported", message=f"Missing optional dependency: {exc}")
    except BudgetExceeded as exc:
        result.update(outcome="budget_exhausted", message=str(exc))
    except Exception as exc:
        result.update(outcome="exception", message=f"{type(exc).__name__}: {exc}")
    finally:
        result["work"] = counter.to_dict()
        result["trace"] = counter.trace
        result["elapsed_seconds"] = time.perf_counter() - started
        result["callback_precision_bits_observed"] = sorted(callback_precisions)
        result["output_precision_bits"] = (
            config.precision if config.method.startswith("mpmath") else 53
        )
    return result
