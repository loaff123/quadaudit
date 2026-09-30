# Reproducibility and measured preview results

## Frozen question and scope

The fixed question is descriptive: how do native termination, returned-value accuracy, error-estimate adequacy, and charged callback work differ across this designed corpus and the blind/split information policies? It is not a competition with matched total computational cost.

The corpus has 504 cases, 72 in each of seven archetypes. The protocol runs three methods and two tracks, producing 3,024 scheduled rows. The exact post-hoc absolute target is 1/100000000, with at most 4,096 charged scalar callbacks and a 10-second per-case worker deadline. Tracing is disabled in the main experiment. SciPy uses binary64 output; mpmath uses 80-bit output and observed 100-bit callback arithmetic. Native stopping policies differ as documented in the README.

Frozen corpus SHA-256: `543c08a6a759a2ebcfc7f81ac94f32f5fb23b29d5a73d1dbf41ddb454ba07e1d`

Frozen protocol SHA-256: `7d552a1467e9c48a90b708c999f531f5013b0b923030efc23bb560a03fcc102e`

The final run used clean source revision `16758c051f967b56ac61ebd9017fb9ac87b58338`. Its retained execution-source snapshot is `experiments/preview-v1/source-snapshot.zip`, SHA-256 `c825ebc2b0f188ded51f64d0f56795b2ac180dc09052f18de3cc5695b74f1f7f`. Source snapshots omit build-only planning notes; the executable source is preserved. The original development revision identifier is retained in the manifest even if a distribution imports the public source tree into a new repository history.

Final raw results SHA-256: `a55b235fab262dcedb15ff9cb5941f2bf30330d6a9a2bc695897ba7df3c8d0c8`

## Environment and outcomes

Measured on the available shared Linux x86_64 environment, Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, mpmath 1.3.0. The CPU model was not exposed by the environment's normal hardware inventory. The final manifest reports 77.49 seconds elapsed for the full instrumented run. This is a measurement on this host, not a runtime promise or solver-speed benchmark.

There were 2,877 returned results and 147 budget-exhausted rows. No timeout or exception occurred in this fixed run. Every one of the 3,024 rows is retained. All numerical values, estimates, outcomes, work counts and native piece records matched the preserved first run exactly; interpretation metadata and durations differ.

| Method and track | In-contract rows | Accurate | Inaccurate | No complete value |
|---|---:|---:|---:|---:|
| SciPy quad, blind | 504 | 433 | 69 | 2 |
| SciPy quad, split | 504 | 475 | 29 | 0 |
| SciPy tanh-sinh, blind | 234 | 213 | 10 | 11 |
| SciPy tanh-sinh, split | 504 | 449 | 15 | 40 |
| mpmath tanh-sinh, blind | 504 | 366 | 138 | 0 |
| mpmath tanh-sinh, split | 504 | 497 | 0 | 7 |

The remaining 270 blind SciPy tanh-sinh rows are explicitly exploratory because of conservative treatment of interior piece boundaries. Their outcomes are still present in the report and raw evidence; they are not ordinary in-contract failures. The table must not be read as a ranking: precision, applicability, native stopping policies and work costs differ. A native warning and a returned value meeting the post-hoc target can coexist. mpmath has no native success flag.

## Required interpretation strata

Eleven references cannot meet the absolute target at any binary64 output, even after ideal integration and rounding. None have that limitation at 80-bit output. A non-returning run remains unscorable; an unreachable target does not fabricate a returned failure.

Zero meets the absolute target for 183 cases, including 93 nonzero references. A small target-relative amplitude therefore makes an uninformative zero answer sufficient by the declared rule. The report shows target-attainability × zero-baseline strata separately for every method/track/configuration, with all rows retained. It does not discard cases to improve scores.

Strict estimate adequacy is a different question from target accuracy. For example, a represented answer can meet 1e-8 while a reported zero or very small estimate understates its much smaller actual error. These estimators are not generally documented as rigorous error bounds. QuadAudit reports the discrepancy, not a library-defect verdict.

## Explanatory examples and development sweep

After viewing the first run, three cases were selected for teaching:

- beta-014: a narrow interior feature missed by blind sampling; all three methods improve with supplied breakpoints in the measured tutorial
- legendre-037: large opposing contributions and a zero exact integral; warnings and precision matter
- power-036: the requested absolute target lies below the binary64 output-grid floor

`experiments/explanatory-traces/` contains 18 separately traced runs. `experiments/development-grid/` contains 108 runs crossing these three selected cases with targets 1e-4, 1e-8 and 1e-12, budgets 256 and 4096, three methods and two tracks. These are post-hoc explanatory/development runs, not independent prevalence evidence, and never replace the frozen outcomes. Configuration-aware summaries prevent mixed settings from being silently pooled.

## Reproduce

```sh
python -m pip install -r requirements-study.txt .
python corpus/freeze.py
python scripts/run_study.py --check
python scripts/run_study.py --output experiments/my-reproduction
quadaudit report experiments/my-reproduction
```

The version-checked script refuses a different pinned dependency set. The general CLI can explore other versions/settings; those runs are separate experiments. Exact corpus regeneration is byte-for-byte. Solver values and native outcomes may vary across library versions and platforms, so cross-platform bitwise numerical equality is not promised.

The report CLI checks corpus/protocol/result hashes and counts, then recomputes displayed judgments against audited matching cases. Hashes detect inconsistent artifacts; they are not authentication signatures. The first dirty-source run and its limitations are preserved in `experiments/README.md`.

## Verification boundary

At the reviewed implementation milestone, 92 source tests passed. A separately installed core-only wheel passed 61 tests, with 31 optional-solver tests explicitly skipped; an independent repeat check reproduced that result. Wheel and source distributions build, and frozen artifacts regenerate. The clean installed wheel with freshly installed pinned solvers also passed all 92 tests. Hosted browser QA is recorded separately in docs/release-verification.md.

Remote CI, macOS/Windows execution, independent human numerical review, upstream acceptance and research adoption must not be inferred from local success. Their status is listed separately in the release verification record.
