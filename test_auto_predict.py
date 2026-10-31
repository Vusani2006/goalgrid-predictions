import unittest
import auto_predict as a
import quality_model as q
import datetime as dt

class ForecastTests(unittest.TestCase):
    def test_pois_over(self):
        self.assertAlmostEqual(a.over(3,3), 1-8.5*a.math.exp(-3),places=9)
    def test_x2_probabilities_sum(self):
        self.assertAlmostEqual(sum(a.match_probs(1.7,0.95).values()),1,places=6)
    def test_two_up_invariants(self):
        self.assertAlmostEqual(a.two_up_probs(0,0)['H'],0)
        self.assertAlmostEqual(a.two_up_probs(2.5,0)['H'],a.over(2,2.5),places=8)
        self.assertLess(a.two_up_probs(0.4,2.1)['H'],a.two_up_probs(0.4,2.1)['A'])
    def test_no_first_half_from_fulltime(self):
        side={'statistics':[{'type':'Corner Kicks','value':7}]}
        self.assertEqual(a.parse_stats_side(side,'Corner Kicks'),7)
        self.assertIsNone(a.parse_stats_side(side,'Corner Kicks','first'))
    def test_first_half_tagged(self):
        side={'statistics':[{'type':'Corner Kicks','value':{'full':8,'first_half':3}}]}
        self.assertEqual(a.parse_stats_side(side,'Corner Kicks','first'),3)
    def test_forecast_no_corners_when_missing(self):
        a.all_ids={39}
        kickoff='2026-11-01T17:00:00+02:00'
        new={'fixture':{'id':6000,'date':kickoff,'status':{'short':'NS'}},
             'league':{'id':39},'teams':{'home':{'id':1,'name':'Alpha FC'},'away':{'id':2,'name':'Beta FC'}},
             'goals':{'home':None,'away':None}}
        historic=[]
        for i in range(12):
            historic.append({'fixture':{'id':i+1,'date':f'2026-09-{i+1:02d}T10:00:00+02:00','status':{'short':'FT'}},
                'league':{'id':39},'teams':{'home':{'id':1,'name':'Alpha FC'},'away':{'id':3,'name':'Other'}},
                'goals':{'home':3,'away':1}})
            historic.append({'fixture':{'id':i+50,'date':f'2026-09-{i+1:02d}T10:00:00+02:00','status':{'short':'FT'}},
                'league':{'id':39},'teams':{'home':{'id':4,'name':'Other'},'away':{'id':2,'name':'Beta FC'}},
                'goals':{'home':1,'away':2}})
        picks=a.build_forecast(new,historic)
        markets={p['marketType'] for p in picks}
        self.assertIn('goals25',markets)
        # Selective publisher abstains unless the model passes a stricter threshold.
        self.assertNotIn('corners1H',markets)
        self.assertNotIn('cornersFT',markets)
    def test_recency_order_ignores_input_order(self):
        cutoff=dt.datetime(2026,11,1,tzinfo=dt.timezone.utc)
        rows=[]
        for i in range(9):
            date=cutoff-dt.timedelta(days=i+1)
            rows.append((date,10 if i==0 else 0,0))
        fresh=q.weighted_rates(rows,cutoff,6)
        reversed_data=q.weighted_rates(list(reversed(rows)),cutoff,6)
        self.assertAlmostEqual(fresh['for'],reversed_data['for'])
        self.assertGreater(fresh['for'],1.1)

    def test_missing_data_abstains(self):
        cutoff=dt.datetime(2026,11,1,tzinfo=dt.timezone.utc)
        rows=[(cutoff-dt.timedelta(days=i+1),2,2) for i in range(5)]
        self.assertIsNone(q.weighted_rates(rows,cutoff,6))
        self.assertIsNone(q.league_baseline([{'goals':{'home':1,'away':0}}]*19))

    def test_shrinkage_reduces_extreme_rates(self):
        prior={'home':1.45,'away':1.08}
        h={'for':3.5,'against':0.7,'effectiveN':6}
        a={'for':0.8,'against':3.2,'effectiveN':6}
        ph,pa=q.venue_strength_expectation(h,a,prior)
        self.assertLess(ph,3.5)
        self.assertGreater(ph,prior['home'])
        self.assertGreater(pa,0)

    def test_period_specific_corner_pair_is_not_inferred(self):
        f={'fixture':{'id':777},'teams':{'home':{'id':1},'away':{'id':2}}}
        a.CACHE['stats']['777']={'cornersFT':{'1':7,'2':3}}
        self.assertEqual(a.fixture_stats_pair(f,'cornersFT'),(7,3))
        self.assertEqual(a.fixture_stats_pair(f,'corners1H'),(None,None))
        del a.CACHE['stats']['777']

    def test_goal_timeline_reversal(self):
        f={'goals':{'home':2,'away':2},'teams':{'home':{'id':4},'away':{'id':5}}}
        p={'tip':'Home FC to lead by 2 at any point','home':'Home FC'}
        ev=[{'type':'Goal','detail':'Normal Goal','team':{'id':tid},'time':{'elapsed':t}} for tid,t in [(4,12),(4,38),(5,65),(5,86)]]
        self.assertEqual(a.settle_two_up_with_events(p,f,ev),'won')
        p['tip']='Away FC to lead by 2 at any point'
        self.assertEqual(a.settle_two_up_with_events(p,f,ev),'lost')
        ev.pop()
        self.assertIsNone(a.settle_two_up_with_events(p,f,ev))

if __name__=='__main__':unittest.main()
