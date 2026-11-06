# MolLingo — MolLingo: Making Molecules More LLM-Readable for Autonomous Chemist Agents

MolLingo is a multi-agent system that emulates the reasoning process of a medicinal chemist to automate early-stage drug discovery. It coordinates a **Literature Agent**, a **Chemist Agent**, and an **Orchestrator** through a shared memory module, grounding molecular reasoning in block-based chemical representations and physics-based docking simulations.

> Based on the paper: *"Chemistry in Plain Language: Block-Based Representation Enable LLMs as Medicinal Chemist Agents"* (NeurIPS 2026 submission)

---

## Pipeline Overview

```
User Prompt
    │
    ▼
[Stage 1] Target Identification      ← LiteratureAgent (GPT + web search)
    │  disease → protein name + UniProt ID
    ▼
[Stage 2] Hit Identification         ← ChemistAgent
    │  ChEMBL retrieval → Butina clustering → ADMET scoring
    ▼
[Stage 3] Hit-to-Lead                ← ChemistAgent
    │  AutoDock Vina docking → binding-site hotspots → GPT fragment growing
    ▼
[Stage 4] Lead Optimization          ← ChemistAgent
    │  Block-based SMILES → GPT substitution proposals → ADMET filtering
    ▼
Best Drug Candidate
```

All intermediate results, reasoning traces, and design rationales are persisted in a `SharedMemory` object that every agent reads from and writes to.

---

## Repository Structure

```
MolLingo/
├── agent.py              # LiteratureAgent + ChemistAgent
├── planner.py            # OrchestratorAgent — coordinates the pipeline
├── memory.py             # SharedMemory — single source of truth across agents
├── run_agent.py          # CLI entry point
│
├── toolset/
│   ├── call_gpt.py                       # OpenAI API wrapper (web search enabled)
│   ├── call_gemini.py                    # Gemini API wrapper
│   ├── ADMET.py                          # ADMET oracle models (DILI, hERG, AMES, Pgp, HIA, BBBP)
│   ├── admet_inference.py                # GNN-based ADMET inference
│   ├── autodockvina_docking.py           # AutoDock Vina orchestration
│   ├── autodockvina_w_ligand.py          # Docking with known co-crystal ligand
│   ├── autodockvina_wo_ligand.py         # Blind docking (no reference ligand)
│   ├── fragment_growing.py               # Context-aware fragment growing
│   ├── optimize_mol.py                   # Block-based lead optimization
│   ├── biological_target_identification.py  # GPT-based target identification
│   ├── protein2binders.py                # ChEMBL binding data retrieval
│   ├── tokenizer.py                      # BFE tokenizer + block-based SMILES
│   ├── Butina_clustering.py              # Chemical diversity clustering
│   ├── calculate_druggability.py         # QED + SA score druggability metric
│   ├── mol_similarity.py                 # Tanimoto similarity
│   ├── sascorer.py                       # Synthetic accessibility scorer
│   ├── config.py                         # API keys + model names (not committed)
│   └── ...
│
├── models/               # Model architecture definitions
├── model_weights/        # Pretrained ADMET oracle weights (not committed)
├── data/                 # Datasets (not committed)
├── experiment_results/   # Benchmark outputs (not committed)
│
├── requirements.txt
└── README.md
```

---

## Installation

### 1. Clone and set up environment

```bash
git clone https://github.com/thaonguyen217/MolLingo
cd MolLingo
conda create -n MolLingo python=3.12
conda activate MolLingo
pip install -r requirements.txt
```

### 2. Install AutoDock Vina (system binary)

AutoDock Vina is called as a subprocess — it must be available on your `PATH`:

```bash
conda install -c conda-forge vina
```

### 3. Configure API keys

Copy the config template and fill in your keys:

```bash
cp toolset/config.example.py toolset/config.py
```

Edit `toolset/config.py`:

```python
OPENAI_API_KEY  = "sk-..."           # Required — used by all agents
GPT_MODEL       = "gpt-5.4"
GEMINI_API_KEY  = "AIza..."          # Optional — for Gemini baseline runs
GEMINI_MODEL    = "gemini-pro-latest"
```

---

## Usage

### Command-line (recommended)

```bash
cd MolLingo
conda activate MolLingo
```

**Full pipeline from a disease prompt:**
```bash
python3 run_agent.py "Design a novel drug for Alzheimer's disease"
```

**With a known target (skips Stage 1):**
```bash
python3 run_agent.py "Design a novel drug for Alzheimer's disease targeting GSK-3β" \
    --uniprot P49841 --protein "GSK-3β" \
    --task ADMET \
    --hits 10 --growing-hits 3 --frags 3 --leads 2 --variants 10 \
    --save alzheimer_results.json
```

**Optimize specifically for liver safety:**
```bash
python3 run_agent.py "Treat Chronic Myeloid Leukemia" \
    --uniprot P00519 --protein "ABL1" \
    --task DILI --hits 20 --save cml_results.json
```

**Skip fragment growing (ADMET-only optimization):**
```bash
python3 run_agent.py "Design a CNS drug for Parkinson's disease" \
    --mutation "LRRK2 G2019S" --no-fragment-growing --variants 30
```

**Interactive mode:**
```bash
python3 run_agent.py
# → Enter your research prompt: ...
```

#### All CLI flags

| Flag | Default | Description |
|---|---|---|
| `--uniprot ID` | — | UniProt ID — skips target identification |
| `--protein NAME` | — | Protein name (required with `--uniprot`) |
| `--mutation MUT` | — | Gene mutation context (e.g. `"GBA1 loss-of-function"`) |
| `--pathway PATH` | — | Pathway context for target identification |
| `--task` | `ADMET` | Optimization endpoint: `ADMET` `DILI` `hERG` `AMES` `Pgp` `HIA` `BBBP` |
| `--no-bbbp` | — | Set BBB permeability as undesirable (non-CNS drugs) |
| `--hits N` | 30 | ChEMBL candidates to retrieve |
| `--growing-hits N` | 5 | Top hits to run fragment growing on |
| `--frags N` | 5 | GPT fragment proposals per hotspot |
| `--leads N` | 3 | Leads passed to optimization |
| `--variants N` | 20 | Block substitution variants per lead |
| `--no-fragment-growing` | — | Skip Stage 3, go straight to lead optimization |
| `--save PATH` | — | Save full `SharedMemory` to a JSON file |

---

### Python API

```python
from planner import OrchestratorAgent

# Full pipeline
agent = OrchestratorAgent(
    disease="Alzheimer's disease",
    gene_mutation="GBA1 loss-of-function",
    bbbp_desired=True,          # CNS target → BBB penetration required
    main_task="ADMET",
)
summary = agent.run(
    num_hits=30,
    num_growing_hits=5,
    num_fragment_candidates=5,
    num_leads=3,
    variants=20,
    save_path="results.json",
)
print(summary)
```

```python
# Known target — run stages individually
agent = OrchestratorAgent(
    disease="CML",
    uniprot_id="P00519", protein_name="ABL1",
    main_task="DILI",
)
agent.run_hit_identification(num_candidates=30)
agent.run_hit_to_lead(num_hits=5, num_fragment_candidates=5)
agent.run_lead_optimization(num_leads=3, variants=20)

# Inspect results
print(agent.memory.summary())
print("Best candidate:", agent.memory.best_candidate())
```

```python
# Resume from a saved checkpoint
from memory import SharedMemory
from planner import OrchestratorAgent

mem = SharedMemory.load("results.json")
agent = OrchestratorAgent(memory=mem)
agent.run_lead_optimization(num_leads=5, variants=30)  # continue from leads
```

---

## Key Components

### Block-Based SMILES (BFE Tokenization)

Instead of raw SMILES strings, MolLingo decomposes molecules into chemically meaningful building blocks using BRICS-based Fragment Enumeration (BFE). Each block is represented as a SMILES token with attachment points (`[1*]`, `[2*]`) and paired with its common chemical name:

```
imatinib → pyridine → 3-aminopyridine → toluene → benzamide → piperazine
```

This alignment between molecular structure and LLM semantic space enables block-level reasoning and editing that is impossible with raw SMILES.

### ADMET Oracle Models

Six GNN-based binary classifiers predict pharmacokinetic and toxicity endpoints:

| Endpoint | Favorable direction | Description |
|---|---|---|
| DILI | ↓ low probability | Drug-induced liver injury |
| hERG | ↓ low probability | Cardiotoxicity (K⁺ channel inhibition) |
| AMES | ↓ low probability | Mutagenicity |
| Pgp | ↓ low probability | P-glycoprotein efflux |
| HIA | ↑ high probability | Human intestinal absorption |
| BBBP | ↑ or ↓ | Blood-brain barrier (target-dependent) |

Composite ADMET score: `(1−DILI) + (1−hERG) + (1−AMES) + (1−Pgp) + HIA [± BBBP]`

### Context-Aware Fragment Growing

For each hit molecule:
1. AutoDock Vina docks the hit into the binding pocket
2. Growth hotspots are identified by available volume + neighboring residues
3. GPT proposes building blocks for each hotspot, grounded in the 3D pocket environment
4. Each proposal is docked and only improvements are kept

<!-- --- -->

<!-- ## Citation -->

<!-- If you use MolLingo in your research, please cite:

```bibtex
@inproceedings{MolLingo2026,
  title     = {Chemistry in Plain Language: Block-Based Representation Enable LLMs as Medicinal Chemist Agents},
  author    = {Anonymous},
  booktitle = {Advances in Neural Information Processing Systems (NeurIPS)},
  year      = {2026}
}
``` -->
