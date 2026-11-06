# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Research code for the EMNLP'25 Findings paper *AgentDrug: Utilizing Large Language Models in an Agentic Workflow for Zero-Shot Molecular Editing*. It evaluates zero-shot molecular editing: given a SMILES string and a natural-language property request (e.g. "increase LogP"), a frozen instruct LLM proposes an edited molecule, optionally refined over several feedback rounds. There is no training loop, no test suite, and no linter — the deliverable is inference + metrics.

## Commands

```bash
# single run (one dataset, one refinement method)
python inference.py --llm_name qwen2.5-3b --data "ZINC500/single/LogP+" \
    --refine agentdrug --refine_steps 3 --hit_thres 0 --DB_size 10000

# all 14 datasets (6 single-property + 8 multi-property) for one config:
#   inference.sh <llm_name> <refine> <hit_thres> <DB_size>
bash inference.sh 'qwen2.5-3b' "agentdrug" 0 10000
```

`*.job` files are SGE/UGE cluster submissions (`qsub inference-Qwen2.5-3B.job`); they activate the `ME-AgentDrug` conda env and sweep every `refine` × `hit_thres` combination. Requires 2 GPUs by default (`--n_gpus`, and `source/models/llm.py` requests 80GiB per device).

Datasets are **not** in this repo. Download `AgentDrug-datasets` from HuggingFace (`lhkhiem28/AgentDrug-datasets`) and place it as a **sibling** of this directory — `--path` defaults to `../AgentDrug-datasets`. Layout expected by `GenerationDataset`: `{path}/{data}/test.csv` plus a shared `{path}/ZINC500/database.csv` retrieval pool.

Results are written to `output/inference/{data}/...csv` (gitignored) and the run prints `Hit / Hit@0.5 / Morgan-FTS / Validity / Validity check / Runtime`. Metrics are scaled by 99.99, not 100.

## Architecture

`inference.py` is the whole experiment driver; everything else is support. Its `main()` is four steps — build dataset, build model, loop over test molecules one at a time, score — and its bulk is one `if/elif` chain over `--refine`, one branch per method being compared. **The branches are deliberate copy-paste variants; a change to the loop usually has to be replicated across all six.**

Refinement methods (`--refine`), in increasing order of feedback richness:

| value | feedback given back to the LLM each round |
|---|---|
| `None` | none — single-shot generation, no loop |
| `self` | the LLM critiques its own output (validity + property) and re-prompts itself |
| `chatdrug-e` | ground-truth hit check only ("The provided molecule is not correct.") |
| `chatdrug` | the above + a retrieved exemplar: the DB molecule that satisfies the constraint and is most Tanimoto-similar to the current output |
| `agentdrug-e` | RDKit-computed validity + numeric property comparison, phrased as structured `Validity:` / `Desired property:` feedback |
| `agentdrug` | the above + the retrieved exemplar (the full method) |

Loop control worth knowing: the loop breaks early as soon as a proposal *hits* the target, so `refine_steps` is an upper bound. `agentdrug*` uses `refine_steps + 1` iterations while `self`/`chatdrug*` use exactly `refine_steps`; `inference.sh` passes 3 for single-property and 4 for multi-property tasks.

Key mechanics spread across files:

- **Validity check is executed, not asserted.** `utils.py:get_validity_feedback` builds an RDKit snippet and runs it through an AutoGen `ConversableAgent` + `LocalCommandLineCodeExecutor` in a temp dir (set up at the top of `inference.py`). The `agentdrug*` branches increment `validity_work` only when the executor output contains `"Error"` (i.e. the generated snippet itself failed), and report `validity_work/total_work` as "Validity check". This is why AutoGen is a dependency at all — no LLM-driven agent conversation happens.
- **Vendored AutoGen.** `autogen/` is a checked-in copy of autogen **0.2.32** (`autogen/version.py`) despite the README listing 0.9.4. Because it sits at the repo root it shadows any installed `autogen` package. Treat it as a third-party vendored tree — don't refactor it.
- **Task definitions live in `source/utils/evaluation.py`.** `task2prop`/`task2func` map task names (`LogP+`, `TPSA-`, `QED+`, `HBD±`, `HBA±`) to RDKit descriptors; `task2thres[task][hit_thres]` gives the required delta — index `0` is the loose threshold (any change in the right direction), index `1` is strict (e.g. LogP ≥ 0.5, TPSA ≥ 10, QED ≥ 0.1). `--hit_thres` is that index, and it is used in three places that must stay consistent: prompt text rewriting in `GenerationDataset`, the in-loop hit check and DB filter in `inference.py`, and final scoring.
- **Multi-property tasks are parsed positionally.** A name like `LogP+TPSA-` is split as `prop[:5]`/`prop[5:]`, so any new property must keep that 5-character LogP prefix convention or the split breaks.
- **Prompt construction bypasses chat templates.** `source/models/llm.py` builds `inputs_embeds` by hand and hardcodes BOS/EOS marker strings per model family (`Qwen2.5`, `Llama-3`) keyed off substrings of `args.llm_path`. Adding a model means adding an entry to `get_llm_path` in `source/models/__init__.py` **and** a matching token block here, otherwise `self.BOS` is undefined at runtime.
- **The test split is subsampled** to 100 molecules (`random_state=0`), and the retrieval DB is shuffled with `random_state=42` then truncated to `--DB_size`. Changing either changes reported numbers.
- LoRA/checkpoint plumbing (`--llm_frozen`, `--lora_r`, `_save_checkpoint`) exists but is unused by the inference path, which always runs frozen.

## Known rough edges

Verified defects in the current tree — check whether they are still present before trusting any number the pipeline prints:

- **Multi-property scoring crashes.** `get_scores_generation` (`source/utils/evaluation.py:94`) iterates `zip(preds, labels)` in its `"multi"` branch, but those names are never bound (the single-property branch uses `df['pred']`/`df['label']`). Raises `NameError`.
- **`&` binds tighter than `<` in the multi-property DB filters.** 32 sites (e.g. `inference.py:149`, `:174`, `:267`, `:394`, `:541`) write `(cond) & DB["prop"] + thres < input_prop`, which pandas evaluates as `((cond) & (prop+thres)) < input_prop` — silently the *negation* of `cond`, with the second property ignored. Parenthesise the right operand. The parenthesised "increase" variants next to them are correct.
- **`agentdrug*` discards chemical-invalidity feedback.** When the prediction is unparseable, `task2func[prop](None)` raises inside the outer `try`, hitting `except: continue` (`inference.py:465`, `:609`) without updating `batch['prompt']` — so the "not chemically valid" message is computed and thrown away, and greedy decoding regenerates the same molecule. `chatdrug*` handles this case explicitly (`inference.py:102`, `:220`).
- **Invalid predictions are double-counted in `validities`.** `Chem.MolFromSmiles` returns `None` without raising, so `validities.append(1)` runs before the fingerprint call raises and appends `0` (`source/utils/evaluation.py:54`, `:91`), inflating the denominator of every rate.
- **Metrics are scaled by 99.99, not 100** (`source/utils/evaluation.py:156`).
- Output filenames embed `args.split`, which defaults to `train` even though `main()` always loads the `test` split (`inference.py:44` vs `:620`).
