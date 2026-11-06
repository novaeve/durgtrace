# MolClaw PMO-1K v3

User-authorized stall exception: after 30 minutes without a new complete scored submission, stop that target and continue the queue. Save the original ledger unchanged, the valid contiguous prefix, and its observed Top-10 AUC normalized by actual count; also save observed area divided by 1000. No unobserved tail is filled. Such runs are labeled `skipped_stalled`, never full 1000-submission completions. JNK3 and median2 are explicitly skipped at the user's request.

All 23 objectives restart in this independent directory. Completion requires exactly 1000 recorded candidate submissions and scoring responses. Initial candidate counts as submission 1, as in the existing shared submission protocol. Invalid submissions return zero; duplicate submissions consume a slot and return the cached official score. Deliberate repetition to fill the budget is forbidden in the prompt.

Early native final answers trigger continuation of the same session and ledger. The runner never manufactures submissions or fills an unobserved trajectory. Every objective writes the complete 1000-point unique-valid Top-10 mean trajectory; normalized AUC is trapezoidal with the score at submission zero defined as zero. Fewer than ten valid unique molecules use the available set. Invalid and repeated candidates consume actual positions without entering Top-10 again.

Official scoring, SCP charging and code guards are retained from v2. Guards enforce the scientific protocol but are not an adversarial security sandbox; traces remain available for review. Model deepseek-v4.1-flash, original MolClaw skills, seed 0 and concurrency 2 remain in use. v1/v2 results are excluded. Native failures or the 2048-segment recovery limit produce needs_attention, never completed status.

Run `bash launch.sh`; inspect `control/*/0/oracle_queries.jsonl`, `top10_trajectory.json`, and `result.json`. Independent result verification: `python acceptance.py OBJECTIVE`.
