# Project rules

- Read `README.md`, `docs/protocol.md` and `docs/data_provenance.md` before changes.
- Scope is the submitted main experiments and appendices. Preserve benchmark denominators, final-submission rules, descriptor variants and PMO accounting conventions.
- Treat `experiments/` and `benchmarks/smdd/` as frozen scientific snapshots. New fixes belong in separate reviewed code; update provenance if a source file changes.
- Never include credentials, account/session state, raw API traces, model weights or generated run directories in a public package.
- Run `python scripts/release.py verify` and offline tests after code changes. Do not start paid API/GPU experiments as part of documentation cleanup.
- Report known reproduction limits; rendering a published table is not recomputing an experiment.
