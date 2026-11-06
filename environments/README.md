# Recorded environments

These environments are separate because evaluator versions affect scientific results. Do not install all requirements into a single shared Python environment.

- `property-scoring.yml` records RDKit 2022.09.4 for the paper's common LogP/QED calculations. Its supporting dependencies are a reconstruction scaffold, not a complete lockfile of every original workflow.
- `pmo.yml` records the submitted oracle/evaluator versions. Method-specific native runtime dependencies still come from the frozen workflow snapshots.
- `smdd-frozen-requirements.txt` is copied verbatim from the preserved evaluator. It requires the matching system/GPU/container environment and model assets, and may differ from runtime-specific compatibility deployments documented in source snapshots.
- `native_runtimes.json` records submitted versions and upstream revision identifiers. These fields distinguish submitted configuration from the local smoke-test environment recorded in validation results.

End-to-end runs require external model weights, scientific assets, native tools and the matching execution environment. The files here record versions and requirements for reconstructing those environments.
