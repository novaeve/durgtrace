"""SMDD-specific LIDDIA tools. No docking or unrestricted prediction fallback.

This module does not replace LIDDIA's planner or memory. Callers must supply
task-public pocket inputs and bind learned scorers to the shared BudgetGate.
"""
from pathlib import Path
import json
import math
import os
import random
import subprocess
import threading
import uuid

import pandas as pd
import yaml
from rdkit import Chem
from rdkit.Chem import QED
from rdkit.Contrib.SA_Score import sascorer
from runtime_safety import ToolExecutionError, require_disk


class BudgetExhausted(RuntimeError):
    pass


class BudgetGate:
    """Count attempts before execution, including failed calls; no free retry.

    A fresh journal is required: interrupted runs must not silently reset budgets.
    Backends receive one SMILES per call, so batching cannot bypass the limit.
    """
    def __init__(self, journal, backends, limits=None, resume=False):
        self.journal = Path(journal)
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        if self.journal.exists() and not resume:
            raise FileExistsError('Refuse to reset an existing budget journal')
        if resume and not self.journal.exists():raise FileNotFoundError(self.journal)
        self.journal.touch(exist_ok=resume)
        self.backends = backends
        self.limits = dict(limits or {'admet': 15, 'boltz': 8})
        if set(self.limits) != {'admet', 'boltz'} or set(backends) - set(self.limits):
            raise ValueError('Only ADMET and Boltz backends are supported')
        self.used = dict.fromkeys(self.limits, 0)
        if resume:
            for line in self.journal.read_text().splitlines():
                event=json.loads(line)
                if event['event']=='reserved':
                    kind=event['kind'];self.used[kind]+=1
                    if event['call']!=self.used[kind] or self.used[kind]>self.limits[kind]:
                        raise ValueError('Invalid resumed budget journal')
        self.lock = threading.Lock()

    def _record(self, event):
        with self.journal.open('a') as f:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')

    def predict(self, kind, smiles):
        if kind not in self.backends:
            raise ValueError('Prediction backend unavailable: ' + kind)
        if not isinstance(smiles, str) or Chem.MolFromSmiles(smiles) is None:
            raise ValueError('One valid SMILES is required')
        with self.lock:
            if self.used[kind] >= self.limits[kind]:
                raise BudgetExhausted(kind)
            self.used[kind] += 1
            call = self.used[kind]
            self._record({'event': 'reserved', 'kind': kind, 'call': call, 'smiles': smiles})
        try:
            result = self.backends[kind](smiles)
        except Exception as exc:
            with self.lock:
                self._record({'event': 'error', 'kind': kind, 'call': call, 'type': type(exc).__name__})
            raise
        with self.lock:
            self._record({'event': 'result', 'kind': kind, 'call': call, 'result': result})
        return result


class Pocket2MolTool:
    def __init__(self, root, output_dir, center, seed=42, bbox_size=23.0, beam_size=300, device='cpu', gpu=3):
        self.root = Path(root).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.center = [float(x) for x in center]
        if len(self.center) != 3 or not all(math.isfinite(x) for x in self.center):
            raise ValueError('A real task pocket center is required')
        self.seed, self.bbox_size = seed, float(bbox_size)
        self.rng = random.Random(seed)
        self.beam_size = int(beam_size)
        if device not in ('cpu','cuda'):
            raise ValueError('Unknown sampling device')
        self.device, self.gpu = device, int(gpu)

    def __call__(self, input_pdb, n_samples=100):
        pdb = Path(input_pdb).resolve()
        if not pdb.is_file() or not any(x.startswith('ATOM  ') for x in pdb.read_text().splitlines()):
            raise ValueError('Pocket must contain protein atoms')
        if not isinstance(n_samples, int) or not 1 <= n_samples <= 100:
            raise ValueError('n_samples must be 1..100')
        repo = self.root / 'Pocket2Mol'
        job = self.output_dir / ('pocket_' + uuid.uuid4().hex[:12])
        job.mkdir(parents=True, exist_ok=False)
        config = yaml.safe_load((repo / 'configs/sample_for_pdb.yml').read_text())
        config['model']['checkpoint'] = str(repo / 'ckpt/pretrained_Pocket2Mol.pt')
        action_seed = self.rng.randrange(1, 1_000_000_000)
        config['sample'].update(seed=action_seed, num_samples=n_samples, beam_size=self.beam_size, save_snapshots=False)
        cfg = job / 'config.yml'
        cfg.write_text(yaml.safe_dump(config))
        python = self.root / ('envs/pocket_gpu/bin/python' if self.device=='cuda' else 'envs/liddia/bin/python')
        require_disk(job)
        cmd = [str(python), str(Path(__file__).with_name('pocket_runtime.py')),
               '--pdb_path', str(pdb), '--center', ' ' + ','.join(map(str, self.center)),
               '--bbox_size', str(self.bbox_size), '--device', self.device, '--config', str(cfg),
               '--outdir', str(job / 'output')]
        env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        env['PYTHONPATH']=str(repo)+os.pathsep+env.get('PYTHONPATH','')
        if self.device == 'cuda':
            env.update(CUDA_VISIBLE_DEVICES=str(self.gpu),TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD='1')
        with (job / 'sampling.log').open('w') as log:
            try:
                subprocess.run(cmd, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=3600)
            except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as exc:
                require_disk(job)
                raise ToolExecutionError('Pocket2Mol failed; see '+str(job/'sampling.log')) from exc
        smis = []
        for path in sorted((job / 'output').glob('*/SMILES.txt')):
            for line in path.read_text().splitlines():
                smi = line.strip()
                if smi and Chem.MolFromSmiles(smi) is not None:
                    smis.append(smi)
        return pd.DataFrame({'SMILES': list(dict.fromkeys(smis))[:n_samples]}), {
            'seed': action_seed, 'run_seed': self.seed, 'requested': n_samples, 'generated_valid': len(smis),
            'job': str(job), 'center': self.center, 'beam_size': self.beam_size,
            'device':self.device, 'gpu':self.gpu if self.device=='cuda' else None, 'vina_calls': 0}


class GraphGATool:
    """Original GraphGA search with a strict outer scoring-call cap.

    Additional scorers must be trusted host callbacks using the SAME BudgetGate
    as explicit agent calls. No API clients or Vina scorers are created here.
    """
    def __init__(self, scorers=None, seed=42):
        self.scorers = dict(scorers or {})
        if any('vina' in x.lower() or 'dock' in x.lower() for x in self.scorers):
            raise ValueError('Docking is disabled for SMDD')
        self.seed = seed
        self.rng = random.Random(seed)

    def __call__(self, input_df, property, n_outputs, output_dir, **kwargs):
        from molopt.graph_ga import GraphGA
        if property == 'QED':
            scorer, cap = lambda s: QED.qed(Chem.MolFromSmiles(s)), 500
        elif property == 'SAScore':
            scorer, cap = lambda s: 1 - (sascorer.calculateScore(Chem.MolFromSmiles(s)) - 1) / 9, 300
        elif property in self.scorers:
            scorer, cap = self.scorers[property], 500
        else:
            raise ValueError('Unsupported objective; Vina/docking is disabled: ' + property)
        cap = min(cap, int(kwargs.get('score_cap', cap)))
        if cap < 1:
            raise ValueError('score_cap must be positive')
        output = Path(output_dir) / ('graphga_' + uuid.uuid4().hex[:12])
        output.mkdir(parents=True, exist_ok=False)
        scores = {}
        def reward(smi):
            if smi in scores:
                return scores[smi]
            if len(scores) >= cap:
                raise BudgetExhausted('graphga_score_cap')
            value = float(scorer(smi))
            if not math.isfinite(value) or value < 0:
                raise ValueError('GraphGA requires finite nonnegative rewards')
            scores[smi] = value
            return value
        smiles = [s for s in input_df['SMILES'] if Chem.MolFromSmiles(s) is not None]
        if not smiles:
            raise ValueError('GraphGA needs a valid starting population')
        optimizer = GraphGA(smi_file=smiles, n_jobs=1, max_oracle_calls=cap,
                            freq_log=max(100, cap + 1), output_dir=str(output), log_results=False)
        optimizer.oracle.mol_buffer = {}
        stop = 'algorithm_finished'
        action_seed = self.rng.randrange(1, 1_000_000_000)
        try:
            optimizer.optimize(oracle=reward, patience=5, seed=action_seed)
        except BudgetExhausted as exc:
            stop = 'budget_exhausted:' + str(exc)
        except ToolExecutionError as exc:
            stop = 'tool_error:' + str(exc)
        ranked = sorted(scores, key=scores.get, reverse=True)
        metadata = {'seed': action_seed, 'run_seed': self.seed, 'objective': property, 'score_calls': len(scores),
                    'score_cap': cap, 'stop': stop, 'scores': scores, 'vina_calls': 0}
        (output / 'adapter_results.json').write_text(json.dumps(metadata, indent=2))
        return pd.DataFrame({'SMILES': ranked[:n_outputs]}), metadata
