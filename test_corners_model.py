import datetime as dt
import unittest
import corners_model as cm
from free_predict import create_feed, settle_pick

class TestCorners(unittest.TestCase):
    def test_no_data_no_picks(self):
        now=dt.datetime(2026,11,3,tzinfo=dt.timezone.utc)
        match={'id':123,'utcDate':'2026-11-04T12:00:00Z','status':'SCHEDULED','homeTeam':{'id':1,'name':'Home'},'awayTeam':{'id':2,'name':'Away'},'_corner_league_ids':{'123'}}
        from free_predict import kickoff,team_id,team_name
        self.assertEqual(cm.forecast_corners(match,'Premier League',{},now,kickoff,team_id,team_name),[])
    def test_corner_settlement_requires_record(self):
        match={'status':'FINISHED','score':{'fullTime':{'home':2,'away':0}}}
        pick={'marketType':'cornersFT','threshold':9.5,'status':'pending'}
        self.assertFalse(settle_pick(pick,match))
        self.assertTrue(settle_pick(pick,match,{'ft_total':10}))
        self.assertEqual(pick['status'],'won')
    def test_first_half_not_inferred_from_full_time(self):
        match={'status':'FINISHED','score':{'fullTime':{'home':1,'away':1}}}
        pick={'marketType':'corners1H','threshold':3.5,'status':'pending'}
        self.assertFalse(settle_pick(pick,match,{'ft_total':12}))
