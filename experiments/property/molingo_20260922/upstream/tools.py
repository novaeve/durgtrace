# generic Tool interface
from toolset.ADMET import *
from toolset.autodockvina_docking import autodockvina_docking
from toolset.protein2binders import protein2binders
from toolset.sascorer import calculateScore
from toolset.uniprotID2name import uniprotID2name
from toolset.drug2protein import drug2protein
from toolset.optimize_mol import optimize_mol


class FunctionTool:
    """
    Generic wrapper for any function-based tool.
    """

    def __init__(self, name: str, description: str, inp: str, outp : str,  func):
        self.name = name
        self.inp = inp
        self.outp = outp
        self.description = description
        self.func = func

    def run(self, **kwargs):
        return self.func(**kwargs)

############################### Tool Register ###############################


# Tool registry
TOOLS = {
    "admet_profile": FunctionTool(
        name="admet_property_predictor",
        description="Comprehensive ADMET profiling. Predicts toxicity, metabolism, and physical properties in one call.",
        inp="smiles (str): The SMILES string of the molecule to analyze.",
        outp=(
            "dict: { "
            "'AMES': bool, 'DILI': bool, 'hERG': bool, 'HIA': bool, 'Pgp': bool, 'BBBP': bool, 'CYP3A4': bool, "
            "'Lipophilicity': float (logP), 'Solubility': float (logS)"
            "}"
        ),
        func=ADMET_Profile,
    ),

    ###########################################################################################################
    "autodock_vina_docking": FunctionTool(
        name="autodock_vina_docking",
        description="Perform molecular docking to estimate the binding affinity between a small molecule and a target protein.",
        inp=(
            "smiles (str): The SMILES string of the ligand molecule. "
            "uniprot_id (str): The UniProt accession number of the target protein (e.g., 'P00533')."
        ),
        outp="float: The predicted binding affinity score (Gibbs free energy, $\Delta G$) in kcal/mol. Lower (more negative) values indicate stronger binding.",
        func=autodockvina_docking
    ),

    "protein_binder_retrieval": FunctionTool(
        name="protein_binder_retrieval",
        description=(
            "Search the ChEMBL database for molecules with experimentally validated binding activity against a specific protein target."
        ),
        inp="uniprot_id (str): The UniProt accession number of the target protein (e.g., 'P00533').",
        outp=(
            "pd.DataFrame: A table of bioactivity data. Columns include: "
            "'molecule_chembl_id' (ID), 'canonical_smiles' (SMILES), "
            "'standard_type' (e.g., IC50, Ki, Kd), 'standard_value' (the numerical value), "
            "'standard_units' (e.g., nM), 'standard_relation' (e.g., '<', '='), "
            "and 'pchembl_value' (logarithmic scale of potency)."
        ),
        func=protein2binders
    ),

    "synthetic_accessibility_score": FunctionTool(
        name="synthetic_accessibility_score",
        description=(
            "Calculate the Synthetic Accessibility (SA) Score to estimate the ease of synthesis for a molecule "
            "based on molecular complexity and fragment contributions."
        ),
        inp="smiles (str): The SMILES string of the molecule to be evaluated.",
        outp=(
            "float: The SA Score, typically ranging from 1 to 10. "
            "A score of 1 indicates very high accessibility (easy to synthesize), "
            "while a score of 10 indicates very low accessibility (extremely difficult to synthesize)."
        ),
        func=calculateScore
    ),

    "uniprot_id_to_name": FunctionTool(
        name="uniprot_id_to_name",
        description="Retrieve the primary, recommended protein name associated with a specific UniProt accession number.",
        inp="uniprot_id (str): The UniProt accession number (e.g., 'P04637').",
        outp="str: The official recommended name of the protein (e.g., 'Cellular tumor antigen p53').",
        func=uniprotID2name
    ),

    "drug2protein": FunctionTool(
        name="drug2protein",
        description=(
            "Search for known or predicted protein targets for a specific drug. "
            "Useful for identifying the mechanism of action or potential off-target effects."
        ),
        inp="drug_name (str): The common name or brand name of the drug (e.g., 'Gleevec' or 'Imatinib').",
        outp=(
            "dict: A mapping where keys are UniProt Accession IDs (str) "
            "and values are the corresponding Protein Names (str). "
            "Example: {'P00519': 'Tyrosine-protein kinase ABL1'}."
        ),
        func=drug2protein
    ),

    "molecule_optimizer": FunctionTool(
        name="molecule_optimizer",
        description=(
            "An AI-driven lead optimization tool that suggests structural modifications to a lead compound. "
            "It aims to resolve specific liabilities (e.g., high toxicity or low solubility) while maintaining core scaffold potency."
        ),
        inp=(
            "smiles (str): The SMILES string of the starting molecule. "
            "molecule_name (str): The common name or identifier of the molecule."
        ),
        outp=(
            "list[dict]: A list of SMILES of optimized molecule candidates for the given task."
        ),
        func=optimize_mol
    ),
}