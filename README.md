# QuadAudit

[Live evidence explorer](https://quadaudit.lyczz.chatgpt.site/) · [Public source repository](https://github.com/loaff123/quadaudit)

**When an integration routine returns an answer, how much should you trust it?**

QuadAudit is an offline, solver-neutral research workbench for numerical quadrature reliability. It combines an original exact-reference corpus, explicit solver contracts, enforced function-evaluation caps, reproducible raw results, and an interactive evidence explorer.

**Status: 0.1.0a1 research preview.** The built-in mathematical targets are rational piecewise polynomials. This is not a new quadrature algorithm, a general verifier for arbitrary functions, or a claim that numerical integration failures are newly discovered. The project has automated independent review; independent human numerical review and research adoption have not yet been established.

## Quick start

Python 3.10 or newer. From a source checkout:

```sh
python -m pip install '.[solvers]'
quadaudit verify
quadaudit run --per-family 1 --output tutorial-run --trace 256
quadaudit report tutorial-run
```

Open `tutorial-run/report.html`. The report is standalone and works without a network connection. The run writes every outcome to `results.jsonl`, the exact problems to `corpus.jsonl`, effective settings to `protocol.json`, and hashes/environment/completion state to `manifest.json`.

The core package has no runtime dependencies. `pip install .` installs corpus, exact algebra, scoring, and reporting; SciPy and mpmath are optional comparison targets. Missing optional solvers produce explicit unsupported outcomes.

## What is different here?

- **Inspectable mathematical targets:** 504 frozen original cases across seven construction archetypes. Rational parameters and coefficients are serialized exactly
- **Independent reference checks:** local polynomial antiderivatives, separately implemented global-polynomial expansion, family identities, and independent formula point tests
- **Conservative adjudication:** exact represented solver results are compared to exact rational integrals or validated enclosures without rounding the reference to a float
- **Honest outcome axes:** returned value accuracy, native termination, error-estimate adequacy, applicability, and resource termination remain separate
- **Actual scalar-point caps:** repeated evaluations and vectorized probes count. Oversized batches are rejected before execution. Native evaluation counts are retained separately
- **Portable evidence:** JSONL, CSV, standalone HTML, and exportable Python regression fixtures

Existing work already studies estimator failure and provides quadrature test suites. Our intended contribution is a reusable, auditable protocol across independently maintained implementations. See [prior art](docs/prior-art.md), [mathematical families](docs/families.md), and [limitations](docs/limitations.md).

## A small example you can check by hand

For `f(x)=x²` on `[0,1]`, the exact integral is `1/3`. A binary64 result equal to Python's `1/3` is not exactly that rational number. QuadAudit retains its binary ratio and compares the small difference exactly.

For a narrow positive bump, a routine may sample only zero-valued regions and return zero with estimated error zero. That is a finite-information limitation, not automatically a library bug. A second track supplies identical mathematical breakpoints to every method and records the additional work.

## Comparison contracts

Initial adapters are SciPy `quad`, SciPy `tanhsinh`, and mpmath `quad(method='tanh-sinh')`.

The common target is a **post-hoc absolute accuracy target**. SciPy receives its absolute stopping tolerance with relative tolerance disabled. mpmath uses its own precision-driven stopping rule; there is no fabricated matching `epsabs` setting or success flag.

The blind track passes only the function and interval. The split track integrates each polynomial piece, using one shared evaluation budget and an equal division of SciPy's absolute tolerance. Summed error estimates are wrapper aggregates, not certified bounds. Blind multi-segment SciPy tanh-sinh runs are conservatively marked exploratory and excluded from in-contract summaries, because its documented domain excludes interior singularities and non-finite derivatives.

### Important: callback cost is different

The default `exact_rounded` callback evaluates the mathematical polynomial exactly at each represented abscissa, then rounds the value once to the solver's current numeric type. This isolates many callback-conditioning errors, but it is much more expensive than ordinary floating arithmetic. **Equal evaluation caps do not imply equal computational cost or a fair speed ranking.** Even native mpmath node-generation cost is not captured by evaluation counts.

The optional `native_horner` mode evaluates converted polynomial coefficients using ordinary arithmetic. These experiments remain separately labeled. At configured 80-bit output precision, mpmath 1.3.0 adds guard bits and ordinarily calls the function at 100 bits; the observed callback precision is recorded.

## Commands

```sh
quadaudit corpus --output cases.jsonl
quadaudit verify cases.jsonl
quadaudit explain beta-000
quadaudit run --case beta-000 --trace 1000 --output one-case
quadaudit run --methods scipy_quad --tracks blind,split --budget 1024 --atol 1e-8 --output capped-run
quadaudit report capped-run
quadaudit csv capped-run/results.jsonl --output capped-run/results.csv
quadaudit export-regression beta-000 --output beta_case.py
```

Output directories containing existing raw results are never overwritten. A fresh directory is required. Hard wall-clock termination uses replaceable subprocesses. A killed worker's exact work count is unavailable and is reported as unknown, never zero. An optional `--memory-mb` cap uses `RLIMIT_AS` where supported; enforcement status is recorded. A Linux address-space cap is not a portable resident-memory guarantee.

## Reproduce and test

```sh
python -m unittest discover -s tests -v
python corpus/freeze.py
quadaudit run --output experiments/my-reproduction
quadaudit report experiments/my-reproduction
```

The frozen protocol is in `corpus/protocol.json`. Raw preview measurements and their interpretation belong in `experiments/` and `docs/reproducibility.md`; do not infer results from this README. The corpus is a designed stress sweep, not a random sample of real scientific workloads. Its percentages are not population failure probabilities. Tighter tolerances, more precision, and splitting can change work and applicability as well as accuracy.

## Scope and roadmap

Included now: finite, real, scalar, one-dimensional integrals; exact rational piecewise polynomials; audited references; bounded experiments; offline reports.

Deferred: transcendental interval oracles, arbitrary user callables, multidimensional integration, probabilistic quadrature, automated algorithm selection, and claims of external adoption. FLINT/Arb would be valuable reference infrastructure for future families, but its analyticity requirements need their own review.

Contributions are welcome after reading [CONTRIBUTING.md](CONTRIBUTING.md). The first goal is trustworthy evidence useful to upstream numerical libraries, not a leaderboard. No telemetry, accounts, paid services, or GPU are required.

License: BSD-3-Clause for original source and synthetic fixtures. Third-party numerical libraries retain their own licenses. See [LICENSE](LICENSE).
