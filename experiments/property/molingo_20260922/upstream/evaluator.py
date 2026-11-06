class MoleculeEvaluator:

    def score(self, admet, docking, sa):

        score = 0

        score -= docking

        score += admet["HIA"]
        score -= admet["AMES"]
        score -= admet["hERG"]
        score -= admet["DILI"]
        score -= admet["Pgp"]*0.8
        score -= admet["CYP3A4"]*0.8

        score -= sa

        return score