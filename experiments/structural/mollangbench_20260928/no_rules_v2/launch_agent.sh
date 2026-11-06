#!/bin/bash
set -euo pipefail
cd /data2/chenfuxin/mollangbench_20260928/no_rules_v2
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONUNBUFFERED=1
METHOD="$1"
PY=/data2/chenfuxin/pmo_1k_20260924/venv/bin/python
"$PY" run_agents.py pilot "$METHOD"
"$PY" run_agents.py full "$METHOD"
"$PY" score.py full --method "$METHOD"
echo "$METHOD FULL_FINISHED"
