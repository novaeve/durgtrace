# Submitted evaluation protocol

The submitted PDF is authoritative. Its SHA-256 is stored with `results/published/tables.json`. Historical notes remain source evidence and may describe superseded deployments. This page records the submitted definitions; it does not change any evaluator.

## Tasks and final submissions

| Task | Size | Reported criterion |
| --- | ---: | --- |
| ChatDrug-MolEdit-28 | 5600 | 200 inputs × 14 tasks × loose/strict; strict requested property improvements; native Kekulize path |
| S2-miniMolOpt | 1500 | 500 each LogP/QED/MR; strict improvement in requested direction |
| S2-MolEdit | 1500 | Frozen functional-group count edits |
| S2-MolCustom | 1500 | Frozen atom/bond/group count constraints |
| MolLangBench Editing | 400 | Test/core 200 + extended 200; stereochemistry-preserving canonical SMILES exact match |
| MolLangBench Generation | 400 | Same split sizes and exact-match convention |
| PMO-1K | 23 objectives | Seed 0; 1000 logical submissions/objective; mean Top-10 AUC |
| SMDD Type2 | 25 tasks / 75 points | First three parseable points; compatible types, one-to-one Hungarian matching, distance strictly <2.5 Å |
| SMDD Type3 | 52 | All scaffold, interaction and predicted binding conditions jointly |
| SMDD Type4 | 340 / 25 targets | All optimization, maintenance, chemistry and predicted binding conditions jointly |

Errors, invalid outputs and missing submissions remain in the task denominator. Outside PMO's search archive, each workflow submits one final answer. MolLingo uses model-only selection of a single final molecule from generated candidates. MolLangBench gold answers are used offline only. ChatDrug/AgentDrug no-rules adaptations retain format/validity feedback without hidden exact-match answers.

S2 MolCustom BondNum ignores zero-valued bond requirements in the frozen evaluator. Functional-group evaluation follows the official list: the mini CSV `benzene_ring` spelling is aligned, and `thioether` is not added as a new condition. Property and S2 success criteria do not add a hard similarity threshold.

## Appendix rescoring and regeneration

Table A5 uses all 5600 CD outputs. Direction-only sets zero improvement thresholds but retains the native ChatDrug descriptor path. Table A6 uses 800 CD and 500 independent S2 cases per LogP/QED property. Its rescoring and new-prompt columns use S2 calculations in RDKit 2022.09.4 with no extra Kekulize. A6 comparisons with Original therefore change evaluator implementation as well as the improvement condition.

New prompts both remove similarity wording and explicitly name the target property. They require fresh generation; they are not saved-output rescoring and are not a single-factor similarity-only ablation. Table B1 repeats the property-specific comparison with GLM-5.3 Flash. Main experiments use DeepSeek v4.1 Flash.

## PMO accounting

Invalid and duplicate outputs consume logical submission budget. Default ChatDrug/AgentDrug charges reference and candidate evaluation within 1000 submissions. The precomputed setting moves reference scoring outside that budget and continues search; free references do not enter the online archive. Early-ended recorded trajectories use the reported terminal hold when forming the offline tail.

MolClaw/Codex/SoL-Pi use submission-wise trapezoidal integration with an initial zero. Baseline/ChatDrug/AgentDrug retain MT-Mol `top_auc(top_n=10, freq_log=1, finish=True)` with the original indices. These conventions are preserved and are a comparability limitation. There are no repeated-seed uncertainty estimates for PMO.

## SMDD joint conditions

Type2 accepts Aromatic/Hydrophobic interchangeability only as specified by the frozen compatibility matrix; distance at exactly 2.5 Å fails. At most three parseable points are scored, with a denominator of three even when fewer are supplied.

Type3 requires valid chemistry, Morgan radius-2/2048-bit Tanimoto <0.5, scaffold MCS / larger scaffold <0.65 with 10-second timeout, PLIP consensus interaction Tanimoto >0.75 and mean Boltz binding probability >0.7. Use ten diffusion samples and interaction consensus at ≥6 samples. The scientific tool seed is 42.

Type4 requires valid single-fragment, nonradical chemistry; MW <600; LogP in [-1,5]; TPSA <140; HBD ≤5; HBA ≤10; rotatable bonds ≤10; formal charge in [-2,2]; SA <4.5; no PAINS/Brenk alerts; Morgan similarity ≥0.7; binding probability >0.7. Minimum improvements are inclusive. Exact per-task maintained-property tolerances come from the frozen YAML, never a newly inferred global tolerance. Recorded improvements include 0.1 for hERG/CYP3A4/Ames decrease and BBB direction, 0.5 solubility increase, 5 clearance/PPB decrease, 0.3 Caco2 increase and 0.3 predicted affinity decrease.

Common SMDD scientific budgets are 100 model calls, 10 million cumulative input/output tokens, 8 Boltz calls and 15 ADMET calls per instance. Actual workflow temperatures, iteration limits and reasoning settings differ; see original manifests and the PDF's Tables C8-C9. They must not be silently unified. Baseline and general-purpose tools use the task-specific submitted configuration. Final scoring is independent of the online generation budget.

Nine count tasks use unpaired two-proportion z-tests at p<0.05 in the submitted comparison. PMO uses direct AUC comparison. Do not infer paired significance or exact counts from rounded percentages. No comparison here asserts identical tool permissions, token budgets, call counts or wall-clock conditions across all workflows.
