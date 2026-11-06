import json
from collect import ROOT,connect
from deploy import CPU
c=connect('cpu');s=c.open_sftp()
try:
 s.put(str(ROOT/'README.md'),CPU+'/README.md')
 for name in ['protocol_manifest.json','tasks340.txt']:
  s.get(CPU+'/'+name,str(ROOT/name))
 for method in ['chatdrug','agentdrug']:
  (ROOT/'status'/method).mkdir(parents=True,exist_ok=True)
  for name in ['summary.json','current.json','supervisor.pid']:
   try:s.get(CPU+'/'+method+'/'+name,str(ROOT/'status'/method/name))
   except FileNotFoundError:pass
 print('Protocol and progress synchronized; API credentials were not transferred.')
finally:s.close();c.close()
