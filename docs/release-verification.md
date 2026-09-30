# Release-candidate verification

Version: 0.1.0a1 research preview.

## Checked on the available Linux environment

- Full source suite: 96 tests passed
- Clean installed core-only wheel: 65 passed, 31 optional-solver tests skipped; an earlier 61-pass/31-skip checkpoint was independently repeated
- Clean installed wheel with freshly installed pinned solvers: all 96 tests passed
- Installed-wheel seven-family CLI smoke: 42 scheduled rows and offline report
- Ruff static checks and formatting checks passed
- Wheel and source distribution build succeeded
- Frozen corpus regeneration: all five artifacts match byte-for-byte
- Final frozen experiment: 3,024 rows, 2,877 returned, 147 budget-limited, no case omitted
- Every numerical/value/estimate/status/work/piece record matches the preserved first run
- Independent mathematical, corpus, and whole-project automated reviews completed; consequential findings have regression tests
- Generated explorer JavaScript syntax and simulated DOM rendering tests passed
- Hosted desktop QA: filters, empty/reset state, keyboard pagination, selected evidence, segment zoom, and full traces verified
- Public source ZIP downloaded through the browser and matched against the local SHA-256
- Hosted 390-pixel-wide frame: filters, selection, and segment zoom worked without document horizontal overflow; this was not a physical-phone or touch test
- Static raw JSONL download matched the main-study hash; observation of the browser-generated Blob download did not complete
- Browser-found precision labels and post-hoc disclosure issues fixed with regression tests; readable default type sizes increased

The main final experiment records clean source revision 16758c051f967b56ac61ebd9017fb9ac87b58338 and retains its execution-source archive. Raw evidence and checksum provenance are in docs/reproducibility.md.

## Public-source CI

The [seven-job workflow](https://github.com/loaff123/quadaudit/actions/runs/36760366156) passed on public source commit `e9d14274d3a6e188913f357595d6e3697ad25616`: core plus Python 3.10 and 3.12 on Ubuntu, Windows, and macOS. Each solver job ran all 96 tests, corpus verification, the seven-family traced smoke experiment, and report generation. Core ran lint, format, core tests, freeze regeneration and package builds.

This compatibility matrix resolved SciPy 1.15.3 / NumPy 2.2.6 on Python 3.10 and SciPy 1.18.1 / NumPy 2.5.3 on Python 3.12, with mpmath 1.4.1. These are separate checks from the frozen experiment, which used the explicitly pinned versions in requirements-study.txt. Passing compatibility tests do not imply identical study outcomes across dependency versions.

## Pending at this checkpoint

- Complete GitHub mirror of eight large experiment artifacts; the full source-and-evidence ZIP on the public explorer already includes them
- Independent human numerical review
- Upstream acceptance, independent users, or research adoption

The workflow definition is not evidence that remote jobs passed. Automated review is not human expert certification. A public preview is not a claim that these unfinished external gates are complete.
