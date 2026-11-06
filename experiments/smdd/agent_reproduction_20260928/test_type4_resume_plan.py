from pathlib import Path
import json
import tempfile
import unittest
from type4_resume_plan import build_plan

class ResumeTest(unittest.TestCase):
    def test_preserves_scientific_failure_and_retries_only_infrastructure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def put(task,name,obj):
                p=root/task/name;p.parent.mkdir(parents=True,exist_ok=True)
                p.write_text(json.dumps(obj))
            put('a','agent_result.json',{'status':'submitted'})
            put('a','evaluation/result.json',{'status':'failed'})
            (root/'a/solution.smi').write_text('CC\n')
            put('b','agent_result.json',{'status':'submitted'})
            put('b','evaluation/result.json',{'status':'errored'})
            (root/'b/solution.smi').write_text('CCC\n')
            put('c','agent_result.json',{'status':'runtime_error'})
            (root/'d').mkdir();(root/'d/agent_result.json').write_text('')
            (root/'batch_status.json').write_text(json.dumps({'finished':{'a':{'evaluation_status':'failed'}}}))
            result=build_plan(['a','b','c','d','e'],root)
            self.assertEqual(list(result['inherited']),['a'])
            self.assertEqual(list(result['evaluation_only']),['b'])
            self.assertEqual(result['retry_infrastructure'],['c','d'])
            self.assertEqual(result['not_started'],['e'])

if __name__=='__main__':unittest.main()
