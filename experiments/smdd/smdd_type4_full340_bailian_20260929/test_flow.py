"""Checks protocol edge cases without spending API/oracle budget."""
import pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'harness'))
import agentdrug_smdd as a
from agent_harness.config import AgentConfig
real_e,real_request=a.AgentDrugExecutor,a.request
class Fake:
 instances=[];success_at=None
 def __init__(self,*args):
  self.reference_smiles='CC';self.events=[];self.admet_calls=15;self.boltz_calls=8;self.assess_count=0;Fake.instances.append(self)
 def event(self,name,data):self.events.append((name,data))
 def assess(self,s):
  self.assess_count+=1
  return self.assess_count==self.success_at,'Validity: numerical feedback; budget exhausted'
 def retrieve(self,s):return None
 def finalize_stopped(self):pass
calls=[]
def response(messages,**kw):
 assert kw=={'temperature':0,'max_tokens':256};calls.append(messages[0]['content'])
 return {'choices':[{'message':{'content':'CCC'},'finish_reason':'length'}],'usage':{'prompt_tokens':10,'completion_tokens':256}}
try:
 a.AgentDrugExecutor=Fake;a.request=response
 result=a.run_agent({'description':'public task'},'',AgentConfig(),'','')
 assert result.turns_used==5 and len(calls)==5 and result.status=='submitted'
 assert all('numerical feedback' in x for x in calls[1:])
 assert Fake.instances[-1].terminal_candidate=='CCC'
 calls.clear();Fake.success_at=1
 result=a.run_agent({'description':'public task'},'',AgentConfig(),'','')
 assert result.turns_used==1 and len(calls)==1
 print('PASS: exhausted budgets/no reference still allow five generations, truncated output retained, verified success stops early.')
finally:a.AgentDrugExecutor=real_e;a.request=real_request
