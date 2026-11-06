import os,sys,runpy
from pathlib import Path
root=Path(__file__).resolve().parent
cfg={}
for line in Path('/data2/chenfuxin/molingo_20260922/private/deepseek_canchen.env').read_text().splitlines():
    line=line.strip().removeprefix('export ')
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1);cfg[k.strip()]=v.strip().strip(chr(34)+chr(39))
os.environ['OPENAI_API_KEY']=cfg['api_key']
os.environ['OPENAI_BASE_URL']=cfg['base_url']
os.environ['OPENAI_API_BASE']=cfg['base_url']
os.environ.setdefault('AGENTD_CHAT_MODEL','deepseek-v4.1-flash')
os.environ['HF_HOME']=str(root/'cache/huggingface')
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('MKL_NUM_THREADS','2')
if len(sys.argv)<2 or sys.argv[1]=='--status':
    print('Chat model:',os.environ['AGENTD_CHAT_MODEL'])
    print('Existing private configuration loaded; key not displayed.')
    print('Embedding configured:',bool(os.environ.get('AGENTD_EMBEDDING_API_KEY')))
    print('Serper configured:',bool(os.environ.get('SERPER_API_KEY')))
    raise SystemExit(0)
script=sys.argv[1]
sys.argv=sys.argv[1:]
sys.path.insert(0,str(Path(script).resolve().parent))
runpy.run_path(script,run_name='__main__')
