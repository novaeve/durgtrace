# Reproduction and saved-output scoring

## Offline checks and reported tables

Use Python 3.10+ for the release utilities. Full upstream-source parsing requires Python 3.12+ for one preserved, unused MolLingo docking helper; older interpreters receive a recorded compatibility notice. `release.py catalog`, `verify` and `tables` require only the standard library. Protocol smoke checks additionally require RDKit, NumPy, SciPy, requests and PyYAML. Run all commands from the release root. `results/generated/tables.md` and CSVs render the submitted values; they do not recompute raw runs.

## Rescore final SMILES

`score_saved.py` loads the frozen task IDs and actual evaluator functions. Input is UTF-8 JSONL containing `id`, one final `candidate` SMILES and optional `status` (default `complete`). An output that is missing or has a non-complete status remains a failure in the full denominator. Duplicate and unknown IDs are errors. Do not mix retained runs or select candidates using evaluation scores.

```bash
python scripts/export_predictions.py /path/to/one/retained/run --candidate-field candidate --output results/predictions.jsonl
python scripts/score_saved.py --task s2_edit --predictions results/predictions.jsonl --output results/generated/s2_edit_scores.json
python scripts/score_saved.py --task cd28 --protocol direction-native --predictions results/cd28_predictions.jsonl --output results/generated/cd28_direction.json
python scripts/score_saved.py --task cd28_logp --protocol direction-s2 --predictions results/cd28_logp_predictions.jsonl --output results/generated/cd28_logp_s2.json
```

For the original combined ChatDrug baseline results, the candidate field can be `arms.direct.candidate` or `arms.chatdrug.candidate`. Only export one selected benchmark subset at a time; the scorer rejects records outside that fixed task set. `score_saved.py --help` lists all task subsets. The exporter does not interpret every method's trace schema; check the indexed native scorer when final submissions are CSV files, SMDD solution files or PMO oracle trajectories.

`native` uses the original task evaluator. `direction-native` sets ChatDrug thresholds to zero while retaining ChatDrug's descriptor path. `direction-s2` applies the S2 descriptor implementation to the 800-instance CD LogP or QED subset. It is restricted to those two subsets. No option regenerates molecules. The RDKit version is recorded in every new score file; use the original environment to compare numerical outputs with the paper.

## Original online experiments

1. Find the method/task bundle in `manifests/coverage.json` or `paper_map.md`. Inspect the relevant `README.release.md`, original manifest and parser arguments.
2. Rebuild the corresponding environment from `environments/` and the frozen source requirements. Property evaluation, PMO and SMDD use different environments. The native Codex, Claude Code and Pi runtimes are separate dependencies.
3. Restore benchmark PDB/SDF inputs, model weights and container filesystems from the preserved server assets or migration backup. Verify their original hashes before use. Private credentials must be configured locally at the original transport's expected location; examples contain placeholders only.
4. Generate a binding plan, using the chosen scientific image. This prints a command and never runs it:

```bash
python scripts/release.py plan smdd_type3_harness_20261001 run.py --image smdd-reproduction:local
```

`configs/path_aliases.json` maps historical absolute project roots to the organized source folders. The plan binds these paths within the container, avoiding edits to scientific functions or AST-extracted function namespaces. Root filesystem, weights and credentials require additional bindings listed in a local JSON file shaped like `configs/external_bindings.example.json`. The example is a schema, not a complete asset manifest. Paths, tools, local proxies and runtime dependencies must be checked before executing a plan. Full end-to-end regeneration has not been validated by this cleanup.

Native scripts create run outputs beside their source. Use a writable copy of the release for experiments so the checked release remains immutable. Keep gold answers and evaluator-only assets outside agent-visible sandbox mounts; preserve the original public-input isolation rules. Do not mount the entire benchmark into an agent's sandbox.

## Scientific scoring entrypoints

- ChatDrug/S2 property: `experiments/property/chatdrug_generalization_20260920/full_experiment.py`, frozen ChatDrug `small_molecule_editing.py`, frozen S2 `evaluation.py`.
- S2 editing/custom generation: `experiments/structural/s2_edit_custom_20260928/benchmark.py` and `source/s2_properties.py`.
- MolLangBench: its frozen official `evaluate_results.py` and the benchmark's `score.py` / native four-benchmark scorers.
- SMDD: `benchmarks/smdd/evaluator/` and `metrics/`; workflow-side `evaluate.py` / `score.py` are indexed per bundle. Type3/4 require the recorded Boltz/ADMET assets.
- PMO: use `submission_budget.py`, the recorded trajectory and the workflow-specific AUC implementation described in the [protocol](protocol.md).
