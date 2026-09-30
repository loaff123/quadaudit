# Contributing to QuadAudit

A useful contribution makes an experiment easier to trust or reproduce. Small, independently checked regression cases can be more valuable than more families.

1. Describe the mathematical target and library/version/configuration
2. Give exact parameters and a derivation or a properly validated enclosure
3. Preserve native status and callback semantics; do not label warnings as success
4. Account for every started scalar callback, including vectorized batches and repeats
5. Write a failing regression test before changing behavior
6. Run the complete test suite, corpus regeneration check, and optional adapter tests
7. Disclose review limits and platform checks that were not run

Do not change the frozen core-v1 corpus in place. A corrected or expanded corpus requires a new version, provenance, checksum, and discussion of affected results. Preserve original failed experimental runs alongside corrected runs when a methodological mistake changes their interpretation.

Do not copy fixtures, source code, prose or figures from a paper or library without checking the exact source license. Original mathematical constructions and explanatory derivations are preferred. Do not submit private user data or credentials.

Keep numerical-library reports precise: a missed hidden peak is not by itself evidence of a library bug. Check the documented applicability, stopping criteria, input conversion, callback error, native status, and resource cap first.

External communication and public issue submission are separate from preparing a fixture. No automated outreach is part of the default workflow.
