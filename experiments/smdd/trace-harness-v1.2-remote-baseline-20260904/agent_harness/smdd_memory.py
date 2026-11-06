"""Lightweight, task-local dynamic memory for SMDD agent runs.

This is a harness component, not a trainable model.  It records evaluated
candidate transitions, ranks reusable edits by structure and observed
outcomes, and emits a compact prompt block when progress plateaus.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

try:
    from rdkit import Chem, DataStructs
    from rdkit.Chem.rdMolDescriptors import GetMorganFingerprintAsBitVect
    _HAS_RDKIT = True
except Exception:  # pragma: no cover - fallback keeps the harness importable
    _HAS_RDKIT = False


@dataclass
class MemoryEntry:
    task_signature: str
    parent_smiles: str
    candidate_smiles: str
    metric_deltas: Dict[str, float] = field(default_factory=dict)
    score_delta: float = 0.0
    constraints_ok: Optional[bool] = None
    edit_summary: str = ""
    retrieval_count: int = 0
    positive_uses: int = 0
    negative_uses: int = 0


def _canonical(smiles: str) -> str:
    if not smiles:
        return ""
    if not _HAS_RDKIT:
        return str(smiles).strip()
    mol = Chem.MolFromSmiles(str(smiles))
    return Chem.MolToSmiles(mol) if mol is not None else str(smiles).strip()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if not _HAS_RDKIT:
        return 1.0 if a == b else 0.0
    ma, mb = Chem.MolFromSmiles(a), Chem.MolFromSmiles(b)
    if ma is None or mb is None:
        return 0.0
    fa = GetMorganFingerprintAsBitVect(ma, 2, nBits=2048)
    fb = GetMorganFingerprintAsBitVect(mb, 2, nBits=2048)
    return float(DataStructs.TanimotoSimilarity(fa, fb))


def infer_objective_directions(task_description: str) -> Dict[str, float]:
    """Infer primary optimize directions from public task text only."""
    directions: Dict[str, float] = {}
    for match in re.finditer(
        r"[-*]\s*([A-Za-z0-9_]+)\s*:\s*(increase|decrease|maximize|minimize)",
        task_description or "",
        flags=re.IGNORECASE,
    ):
        name, direction = match.group(1).lower(), match.group(2).lower()
        directions[name] = -1.0 if direction in ("decrease", "minimize") else 1.0
    return directions


class SMDDSkillMemory:
    """Small persistent experience pool intended for one SMDD task/run."""

    def __init__(
        self,
        path: Optional[str] = None,
        max_entries: int = 256,
        top_k: int = 2,
        min_delta: float = 0.01,
        plateau_window: int = 3,
        similarity_threshold: float = 0.30,
        objective_directions: Optional[Dict[str, float]] = None,
    ):
        self.path = path
        self.max_entries = max_entries
        self.top_k = top_k
        self.min_delta = min_delta
        self.plateau_window = plateau_window
        self.similarity_threshold = similarity_threshold
        self.objective_directions = objective_directions or {}
        self.entries: List[MemoryEntry] = []
        self.recent_scores: List[float] = []
        self.observation_count = 0
        self._lock = threading.Lock()
        if path and os.path.isfile(path):
            self.load(path)

    def _score(self, deltas: Dict[str, float]) -> float:
        if not deltas:
            return 0.0
        if self.objective_directions:
            return sum(
                float(self.objective_directions.get(k, 0.0)) * float(v)
                for k, v in deltas.items()
                if k in self.objective_directions
            )
        return sum(float(v) for v in deltas.values())

    def observe(
        self,
        *,
        task_signature: str,
        parent_smiles: str,
        candidate_smiles: str,
        metrics_before: Optional[Dict[str, Any]],
        metrics_after: Optional[Dict[str, Any]],
        constraints_ok: Optional[bool] = None,
        edit_summary: str = "",
    ) -> Optional[MemoryEntry]:
        parent = _canonical(parent_smiles)
        candidate = _canonical(candidate_smiles)
        self.observation_count += 1
        if not candidate or candidate == parent:
            return None
        before = metrics_before or {}
        after = metrics_after or {}
        deltas = {}
        for key in set(before) & set(after):
            try:
                deltas[key] = float(after[key]) - float(before[key])
            except (TypeError, ValueError):
                continue
        score = self._score(deltas)
        self.recent_scores.append(score if constraints_ok is not False else -abs(score))
        self.recent_scores = self.recent_scores[-self.plateau_window:]
        if abs(score) < self.min_delta and constraints_ok is not False:
            return None
        entry = MemoryEntry(
            task_signature=task_signature,
            parent_smiles=parent,
            candidate_smiles=candidate,
            metric_deltas=deltas,
            score_delta=score,
            constraints_ok=constraints_ok,
            edit_summary=edit_summary or "observed structural edit",
        )
        with self._lock:
            duplicate = next(
                (e for e in self.entries
                 if e.task_signature == entry.task_signature
                 and e.parent_smiles == entry.parent_smiles
                 and e.candidate_smiles == entry.candidate_smiles),
                None,
            )
            if duplicate is not None:
                if abs(entry.score_delta) > abs(duplicate.score_delta):
                    duplicate.metric_deltas = entry.metric_deltas
                    duplicate.score_delta = entry.score_delta
                    duplicate.constraints_ok = entry.constraints_ok
                return duplicate
            self.entries.append(entry)
            self.entries.sort(key=lambda e: abs(e.score_delta), reverse=True)
            self.entries = self.entries[: self.max_entries]
        self.save()
        return entry

    def is_plateau(self) -> bool:
        return len(self.recent_scores) >= self.plateau_window and not any(
            score > self.min_delta for score in self.recent_scores
        )

    def retrieve(self, *, task_signature: str, smiles: str, top_k: Optional[int] = None) -> List[MemoryEntry]:
        query = _canonical(smiles)
        candidates = []
        total = max(1, sum(e.retrieval_count for e in self.entries))
        for entry in self.entries:
            if entry.task_signature != task_signature or entry.constraints_ok is False:
                continue
            sim = _similarity(query, entry.parent_smiles)
            if sim < self.similarity_threshold:
                continue
            usage_rate = (
                (entry.positive_uses - entry.negative_uses)
                / max(1, entry.retrieval_count)
            )
            explore = 0.25 * math.sqrt(math.log(total + 1) / (entry.retrieval_count + 1))
            rank = abs(entry.score_delta) + usage_rate + explore + sim
            candidates.append((rank, entry))
        candidates.sort(key=lambda x: x[0], reverse=True)
        result = [entry for _, entry in candidates[: (top_k or self.top_k)]]
        for entry in result:
            entry.retrieval_count += 1
        if result:
            self.save()
        return result

    def record_outcome(self, entries: List[MemoryEntry], score_delta: float) -> None:
        for entry in entries:
            if score_delta > 0:
                entry.positive_uses += 1
            else:
                entry.negative_uses += 1
        if entries:
            self.save()

    @staticmethod
    def render(entries: List[MemoryEntry]) -> str:
        if not entries:
            return ""
        lines = ["## Retrieved molecular-edit skills (参考，不要复制分子)"]
        for i, entry in enumerate(entries, 1):
            delta = ", ".join(f"{k}={v:+.3g}" for k, v in entry.metric_deltas.items())
            lines.append(
                f"{i}. {entry.edit_summary}; observed delta: {delta or 'unknown'}; "
                f"reuse success={entry.positive_uses}/{max(1, entry.retrieval_count)}"
            )
        lines.append("基于这些经验提出一个新的、可验证的修改，不要直接复制作历史 SMILES。")
        return "\n".join(lines)

    def save(self, path: Optional[str] = None) -> None:
        target = path or self.path
        if not target:
            return
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        payload = {
            "entries": [asdict(e) for e in self.entries],
            "recent_scores": self.recent_scores,
            "observation_count": self.observation_count,
        }
        with open(target, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def load(self, path: Optional[str] = None) -> None:
        target = path or self.path
        if not target or not os.path.isfile(target):
            return
        with open(target, encoding="utf-8") as f:
            payload = json.load(f)
        self.entries = [MemoryEntry(**item) for item in payload.get("entries", [])]
        self.recent_scores = [float(x) for x in payload.get("recent_scores", [])]
        self.observation_count = int(payload.get("observation_count", len(self.recent_scores)))
