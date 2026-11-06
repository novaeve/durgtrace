"""Offline boundaries that would materially change the submitted metrics."""
from pathlib import Path
import importlib.util,json,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from score_saved import Scorer,score_records,module

class FrozenProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.s=Scorer()

    def test_frozen_denominators(self):
        for task,n in [('cd28',5600),('cd28_logp',800),('cd28_qed',800),('s2_molopt',1500),('s2_edit',1500),('s2_custom',1500),('mollang_edit',400),('mollang_generation',400)]:
            with self.subTest(task=task):self.assertEqual(len(self.s.cases(task)),n)

    def test_identity_fails_strict_property_direction(self):
        for task in ['cd28','s2_molopt']:
            for case in self.s.cases(task)[::199]:
                with self.subTest(task=task,id=case['id']):self.assertFalse(self.s.score(task,case,case['smiles'])['success'])

    def test_bond_zero_constraints_follow_frozen_exception(self):
        cases=[c for c in self.s.cases('s2_custom') if c['subtask']=='BondNum'];case=cases[0]
        targets=self.s.s2.constraints(case)
        for key in self.s.s2.BONDS:
            if int(case['row'][key])==0:self.assertNotIn('rot_bonds' if key=='rotatable' else 'num_'+key+'_bonds',targets)

    def test_mollang_accepts_equivalent_string_order(self):
        case=self.s.cases('mollang_edit')[0];answer=self.s.answers[case['id']]
        mol=self.s.Chem.MolFromSmiles(answer);other=self.s.Chem.MolToSmiles(mol,canonical=False)
        self.assertTrue(self.s.score('mollang_edit',case,other)['success'])
        self.assertFalse(self.s.score('mollang_edit',case,None)['success'])

    def test_missing_and_failed_submissions_stay_in_denominator(self):
        case=self.s.cases('mollang_edit')[0]
        result=score_records('mollang_edit',[{'id':case['id'],'candidate':self.s.answers[case['id']],'status':'error'}])
        self.assertEqual(result['expected'],400);self.assertEqual(result['successes'],0);self.assertEqual(len(result['rows']),400)

    def test_no_duplicate_or_unknown_final_submissions(self):
        case=self.s.cases('mollang_edit')[0];row={'id':case['id'],'candidate':None}
        with self.assertRaises(ValueError):score_records('mollang_edit',[row,row])
        with self.assertRaises(ValueError):score_records('mollang_edit',[{'id':'not-a-task','candidate':'C'}])

    def test_smdd_type2_strict_distance_and_one_to_one(self):
        m=module('frozen_pharmacophore',ROOT/'benchmarks/smdd/metrics/pharmacophore_3d.py')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);gold=p/'truth.json';pred=p/'solution.csv'
            self.assertTrue(m.are_types_compatible('Aromatic',['Hydrophobic']))
            self.assertFalse(m.are_types_compatible('Donor',['Acceptor']))
            pred.write_text('0,0,0,Donor\n2.5,0,0,Acceptor\n0,0,0,Donor\n5,0,0,Acceptor\n',encoding='utf-8')
            # Supply ground truth through the loader seam; evaluate the original matching code.
            import numpy as np
            m.load_ground_truth=lambda _: [{'coords':np.array([0.,0.,0.]),'types':['Donor']},{'coords':np.array([5.,0.,0.]),'types':['Acceptor']}]
            result=m.evaluate_3d_pharmacophore(str(pred),str(gold))
            self.assertEqual(result['n_correct'],1);self.assertEqual(result['n_required'],3);self.assertEqual(len(m.parse_agent_csv(str(pred))),3)

if __name__=='__main__':unittest.main()
