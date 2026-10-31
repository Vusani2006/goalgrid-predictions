import datetime as dt
import unittest
import squad_intel as si
import auto_predict as a

T = dt.datetime.fromisoformat('2026-11-01T18:00:00+02:00')

def match(fid, when, gf=2, ga=1):
    return {'fixture': {'id': fid,'date':when.isoformat(), 'status':{'short':'FT'}},
            'teams':{'home':{'id':1}, 'away':{'id':2}},'goals':{'home':gf,'away':ga}}


def lineup(starters, tid=1):
    return [{'team':{'id':tid},'formation':'4-3-3',
             'startXI':[{'player':{'id':i,'name':f'Player {i}'}} for i in starters],
             'substitutes': []}]

class SquadTests(unittest.TestCase):
    def test_possession_as_percentage(self):
        rows=[{'team':{'id':1},'statistics':[{'type':'Ball Possession','value':'58%'},
                  {'type':'Total Shots','value':15}, {'type':'Shots on Goal','value':4}]}]
        stats=si.extra_match_stats(rows)
        self.assertEqual(stats['possession']['1'], 58)
        self.assertEqual(stats['shots']['1'], 15)
        self.assertEqual(stats['shotsOnTarget']['1'], 4)

    def test_no_imagined_stats(self):
        self.assertEqual(si.extra_match_stats([{'team':{'id':1},'statistics':[]}])['shots'],{})
        self.assertIsNone(si.number('58x'))
        self.assertIsNone(si.number('150%', percent=True))

    def test_lineup_requires_actual_starting_eleven(self):
        self.assertIsNone(si.lineup_for_team([{'team':{'id':1},'formation':'4-3-3'}],1))
        self.assertEqual(si.lineup_for_team(lineup([4,5]),1)['formation'], '4-3-3')

    def test_injuries_respect_missing_vs_questionable(self):
        rows=[{'team':{'id':1},'player':{'id':10,'name':'A'}, 'type':'Missing Fixture'},
              {'team':{'id':1},'player':{'id':11,'name':'B'}, 'type':'Questionable'}]
        out=si.injuries_by_team(rows,1,2)
        self.assertEqual([i['status'] for i in out['1']], ['missing','questionable'])
        self.assertEqual(out['2'],[])

    def test_with_without_only_on_verified_starts(self):
        fixtures = [match(i, T-dt.timedelta(days=i+1),gf=3 if i<3 else 1) for i in range(6)]
        cache={str(i):lineup([10] if i<3 else [20]) for i in range(6)}
        observed=si.observed_lineups(fixtures,1,cache,T)
        out=si.with_without(observed,'10',1)
        self.assertEqual(out['started']['matches'],3)
        self.assertEqual(out['started']['scored'],3)
        self.assertEqual(out['didNotStart']['matches'],3)
        self.assertEqual(out['didNotStart']['scored'],1)
        self.assertIsNone(si.with_without(observed[:4],'10',1))

    def test_style_needs_four_real_observations(self):
        fixtures = [match(i,T-dt.timedelta(days=i+1)) for i in range(6)]
        stats={str(i): {'shots': {'1': 14}, 'possession':{'1':56},'cornersFT':{'1':5}} for i in range(6)}
        result=si.playing_style(fixtures,1,stats,T)
        self.assertIn('possession-oriented',result['description'])
        self.assertIn('high shot volume',result['description'])
        self.assertEqual(result['stats']['shots']['n'],6)
        self.assertNotIn('pressing',result['description'])
        self.assertEqual(si.playing_style(fixtures,1,{},T)['stats'],{})

    def test_scout_says_unavailable_not_healthy(self):
        f=match(100,T)
        report=si.scout_fixture(f,[],{}, {}, injury_records=None,confirmed_lineups=None)
        self.assertEqual(report['injuryData'],'unavailable')
        self.assertIn('unverified', a.squad_news(report))
        self.assertFalse(report['teams']['home']['lineupVerified'])

    def test_core_player_missing_reduces_trust(self):
        f=match(100,T)
        fixtures=[match(i,T-dt.timedelta(days=i+1)) for i in range(8)]
        cache={str(i):lineup([10,20]) for i in range(8)}
        injuries={'1':[{'id':'10','name':'Player 10','status':'missing'}], '2':[]}
        report=si.scout_fixture(f,fixtures,{},cache,injury_records=injuries)
        self.assertEqual(report['teams']['home']['keyUnavailable'],['Player 10'])
        self.assertEqual(report['cautionTeams'], ['home'])
        injuries['1'].append({'id':'20','name':'Player 20','status':'missing'})
        report=si.scout_fixture(f,fixtures,{},cache,injury_records=injuries)
        self.assertTrue(report['risk'])

if __name__ == '__main__': unittest.main()
