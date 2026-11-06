# AgentDrug

Datasets: https://huggingface.co/datasets/lhkhiem28/AgentDrug-datasets

---

# AgentDrug: Utilizing Large Language Models in an Agentic Workflow for Zero-Shot Molecular Editing

EMNLP'25 Findings

[![Paper](https://img.shields.io/badge/Paper-arXiv:2410.13147-red?logoWidth=40)](https://arxiv.org/abs/2410.13147)

## Requirements
```bash
rdkit==2025.3.3
torch==2.7.1
transformers==4.53.0
autogen==0.9.4
```

<!---
## Quick start
-->

## Reproducibility

### 1. Download datasets
Download datasets from the above link and place the folder in the master directory:
```bash
├───AgentDrug
│   ├───autogen
│   └───source
├───AgentDrug-datasets
│   └───ZINC500
```

### 2. Run
Use the `inference.sh` script with the following arguments to reproduce our main results (Table 2):
- `llm_name`: LLM name
- `data`: path to the set of input molecules (`single/multi`/`property`/`+/-`)
- `refine`: refinement method
- `refine_steps`: number of refinement steps
- `hit_thres`: threshold (`l`: loose or `s`: strict)
- `DB_size`: size of the database for retrieval

Examples are provided in `*.job` files.

## Citation
```
@article{le2024utilizing,
  title={AgentDrug: Utilizing Large Language Models in an Agentic Workflow for Zero-Shot Molecular Editing},
  author={Khiem Le and Ting Hua and Nitesh V. Chawla},
  journal={arXiv preprint arXiv:2410.13147},
  year={2024}
}
```
