from typing import Optional
from memory import SharedMemory
from agent import LiteratureAgent, ChemistAgent


class OrchestratorAgent:
    """
    Coordinates the full MolLingo drug discovery pipeline through a shared memory module:

      Stage 1 — Target identification   (LiteratureAgent)
      Stage 2 — Hit identification       (ChemistAgent)
      Stage 3 — Hit-to-lead              (ChemistAgent — context-aware fragment growing)
      Stage 4 — Lead optimization        (ChemistAgent — block-based ADMET refinement)

    Each stage writes its results to SharedMemory, which all agents read from.
    The pipeline can be started at any stage by pre-populating the memory.

    Example — full run from disease name:
        agent = OrchestratorAgent(
            disease="Alzheimer's disease",
            gene_mutation="GBA1 loss-of-function",
            bbbp_desired=True,
        )
        summary = agent.run(save_path="results.json")

    Example — skip target identification (known target):
        agent = OrchestratorAgent(
            disease="CML",
            uniprot_id="P00519", protein_name="ABL1",
            main_task="DILI",
        )
        summary = agent.run()

    Example — run stages manually for inspection:
        agent = OrchestratorAgent(disease="Parkinson's disease", gene_mutation="LRRK2")
        agent.run_target_identification()
        hits = agent.run_hit_identification(num_candidates=50)
        leads = agent.run_hit_to_lead(num_hits=5)
        candidates = agent.run_lead_optimization(num_leads=3)
        print(agent.memory.summary())
    """

    def __init__(
        self,
        disease: Optional[str] = None,
        disease_subtype: Optional[str] = None,
        gene_mutation: Optional[str] = None,
        pathway: Optional[str] = None,
        uniprot_id: Optional[str] = None,
        protein_name: Optional[str] = None,
        main_task: str = 'ADMET',
        bbbp_desired: bool = True,
        memory: Optional[SharedMemory] = None,
    ):
        self.memory = memory or SharedMemory()
        self.memory.main_task = main_task
        self.memory.bbbp_desired = bbbp_desired

        if disease:
            self.memory.disease = disease
            self.memory.disease_subtype = disease_subtype
        if gene_mutation:
            self.memory.gene_mutation = gene_mutation
        if pathway:
            self.memory.pathway = pathway
        if uniprot_id and protein_name:
            self.memory.set_target(protein_name, uniprot_id)

        self.literature_agent = LiteratureAgent(self.memory)
        self.chemist_agent = ChemistAgent(self.memory)

    # ------------------------------------------------------------------ #
    # Individual stage runners                                             #
    # ------------------------------------------------------------------ #

    def run_target_identification(self) -> dict:
        assert self.memory.disease, "Set disease before running target identification."
        return self.literature_agent.identify_target(
            disease=self.memory.disease,
            subtype=self.memory.disease_subtype,
            pathway=self.memory.pathway,
            gene_mutation=self.memory.gene_mutation,
        )

    def run_hit_identification(self, num_candidates: int = 30) -> list:
        assert self.memory.uniprot_id, "Target must be set before hit identification."
        return self.chemist_agent.identify_hits(num_candidates=num_candidates)

    def run_hit_to_lead(
        self, num_hits: int = 5, num_fragment_candidates: int = 5
    ) -> list:
        assert self.memory.hits, "Identify hits before running hit-to-lead."
        return self.chemist_agent.grow_hits(
            num_hits=num_hits,
            num_fragment_candidates=num_fragment_candidates,
        )

    def run_lead_optimization(self, num_leads: int = 3, variants: int = 20) -> list:
        assert self.memory.hits or self.memory.leads, \
            "Hits or leads must exist before lead optimization."
        return self.chemist_agent.optimize_leads(num_leads=num_leads, variants=variants)

    # ------------------------------------------------------------------ #
    # Full pipeline                                                        #
    # ------------------------------------------------------------------ #

    def run(
        self,
        num_hits: int = 30,
        num_growing_hits: int = 5,
        num_fragment_candidates: int = 5,
        num_leads: int = 3,
        variants: int = 20,
        skip_fragment_growing: bool = False,
        save_path: Optional[str] = None,
    ) -> dict:
        """
        Run the full MolLingo pipeline end-to-end and return a result summary.
        All task context (disease, target, gene_mutation, pathway, main_task, etc.)
        must be set on self.memory before calling run().

        Parameters
        ----------
        num_hits                : How many ChEMBL candidates to retrieve.
        num_growing_hits        : How many top hits to run fragment growing on.
        num_fragment_candidates : GPT fragment proposals per hotspot per hit.
        num_leads               : How many leads to pass to lead optimization.
        variants                : Block substitution variants to explore per lead.
        skip_fragment_growing   : Go directly from hits to lead optimization.
        save_path               : If set, saves full memory to this JSON path.
        """
        self.memory.log("OrchestratorAgent", "pipeline_start",
                        f"MolLingo starting for '{self.memory.disease}'")

        # Stage 1 — Target identification
        if not self.memory.uniprot_id:
            self.run_target_identification()

        if not self.memory.uniprot_id:
            self.memory.log("OrchestratorAgent", "pipeline_abort",
                            "Could not identify a target. Stopping.")
            return self.memory.summary()

        # Stage 2 — Hit identification
        self.run_hit_identification(num_candidates=num_hits)

        if not self.memory.hits:
            self.memory.log("OrchestratorAgent", "pipeline_abort",
                            "No hits found. Stopping.")
            return self.memory.summary()

        # Stage 3 — Hit-to-lead via fragment growing
        if not skip_fragment_growing:
            self.run_hit_to_lead(
                num_hits=num_growing_hits,
                num_fragment_candidates=num_fragment_candidates,
            )
        else:
            self.memory.log("OrchestratorAgent", "skipping_fragment_growing",
                            "Proceeding directly to lead optimization.")

        # Stage 4 — Lead optimization
        self.run_lead_optimization(num_leads=num_leads, variants=variants)

        best = (self.memory.best_candidate()
                or self.memory.best_lead()
                or self.memory.best_hit())
        self.memory.log("OrchestratorAgent", "pipeline_complete",
                        f"Best molecule: {best}")

        if save_path:
            self.memory.save(save_path)
            self.memory.log("OrchestratorAgent", "saved", f"Results → {save_path}")

        return self.memory.summary()
