import json
from pathlib import Path
import tempfile
import unittest
from stall_watchdog import progress, read_prefix, partial_result
import runner

class WatchdogTests(unittest.TestCase):
    def test_only_complete_new_rows_reset_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Path(temp);p=c/'oracle_queries.jsonl'
            row={'index':1,'score':0.5,'canonical':'C','status':'new'}
            p.write_text(json.dumps(row)+'\n')
            self.assertFalse(progress(c,now=0))
            p.write_text(p.read_text()+'{"index":2')
            self.assertFalse(progress(c,now=1799))
            self.assertTrue(progress(c,now=1800))
            p.write_text(json.dumps(row)+'\n'+json.dumps(dict(row,index=2,status='duplicate'))+'\n')
            self.assertFalse(progress(c,now=1801))
            self.assertFalse(progress(c,now=3600))
            self.assertTrue(progress(c,now=3601))

    def test_partial_preserves_damage_and_labels_partial_auc(self):
        with tempfile.TemporaryDirectory() as temp:
            c=Path(temp);p=c/'oracle_queries.jsonl'
            p.write_text(json.dumps({'index':1,'score':0.5,'canonical':'C','status':'new'})+'\n{"index":2')
            original=p.read_bytes();(c/'state.json').write_text('{}')
            result=partial_result(c,'qed')
            self.assertEqual(p.read_bytes(),original)
            self.assertEqual(result['oracle_submissions'],1)
            self.assertEqual(result['auc_top10_observed'],0.25)
            self.assertFalse(result['complete'])
            self.assertEqual(result['status'],'skipped_stalled')

if __name__=='__main__':unittest.main()
