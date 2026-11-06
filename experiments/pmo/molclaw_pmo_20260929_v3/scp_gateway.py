"""Preserve SCP tools while charging score-returning calls before execution."""
import copy
import json
from pathlib import Path
import sys
import requests
from oracle_server import OracleService, serve

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'vendor'))
CATALOG=json.loads((ROOT/'scp_tools.json').read_text())['result']['tools']
TOOL_MAP={t['name']:t for t in CATALOG}
SIMILARITY_TOOLS={'calculate_morgan_fingerprint_similarity'}
QED_TOOLS={'calculate_mol_drug_chemistry','pred_mol_admet'}


def charge_molecules(task,name,args):
    if name in SIMILARITY_TOOLS:
        return args.get('candidate_smiles_list', [])
    if task=='qed' and name in QED_TOOLS:
        if args.get('smiles_file'):
            raise ValueError('For budgeted scoring use explicit smiles_list, not a remote file.')
        return args.get('smiles_list', [])
    return []


class SCPGateway:
    def __init__(self,out,task):
        self.out=Path(out);self.task=task;self.oracle=OracleService(out,task)
        self.session=requests.Session();self.ready=False;self.rpc_id=0
        key=Path('/data2/chenfuxin/molclaw_20260924/private/scp.env').read_text().strip().split('=',1)[1]
        self.headers={'SCP-HUB-API-KEY':key,'Accept':'application/json, text/event-stream','Content-Type':'application/json'}

    def remote(self,method,params=None,notification=False):
        self.rpc_id+=1
        body={'jsonrpc':'2.0','method':method,'params':params or {}}
        if not notification:body['id']=self.rpc_id
        res=self.session.post('https://scp.intern-ai.org.cn/api/v1/mcp/2/DrugSDA-Tool',headers=self.headers,json=body,timeout=(20,180))
        res.raise_for_status()
        if res.headers.get('mcp-session-id'):self.headers['Mcp-Session-Id']=res.headers['mcp-session-id']
        if notification or not res.content:return {}
        if 'text/event-stream' in res.headers.get('content-type',''):
            items=[json.loads(line[5:]) for line in res.text.splitlines() if line.startswith('data:')]
            data=next(v for v in items if v.get('id')==body['id'])
        else:data=res.json()
        if 'error' in data:raise RuntimeError(str(data['error'])[:500])
        return data['result']

    def handle(self,request):
        method=request['method'];params=request.get('params',{})
        if method in ('initialize','ping'):return self.oracle.handle(request)
        if method=='tools/list':
            items=copy.deepcopy(CATALOG)
            for t in items:
                if t['name'] in SIMILARITY_TOOLS or (self.task=='qed' and t['name'] in QED_TOOLS):
                    t['description']+=' BENCHMARK: every scored input molecule consumes the shared PMO oracle budget, including repeats. Reduce batch size if insufficient budget remains.'
                # Upstream schema describes original fields; added receipt is an extra text block.
            return {'tools':items}
        if method!='tools/call':raise ValueError('Unsupported method')
        name=params['name'];args=params.get('arguments',{})
        try:
            if name not in TOOL_MAP:raise ValueError('Unknown SCP tool')
            import jsonschema
            jsonschema.validate(args,TOOL_MAP[name]['inputSchema'])
            molecules=charge_molecules(self.task,name,args)
            if not isinstance(molecules,list) or not all(isinstance(s,str) for s in molecules):raise ValueError('Molecule inputs must be strings')
            if not self.ready:
                initialized=self.remote('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'pmo-scp-gateway','version':'2'}})
                self.headers['MCP-Protocol-Version']=initialized['protocolVersion']
                self.remote('notifications/initialized',notification=True);self.ready=True
            receipt=self.oracle.score_external(molecules,'scp_'+name) if molecules else []
            result=self.remote('tools/call',{'name':name,'arguments':args})
            if receipt:
                result.setdefault('content',[]).append({'type':'text','text':json.dumps({'pmo_budget_receipt':receipt,'remaining':1000-len(self.oracle.ledger().rows)})})
            return result
        except Exception as error:
            return {'content':[{'type':'text','text':type(error).__name__+': '+str(error)[:600]}],'isError':True}


if __name__=='__main__':serve(SCPGateway(sys.argv[1],sys.argv[2]))
