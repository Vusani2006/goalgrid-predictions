#!/usr/bin/env python3
"""Walk-forward evaluation of *simulated* historical model selections.

Uses only archived, observed fixtures collected by the updater. It never
contacts API-Football, has no fabricated sample matches and never reports
historical simulations as actual published predictions. Two-goal leads are
excluded until complete chronological goal events are archived.
"""
import collections
import datetime as dt
import json
import pathlib
import statistics
import auto_predict as a

ROOT=pathlib.Path(__file__).resolve().parent
OUTPUT=ROOT/'backtest_data.js'
ARCHIVE=ROOT/'archive_history.json'
CUTOFF=50

def outcome(p, f):
    h,x=a.score(f)
    if h is None or x is None: return None
    market=p['marketType']
    if market=='goals25': return int(h+x>=3)
    if market=='resultFT':
        actual='Home win' if h>x else ('Draw' if h==x else 'Away win')
        return int(p['tip']==actual)
    if market in ('cornersFT','corners1H'):
        l,r=a.fixture_stats_pair(f,market)
        if l is None or r is None: return None
        return int(l+r >= (9 if market=='cornersFT' else 4))
    # A final score cannot establish whether the team ever went 2 ahead.
    # Actual event timelines have not yet been archived by this package.
    return None

def evaluate(fixtures):
    a.all_ids={f.get('league',{}).get('id') for f in fixtures}
    # API response must label leagues, and no statistic is inferred.
    for f in fixtures:
        lid=f.get('league',{}).get('id')
        if lid not in a.LEAGUES and lid is not None:
            a.LEAGUES[lid]=f.get('league',{}).get('name') or f'League {lid}'
    ordered=sorted(fixtures,key=lambda f:f['fixture']['date'])
    tested=collections.defaultdict(list)
    total_settled=0
    end=dt.datetime.fromisoformat(ordered[-1]['fixture']['date']) if ordered else None
    evaluation_from=end-dt.timedelta(days=180) if end else None
    for idx,f in enumerate(ordered):
        if (f.get('fixture') or {}).get('status',{}).get('short') !='FT': continue
        total_settled+=1
        # Assess a rolling 180-day window; all older archived games remain available as training history.
        if evaluation_from and dt.datetime.fromisoformat(f['fixture']['date']) < evaluation_from: continue
        # Critical: only fixtures strictly before this kickoff are model inputs.
        past=ordered[:idx]
        for p in a.build_forecast(f,past):
            actual=outcome(p,f)
            if actual is None: continue
            prob=p.get('confidence',0)/100
            tested[p['marketType']].append((prob,actual))
    summary={}
    for m, rows in sorted(tested.items()):
        n=len(rows)
        summary[m]={'observations':n,
                    'verifiedEnough': n>=CUTOFF,
                    'hitRate':round(sum(y for _,y in rows)/n,4) if n>=CUTOFF else None,
                    'brier':round(sum((p-y)**2 for p,y in rows)/n,4) if n>=CUTOFF else None,
                    'averageModelEstimate':round(statistics.mean(p for p,_ in rows),4) if n>=CUTOFF else None}
    return {'model':'quality-v2-experimental',
            'method':'Walk-forward historical simulation using archived matches; not a record of published tips.',
            'meetsMinimumPerMarket':CUTOFF,'archivedMatches':total_settled,
            'markets':summary,
            'limitations':'Not independently audited; retrospective sample is limited by API coverage and fixture archiving. 2UP excluded until full verified goal-event timelines are archived.'}


def main():
    archive=json.loads(ARCHIVE.read_text()) if ARCHIVE.exists() else {'fixtures':{}}
    rows=list((archive.get('fixtures') or {}).values())
    report=evaluate(rows)
    OUTPUT.write_text('window.GOALGRID_BACKTEST = '+json.dumps(report,ensure_ascii=False)+';\n',encoding='utf8')
    for market, d in report['markets'].items():
        print(f'{market}: {d["observations"]} historical model selections; '+
              (f'hit={d["hitRate"]:.1%}, Brier={d["brier"]}' if d['verifiedEnough'] else 'too few for a credible score'))
    if not report['markets']: print('Insufficient archived data: no historical performance claims published.')

if __name__=='__main__':main()
