# QuadAudit: exact-reference quadrature reliability workbench

Status: initial research-preview architecture, 2026-09-30. This is not a claim of mathematical novelty, external expert certification, or research adoption.

## Intent and success

Build useful, reusable numerical-research infrastructure through correctness, transparent experiments, and maintenance. A successful preview lets someone install a small Python package, inspect a frozen problem, run several quadrature implementations with bounded work, independently verify the oracle, and understand what an inaccurate return or underestimated error actually means.

The full research brief's 12-family, external-review, multi-OS and adoption goals remain later gates. This preview prioritizes a smaller mathematically reviewable domain and publishes unmet gates explicitly. An automated independent code/mathematics review is useful but is not an external numerical analyst's endorsement.

## Alternatives considered

1. **Exact-reference workbench (selected).** A restricted rational piecewise-polynomial language, independent exact oracle audit, solver adapters, exact adjudication, immutable corpus, and explanatory reports. Removes transcendental-oracle ambiguity and provides a reusable protocol.
2. **Broad certified transcendental corpus.** Add FLINT/Arb integration, Gaussian and rational-peak closed forms immediately. Larger real-world coverage, but branch analyticity, ball extraction, license and platform packaging are additional correctness risks. Defer until separately reviewed.
3. **Only contribute cases to SciPy.** Valuable and ultimately encouraged, but cannot host cross-implementation metadata, uniform outcome semantics, or the full portable corpus as naturally. Keep fixture export a first-class feature so this project can serve upstream test suites rather than compete with them.

## Relationship to prior work

Gonnet already reviews error estimators and compares parameterized families with test batteries. SciPy already tests integration accuracy and error estimates. Burkardt TEST_INT distributes many integrands with references. mpmath already documents missed features and the utility of subdivision. The proposed value is a compact audited format and executable protocol combining these concerns, not the invention of reliability tests, adversarial curves, quadrature, or error calibration. The name QuadAudit is provisional; a bounded web search found no exact quadrature project match, not trademark clearance.

Primary sources inspected:
- https://arxiv.org/html/1003.4629
- https://arxiv.org/pdf/1006.3962
- https://docs.scipy.org/doc/scipy/tutorial/integrate.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.quad.html
- https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.tanhsinh.html
- https://github.com/mpmath/mpmath/blob/1.3.0/mpmath/calculus/quadrature.py
- https://people.math.sc.edu/burkardt/cpp_src/test_int/test_int.html
- https://python-flint.readthedocs.io/en/latest/acb.html#flint.acb.integral

No third-party test code, prose, figures, or datasets will be copied. Synthetic formulas and rational arithmetic are authored here. Dependency/source provenance is recorded separately.

## Mathematical problem contract

A Case has a stable identifier, family, rational parameters, finite rational domain [a,b] with a<b, contiguous ordered segments, rational local polynomial coefficients, regularity metadata, and an exact rational reference integral. On segment [l,r], p(x)=sum(c_k t^k), t=(x-l)/(r-l). Segments cover the complete domain, including explicit zero regions. Interior knots use the right-hand branch; the final endpoint uses the final segment. Values at a finite number of knots do not affect the exact integral.

The primary reference is sum over segments of (r-l) sum(c_k/(k+1)). A separate audit converts local coefficients into global-x monomials with binomial expansion and integrates endpoint powers. Family-level closed-form area identities provide a third check. Independent tests must cover zero, signed areas, cancellation, and transformations. None of these checks substitutes high-precision quadrature agreement for a proof.

Affine coordinate changes and amplitude scaling preserve the integral by explicit formulas and remain transformations, not additional families. Positive or negative orientation changes must be normalized carefully; the initial public affine operator accepts positive scale only. Sums align all knots and transform coefficients exactly.

The initial corpus has a modest set of mechanism families, with at least 504 frozen parameterized cases only if all independently checked. Candidate families include power controls, beta-polynomial profiles, Legendre cancellation, even Chebyshev oscillation, rational staircases, truncated-power hinges, and cardinal B-splines. The final number and taxonomy must not imply that 504 cases are 504 independent phenomena.

## Callback semantics: separate integration from evaluation error

The primary callback mode is exact-rounded: convert each supplied finite binary floating point abscissa into its exact rational value, evaluate the polynomial in Fraction arithmetic, and round the resulting rational once into the solver's current numeric type. This is slower than normal callbacks; work comparisons therefore use evaluated abscissae, not claims about solver speed. The mathematical oracle still measures error against the intended real-valued function, but the callback avoids coefficient conversion and Horner cancellation as confounders apart from the documented final rounding.

A separate explicitly labeled native-Horner mode may evaluate converted coefficients and can demonstrate conditioning effects. It never silently mixes with exact-rounded outcomes. Trace auditing compares sampled callback outputs with exact values; such point checks are not a global bound on callback error.

Binary64 endpoints and knots must be exactly representable and distinct for binary64 adapters, or the configuration is unsupported. mpmath endpoints must be exactly representable at configured precision. The frozen corpus uses dyadic breakpoints. Nonfinite values are outcomes, not silently coerced data.

## Exact adjudication

The core also accepts validated rational reference enclosures [L,U], even though built-in preview cases use L=U. For exact represented result q:
- lower error = max(L-q, q-U, 0)
- upper error = max(abs(q-L),abs(q-U))
- accurate if upper <= target absolute tolerance
- inaccurate if lower > target absolute tolerance
- unresolved otherwise

All threshold comparisons use rational arithmetic, not float conversion. Unknown/unvalidated references are unscorable. For reported nonnegative error e, confirmed underestimation means e<lower; sufficient for this case means e>=upper; otherwise unresolved. A zero estimate is labeled separately, including zero/zero, and no arbitrary epsilon is introduced. Invalid negative/nonfinite estimates, nonfinite results, exceptions, budget exhaustion, timeout, unsupported configurations, and missing estimates have distinct states.

Termination, accuracy, and estimate adequacy are separate axes. mpmath quad has no native success flag; a return does not become a fabricated convergence success. Tolerance targets are common post-hoc absolute accuracy targets. SciPy receives its documented absolute stopping tolerance and zero relative tolerance. mpmath uses configured precision and maximum degree, not a nonexistent matching epsabs parameter. Cross-method output states make that asymmetry explicit.

## Adapter and work contract

Initial methods: SciPy quad, SciPy tanhsinh, mpmath tanh-sinh. mpmath Gauss-Legendre is optional after the main three are sound. Each result preserves library/version, numeric precision, every effective setting, native status/warnings, exact binary result and error where available, and requested/evaluated callback counts.

A single shared budget wrapper counts scalar abscissae, including repeated points and probes. Vectorized batches are charged by size; a batch exceeding the remaining budget is rejected before evaluating any member. Record completed evaluations, attempted evaluations including the rejected request, denied batch size, call count, and native-reported nfev separately. No claim that native nfev and wrapper count must agree.

The blind track reveals only f,a,b. Any unsplit piecewise case whose derivatives fail to exist at interior knots is outside the SciPy tanhsinh documented domain: retain it as an explicitly exploratory diagnostic and exclude it from in-contract scores. In the preview, conservatively treat every multi-segment case as exploratory for blind tanhsinh; the split track is in-contract because each piece is a polynomial. Applicability is stored per run and is a separate filter from numerical accuracy. The structure-informed track partitions at all case knots for every method and records this same information. The total budget is shared across pieces; SciPy's absolute target is divided equally between pieces. Piece values and error estimates are retained, and aggregation rounding is explicit. Split methods are adapter policies, not native single-call methods. Return-only statuses remain return-only after aggregation.

Workers run in reusable isolated subprocesses. A parent wall-clock timeout terminates and replaces a worker rather than trusting callback polling to stop a stalled solver. An optional memory ceiling is enforced only where supported and reported honestly elsewhere. Case/degree/segment/integer-bit/trace limits prevent unbounded artifact inputs. No untrusted Python evaluation or arbitrary callable loading is included.

## Architecture and interface

- model.py: validated rational case/segment schema, exact operations and canonical serialization
- oracle.py: exact/enclosed references, independent global-polynomial audit, conservative classification
- families.py/corpus.py: original parameterized generators, frozen canonical JSONL, checksums and manifest
- instrumentation.py: budget wrapper, bounded trace and callback diagnostics
- adapters.py: thin native-library contracts with full status preservation
- runner.py: isolated execution and experiment manifests
- analysis.py: per-family outcome summaries, estimator adequacy and paired-track comparisons
- report.py: offline HTML with embedded SVG plots, sample locations, filtering, provenance and accessible detail views
- cli.py: corpus, verify, run, report, explain, and export-regression commands

Core install has no runtime dependencies. Numerical adapters are extras. JSON is authoritative; CSV is a convenience export. No hosted service, tracking, account, GPU, network-after-install, or new integration algorithm is in scope.

## Frozen experiment protocol

Before main execution freeze the canonical corpus, protocol, library pins, targets, budgets, settings, and aggregation rules in version control. Demonstration cases are documented as development cases. Parameterized sweeps are deterministic designed stress tests, not random samples from scientific workloads. Publish all raw outcomes, exclusions, failed/budget-limited configurations, and unresolved classifications. Summaries group by family and method; report denominator choices. Family-macro summaries supplement but never conceal counts.

A tractable preview run uses all frozen cases, three methods, blind and split tracks, one preregistered absolute target, and fixed budget. A separately labeled small development sweep studies tolerance and budget changes. No claim of general software superiority or real-world failure probabilities follows. If the study cannot finish within bounded resources, publish a partial manifest rather than silently pruning hard cases.

## Verification and release gates

1. Exact unit cases with hand-derived areas; independent symbolic audit for every frozen case
2. Mutation/negative tests of parameters, reference corruption, rational result parsing, invalid enclosures, boundary thresholds, and zero estimates
3. Instrumentation tests for scalar, vector, duplicate, rejected-batch, split shared-budget, and native-nfev accounting
4. Fake worker timeout/error tests plus real adapter smoke tests, preserving mpmath's lack of success state
5. Seeded/canonical corpus regeneration must produce identical bytes and hash
6. Independent numerical/code review and resolution of critical findings; clearly label review as automated if it is
7. Clean environment wheel/source installation, CLI tutorial, actual tests and lint/build outputs
8. Linux/macOS/Windows CI definition; do not claim remote CI or untested operating systems passed
9. Main experiment raw output and offline report verified; a technical limitations/reproducibility document
10. Publication requires verified source, explicit audience, and actual release checks; unrun remote CI remains unverified

A release candidate can be useful before independent human adoption. It is not counted as a completed public project until publication and verification. Mature research use requires independent review and maintenance beyond the preview.
