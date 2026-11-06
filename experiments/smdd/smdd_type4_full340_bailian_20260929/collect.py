import os,pathlib,paramiko
ROOT=pathlib.Path(__file__).resolve().parent
def connect(host):
 c=paramiko.SSHClient();c.load_system_host_keys();c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
 kw=dict(username='chenfuxin',timeout=25,look_for_keys=False,allow_agent=False)
 if host=='cpu':kw.update(hostname='159.138.92.174',password=os.environ['SMDD_AUDIT_PASSWORD'])
 else:kw.update(hostname='123.157.219.189',port=17065,key_filename=r'C:\Users\Administrator\.ssh\id_ed25519')
 c.connect(**kw);return c
if __name__=='__main__':
 for host,base,names in [('cpu','/home/chenfuxin/smdd-migration/smdd-assets/experiments/chatdrug_type4_formal_20260920',['chatdrug_adapter.py','run_smoke.py','harness/agent_harness/run.py','harness/agent_harness/agent_loop.py','harness/agent_harness/tools.py','harness/agent_harness/config.py','harness/agent_harness/prompts.py']),('gpu','/data2/chenfuxin/agentdrug_20260922',['core_fixed.py','core_original.py','reproduction_protocol.md','upstream/CLAUDE.md','upstream/README.md'])]:
  c=connect(host);s=c.open_sftp()
  for name in names:
   dest=ROOT/'sources'/host/name;dest.parent.mkdir(parents=True,exist_ok=True);s.get(base+'/'+name,str(dest));print(host,name)
  s.close();c.close()
