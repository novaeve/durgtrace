import unittest
from trajectory import complete_auc

class TrajectoryTests(unittest.TestCase):
    def test_requires_all_actual_submissions(self):
        for count in (0,99,999,1001):
            with self.assertRaises(ValueError):complete_auc([{}]*count)

    def test_full_curve_includes_repeats_and_invalid_positions(self):
        rows=[{'index':i,'canonical':'C','status':'new' if i==1 else 'duplicate','score':0.5} for i in range(1,1001)]
        rows[499]={'index':500,'canonical':'CC','status':'new','score':1.0}
        rows[500]={'index':501,'canonical':None,'status':'invalid','score':0.0}
        auc,curve=complete_auc(rows)
        self.assertEqual(len(curve),1000)
        self.assertAlmostEqual(auc,(0.25+498*0.5+0.625+500*0.75)/1000)
        self.assertEqual(curve[500]['top10_mean'],0.75)

if __name__=='__main__':unittest.main(verbosity=2)
