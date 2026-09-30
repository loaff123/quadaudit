# Release-candidate verification

Version: 0.1.0a1 research preview.

## Checked on the available Linux environment

- Full source suite: 95 tests passed
- Clean installed core-only wheel: 64 passed, 31 optional-solver tests skipped; independently repeated
- Clean installed wheel with freshly installed pinned solvers: all 95 tests passed
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
- Browser-found precision labels and post-hoc disclosure issues fixed with regression tests; readable default type sizes increased

The main final experiment records clean source revision 16758c051f967b56ac61ebd9017fb9ac87b58338 and retains its execution-source archive. Raw evidence and checksum provenance are in docs/reproducibility.md.

## Pending at this checkpoint

- Hosted phone-width rendering and final revised-deployment check
- Remote GitHub CI on the public release commit
- Actual macOS and Windows execution
- Independent human numerical review
- Upstream acceptance, independent users, or research adoption

The workflow definition is not evidence that remote jobs passed. Automated review is not human expert certification. A public preview is not a claim that these unfinished external gates are complete.
