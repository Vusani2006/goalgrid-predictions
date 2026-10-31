import datetime as dt
import unittest
from free_predict import (LEAGUES, completed_score, kickoff, probabilities,
                          league_reference, weighted_team_rates, forecast, settle_pick, create_feed)

UTC=dt.timezone.utc

def fixture(i, when, ht, at, hs=None, a_s=None, status=None):
    if status is None:
        status='FINISHED' if hs is not None else 'SCHEDULED'
    return {'id':i,'utcDate':when.isoformat().replace('+00:00','Z'),'status':status,
            'homeTeam':{'id':ht,'name':f'Team {ht}'},'awayTeam':{'id':at,'name':f'Team {at}'},
            'score':{'fullTime':{'home':hs,'away':a_s}}}

class TestFreePredict(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,10,31,6,tzinfo=UTC)
        self.matches=[]
        # Dense observed league fixtures with six home and six away team starts
        for j in range(24):
            w=self.now-dt.timedelta(days=35-j)
            self.matches.append(fixture(j+1,w,100+j%8,200+(j+3)%8,2+(j%2),j%2))
        for j in range(8):
            self.matches.append(fixture(1000+j,self.now-dt.timedelta(days=20-j),1,400+j%4,3,0))
            self.matches.append(fixture(2000+j,self.now-dt.timedelta(days=20-j),500+j%4,2,0,2))
        self.target=fixture(9999,self.now+dt.timedelta(days=1),1,2)
        self.matches.append(self.target)

    def test_no_unknown_score(self):
        self.assertIsNone(completed_score(self.target))
        self.assertIsNone(completed_score(fixture(4,self.now,1,2,0,0,'IN_PLAY')))

    def test_probability_limits(self):
        result, over=probabilities(1.5,1.3)
        self.assertAlmostEqual(sum(result.values()),1,places=4)
        self.assertGreater(over,0)
        self.assertLess(over,1)

    def test_reference_observed(self):
        self.assertEqual(league_reference(self.matches,self.now)['n'],40)
        self.assertIsNone(league_reference(self.matches[:5],self.now))

    def test_home_away_samples(self):
        self.assertIsNotNone(weighted_team_rates(self.matches,1,True,self.now))
        self.assertIsNotNone(weighted_team_rates(self.matches,2,False,self.now))
        self.assertIsNone(weighted_team_rates(self.matches,123456,False,self.now))

    def test_unsupported_market_absent(self):
        picks=forecast(self.target,LEAGUES['PL'],self.matches,self.now)
        self.assertTrue(all(p['marketType'] in ('goals25','resultFT') for p in picks))
        self.assertTrue(all(p['research']['sampleHome']>=3 for p in picks))
        self.assertTrue(all(p['status']=='pending' for p in picks))

    def test_no_future_score_leak(self):
        later=fixture(555,self.now+dt.timedelta(days=3),1,400,20,0)
        old=forecast(self.target,LEAGUES['PL'],self.matches,self.now)
        new=forecast(self.target,LEAGUES['PL'],self.matches+[later],self.now)
        self.assertEqual(old,new)

    def test_settle_goal(self):
        p={'marketType':'goals25','tip':'Over 2.5 goals','status':'pending'}
        self.assertTrue(settle_pick(p,fixture(9999,self.now,1,2,2,1)))
        self.assertEqual(p['status'],'won')
        self.assertEqual(p['finalScore'],'2–1')

    def test_result_settle(self):
        p={'marketType':'resultFT','tip':'Away win','status':'pending'}
        self.assertTrue(settle_pick(p,fixture(9999,self.now,1,2,2,1)))
        self.assertEqual(p['status'],'lost')

    def test_no_fabricated_psl(self):
        self.assertNotIn('PSL',LEAGUES)
        self.assertNotIn('cornersFT',[p['marketType'] for p in forecast(self.target,'Premier League',self.matches,self.now)])

    def test_history_keeps_published_time(self):
        existing={'FDORG-9999-goals25':{'id':'FDORG-9999-goals25','fixtureId':9999,'kickoff':self.target['utcDate'],
                'status':'pending','marketType':'goals25','tip':'Over 2.5 goals'}}
        result, picks=create_feed({'PL':self.matches},self.now,existing)
        self.assertIn('FDORG-9999-goals25',result)

if __name__=='__main__':unittest.main()
