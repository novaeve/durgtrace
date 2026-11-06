"""Submission-index budget and MT-Mol AUC; no initialization/search policy.

Call submit once per submitted molecule, not per cache lookup or feedback read.
Stable event IDs make recovery idempotent without erasing real repeated answers.
"""
import json
import math
import os
from pathlib import Path


class SubmissionBudgetExhausted(Exception):
    pass


def mt_mol_auc(buffer, budget=1000, top_n=10, finish=False):
    """MT-Mol top_auc with freq_log=1 and first submission indices.

    Matches source/mt_mol-main/utils/auc.py. Empty valid sets return zero
    instead of upstream's IndexError. Unfinished runs are not tail-filled.
    """
    ordered = sorted(buffer.values(), key=lambda row: row[1])
    if not ordered:
        return 0.0
    last = ordered[-1][1]
    if last > budget:
        raise ValueError('Submission index exceeds budget')

    def top_mean(values):
        scores = sorted((r[0] for r in values), reverse=True)[:top_n]
        return sum(scores) / len(scores)

    area, previous, called = 0.0, 0.0, 0
    for index in range(1, min(last, budget)):
        available = [r for r in ordered if r[1] <= index]
        if not available:
            continue
        current = top_mean(available)
        area += (current + previous) / 2
        previous, called = current, index
    current = top_mean(ordered)
    area += (last - called) * (current + previous) / 2
    if finish and last < budget:
        area += (budget - last) * current
    return area / budget


class SubmissionLedger:
    def __init__(self, path, canonicalize, evaluator, budget=1000):
        self.path = Path(path)
        self.canonicalize = canonicalize
        self.evaluator = evaluator
        self.budget = budget
        self.rows, self.events, self.buffer = [], {}, {}
        if self.path.exists():
            for line in self.path.read_text(encoding='utf-8').splitlines():
                self._restore(json.loads(line))

    def _restore(self, row):
        if row['index'] != len(self.rows) + 1 or row['event_id'] in self.events:
            raise ValueError('Corrupt submission sequence')
        if row['index'] > self.budget:
            raise ValueError('Existing submissions exceed configured budget')
        if row['status'] == 'new':
            if row['canonical'] in self.buffer:
                raise ValueError('Duplicate labeled as new')
            self.buffer[row['canonical']] = [row['score'], row['index']]
        elif row['status'] == 'duplicate':
            if self.buffer.get(row['canonical'], [None])[0] != row['score']:
                raise ValueError('Duplicate has inconsistent cached score')
        elif row['status'] != 'invalid':
            raise ValueError('Unknown submission status')
        self.rows.append(row)
        self.events[row['event_id']] = row

    @property
    def exhausted(self):
        return len(self.rows) >= self.budget

    def submit(self, smiles, event_id):
        if not isinstance(event_id, str) or not event_id:
            raise ValueError('A stable nonempty event ID is required')
        if event_id in self.events:
            row = self.events[event_id]
            if row['raw'] != smiles:
                raise ValueError('Recovery event changed its submitted answer')
            return row
        if self.exhausted:
            raise SubmissionBudgetExhausted()
        canonical = self.canonicalize(smiles)
        if canonical is None:
            status, score = 'invalid', 0.0
        elif canonical in self.buffer:
            status, score = 'duplicate', self.buffer[canonical][0]
        else:
            status, score = 'new', float(self.evaluator(canonical))
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Nonfinite or out-of-range oracle score')
        row = {'index': len(self.rows) + 1, 'event_id': event_id,
               'raw': smiles, 'canonical': canonical, 'status': status,
               'score': score}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        self._restore(row)
        return row

    def metrics(self):
        return {
            'submissions': len(self.rows), 'submission_budget': self.budget,
            'unique_valid': len(self.buffer),
            'duplicates': sum(r['status'] == 'duplicate' for r in self.rows),
            'invalid': sum(r['status'] == 'invalid' for r in self.rows),
            'complete': self.exhausted,
            'auc_top10_mt_mol': mt_mol_auc(self.buffer, self.budget,
                                          finish=self.exhausted),
            'auc_index': 'first_submission_index', 'auc_frequency': 1,
        }
