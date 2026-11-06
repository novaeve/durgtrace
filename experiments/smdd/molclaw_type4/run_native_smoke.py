import remote
c=remote.connect()
remote.run(c,"cd /yimin/zlc/molclaw_type4_20261003 && LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONNOUSERSITE=1 timeout 300 ./proxy_env/bin/python run.py --task smdd_004_ACE_0 --smoke",timeout=330)
c.close()
