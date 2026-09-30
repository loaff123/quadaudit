# Automated numerical review record

An independent automated reviewer inspected the initial mathematical kernel, adapters and instrumentation before the main frozen run. This is not external human numerical certification.

The reviewer ran 180 independent exact Lagrange-integration/transformation/aligned-sum trials, 9,520 exact enclosure combinations, and 5,000 nearest-neighbor 53-bit rounding trials. Those sampled checks found no errors in the finite algebra and adjudication exercised.

It did find consequential implementation errors. Every item below has a failing-then-passing regression in tests/test_review_regressions.py:

- mpmath special-value conversion could map infinity to zero: reject all nonfinite special representations before rational conversion
- Invalid error estimates erased finite value accuracy: parse these axes independently
- A negative piece estimate could disappear in a positive aggregate: any invalid piece invalidates aggregate estimate adequacy
- Trace capture could alter nonfinite callback behavior: record nonfinite evidence without changing native control flow
- Counts called completed included failed callbacks: distinguish charged/started and completed scalar evaluations
- Case metadata could be mutated through an alias: defensive immutable mapping and copy-on-serialization
- Exact evaluators silently accepted floats: reject floating input without imposing serialization bit limits on runtime Fractions
- mpmath guard precision was hidden: record actual callback precision separately from output precision
- Primitive budget inputs were not validated: enforce supported integer ranges
- Invalid estimates became missing without a reference: preserve validity independently of reference availability

The initial defects were caught before frozen main-study execution. The source history and regression tests preserve their existence and repairs. A further independent whole-project automated review was completed and led to the hardening described below.

## Independent corpus reconstruction

A second fresh automated reviewer reconstructed all 2,664 segment polynomials independently, using Rodrigues differentiation for Legendre polynomials and polynomial Cox–de Boor recurrence for B-splines. It checked 504 symbolic areas, 7,992 exact local point values, 3,168 knot/convention/representability properties, and all 504 function identities with a derivative-jump canonicalization distinct from the implementation fingerprint. All checks passed and frozen hashes remained unchanged.

The reviewer found stale known-family metadata in the public affine/amplitude transformations, including manually constructed cases using implicit default modifiers. Regression tests now preserve family parameters for both canonical and minimal cases.

It also found an interpretation constraint: 11 exact references cannot meet the common 1e-8 target at any binary64 output; none are unreachable at 80-bit output. Zero satisfies the target on 183 cases, 93 of which have nonzero references. These are disclosed as separate strata; the corpus and target are not changed to improve scores.

## Whole-project review hardening

A fresh whole-project automated reviewer tested artifact parsing, callback tracing, worker behavior and clean-package workflows. Its consequential findings produced additional regressions:

- Bound decimal-exponent tolerance input before Fraction conversion
- Bound and validate serialized rational evidence, rather than parsing hostile exponent syntax
- Recompute report judgments against matching audited cases; preserve and flag disagreement with recorded fields
- Check artifact checksums and completion counts before loading an experiment through the CLI
- Treat malformed classification labels as invalid evidence instead of crashing
- Bound optional trace serialization so very large exact callback errors cannot change the solver outcome; omitted diagnostic fields are labeled

No authentication, source signatures, or hostile-process security sandbox is claimed. Integrity hashes detect disagreement between local artifacts, not a malicious author replacing all files consistently.

## Hosted browser QA findings

Desktop inspection found that configuration headings displayed an unused precision setting for SciPy. Labels now show effective 53-bit SciPy output versus configured mpmath output precision. Post-hoc selected runs now receive a prominent visible selection warning. Both changes have regressions. Default report text is 16 pixels, with controls and data labels at least 14 pixels. These reporting-only changes do not change frozen numerical measurements.

## Cross-platform CI repairs

The first public-source CI run passed core, Linux and macOS jobs, but both Windows jobs failed. Git checkout newline conversion altered the frozen JSONL bytes, and a 10-second Node cold-start limit was too short. Canonical LF attributes now preserve text bytes while retaining binary archive bytes. A regression performs a real temporary Git checkout with `core.autocrlf=true`; it failed without the attributes and passed with them. The JavaScript rendering test retains its assertions with a bounded 60-second startup wait. Frozen corpus and numerical results were not changed.
