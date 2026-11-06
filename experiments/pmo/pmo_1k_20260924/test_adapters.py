"""Exercise source-derived feedback paths without paid model calls."""
import pathlib,tempfile,types
from pmo_common import ROOT,Ledger,dump
import adapters
from adapters import METHODS

class Stub:
    def __init__(self,outputs):self.outputs=iter(outputs);self.calls=[]
    def complete(self,messages,label,cap=None):
        self.calls.append({'messages':messages,'label':label,'cap':cap});return next(self.outputs)

def run():
    report={}
    for name in ['deepseek','chatdrug','agentdrug']:
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            out=pathlib.Path(tmp)
            values={'CCCOCC':.3,'CCCCCCCC':.7,'CCCCCC':.1,'CCCCCCC':.5}
            ledger=Ledger(out,lambda sm:values[sm],10)
            ledger.score('CCCOCC','initialization');ledger.score('CCCCCCCC','initialization')
            ledger.episode_boundary=2
            relay=Stub(['CCCCCC','CCCCCCC'])
            trace=METHODS[name]('qed','CCCOCC',ledger,relay,'test',out)
            if name=='deepseek':assert len(relay.calls)==1 and len(ledger.rows)==3
            else:
                assert len(relay.calls)==2 and len(ledger.rows)==4
                assert 'CCCCCCCC' in str(relay.calls[1]['messages'])
            if name=='agentdrug':assert all(c['cap']==256 for c in relay.calls)
            report[name]={'passed':True,'calls':len(relay.calls),'new_evaluations':len(ledger.rows)-2}
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        out=pathlib.Path(tmp);ledger=Ledger(out,lambda sm:.5,3)
        ledger.score('CCO','initialization');ledger.episode_boundary=1
        def namespace(call):
            def optimize(*args,**kwargs):
                assert kwargs['variants']==3
                call('fragment modifications')
                return ['CCO','CCN','NCC','CCC','CCCC']
            return {'optimize_mol_tomg':optimize}
        saved=adapters._mol;adapters._mol=types.SimpleNamespace(core_namespace=namespace)
        try:
            relay=Stub(['[]']);METHODS['molingo']('qed','CCO',ledger,relay,'test',out)
        finally:adapters._mol=saved
        assert len(relay.calls)==1 and len(ledger.rows)==3
        assert [r['smiles'] for r in ledger.rows]==['CCO','CCN','CCC']
        report['molingo']={'passed':True,'one_generation_no_selector':True,'raw_order_and_duplicate_cache_and_batch_cap':True}
    dump(ROOT/'prepared/adapter_validation.json',report)
    print(report)

if __name__=='__main__':run()
