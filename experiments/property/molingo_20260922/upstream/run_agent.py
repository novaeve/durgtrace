#!/usr/bin/env python
"""
MolLingo — Autonomous LLM Medicinal Chemist Agent
==============================================
Runs the full drug discovery pipeline from a free-text research prompt.

Usage
-----
Interactive:
    python run_agent.py

One-liner:
    python run_agent.py "Design a novel drug for Alzheimer's disease"

With overrides:
    python run_agent.py "Treat Parkinson's targeting LRRK2" \\
        --task BBBP --hits 20 --save results.json

Skip to lead optimization (known target, known hit):
    python run_agent.py "Optimize imatinib for CML" \\
        --uniprot P00519 --protein "ABL1" --task DILI --no-fragment-growing
"""

import argparse
import sys
import textwrap
from ast import literal_eval

from toolset.call_gpt import gpt_api
from planner import OrchestratorAgent
from memory import SharedMemory


# ------------------------------------------------------------------ #
# Prompt parser                                                        #
# ------------------------------------------------------------------ #

_PARSE_PROMPT = """\
You are a biomedical expert assistant. Extract structured drug discovery \
parameters from the research prompt below.

Rules:
- Return ONLY a valid Python dictionary literal — no explanation, no markdown.
- Keys must be exactly as shown in the example.
- For main_task: choose the most relevant single endpoint from \
[ADMET, DILI, hERG, AMES, Pgp, HIA, BBBP]. \
Use ADMET (overall) unless the prompt specifically mentions a single endpoint.
- For bbbp_desired: set True for CNS/brain diseases (Alzheimer, Parkinson, \
depression, epilepsy, schizophrenia, glioma, MS …), False otherwise.
- Use None for any field not mentioned or inferable.

Example output:
{{
    "disease": "Alzheimer's disease",
    "disease_subtype": None,
    "uniprot_id": None,
    "protein_name": "GSK-3β",
    "gene_mutation": None,
    "pathway": None,
    "main_task": "BBBP",
    "bbbp_desired": True
}}

Research prompt: {prompt}
"""


def parse_prompt(prompt: str) -> dict:
    """Use GPT to extract structured pipeline parameters from a free-text prompt."""
    response = gpt_api(_PARSE_PROMPT.format(prompt=prompt))

    # Try to pull out the first dict literal from the response
    try:
        # Strip markdown fences if present
        text = response
        for fence in ["```python", "```json", "```"]:
            if fence in text:
                text = text.split(fence)[1].split("```")[0]
                break
        params = literal_eval(text.strip())
        assert isinstance(params, dict)
        return params
    except Exception:
        print("[WARNING] Could not parse GPT response as a dict. Using defaults.")
        print(f"  Raw response: {response[:300]}")
        return {}


# ------------------------------------------------------------------ #
# Result printer                                                       #
# ------------------------------------------------------------------ #

def _divider(char="─", width=60):
    print(char * width)

def print_summary(memory: SharedMemory):
    _divider("═")
    print("  MolLingo  —  Pipeline Summary")
    _divider("═")

    # Research context
    if memory.user_prompt:
        prompt_short = textwrap.shorten(memory.user_prompt, width=72, placeholder="…")
        print(f"  Prompt    : {prompt_short}")
    print(f"  Disease   : {memory.disease}"
          + (f"  [{memory.disease_subtype}]" if memory.disease_subtype else ""))
    if memory.gene_mutation:
        print(f"  Mutation  : {memory.gene_mutation}")
    if memory.pathway:
        print(f"  Pathway   : {memory.pathway}")

    # Target
    print(f"  Target    : {memory.protein_name}  (UniProt: {memory.uniprot_id})")
    if memory.target_reference:
        ref = textwrap.shorten(memory.target_reference, width=70, placeholder="…")
        print(f"  Reference : {ref}")

    # Optimization goal
    print(f"  Task      : {memory.main_task}  |  BBBP desired: {memory.bbbp_desired}")
    _divider()

    # Stage 2 — Hits
    print(f"\n  [Stage 2] Hit Identification  —  {len(memory.hits)} hits")
    best_hit = memory.best_hit()
    if best_hit:
        h = memory.hits[best_hit]
        print(f"    Best hit : {best_hit}")
        print(f"    Docking  : {h['docking_score']}")
        if h['admet_profile']:
            admet_str = "  ".join(f"{k}: {v:.2f}" for k, v in h['admet_profile'].items())
            print(f"    ADMET    : {admet_str}")
    else:
        print("    No hits found.")

    # Stage 3 — Leads
    print(f"\n  [Stage 3] Hit-to-Lead  —  {len(memory.leads)} leads")
    best_lead = memory.best_lead()
    if best_lead:
        ld = memory.leads[best_lead]
        print(f"    Best lead : {best_lead}")
        print(f"    Docking   : {ld['docking_score']}")
        print(f"    Fragment  : {ld['fragment']}")
        rationale = textwrap.shorten(ld['rationale'] or "", width=80, placeholder="…")
        print(f"    Rationale : {rationale}")
    else:
        print("    No leads generated.")

    # Stage 4 — Candidates
    print(f"\n  [Stage 4] Lead Optimization  —  {len(memory.candidates)} candidates")
    best_cand = memory.best_candidate()
    if best_cand:
        cd = memory.candidates[best_cand]
        print(f"    Best candidate : {best_cand}")
        print(f"    ADMET score    : {cd['admet_score']:.3f}")
        if cd['admet_profile']:
            admet_str = "  ".join(f"{k}: {v:.2f}" for k, v in cd['admet_profile'].items())
            print(f"    ADMET profile  : {admet_str}")
    else:
        print("    No optimized candidates.")

    _divider("═")


# ------------------------------------------------------------------ #
# CLI                                                                  #
# ------------------------------------------------------------------ #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="MolLingo: Autonomous LLM Medicinal Chemist Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "prompt", nargs="?", default=None,
        help="Free-text research prompt (prompted interactively if omitted).",
    )

    # Manual overrides — all optional
    p.add_argument("--disease", default=None, help="Disease name (overrides parsed value).")
    p.add_argument("--subtype", default=None, help="Disease subtype.")
    p.add_argument("--uniprot", default=None, metavar="ID",
                   help="UniProt ID (skips target identification).")
    p.add_argument("--protein", default=None, metavar="NAME",
                   help="Protein name (required with --uniprot).")
    p.add_argument("--mutation", default=None, metavar="MUT",
                   help="Gene mutation context (e.g. 'GBA1 loss-of-function').")
    p.add_argument("--pathway", default=None, help="Pathway context.")
    p.add_argument("--task", default=None,
                   choices=["ADMET", "DILI", "hERG", "AMES", "Pgp", "HIA", "BBBP"],
                   help="ADMET optimization target (default: ADMET).")
    p.add_argument("--no-bbbp", action="store_true",
                   help="Set bbbp_desired=False (peripheral/non-CNS drug).")

    # Pipeline scale
    p.add_argument("--hits", type=int, default=30, metavar="N",
                   help="Number of ChEMBL hit candidates to retrieve (default: 30).")
    p.add_argument("--growing-hits", type=int, default=5, metavar="N",
                   help="Number of top hits to run fragment growing on (default: 5).")
    p.add_argument("--frags", type=int, default=5, metavar="N",
                   help="GPT fragment proposals per hotspot (default: 5).")
    p.add_argument("--leads", type=int, default=3, metavar="N",
                   help="Number of leads to pass to lead optimization (default: 3).")
    p.add_argument("--variants", type=int, default=20, metavar="N",
                   help="Block substitution variants per lead (default: 20).")
    p.add_argument("--no-fragment-growing", action="store_true",
                   help="Skip fragment growing and go directly to lead optimization.")

    # Output
    p.add_argument("--save", default=None, metavar="PATH",
                   help="Save full memory (hits, leads, candidates, trace) to a JSON file.")

    return p


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #

def main():
    parser = build_parser()
    args = parser.parse_args()

    # Get prompt
    prompt = args.prompt
    if not prompt:
        print("MolLingo — Autonomous LLM Medicinal Chemist Agent")
        print("Enter your research prompt (e.g. 'Design a drug for Alzheimer's disease'):")
        prompt = input("> ").strip()
        if not prompt:
            print("No prompt provided. Exiting.")
            sys.exit(1)

    print(f"\n[MolLingo] Research prompt: \"{prompt}\"")
    print("[MolLingo] Parsing prompt ...\n")

    # Parse prompt with GPT
    params = parse_prompt(prompt)

    # Apply CLI overrides (explicit args always win over GPT-parsed values)
    if args.disease:
        params["disease"] = args.disease
    if args.subtype:
        params["disease_subtype"] = args.subtype
    if args.uniprot:
        params["uniprot_id"] = args.uniprot
    if args.protein:
        params["protein_name"] = args.protein
    if args.mutation:
        params["gene_mutation"] = args.mutation
    if args.pathway:
        params["pathway"] = args.pathway
    if args.task:
        params["main_task"] = args.task
    if args.no_bbbp:
        params["bbbp_desired"] = False

    # Validate minimum required field
    if not params.get("disease"):
        print("[ERROR] Could not identify a disease from the prompt.")
        print("  Tip: be explicit, e.g. 'Design a drug for Parkinson\\'s disease'")
        print("  Or use --disease <name> to specify it directly.")
        sys.exit(1)

    # Echo parsed parameters
    print("[MolLingo] Extracted parameters:")
    for k, v in params.items():
        if v is not None:
            print(f"  {k:<20}: {v}")
    print()

    # Build agent and write ALL parsed entities into shared memory up front
    agent = OrchestratorAgent(
        main_task=params.get("main_task", "ADMET"),
        bbbp_desired=params.get("bbbp_desired", True),
    )

    mem = agent.memory
    mem.user_prompt    = prompt
    mem.disease        = params.get("disease")
    mem.disease_subtype= params.get("disease_subtype")
    mem.gene_mutation  = params.get("gene_mutation")
    mem.pathway        = params.get("pathway")

    if params.get("uniprot_id") and params.get("protein_name"):
        mem.set_target(params["protein_name"], params["uniprot_id"])

    agent.run(
        num_hits=args.hits,
        num_growing_hits=args.growing_hits,
        num_fragment_candidates=args.frags,
        num_leads=args.leads,
        variants=args.variants,
        skip_fragment_growing=args.no_fragment_growing,
        save_path=args.save,
    )

    print()
    print_summary(agent.memory)


if __name__ == "__main__":
    main()
