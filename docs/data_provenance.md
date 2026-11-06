# Data provenance and verification limits

## Results and source versions

The numerical results in `results/published/` correspond to Tables 2–5, A1–A6 and B1 of the paper. Missing cells denote unreported results. The [paper-to-code index](paper_map.md) identifies the workflows and benchmark subsets used for each reported comparison. `environments/native_runtimes.json` records the software versions and upstream revisions; `manifests/sources.json` records file-level provenance.

Experiment directories contain separate workflow implementations. Use the corresponding evaluator and environment for each benchmark. Some source snapshots also include pilot configurations; use the paper-to-code index to select the reported configuration.

## Table rendering and scoring

`scripts/release.py tables` renders the paper values. Use the [evaluation entrypoints](reproduction.md) to score per-instance submissions. Full run outputs and scientific assets are separate inputs.

Table A4 reports Baseline runtimes across 1,500 S²-miniMolOpt instances: 1.18 s mean, 1.11 s median, and 1.54 s at the 90th percentile. See [Table A4](../results/published/table_A4.csv).

The zero-threshold comparison rescores existing outputs. The revised-prompt comparison uses newly generated outputs. See the [evaluation protocol](protocol.md) for the corresponding descriptor paths.

## Verification and compatibility

`scripts/release.py verify` checks source integrity, Python syntax, task counts and table structure. The offline tests check evaluator behavior at protocol boundaries. For numerical reproduction, use the recorded dependency versions. The upstream MolLingo docking helper requires Python 3.12; the single-molecule property benchmark does not load it.
