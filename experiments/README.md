# Frozen experiment evidence

`initial-run/` preserves the first complete run of the unchanged core-v1 corpus and protocol. It contains 3,024 raw rows, including 147 evaluation-budget terminations. It predates the output-grid interpretation fields and final reporting/input hardening. Its results file is not rewritten to add those fields.

`preview-v1/` is the final rerun from reviewed source, with the same mathematical cases, settings, target and budget. The only added numerical metadata are output-grid attainability and whether zero satisfies the common absolute target. These diagnostics were added after independent review. Neither the corpus nor protocol is filtered or tuned in response to observed solver outcomes.

The raw results hash for the first run is `600cd993d75db9427615a6dfce39f5f24cdc1213581fa0bea036a0c1ab5f85f4`. The corpus hash remains `543c08a6a759a2ebcfc7f81ac94f32f5fb23b29d5a73d1dbf41ddb454ba07e1d` and the frozen protocol hash remains `7d552a1467e9c48a90b708c999f531f5013b0b923030efc23bb560a03fcc102e`.

Any traced examples selected after examining this run are explicitly post-hoc explanatory reruns. They do not replace frozen-study outcomes and cannot estimate a prevalence.

## Initial source-state caveat

The initial manifest records `source_dirty: true`. The original runner captured git status after creating experiment output files, which made its own output count as dirtiness; concurrently authored reporting files were also untracked. A full snapshot of that dirty workspace was not captured, so we do not claim to reconstruct every file in it retrospectively. `initial-run/recorded-commit-source.zip` contains the exact source at the recorded commit, not a fabricated dirty-tree snapshot. Treat the first run as preserved exploratory evidence, not the final release's reproducibility anchor. The final run captures git state before creating artifacts and retains a source archive of its clean committed revision.
