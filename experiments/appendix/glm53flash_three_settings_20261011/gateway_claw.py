import os,runpy
from pathlib import Path
os.environ['GLM_GATEWAY_PORT']='18855'
runpy.run_path(str(Path(__file__).resolve().parent/'gateway.py'),run_name='__main__')
