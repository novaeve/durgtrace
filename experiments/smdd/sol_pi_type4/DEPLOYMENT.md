# SoL-Pi SMDD Type4 A100

All 340 tasks run on this A100 host using native Pi 0.86.1 and the SoL-Pi source checkout, with all four mechanisms enabled. DeepSeek V4.1 Flash, thinking off, temperature 1. Official SMDD tools, budgets and scoring; Boltz uses 10 samples and seed 42.

The first task must produce a submission and a valid official score before the scheduler expands to four agent workers. GPU generation and scoring acquire the existing MolClaw slot locks, observe its 90-second start spacing, require 36 GiB free VRAM and allow at most one SoL prediction per GPU. API calls run on this host and use the existing private credential only in the host boundary.

User systemd service sol-pi-type4-a100.service survives SSH logout and restarts its scheduler after failure. Workers are adopted by PID plus process start identity after scheduler restart. Partial interrupted generations are retained for inspection rather than replayed automatically.

Progress: scheduler_status.json. Per task: runs/solpi/<id>/record.json, result.json and evaluation/result.json. Checks: source_validation.json and preflight/result.json. No existing experiment service was restarted or reconfigured.

Transport repair 2026-10-05: native HTTP tools wait up to eight hours instead of Undici default five minutes, with abort support and request-ID deduplication. Successful submission preserves an immutable molecular file and ends native Pi immediately. Four affected sessions were checkpointed; original accepted submission goes directly to scoring, three others resume their saved native sessions with cumulative API/tool budgets retained. Existing completed records and MolClaw source/service were verified unchanged. Regression tests include an actual 310-second response and native submission termination.

2026-10-07 concurrency update: 8 agent workers, 2 shared Boltz slots per A100 (4 total); 90-second admission, 36,000 MiB memory guard and 50 GiB disk reserve preserved. Existing workers adopted without changing terminal results or budgets.
