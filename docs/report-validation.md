# Report validation hardening

This unreleased change hardens report interpretation and experiment validation. It does not change the numerical adapters, oracle, frozen corpus, protocol, or historical evidence. The existing published study results were not found to be wrong.

## Recomputed diagnostic evidence

The report derives the nearest-output-grid error, target attainability, and zero baseline from the independently audited case reference and exact target. The two SciPy methods use binary64; mpmath uses its configured output precision, not callback guard bits. Unknown methods and invalid mpmath precision cannot establish grid attainability. An audited reference and target can still establish the zero baseline independently of precision.

Contradictory recorded fields are flagged in each row's evidence note. Raw rows remain unchanged in the embedded evidence and downloads. The visible precision label also uses verified display evidence. Missing or inconsistent case, family, method/track configuration, or target evidence cannot establish these diagnostic classifications.

## Identity coverage

Hashes and equal row counts are insufficient to show that an experiment covers its schedule. A duplicate row can replace a missing row without changing either count.

The checker matches every row against the corpus crossed with the explicit list of complete `RunConfig` configurations. It does not form a new Cartesian product from individual settings, so heterogeneous schedules remain intact. The manifest's embedded protocol must agree with the protocol file. Configuration fields are compared as recorded, without silently filling defaults.

The CLI rejects invalid, duplicate, unexpected, or falsely complete schedules before writing a report. Coherent partial experiments remain supported. Direct `render_report` imports retain every row and expose `complete`, `partial`, `invalid`, or `unverified` identity coverage, with inspectable reasons and identities. Counts and rates describe supplied rows; invalid or unverified coverage cannot establish complete scheduled-study rates.

## Verification on 2026-10-01

- Baseline: 96 tests passed before changes
- Updated source: 128 tests passed with SciPy 1.17.0, NumPy 2.3.5, and mpmath 1.3.0 on Linux, Python 3.12.14
- Installed core-only wheel: 97 passed, 31 optional-solver tests skipped
- Ruff 0.13.0 lint and format checks, frozen regeneration, pinned-protocol check, wheel and source-distribution builds passed
- Regression failures were observed before implementing diagnostic recomputation, schedule checks, and the visible output-precision correction
- Independent automated code review completed, including a further 96 numerical boundary/method/precision probes; no remaining material findings

All four retained experiment sets were rebuilt into separate validation outputs. Development-grid (108 rows), explanatory-traces (18), initial-run (3,024), and preview-v1 (3,024) each have complete scheduled identity coverage. The 33 historical input files checked remain byte-identical.

For preview-v1, development-grid, and explanatory-traces, all summary values and classifications are unchanged; only the evidence-policy explanation changed. The older initial-run has no recorded target diagnostics: its rebuilt report now derives those strata, while its accuracy, estimate, and pairing counts remain unchanged.

Independent exact rechecking confirms 504 valid references, 183 zero-sufficient targets including 93 nonzero references, 11 binary64-unattainable targets, and none at 80 bits. Preview-v1 still contains 1,512 blind/split pairs, 2,877 returns, and 147 budget-exhausted rows.

These are local checks and automated review. This change does not establish remote CI, new macOS/Windows execution, human numerical review, or new solver measurements.
