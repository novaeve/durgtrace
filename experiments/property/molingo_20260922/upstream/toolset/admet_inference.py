import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.loader import DataLoader
from torch_geometric.nn import GINEConv, GlobalAttention
from toolset.smiles2hierarchical_graph import smiles2hierarchical_graph



class AtomGINE(nn.Module):
    def __init__(self, in_dim, hidden_dim, edge_dim, num_layers=2, dropout=0.1):
        super().__init__()

        self.num_layers = num_layers
        self.dropout = dropout
        self.convs = nn.ModuleList()
        self.convs.append(
            GINEConv(
                nn.Sequential(
                    nn.Linear(in_dim, hidden_dim),
                    nn.ReLU(),
                    nn.Linear(hidden_dim, hidden_dim),
                ),
                edge_dim=edge_dim,
            )
        )

        for _ in range(num_layers - 1):
            self.convs.append(
                GINEConv(
                    nn.Sequential(
                        nn.Linear(hidden_dim, hidden_dim),
                        nn.ReLU(),
                        nn.Linear(hidden_dim, hidden_dim),
                    ),
                    edge_dim=edge_dim,
                )
            )

    def forward(self, x, edge_index, edge_attr):
        for conv in self.convs:
            x = conv(x, edge_index, edge_attr)
            x = F.relu(x)
            x = F.dropout(x, p=self.dropout, training=self.training)

        return x

class HierarchicalGNN(nn.Module):
    def __init__(
        self,
        node_in_dim,
        edge_dim,
        hidden_dim=256,
        block_label_dim=17,
        mol_label_dim=17,
        task_dim=1,
        morgan_fp_dim=1024,
    ):
        super().__init__()

        self.hidden_dim = hidden_dim
        self.mol_label_dim = mol_label_dim
        self.atom_encoder = AtomGINE(node_in_dim, hidden_dim, edge_dim)

        self.block_gru = nn.GRU(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            batch_first=True,
            bidirectional=True,
        )
        self.gru_fc = nn.Linear(hidden_dim * 2, hidden_dim)

        self.mol_pool = GlobalAttention(
            gate_nn=nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, 1),
            )
        )

        self.block_pred = nn.Linear(hidden_dim, block_label_dim)
        self.mol_pred = nn.Linear(hidden_dim, mol_label_dim)

        self.mol_label_proj = nn.Linear(mol_label_dim, hidden_dim)
        self.morgan_proj = nn.Linear(morgan_fp_dim, hidden_dim)
        self.fusion_gate = nn.Sequential(
            nn.Linear(hidden_dim * 3, hidden_dim),  # concat mol_emb + mol_label_proj + morgan_proj
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Sigmoid()
        )

        self.task_pred = nn.Linear(hidden_dim, task_dim)

    def forward(self, data):
        x, edge_index, edge_attr = data.x, data.edge_index, data.edge_attr
        atom_batch = data.batch
        block_assign = data.block_assignment

        x = self.atom_encoder(x, edge_index, edge_attr)
        block_embeddings = []
        seq_lens = []

        for mol_id in atom_batch.unique():
            mask = atom_batch == mol_id
            blocks = block_assign[mask].unique()
            seq_lens.append(len(blocks))

            for b in blocks:
                block_mask = mask & (block_assign == b)
                block_embeddings.append(x[block_mask].mean(dim=0))

        block_embeddings = torch.stack(block_embeddings)

        sequences = []
        start = 0
        for length in seq_lens:
            sequences.append(block_embeddings[start:start+length])
            start += length

        padded = nn.utils.rnn.pad_sequence(sequences, batch_first=True)
        lengths = torch.tensor(seq_lens, dtype=torch.long).cpu()

        packed = nn.utils.rnn.pack_padded_sequence(
            padded,
            lengths,
            batch_first=True,
            enforce_sorted=False,
        )

        gru_out, _ = self.block_gru(packed)
        gru_out, _ = nn.utils.rnn.pad_packed_sequence(gru_out, batch_first=True)

        block_embeddings = torch.cat(
            [gru_out[i, :seq_lens[i]] for i in range(len(seq_lens))],
            dim=0,
        )

        block_embeddings = self.gru_fc(block_embeddings)
        block_out = self.block_pred(block_embeddings)
        mol_batch = torch.cat(
            [
                torch.full((seq_lens[i],), i, dtype=torch.long, device=x.device)
                for i in range(len(seq_lens))
            ]
        )
        mol_embedding = self.mol_pool(block_embeddings, mol_batch)
        mol_out = self.mol_pred(mol_embedding)

        data_list = data.to_data_list()

        mol_label_input = torch.stack([d.mol_label for d in data_list]).to(mol_embedding.device)
        mol_label_proj = self.mol_label_proj(mol_label_input)

        morgan_input = torch.stack([d.morgan_fingerprint for d in data_list]).to(mol_embedding.device)
        morgan_proj = self.morgan_proj(morgan_input)

        fusion_input = torch.cat([mol_embedding, mol_label_proj, morgan_proj], dim=1)
        gate = self.fusion_gate(fusion_input)

        fused_embedding = mol_embedding + gate * (mol_label_proj + morgan_proj)

        task_out = self.task_pred(fused_embedding)

        return block_out, mol_out, task_out

# -----------------------------
# 1. Load model
# -----------------------------
def load_model(model_path, sample, device):
    model = HierarchicalGNN(
        node_in_dim=sample.x.size(1),
        edge_dim=sample.edge_attr.size(1),
    ).to(device)

    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()
    return model


# -----------------------------
# 2. Normalize (reuse stats!)
# -----------------------------
def normalize_dataset(data_list,
                      x_mean, x_std,
                      edge_mean, edge_std,
                      block_mean, block_std,
                      mol_mean, mol_std):
    for d in data_list:
        # --- ensure tensor types (CRITICAL) ---
        if isinstance(d.x, list):
            d.x = torch.tensor(d.x, dtype=torch.float)
        if isinstance(d.edge_attr, list):
            d.edge_attr = torch.tensor(d.edge_attr, dtype=torch.float)
        if isinstance(d.block_label, list):
            d.block_label = torch.tensor(d.block_label, dtype=torch.float)
        if isinstance(d.mol_label, list):
            d.mol_label = torch.tensor(d.mol_label, dtype=torch.float)
        if isinstance(d.block_assignment, list):
            d.block_assignment = torch.tensor(d.block_assignment, dtype=torch.long)

        # --- normalization ---
        d.x = (d.x - x_mean) / x_std
        d.edge_attr = (d.edge_attr - edge_mean) / edge_std
        d.block_label = (d.block_label - block_mean) / block_std
        d.mol_label = (d.mol_label - mol_mean) / mol_std


# -----------------------------
# 3. Build dataset from SMILES
# -----------------------------
def smiles_to_dataset(smiles_list):
    data_list = []
    valid_smiles = []

    for sm in smiles_list:
        try:
            g = smiles2hierarchical_graph(sm, label=0)  # dummy label
            data_list.append(g)
            valid_smiles.append(sm)
        except:
            pass

    return data_list, valid_smiles


# -----------------------------
# 4. Inference function
# -----------------------------
def predict_logits(smiles_list, model, device,
                   x_mean, x_std,
                   edge_mean, edge_std,
                   block_mean, block_std,
                   mol_mean, mol_std,
                   batch_size=64):

    data_list, valid_smiles = smiles_to_dataset(smiles_list)

    if len(data_list) == 0:
        return [], []

    normalize_dataset(data_list,
                      x_mean, x_std,
                      edge_mean, edge_std,
                      block_mean, block_std,
                      mol_mean, mol_std)

    loader = DataLoader(data_list, batch_size=batch_size)

    all_logits = []

    with torch.no_grad():
        for batch in loader:
            batch = batch.to(device)

            # Only care about task_out
            _, _, task_out = model(batch)

            all_logits.append(task_out.cpu())

    all_logits = torch.cat(all_logits)
    all_probs = torch.sigmoid(all_logits).numpy().ravel()

    return valid_smiles, all_probs


# -----------------------------
# 5. Example usage
# -----------------------------
def admet_inference(smiles_list, name, device, ckpt_path='ckpts'):

    checkpoint = torch.load(f"{ckpt_path}/{name}_norm_stats.pt")

    x_mean = checkpoint["x_mean"]
    x_std = checkpoint["x_std"]
    edge_mean = checkpoint["edge_mean"]
    edge_std = checkpoint["edge_std"]
    block_mean = checkpoint["block_mean"]
    block_std = checkpoint["block_std"]
    mol_mean = checkpoint["mol_mean"]
    mol_std = checkpoint["mol_std"]

    # Build one sample to initialize model
    dummy_data, _ = smiles_to_dataset(["CCO"])
    sample = dummy_data[0]

    model = load_model(f"{ckpt_path}/{name}.pt", sample, device)

    smiles_out, logits = predict_logits(
        smiles_list,
        model,
        device,
        x_mean, x_std,
        edge_mean, edge_std,
        block_mean, block_std,
        mol_mean, mol_std
    )

    return logits