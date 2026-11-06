import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SharedMemory:
    """
    Central knowledge store shared across all MolLingo agents.
    Persists structured results (hits, leads, candidates) and unstructured
    reasoning traces throughout the drug discovery workflow.
    """

    # Task context
    user_prompt: Optional[str] = None
    disease: Optional[str] = None
    disease_subtype: Optional[str] = None
    gene_mutation: Optional[str] = None
    pathway: Optional[str] = None
    uniprot_id: Optional[str] = None
    protein_name: Optional[str] = None
    target_reference: Optional[str] = None

    # Optimization goal
    main_task: str = 'ADMET'   # ADMET | DILI | hERG | AMES | Pgp | HIA | BBBP
    bbbp_desired: bool = True  # True for CNS targets, False for peripherally-acting drugs

    # Pipeline state — all dicts keyed by SMILES string
    hits: dict = field(default_factory=dict)
    # hits[smi] = {docking_score, admet_profile, admet_score, source}

    leads: dict = field(default_factory=dict)
    # leads[smi] = {hit_origin, docking_score, fragment, rationale}

    candidates: dict = field(default_factory=dict)
    # candidates[smi] = {lead_origin, admet_score, admet_profile}

    # Reasoning trace
    trace: list = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Write helpers                                                        #
    # ------------------------------------------------------------------ #

    def log(self, agent: str, step: str, content: Any):
        entry = {"agent": agent, "step": step, "content": str(content)}
        self.trace.append(entry)
        print(f"[{agent}] {step}: {content}")

    def set_target(self, protein_name: str, uniprot_id: str, reference: str = None):
        self.protein_name = protein_name
        self.uniprot_id = uniprot_id
        if reference:
            self.target_reference = reference

    def add_hit(self, smiles: str, docking_score: float = None,
                admet_profile: dict = None, admet_score: float = None,
                source: str = 'chembl'):
        self.hits[smiles] = {
            'docking_score': docking_score,
            'admet_profile': admet_profile or {},
            'admet_score': admet_score,
            'source': source,
        }

    def add_lead(self, smiles: str, hit_origin: str, docking_score: float,
                 fragment: str = None, rationale: str = None):
        self.leads[smiles] = {
            'hit_origin': hit_origin,
            'docking_score': docking_score,
            'fragment': fragment,
            'rationale': rationale,
        }

    def add_candidate(self, smiles: str, lead_origin: str,
                      admet_score: float, admet_profile: dict = None):
        self.candidates[smiles] = {
            'lead_origin': lead_origin,
            'admet_score': admet_score,
            'admet_profile': admet_profile or {},
        }

    # ------------------------------------------------------------------ #
    # Query helpers                                                        #
    # ------------------------------------------------------------------ #

    def top_hits(self, n: int = 5) -> list:
        """Top-n hits by docking score (lower is better). Falls back to insertion order."""
        scored = [(s, d['docking_score']) for s, d in self.hits.items()
                  if d['docking_score'] is not None]
        if scored:
            scored.sort(key=lambda x: x[1])
            return [s for s, _ in scored[:n]]
        return list(self.hits.keys())[:n]

    def best_hit(self) -> Optional[str]:
        tops = self.top_hits(1)
        return tops[0] if tops else None

    def best_lead(self) -> Optional[str]:
        if not self.leads:
            return None
        scored = [(s, d['docking_score']) for s, d in self.leads.items()
                  if d['docking_score'] is not None]
        if scored:
            return min(scored, key=lambda x: x[1])[0]
        return list(self.leads.keys())[0]

    def best_candidate(self) -> Optional[str]:
        if not self.candidates:
            return None
        scored = [(s, d['admet_score']) for s, d in self.candidates.items()
                  if d['admet_score'] is not None]
        if scored:
            return max(scored, key=lambda x: x[1])[0]
        return list(self.candidates.keys())[0]

    def summary(self) -> dict:
        best_hit = self.best_hit()
        best_lead = self.best_lead()
        best_cand = self.best_candidate()
        return {
            # Research context
            'user_prompt': self.user_prompt,
            'disease': self.disease,
            'disease_subtype': self.disease_subtype,
            'gene_mutation': self.gene_mutation,
            'pathway': self.pathway,
            # Target
            'protein_name': self.protein_name,
            'uniprot_id': self.uniprot_id,
            'target_reference': self.target_reference,
            # Optimization goal
            'main_task': self.main_task,
            'bbbp_desired': self.bbbp_desired,
            # Pipeline results
            'n_hits': len(self.hits),
            'best_hit': best_hit,
            'best_hit_docking': self.hits[best_hit]['docking_score'] if best_hit else None,
            'n_leads': len(self.leads),
            'best_lead': best_lead,
            'best_lead_docking': self.leads[best_lead]['docking_score'] if best_lead else None,
            'n_candidates': len(self.candidates),
            'best_candidate': best_cand,
            'best_candidate_admet': self.candidates[best_cand]['admet_score'] if best_cand else None,
        }

    # ------------------------------------------------------------------ #
    # Persistence                                                          #
    # ------------------------------------------------------------------ #

    def save(self, path: str):
        with open(path, 'w') as f:
            json.dump({
                'user_prompt': self.user_prompt,
                'disease': self.disease,
                'disease_subtype': self.disease_subtype,
                'gene_mutation': self.gene_mutation,
                'pathway': self.pathway,
                'uniprot_id': self.uniprot_id,
                'protein_name': self.protein_name,
                'target_reference': self.target_reference,
                'main_task': self.main_task,
                'bbbp_desired': self.bbbp_desired,
                'hits': self.hits,
                'leads': self.leads,
                'candidates': self.candidates,
                'trace': self.trace,
            }, f, indent=2)

    @classmethod
    def load(cls, path: str) -> 'SharedMemory':
        with open(path) as f:
            data = json.load(f)
        mem = cls()
        for k, v in data.items():
            setattr(mem, k, v)
        return mem
