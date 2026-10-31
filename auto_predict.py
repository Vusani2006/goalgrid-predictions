#!/usr/bin/env python3
"""Apes Nation Football Prediction daily publisher. Python 3.11+, stdlib only. API key stays server-side.
This is an experimental Poisson forecasting model, NOT backtested/calibrated.
Never fill in missing corner observations with zero, and never fabricate fixtures.
"""
import datetime as dt
import json
import math
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from zoneinfo import ZoneInfo
import quality_model as qm
import squad_intel as si

ROOT = pathlib.Path(__file__).resolve().parent
CACHEFILE = ROOT / 'cache' / 'match_stats.json'
SCOUT_FILE = ROOT / 'cache' / 'squad_intel.json'
OUTPUT = ROOT / 'data.js'
TZ = ZoneInfo('Africa/Johannesburg')
NOW = dt.datetime.now(TZ)
TODAY = NOW.date()
BASE = 'https://v3.football.api-sports.io'
API_KEY = os.getenv('API_SPORTS_KEY')
MAX_CALLS = int(os.getenv('MAX_API_CALLS', '85'))
SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
VIP_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
MIN_SAMPLE = 6
LEAGUES = {39: 'Premier League', 140: 'La Liga', 135: 'Serie A',
           78: 'Bundesliga', 61: 'Ligue 1', 94: 'Primeira Liga'}
# South Africa's league ID is resolved from the provider rather than guessed.
CACHE = json.loads(CACHEFILE.read_text()) if CACHEFILE.exists() else {'stats': {}, 'psl_id': None}
CACHE.setdefault('stats', {})
SCOUT_CACHE = json.loads(SCOUT_FILE.read_text()) if SCOUT_FILE.exists() else {}
SCOUT_CACHE.setdefault('lineups', {})
SCOUT_CACHE.setdefault('injuries', {})
SCOUT_CACHE.setdefault('squads', {})
PREVIOUS = json.loads((ROOT / 'history.json').read_text()) if (ROOT / 'history.json').exists() else {}
PREVIOUS.setdefault('picks', {})
ARCHIVEFILE = ROOT / 'archive_history.json'
ARCHIVE = json.loads(ARCHIVEFILE.read_text()) if ARCHIVEFILE.exists() else {'fixtures': {}}
ARCHIVE.setdefault('fixtures', {})

class QuotaReached(Exception): pass

class Client:
    calls = 0
    def get(self, path, params):
        if self.calls >= MAX_CALLS:
            raise QuotaReached(f'Run stopped at {MAX_CALLS} requests; results use available evidence only')
        # Free API plan permits about ten calls per minute; avoid bursting requests.
        if self.calls: time.sleep(6.1)
        url = BASE + path + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'x-apisports-key': API_KEY, 'Accept': 'application/json', 'User-Agent': 'ApesNationFootballPrediction/1.1'})
        try:
            with urllib.request.urlopen(req, timeout=25) as res:
                payload = json.load(res)
        except urllib.error.HTTPError as err:
            raise RuntimeError(f'API response HTTP {err.code} at {path}') from err
        self.calls += 1
        if payload.get('errors'):
            raise RuntimeError(f'API error at {path}: {payload["errors"]}')
        return payload.get('response') or []

api = Client()

def private_query(method, path, payload=None):
    """Server-only Supabase REST access; never put service role credential in the site."""
    if not VIP_ENABLED:
        raise RuntimeError('Private VIP backend not configured')
    url = SUPABASE_URL + '/rest/v1/' + path
    headers = {'apikey': SUPABASE_SERVICE_ROLE_KEY,
               'Authorization': 'Bearer ' + SUPABASE_SERVICE_ROLE_KEY,
               'Accept': 'application/json'}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
        headers['Prefer'] = 'resolution=merge-duplicates,return=minimal'
    req = urllib.request.Request(url, headers=headers, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read()
    except urllib.error.HTTPError as e:
        # Avoid printing secrets, payloads or URLs.
        raise RuntimeError(f'Private member database returned HTTP {e.code}') from None
    return json.loads(data) if data else []

def load_private_history():
    if not VIP_ENABLED: return {}
    start = (TODAY - dt.timedelta(days=45)).isoformat()
    params = urllib.parse.urlencode({'select': '*', 'kickoff': f'gte.{start}T00:00:00+02:00',
                                     'order': 'kickoff.desc', 'limit': '800'})
    records = private_query('GET','vip_predictions?' + params)
    saved = {}
    for r in records:
        saved[r['id']] = {'id':r['id'], 'fixtureId':r['fixture_id'],
                         'home':r['home'], 'away':r['away'], 'league':r['league'],
                         'kickoff':r['kickoff'], 'marketType':r['market_type'],
                         'market':r['market'], 'tip':r['tip'], 'confidence':r['confidence'],
                         'projectedTotal':r['projected_total'], 'reason':r['reason'],
                         'status':r['status'], 'research':r.get('research') or {},
                         'finalScore':r.get('final_score'), 'selectedSide':(r.get('research') or {}).get('selectedSide')}
    return saved

def publish_private(picks):
    if not VIP_ENABLED: return
    records = []
    for p in picks:
        records.append({'id':p['id'],'fixture_id':p['fixtureId'], 'home':p['home'],
                        'away':p['away'],'league':p['league'],'kickoff':p['kickoff'],
                        'market_type':p['marketType'],'market':p['market'],
                        'tip':p['tip'],'confidence':p['confidence'],
                        'projected_total':p.get('projectedTotal'), 'reason':p.get('reason'),
                        'status':p['status'],'research':p.get('research') or {},
                        'final_score':p.get('finalScore')})
    # Chunk large data: no VIP data is ever serialized into a public file.
    for i in range(0,len(records),100):
        private_query('POST','vip_predictions?on_conflict=id',records[i:i+100])


def as_int(v):
    if v is None or isinstance(v, bool): return None
    try:
        x = int(v)
        return x if x >= 0 else None
    except (TypeError, ValueError): return None

def score(fixture):
    gs = fixture.get('goals') or {}
    return as_int(gs.get('home')), as_int(gs.get('away'))

def season_of(date):
    return date.year if date.month >= 7 else date.year - 1

def get_psl_id():
    if CACHE.get('psl_id'): return int(CACHE['psl_id'])
    candidates = api.get('/leagues', {'country': 'South Africa', 'season': season_of(TODAY)})
    exact = [r for r in candidates if (r.get('league') or {}).get('name', '').casefold() == 'premier soccer league']
    if not exact:
        candidates=api.get('/leagues', {'country': 'South-Africa', 'season': season_of(TODAY)})
        exact=[r for r in candidates if (r.get('league') or {}).get('name', '').casefold() == 'premier soccer league']
    if not exact:
        candidates=api.get('/leagues', {'search': 'Premier Soccer League'})
        exact=[r for r in candidates if (r.get('league') or {}).get('name','').casefold() == 'premier soccer league' and
               'south' in (r.get('country') or {}).get('name','').casefold()]
    if not exact:
        raise RuntimeError('PSL ID not discoverable from coverage: no guessed or substituted league')
    league_id = int(exact[0]['league']['id'])
    CACHE['psl_id'] = league_id
    return league_id

def poisson_pmf(n, mean):
    return math.exp(-mean) * mean ** n / math.factorial(n)

def over(count, mu):
    return max(0., min(1., 1. - sum(poisson_pmf(i, mu) for i in range(count))))

def match_probs(mu_h, mu_a, max_goals=18):
    ph = [poisson_pmf(n, mu_h) for n in range(max_goals + 1)]
    pa = [poisson_pmf(n, mu_a) for n in range(max_goals + 1)]
    h = sum(ph[i]*pa[j] for i in range(max_goals+1) for j in range(max_goals+1) if i>j)
    d = sum(ph[i]*pa[i] for i in range(max_goals+1))
    a = sum(ph[i]*pa[j] for i in range(max_goals+1) for j in range(max_goals+1) if i<j)
    return {'H':h,'D':d,'A':a}

def two_up_probs(mu_h, mu_a):
    """Exact independent homogeneous Poisson scoring-order model, truncated at 30 total goals.
    Result: P(home ever leads by 2), P(away ever leads by 2); includes losses after an early lead.
    """
    total = mu_h + mu_a
    if total <= 0: return {'H': 0., 'A': 0.}
    chance_home = mu_h/total
    states = {(0,False,False): 1.}
    out = {'H':0., 'A':0.}
    p_n = math.exp(-total)
    for n in range(31):
        for (diff, seen_h, seen_a), weight in states.items():
            if seen_h: out['H'] += p_n*weight
            if seen_a: out['A'] += p_n*weight
        following=defaultdict(float)
        for (diff, seen_h, seen_a), weight in states.items():
            following[(diff+1, seen_h or diff+1 >= 2,seen_a)] += weight*chance_home
            following[(diff-1, seen_h, seen_a or diff-1 <= -2)] += weight*(1-chance_home)
        states=following
        p_n=p_n*total/(n+1)
    return out

def fixture_stats_pair(fixture, stat):
    parts=(CACHE['stats'].get(str(fixture['fixture']['id'])) or {}).get(stat) or {}
    teams=fixture.get('teams') or {}
    h=(teams.get('home') or {}).get('id'); a=(teams.get('away') or {}).get('id')
    return as_int(parts.get(str(h))), as_int(parts.get(str(a)))

def rate(fixtures, team_id, venue, stat=None, target_time=None):
    """Newest observed league matches ONLY, with explicit dates and recency decay.

    Old version accidentally used the first eight matches in API response order.
    """
    if target_time is None: target_time=NOW
    values=[]
    for f in fixtures:
        if (f.get('fixture') or {}).get('status',{}).get('short') != 'FT': continue
        if f.get('league',{}).get('id') not in all_ids: continue
        when=dt.datetime.fromisoformat(f['fixture']['date']).astimezone(TZ)
        if when >= target_time: continue
        teams=f.get('teams',{})
        if (teams.get(venue) or {}).get('id') != team_id: continue
        opponent='away' if venue=='home' else 'home'
        if stat is None:
            v1,v2=score(f)
            if venue=='away': v1,v2=v2,v1
        else:
            h,a=fixture_stats_pair(f, stat)
            v1,v2=(h,a) if venue=='home' else (a,h)
        if v1 is not None and v2 is not None:
            values.append((when,v1,v2))
    return qm.weighted_rates(values,target_time,MIN_SAMPLE,12)

def estimate(home,away,league_prior=None):
    return qm.venue_strength_expectation(home,away,league_prior)

def parse_stats_side(side, stat_type, period=None):
    """Explicit periods only; an undifferentiated fulltime value is never used for half."""
    raw=side.get('statistics') or []
    if period:
        if isinstance(raw, dict):
            candidates=[raw.get(k) for k in ['first_half','firstHalf','1H','1st Half','first']]
            raw=next((c for c in candidates if isinstance(c,list)),[])
        if isinstance(raw,list):
            # A row may put explicit period values inside its value object.
            for item in raw:
                if isinstance(item,dict) and item.get('type')==stat_type and isinstance(item.get('value'),dict):
                    for key in ('first_half','firstHalf','1H','first'):
                        if key in item['value']: return as_int(item['value'][key])
            candidates=[item for item in raw if isinstance(item,dict) and 
                        str(item.get('period') or item.get('half') or item.get('time') or '').lower() in ('1h','1','first half','1st half','first')]
            # Some vendor versions structure entire first-half data in a period object.
            if candidates and isinstance(candidates[0].get('statistics'), list): raw=candidates[0]['statistics']
            elif candidates: raw=candidates
            else: return None
    if not isinstance(raw,list): return None
    for item in raw:
        if isinstance(item,dict) and item.get('type')==stat_type:
            v=item.get('value')
            if isinstance(v,dict) and period:
                v=next((v.get(k) for k in ('first_half','firstHalf','1H','first') if k in v),None)
            return as_int(v)
    return None

def parse_stats(rows,fixture):
    """Never claim first-half data without explicit period tagging.
    API versions may format half stats differently: skip when unrecognized.
    """
    if not isinstance(rows,list): return {}
    result={'cornersFT':{}, 'corners1H':{}}
    for team_block in rows:
        tid=(team_block.get('team') or {}).get('id')
        if not tid:continue
        ft=parse_stats_side(team_block,'Corner Kicks')
        first=parse_stats_side(team_block,'Corner Kicks','first')
        if ft is not None: result['cornersFT'][str(tid)]=ft
        if first is not None: result['corners1H'][str(tid)]=first
    result.update(si.extra_match_stats(rows))
    return result

def is_settled(p,fixture):
    if (fixture.get('fixture') or {}).get('status',{}).get('short') != 'FT': return None
    h,a=score(fixture)
    if h is None or a is None:return None
    market=p['marketType']
    if market=='goals25': return 'won' if h+a >= 3 else 'lost'
    if market=='resultFT':
        actual='Home win' if h>a else ('Draw' if h==a else 'Away win')
        return 'won' if p['tip']==actual else 'lost'
    if market in ('cornersFT','corners1H'):
        stats=CACHE['stats'].get(str(fixture['fixture']['id'])) or {}
        k='cornersFT' if market=='cornersFT' else 'corners1H'
        vals=stats.get(k) or {}
        t1,t2=(fixture.get('teams') or {}).get('home',{}).get('id'),(fixture.get('teams') or {}).get('away',{}).get('id')
        x,y=as_int(vals.get(str(t1))),as_int(vals.get(str(t2)))
        if x is None or y is None:return None
        threshold=9 if market=='cornersFT' else 4
        return 'won' if x+y >= threshold else 'lost'
    if market=='twoUP':
        selected_home = p.get('selectedSide') == 'H' if p.get('selectedSide') in ('H','A') else p['tip'].startswith(p['home'])
        # 2UP market means *ever* goes two ahead, not final score difference.
        if (h-a if selected_home else a-h)>=2:return 'won'
        return None
    return None

def settle_two_up_with_events(p, fixture, events):
    """Evaluate goal-by-goal with own goals credited to the opposing side.
    Cross-check all event goals against official FT score; otherwise stay pending.
    """
    gh,ga=score(fixture)
    if gh is None or ga is None or not isinstance(events,list):return None
    ht=fixture['teams']['home']['id'];at=fixture['teams']['away']['id']
    timeline=[]
    for i,event in enumerate(events):
        if event.get('type')!='Goal':continue
        detail=str(event.get('detail') or '').lower()
        if detail not in ('normal goal','penalty','own goal'):continue
        scorer=(event.get('team') or {}).get('id')
        if scorer not in (ht,at):return None
        awarded_to=(at if scorer==ht else ht) if detail=='own goal' else scorer
        when=event.get('time') or {}
        elapsed=as_int(when.get('elapsed'))
        extra=as_int(when.get('extra')) or 0
        if elapsed is None:return None
        timeline.append((elapsed,extra,i,awarded_to))
    timeline.sort()
    h=a=0; home_seen=away_seen=False
    for _,_,_,tid in timeline:
        if tid==ht:h+=1
        else:a+=1
        if h-a>=2:home_seen=True
        if a-h>=2:away_seen=True
    # If vendor timeline is incomplete or includes reversed own goals, do not grade.
    if (h,a)!=(gh,ga):return None
    selected_home=p['tip'].startswith(p['home'])
    return 'won' if (home_seen if selected_home else away_seen) else 'lost'


def new_pick(f,market,tip,prob,mean,nh,na,note):
    fixture_id=f['fixture']['id']
    src=f'https://www.api-football.com/documentation_v3'
    checked=NOW.isoformat(timespec='seconds')
    p={'id':f'{fixture_id}-{market}','fixtureId':fixture_id,
       'home':f['teams']['home']['name'],'away':f['teams']['away']['name'],
       'league':LEAGUES[f['league']['id']],'kickoff':f['fixture']['date'],
       'marketType':market,'market': {'goals25':'FULL-TIME GOALS','cornersFT':'FULL-TIME CORNERS','corners1H':'FIRST-HALF CORNERS','resultFT':'FULL-TIME RESULT','twoUP':'TWO-GOAL LEAD'}[market],
       'tip':tip,'confidence':round(prob*100), 'projectedTotal':round(mean,2),
       'reason':note, 'status':'pending', 'demo':False,
       'research':{'sampleHome':nh,'sampleAway':na,'checkedAt':checked,
                   'sources':[src], 'note':'Conservative, venue-aware recency-weighted estimate with league baseline shrinkage. Historical stats may omit missing fixtures. Model is not backtested, calibrated, or a proven betting edge.'}}
    return p

def build_forecast(f, all_fixtures, squad_report=None):
    league=f['league']['id']; teams=f['teams']; home_id=teams['home']['id']; away_id=teams['away']['id']
    kickoff=dt.datetime.fromisoformat(f['fixture']['date']).astimezone(TZ)
    # Strict chronological filtering avoids leaking future matches into forecasts.
    prior=[x for x in all_fixtures if dt.datetime.fromisoformat(x['fixture']['date']).astimezone(TZ)<kickoff
           and x.get('league',{}).get('id') == league and (x.get('fixture') or {}).get('status',{}).get('short')=='FT']
    priors=qm.league_baseline(prior)
    h=rate(prior,home_id,'home',target_time=kickoff)
    a=rate(prior,away_id,'away',target_time=kickoff)
    picks=[]
    if h and a and priors:
        hm,am=estimate(h,a,priors); base_home=priors['home'];base_away=priors['away']
        probs=match_probs(hm,am); m=hm+am; base_probs=match_probs(base_home,base_away)
        desc=(f'{h["n"]} recent home and {a["n"]} away league matches (recency weighted); '
              f'league reference {priors["n"]} matches; expected goals {hm:.2f}–{am:.2f}. '
              'Availability and playing-style report is shown in research details; estimates are not calibrated.')
        raw_over=over(3,m)
        p_over=qm.careful_probability(raw_over,over(3,base_home+base_away),h['n'],a['n'])
        if p_over>=0.60:
            picks.append(new_pick(f,'goals25','Over 2.5 goals',p_over,m,h['n'],a['n'],desc))
        label=max(probs,key=probs.get)
        p_result=qm.careful_probability(probs[label],base_probs[label],h['n'],a['n'])
        if p_result>=0.58:
            picks.append(new_pick(f,'resultFT',{'H':'Home win','D':'Draw','A':'Away win'}[label],p_result,m,h['n'],a['n'],
                                  f'Model 1X2: H {probs["H"]:.0%}, D {probs["D"]:.0%}, A {probs["A"]:.0%}. '+desc))
        advance=two_up_probs(hm,am); base_advance=two_up_probs(base_home,base_away)
        best=max(advance,key=advance.get)
        p_advance=qm.careful_probability(advance[best],base_advance[best],h['n'],a['n'])
        if p_advance>=0.48:
            who=teams['home']['name'] if best=='H' else teams['away']['name']
            pick=new_pick(f,'twoUP',who+' to lead by 2 at any point',p_advance,m,h['n'],a['n'],
                          f'Experimental goal-order model. A 2-goal lead is not the same as a bookmaker payout rule. '+desc)
            pick['selectedSide']=best
            picks.append(pick)
    # Corners are intentionally skipped if the actual league period data is sparse.
    for stat,threshold,market in [('cornersFT',9,'Over 8.5 corners'),('corners1H',4,'Over 3.5 first-half corners')]:
        h=rate(prior,home_id,'home',stat,kickoff);a=rate(prior,away_id,'away',stat,kickoff)
        if not h or not a: continue
        baseline=qm.league_baseline(prior,lambda fix: fixture_stats_pair(fix,stat))
        if not baseline: continue
        mh,ma=estimate(h,a,baseline);total=mh+ma
        model_prob=qm.overdispersed_tail(threshold,total,baseline['totals'])
        league_prob=qm.overdispersed_tail(threshold,baseline['home']+baseline['away'],baseline['totals'])
        p_corner=qm.careful_probability(model_prob,league_prob,h['n'],a['n'])
        if p_corner < (0.62 if stat=='cornersFT' else 0.60): continue
        picks.append(new_pick(f,stat,market,p_corner,total,h['n'],a['n'],
                              f'Observed {stat} counts: {h["n"]} recent home and {a["n"]} away matches; '
                              f'{baseline["n"]} league comparison matches. Missing periods excluded. '
                              f'Estimated total {total:.2f} corners. Experimental overdispersion adjustment, not calibrated.'))
    # Keep uncertain lineups and verified key-player absences from creating falsely
    # authoritative public tips. No invented goal-based injury multipliers are used.
    if squad_report:
        if squad_report.get('risk'):
            return []
        if squad_report.get('cautionTeams'):
            picks = [p for p in picks if p['marketType'] not in ('resultFT', 'twoUP')]
        for p in picks:
            research = p.setdefault('research', {})
            research['squadReport'] = squad_report
            research['lineupStatus'] = squad_report['lineups']
            research['teamNews'] = squad_news(squad_report)
            research['playingStyles'] = style_text(squad_report)
            research['withWithout'] = observed_player_comparisons(squad_report)
            research['dataQuality'] = 'Injuries checked against provider reports; confirmed XIs only if explicitly available. Style is descriptive, not a tactical scouting claim.'
    return picks


def squad_news(scout):
    lines = []
    for side in ('home', 'away'):
        team = scout['teams'][side]
        missing = [p['name'] for p in team['injuries'] if p['status'] == 'missing']
        questionable = [p['name'] for p in team['injuries'] if p['status'] == 'questionable']
        if missing:
            lines.append(f'{team["name"]}: reported unavailable: {", ".join(missing[:5])}')
        if questionable:
            lines.append(f'{team["name"]}: questionable: {", ".join(questionable[:5])}')
        if team['keyUnavailable']:
            lines.append(f'Historical regular starters out: {", ".join(team["keyUnavailable"][:4])}')
    return '; '.join(lines) if lines else ('No reported absences in fetched feed; not proof that the whole squad is fit.'
                                            if scout['injuryData'] == 'available' else 'Injury feed unavailable; squad fitness unverified.')


def style_text(scout):
    return '; '.join(f'{scout["teams"][side]["name"]}: {scout["teams"][side]["style"]["description"]}'
                     for side in ('home','away'))


def observed_player_comparisons(scout):
    pieces = []
    for side in ('home','away'):
        for entry in scout['teams'][side]['withWithout']:
            a = entry['started']; b = entry['didNotStart']
            pieces.append(f'{entry["player"]}: {a["matches"]} starts — team scored {a["scored"]}/match; '
                          f'{b["matches"]} non-starts — team scored {b["scored"]}/match')
    return '; '.join(pieces) if pieces else 'Not enough verified historical starts and non-starts to make a meaningful comparison.'


def collect_injuries(fixtures):
    """Use /injuries?ids= in 20-fixture batches; missing API data is unknown."""
    ids = [f['fixture']['id'] for f in fixtures]
    for k in range(0,len(ids),20):
        batch = ids[k:k+20]
        # Refresh each run: stale injury information is unsafe.
        try:
            response = api.get('/injuries', {'ids':'-'.join(str(fid) for fid in batch)})
        except (QuotaReached, RuntimeError) as exc:
            print('Squad injury information unavailable:',exc,file=sys.stderr)
            continue
        for fid in batch:
            SCOUT_CACHE['injuries'][str(fid)] = {'checkedAt': NOW.isoformat(), 'records': []}
        for entry in response:
            fid = (entry.get('fixture') or {}).get('id')
            if str(fid) in SCOUT_CACHE['injuries']:
                SCOUT_CACHE['injuries'][str(fid)]['records'].append(entry)


def collect_squads(upcoming, max_teams=8):
    """Check registered team squads using the provider; cache for seven days."""
    tids=sorted({f['teams'][s]['id'] for f in upcoming for s in ('home','away')})
    attempts=0
    for tid in tids:
        if attempts >= max_teams or api.calls >= MAX_CALLS - 24: break
        old=SCOUT_CACHE['squads'].get(str(tid))
        if old:
            checked=dt.datetime.fromisoformat(old['checkedAt'])
            if (NOW - checked).days < 7: continue
        try:
            response=api.get('/players/squads',{'team':tid})
            if response and isinstance(response[0].get('players'),list):
                SCOUT_CACHE['squads'][str(tid)]={'checkedAt': NOW.isoformat(),
                    'players': [{'id': p.get('id'),'name':p.get('name'),'position':p.get('position')}
                                for p in response[0]['players'] if p.get('id') is not None]}
            attempts += 1
        except (QuotaReached,RuntimeError) as exc:
            print('Registered squad unavailable:',exc,file=sys.stderr)
            attempts += 1


def collect_lineups(upcoming, historic):
    """Reserve API requests for confirmed near-kickoff and historical starting XIs."""
    # Never claim daily-morning starting XIs were confirmed.
    for match in sorted(upcoming,key=lambda f:f['fixture']['date']):
        mins = (dt.datetime.fromisoformat(match['fixture']['date']).astimezone(TZ)-NOW).total_seconds()/60
        fid = str(match['fixture']['id'])
        if not 0 <= mins <= 70 or fid in SCOUT_CACHE['lineups'] and SCOUT_CACHE['lineups'][fid]:
            continue
        if api.calls >= MAX_CALLS-2:
            break
        try:
            rows = api.get('/fixtures/lineups', {'fixture':fid})
            if rows: SCOUT_CACHE['lineups'][fid] = rows
        except (QuotaReached, RuntimeError) as exc:
            print('Match lineup unavailable:', exc, file=sys.stderr)
    # Accumulate actual historical starting elevens over repeated runs.
    selected = sorted(historic.values(),key=lambda f:f['fixture']['date'],reverse=True)
    attempts = 0
    for match in selected:
        fid = str(match['fixture']['id'])
        if fid in SCOUT_CACHE['lineups'] or api.calls >= MAX_CALLS-2 or attempts >= 12:
            continue
        try:
            rows = api.get('/fixtures/lineups', {'fixture':fid})
            # Store only complete lineup observations; no synthetic start XI.
            if rows and any(si.lineup_for_team(rows,(match['teams'][side] or {}).get('id'))
                            for side in ('home','away')):
                SCOUT_CACHE['lineups'][fid] = rows
            attempts += 1
        except (QuotaReached, RuntimeError) as exc:
            print('Historical lineup unavailable:',exc,file=sys.stderr)
            attempts += 1


def write_output(picks, message, success):
    picks=sorted(picks,key=lambda x:(x['kickoff'],x['fixtureId'],x['marketType']))
    meta={'automated':success,'updatedAt':NOW.isoformat(timespec='seconds') if success else None,
          'message':message, 'modelVersion':'quality-v3-squad-style-experimental', 'selectedLeagues':list(LEAGUES.values()),'apiCalls':api.calls}
    OUTPUT.write_text('window.GOALGRID_META = '+json.dumps(meta,ensure_ascii=False)+';\nwindow.GOALGRID_PICKS = '+json.dumps(picks,ensure_ascii=False)+';\n',encoding='utf8')


def main():
    if not API_KEY: raise RuntimeError('Missing API_SPORTS_KEY environment variable. No real predictions are generated.')
    psl_id=get_psl_id(); LEAGUES[psl_id]='South African PSL'
    global all_ids; all_ids=set(LEAGUES)
    # One request per day for all competitions rather than seven per league.
    today_fixtures=[]
    for offset in [0,1]:
        date=TODAY+dt.timedelta(days=offset)
        batch=api.get('/fixtures',{'date':date.isoformat(),'timezone':'Africa/Johannesburg'})
        today_fixtures.extend([f for f in batch if (f.get('league') or {}).get('id') in all_ids])
    upcoming=[f for f in today_fixtures if (f.get('fixture') or {}).get('status',{}).get('short') in ('NS','TBD') and dt.datetime.fromisoformat(f['fixture']['date'])>NOW]
    collect_injuries(upcoming)
    collect_squads(upcoming)
    # VIP data is fetched only from protected Supabase storage when configured.
    vip_saved = load_private_history()
    # Retrieve previous public and VIP picks for up to the past 3 days.
    recorded = list(PREVIOUS['picks'].values()) + list(vip_saved.values())
    recent_dates={dt.datetime.fromisoformat(p['kickoff']).astimezone(TZ).date() for p in recorded
                  if p['status']=='pending' and 0 <= (TODAY-dt.datetime.fromisoformat(p['kickoff']).astimezone(TZ).date()).days <= 3}
    by_id={f['fixture']['id']:f for f in today_fixtures}
    for date in sorted(recent_dates):
        for f in api.get('/fixtures',{'date':date.isoformat(),'timezone':'Africa/Johannesburg'}):
            if f.get('league',{}).get('id') in all_ids: by_id[f['fixture']['id']]=f
    # Past played matches from both sides, per team; no synthetic data.
    required_teams={f['teams'][side]['id'] for f in upcoming for side in ('home','away')}
    history=[]
    for team_id in sorted(required_teams):
        try:
            result=api.get('/fixtures',{'team':team_id,'last':20})
            history.extend(x for x in result if x.get('league',{}).get('id') in all_ids)
        except QuotaReached:break
    history={x['fixture']['id']:x for x in history if (x.get('fixture') or {}).get('status',{}).get('short')=='FT'}
    # Expand an auditable match archive over time, without downloading extra data.
    cutoff_archive=NOW-dt.timedelta(days=540)
    for fix in history.values():
        ARCHIVE['fixtures'][str(fix['fixture']['id'])]={k:fix.get(k) for k in ('fixture','league','teams','goals')}
    ARCHIVE['fixtures']={k:v for k,v in ARCHIVE['fixtures'].items() if
        dt.datetime.fromisoformat(v['fixture']['date']).astimezone(TZ)>=cutoff_archive}
    # Reserve some requests for lineups and tactical research, never exhaust the budget on corners alone.
    for fixture_id, f in sorted(history.items(),key=lambda t:t[1]['fixture']['date'],reverse=True):
        if str(fixture_id) in CACHE['stats'] or api.calls >= MAX_CALLS-18:continue
        try:
            response=api.get('/fixtures/statistics',{'fixture':fixture_id,'half':'true'})
            CACHE['stats'][str(fixture_id)]=parse_stats(response,f)
        except QuotaReached:break
        except RuntimeError as e:
            print('Could not fetch stats:', e, file=sys.stderr)
    collect_lineups(upcoming,history)
    saved=dict(PREVIOUS['picks'])
    # One extra researched pick per eligible fixture is reserved for VIP when
    # private database storage is configured. All other picks remain free.
    # Existing picks never change tier (no retroactive hiding of public picks).
    for match in sorted(upcoming,key=lambda f:f['fixture']['date']):
        full_history=list({**ARCHIVE['fixtures'],**{str(k):v for k,v in history.items()}}.values())
        injury_entry=SCOUT_CACHE['injuries'].get(str(match['fixture']['id']))
        reported_injuries = si.injuries_by_team(injury_entry['records'],
                          match['teams']['home']['id'],match['teams']['away']['id']) if injury_entry else None
        scout=si.scout_fixture(match,full_history,CACHE['stats'],SCOUT_CACHE['lineups'],
                              injury_records=reported_injuries,
                              confirmed_lineups=SCOUT_CACHE['lineups'].get(str(match['fixture']['id'])),
                              squad_rosters={tid:entry['players'] for tid,entry in SCOUT_CACHE['squads'].items()})
        fresh=build_forecast(match,full_history,scout)
        # After new verified squad news, old active tips that are no longer
        # permitted under the cautious squad gate are withdrawn, never silently removed.
        valid_ids={p['id'] for p in fresh}
        for store in (saved,vip_saved):
            for old in store.values():
                if old.get('fixtureId') == match['fixture']['id'] and old.get('status') == 'pending':
                    if old['id'] not in valid_ids:
                        old['status']='void'
                        old['reason']='Withdrawn before kickoff: new squad/team evidence or insufficient data.'
                    elif old['id'] in valid_ids:
                        old['research'].update(next(p['research'] for p in fresh if p['id']==old['id']))

        vip_id = None
        if VIP_ENABLED and len(fresh) >= 2:
            # Only data-rich picks can appear as additional VIP research.
            # VIP is not a guarantee of higher prediction success.
            eligible=[p for p in fresh if p['confidence'] >= 67 and
                      p.get('research',{}).get('sampleHome',0) >= 8 and
                      p.get('research',{}).get('sampleAway',0) >= 8]
            if eligible: vip_id=max(eligible,key=lambda p:(p['confidence'],p['marketType']))['id']
        for record in fresh:
            if record['id'] in saved or record['id'] in vip_saved: continue
            if record['id'] == vip_id: vip_saved[record['id']] = record
            else: saved[record['id']] = record
    # Settle only fully supported results. Never mark unknown observations "lost".
    for p in list(saved.values()) + list(vip_saved.values()):
        f=by_id.get(p['fixtureId'])
        if not f or p.get('status')!='pending':continue
        h,a=score(f)
        if h is not None and a is not None and f['fixture']['status']['short']=='FT':
            p['finalScore']=f'{h}-{a}'
            # If needed stats are missing, retrieve exactly this fixture's stats.
            if p['marketType'] in ('cornersFT','corners1H') and str(p['fixtureId']) not in CACHE['stats']:
                try: CACHE['stats'][str(p['fixtureId'])]=parse_stats(api.get('/fixtures/statistics',{'fixture':p['fixtureId'],'half':'true'}),f)
                except (QuotaReached,RuntimeError):pass
            status=is_settled(p,f)
            if p['marketType']=='twoUP' and status is None:
                try: status=settle_two_up_with_events(p,f,api.get('/fixtures/events',{'fixture':p['fixtureId']}))
                except (QuotaReached, RuntimeError): pass
            if status:p['status']=status
    # Keep past picks for transparency, but limit to 45 days for a small static site.
    cutoff=NOW-dt.timedelta(days=45)
    saved={k:p for k,p in saved.items() if dt.datetime.fromisoformat(p['kickoff'])>=cutoff}
    vip_saved={k:p for k,p in vip_saved.items() if dt.datetime.fromisoformat(p['kickoff'])>=cutoff}
    # Upload private selections before writing public data, so failure cannot
    # accidentally result in a public leak or a silent successful deployment.
    publish_private(list(vip_saved.values()))
    CACHEFILE.parent.mkdir(exist_ok=True)
    CACHEFILE.write_text(json.dumps(CACHE,separators=(',',':')))
    SCOUT_FILE.write_text(json.dumps(SCOUT_CACHE,ensure_ascii=False,separators=(',',':')))
    ARCHIVEFILE.write_text(json.dumps(ARCHIVE,ensure_ascii=False,separators=(',',':')))
    (ROOT/'history.json').write_text(json.dumps({'picks':saved},ensure_ascii=False,indent=2))
    write_output(list(saved.values()),f'Connected. Updated {NOW:%d %b %Y %H:%M} SAST. Empty markets mean the sample or coverage is insufficient; schedules may delay.',True)
    print(f'Published {len(saved)} free and {len(vip_saved)} private VIP picks from {len(upcoming)} fixtures; {api.calls} provider calls; PSL ID={psl_id}')

if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'Publishing failed (previous predictions retained): {e}',file=sys.stderr)
        sys.exit(1)
