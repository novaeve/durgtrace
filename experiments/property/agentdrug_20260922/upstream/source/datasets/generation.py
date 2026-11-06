import pandas as pd
from torch.utils.data import Dataset
from source.utils.evaluation import *

class GenerationDataset(Dataset):
    def __init__(self, path, data, split="train", hit_thres=0, DB_size=None):
        super().__init__()
        prop = data.split("/")[-1]
        self.questions = pd.read_csv(f'{path}/{data}/{split}.csv')
        self.questions["SMILES"] = self.questions["SMILES"].str.replace('\\\\', '\\')
        if split == "test":
            self.questions = self.questions.sample(n=100, random_state=0).reset_index(drop=True) if len(self.questions) > 100 else self.questions

        DB_path = "/".join(data.split("/")[:-2])
        self.DB = pd.read_csv(f'{path}/{DB_path}/database.csv')
        self.DB = self.DB.sample(frac=1, random_state=42).reset_index(drop=True)
        self.DB = self.DB.head(DB_size)
        self.DB["SMILES"] = self.DB["SMILES"].str.replace('\\\\', '\\')
        self.DB["mol"] = self.DB["SMILES"].apply(Chem.MolFromSmiles)
        if "single" in data:
            self.DB["prop"] = self.DB["mol"].apply(task2func[prop])
            if hit_thres > 0:
                if "HB" in data:
                    self.questions["Text"] = self.questions["Text"].apply(lambda s: s.replace(". The modified molecule should be similar to the original one.", f' by at least {task2thres[prop][hit_thres][0] + 1}. The modified molecule should be similar to the original one.'))
                else:
                    self.questions["Text"] = self.questions["Text"].apply(lambda s: s.replace(". The modified molecule should be similar to the original one.", f' by at least {task2thres[prop][hit_thres][0]}. The modified molecule should be similar to the original one.'))
        if "multi" in data:
            logp, prop = prop[:5], prop[5:]
            self.DB["logp"], self.DB["prop"] = self.DB["mol"].apply(task2func[logp]), self.DB["mol"].apply(task2func[prop])
            if hit_thres > 0:
                if "HB" in data:
                    self.questions["Text"] = self.questions["Text"].apply(lambda s: s.replace("LogP value", f'LogP value by at least {task2thres[logp][hit_thres][0]}').replace(". The modified molecule should be similar to the original one.", f' by at least {task2thres[prop][hit_thres][0] + 1}. The modified molecule should be similar to the original one.'))
                else:
                    self.questions["Text"] = self.questions["Text"].apply(lambda s: s.replace("LogP value", f'LogP value by at least {task2thres[logp][hit_thres][0]}').replace(". The modified molecule should be similar to the original one.", f' by at least {task2thres[prop][hit_thres][0]}. The modified molecule should be similar to the original one.'))

        self.data = data
        self.hit_thres = hit_thres

    def __len__(self):
        """Return the len of the dataset."""
        return len(self.questions)

    def __getitem__(self, index):
        item = self.questions.iloc[index]

        question = f'{item["Text"]}\nRespond with only the SMILES string of your modified molecule. No explanation is needed.'
        return {"id": index,
            "smiles": item["SMILES"],
            "prompt": f'{question}\n\nMolecule:{item["SMILES"]}\nAnswer:',
            "label": item["modifiedSMILES"],
        }