# When Do Molecular Agents Transfer?

Research code for **When Do Molecular Agents Transfer? A Cross-Task Evaluation of Specialized and General-Purpose Workflows**. The repository covers the main experiments and appendices, including the GLM-5.3 Flash property comparison.

## Start here

```bash
python scripts/release.py catalog
python scripts/release.py verify
python scripts/release.py tables
python -m unittest discover -s tests -v
```

These commands inspect the code, check hashes/task counts, render reported tables and run offline protocol checks. They do not contact a model provider or launch GPU experiments. See [reproduction](docs/reproduction.md) for scoring saved final submissions and preparing the original execution environments.

## Layout

| Directory | Contents |
| --- | --- |
| `experiments/property/` | ChatDrug-MolEdit-28 and S2-miniMolOpt workflows |
| `experiments/structural/` | S2-MolEdit, S2-MolCustom and MolLangBench adapters |
| `experiments/pmo/` | Submission budget accounting, search, references and AUC analysis |
| `experiments/smdd/` | Type2/3/4 workflows, LIDDIA, scientific backends and execution harnesses |
| `experiments/appendix/` | Saved-output rescoring, revised-prompt generation, GLM supplement |
| `experiments/shared/` | Shared SoL-Pi source |
| `benchmarks/smdd/` | Frozen evaluator and exactly 417 Type2/3/4 task definitions |
| `results/published/` | Eleven numerical tables aligned with the submitted PDF |
| `manifests/` | Source hashes, 64 method/task coverage entries, task and entrypoint indices |
| `environments/` | Recorded environment versions and original SMDD requirements |

[Paper-to-code map](docs/paper_map.md) · [Evaluation protocol](docs/protocol.md) · [Data provenance and limits](docs/data_provenance.md)

## Reproduction requirements

Offline scoring uses the included evaluation code. End-to-end runs require the corresponding model access, scientific environment and benchmark assets. Some experiment entrypoints use paths specific to the original deployment; see [reproduction](docs/reproduction.md) for environment and binding requirements.

See [third-party sources and licenses](LICENSES.md).
