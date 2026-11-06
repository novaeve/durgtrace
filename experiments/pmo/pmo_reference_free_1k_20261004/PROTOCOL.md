# PMO-1K continuous editor rerun, 2026-10-04

The preceding pmo_reference_free_20261004 experiment stopped after a single native
editing episode. It is an exploratory single-episode result, not the requested
continuous PMO-1K benchmark. This new run supersedes it for the benchmark.

Run ChatDrug and AgentDrug on all 23 original tasks at seed 0, with the original
first model-generated answer and deepseek-v4.1-flash settings. Repeat native
editing episodes until 1,000 actual counted oracle submissions per method/task.
Native within-episode success can end that episode, but never ends the benchmark.
Carry the highest-scoring valid generated candidate forward as the next parent.
Do not admit free references into the parent pool or evaluation archive.

Keep both original random 10,000-molecule libraries, their row order and hashes.
AgentDrug reuses the 23 complete score tables from the preceding precomputation;
its reference DB is prepared once per worker slice and retained across episodes.
ChatDrug reference feedback is outside the budget and cached independently.
Caching immutable Morgan fingerprints preserves original similarity and sorting.
Native prompts, parser, reference selection and within-episode round limits are
unchanged. AgentDrug keeps its original 256-token output cap.

The initial answer is charged once. Parent and candidate feedback, repeated
oracle requests, invalid submissions that reach the oracle, and unevaluated final
answers keep the prior accounting rules. Episode labels distinguish fresh model
calls; interruption replay never charges the same logical query a second time.

After every ten episodes an unfinished task yields its worker and is requeued.
Yielding, achieving score 1, repeated answers, and failure to improve do not cause
early termination. Four workers serve the 46 jobs. Existing transport retries and
three provider-default truncation policy remain in place. Failed tasks are retried
from checkpoints three additional times and otherwise remain explicitly incomplete.
Errors are not presented as successful 1,000-submission results.

Only a terminal inability to continue can have tail-filled AUC, with explicit
early-stop status and actual query count. In-progress AUC is never tail-filled.
Completed tasks must contain exactly 1,000 ledger rows and need no tail filling.
The new runner stores counts, outputs, reference indices, native traces and API
responses per episode, plus final result and overall summary.

Directory: /data2/chenfuxin/pmo_reference_free_1k_20261004
Session: pmo-ref-free-1k
Log: suite.log
Status: continuous.py status
Results: runs/{method}/{task}/0/result.json
