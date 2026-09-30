# Limitations and claims boundary

## What exact means

The mathematical cases are rational piecewise polynomials. Their integrals and represented numerical outputs can be compared exactly with rational arithmetic. This does not certify a floating-point solver for arbitrary functions or prove a global bound on rounding error in its callback. The core enclosure adjudicator is conservative when its supplied enclosure is valid; the preview does not generate transcendental enclosures.

The independent antiderivative checks and family identities reduce common implementation mistakes but can still share human/agent misunderstandings. Automated review is not human expert review, formal proof verification, or endorsement from a numerical library.

## Work and precision

The budget counts charged scalar callback invocations that began, including duplicates and calls that raise. Completed values are counted separately. Vector batches are refused atomically when too large. Native nfev may count differently and is preserved per piece.

The exact callback is intentionally expensive. mpmath guard precision, internal node construction, native algorithm arithmetic, Python call overhead, exact-rational evaluation, and trace overhead differ. Equal evaluation budgets are not equal total cost. Recorded durations describe this instrumented environment; they are not speed benchmarks.

Abrupt worker termination loses counters. Such rows retain an outcome and unknown work, never a fabricated zero. Memory limits are optional and platform-specific. Input-size, degree, segment, bit-length and trace bounds reduce accidental pathological workloads but do not establish a security sandbox.

## Solver contracts

mpmath does not return a success flag and is not given SciPy's absolute tolerance. Its value can be assessed against a common post-hoc target, but native stopping policies differ. SciPy tanh-sinh's documented restrictions make blind multi-segment cases exploratory in this preview, even where a more nuanced smoothness proof could admit some. Splitting supplies equal breakpoints, but introduces wrapper policies for local tolerance and aggregation.

The native-Horner mode can amplify coefficient conditioning. Never attribute that automatically to the integrator. Exact-rounded and native-Horner configurations must not be mixed silently.

## Study design

Seven construction archetypes are not a comprehensive numerical-analysis taxonomy. Affine, amplitude and compact-support modifiers do not create new independent families. Polynomial and spline family spaces overlap. The fixed 504-case sweep is designed to expose mechanisms, not sampled from production scientific workloads. Counts and percentages are descriptive, not real-world failure rates or estimates with generic confidence intervals.

No library is declared best. No new library defect or mathematical novelty is required or claimed. Historical examples motivate mechanisms, but our synthetic cases are original variants, not automatic reproductions of historical bugs.

## Unfinished external gates

Independent human numerical review and at least one upstream accepted contribution or independent adopter remain evidence to obtain. The observed Linux/macOS/Windows CI results and exact tested source are recorded in [release verification](release-verification.md); a CI configuration alone does not establish those results. Public hosting and package registries are separate release steps. No outside researchers have been contacted by this build.
