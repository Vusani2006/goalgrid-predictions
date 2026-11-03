#!/usr/bin/env python3
"""Apes Nation free-tier daily publisher for football-data.org.

Uses current-season competition match results and schedules. Generates ONLY
experimental 1X2 and Over 2.5 goal estimates; no fake corners, 2UP,
lineups/injuries, PSL or premium picks. No raw API keys enter public files.
Run on GitHub Actions with FOOTBALL_DATA_ORG_KEY repository secret.
"""
import datetime as dt
import json
import math
import os
import pathlib
import time
import urllib.error
import urllib.request
from collections import Counter
from zoneinfo import ZoneInfo
import quality_model as qm

BASE = 'https://api.football-data.org/v4'
ROOT = pathlib.Path(__file__).resolve().parent
TZ = ZoneInfo('Africa/Johannesburg')
LEAGUES = {
    'PL': 'Premier League', 'PD': 'La Liga', 'SA': 'Serie A',
    'BL1': 'Bundesliga', 'FL1': 'Ligue 1', 'PPL': 'Primeira Liga',
    'CL': 'UEFA Champions League', 'EL': 'UEFA Europa League',
    'EC': 'European Championship', 'WC': 'FIFA World Cup',
}
CORE_LEAGUES = ('PL', 'PD', 'SA', 'BL1', 'FL1', 'PPL')
SOURCE = 'https://www.football-data.org/'
MIN_LEAGUE_GAMES = 20
MIN_TEAM_GAMES = 6
MIN_VENUE_GAMES = 3
MAX_AGE_DAYS = 45
MAX_FUTURE_DAYS = 7


def fetch_competition(code, key):
    if code not in LEAGUES:
        raise ValueError('Unsupported league')
    request = urllib.request.Request(
        f'{BASE}/competitions/{code}/matches',
        headers={'X-Auth-Token': key, 'Accept': 'application/json',
                 'User-Agent': 'ApesNationFooty/1.0 (free research forecasts)'},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'football-data.org HTTP {error.code} for {code}; check free-tier subscription') from None
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise RuntimeError(f'football-data.org unavailable for {code}: {type(error).__name__}') from None
    if not isinstance(data.get('matches'), list):
        raise RuntimeError(f'Missing fixtures for {code}, cannot safely publish')
    return data['matches']


def kickoff(match):
    raw = match.get('utcDate')
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(raw.replace('Z', '+00:00')).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def completed_score(match):
    if match.get('status') != 'FINISHED':
        return None
    raw = (match.get('score') or {}).get('fullTime') or {}
    h, a = raw.get('home'), raw.get('away')
    if not isinstance(h, int) or isinstance(h, bool) or h < 0 or not isinstance(a, int) or isinstance(a, bool) or a < 0:
        return None
    return (h, a)


def team_id(match, side):
    return (match.get(side + 'Team') or {}).get('id')


def team_name(match, side):
    team = match.get(side + 'Team') or {}
    return team.get('shortName') or team.get('name') or 'Unknown team'


def weighted_team_rates(matches, team, at_home, before):
    rows = []
    total = 0
    for match in matches:
        when, result = kickoff(match), completed_score(match)
        if when is None or when >= before or result is None:
            continue
        is_home = team_id(match, 'home') == team
        is_away = team_id(match, 'away') == team
        if not (is_home or is_away):
            continue
        total += 1
        if (at_home and not is_home) or (not at_home and not is_away):
            continue
        scored, conceded = result if is_home else result[::-1]
        rows.append((when, scored, conceded))
    if total < MIN_TEAM_GAMES:
        return None
    stats = qm.weighted_rates(rows, before, MIN_VENUE_GAMES, 12)
    if stats:
        stats['total'] = total
    return stats


def league_reference(matches, before):
    pairs = []
    for match in matches:
        when, score = kickoff(match), completed_score(match)
        if when and when < before and score:
            pairs.append(score)
    if len(pairs) < MIN_LEAGUE_GAMES:
        return None
    n = len(pairs)
    return {
        'home': sum(h for h, a in pairs) / n,
        'away': sum(a for h, a in pairs) / n,
        'over25': sum(h + a >= 3 for h, a in pairs) / n,
        'result': {'H': sum(h > a for h, a in pairs) / n,
                   'D': sum(h == a for h, a in pairs) / n,
                   'A': sum(h < a for h, a in pairs) / n},
        'n': n,
    }


def poisson_pmf(k, mean):
    return math.exp(-mean) * mean ** k / math.factorial(k)


def probabilities(lam_home, lam_away):
    home = [poisson_pmf(i, lam_home) for i in range(16)]
    away = [poisson_pmf(i, lam_away) for i in range(16)]
    result = {
        'H': sum(home[i] * away[j] for i in range(16) for j in range(i)),
        'D': sum(home[i] * away[i] for i in range(16)),
        'A': sum(home[i] * away[j] for j in range(16) for i in range(j)),
    }
    goal_mean = lam_home + lam_away
    over25 = 1.0 - sum(poisson_pmf(n, goal_mean) for n in range(3))
    return result, over25


def make_pick(match, league, market, probability, home_mu, away_mu, home_sample, away_sample, now):
    match_id = match.get('id')
    hname, aname = team_name(match, 'home'), team_name(match, 'away')
    when = kickoff(match)
    if market == 'goals25':
        label, tip = 'OVER 2.5 GOALS', 'Over 2.5 goals'
    else:
        label = 'FULL-TIME RESULT (1X2)'
        tip = {'H': 'Home win', 'D': 'Draw', 'A': 'Away win'}[market[-1]]
    return {
        'id': f'FDORG-{match_id}-{market}', 'fixtureId': match_id,
        'league': league, 'home': hname, 'away': aname,
        'kickoff': when.isoformat().replace('+00:00', 'Z'),
        'marketType': 'goals25' if market == 'goals25' else 'resultFT',
        'market': label, 'tip': tip, 'confidence': round(probability * 100),
        'projectedTotal': round(home_mu + away_mu, 2),
        'reason': f'Experimental goals model: {home_mu:.2f} expected home goals and {away_mu:.2f} away; not a verified win probability.',
        'status': 'pending', 'research': {
            'sampleHome': home_sample['n'], 'sampleAway': away_sample['n'],
            'checkedAt': now.isoformat(),
            'teamNews': 'Not available from the free fixtures/results feed.',
            'lineupStatus': 'Not available — do not interpret as checked',
            'playingStyles': 'Not evaluated: no licensed event/style statistics in this feed.',
            'withWithout': 'Not evaluated: player start/absence history unavailable.',
            'dataQuality': 'Current-season results and home/away samples only; no corners, PSL, injury or 2UP confirmation.',
            'note': 'Experimental estimate based on observed scores only. Cannot guarantee accuracy; team news may change the outlook.',
            'sources': [SOURCE],
        }
    }


def forecast(match, league, matches, now):
    when = kickoff(match)
    if when is None or when < now or when > now + dt.timedelta(days=MAX_FUTURE_DAYS):
        return []
    if match.get('status') not in ('SCHEDULED', 'TIMED'):
        return []
    hid, aid = team_id(match, 'home'), team_id(match, 'away')
    if hid is None or aid is None:
        return []
    past = [m for m in matches if kickoff(m) is not None and kickoff(m) < when]
    prior = league_reference(past, when)
    if not prior:
        return []
    h = weighted_team_rates(past, hid, True, when)
    a = weighted_team_rates(past, aid, False, when)
    if h is None or a is None:
        return []
    mu_h, mu_a = qm.venue_strength_expectation(h, a, prior)
    raw_ft, raw_over = probabilities(mu_h, mu_a)
    out = []
    prob_goals = qm.careful_probability(raw_over, prior['over25'], h['total'], a['total'])
    if prob_goals >= .64:
        out.append(make_pick(match, league, 'goals25', prob_goals, mu_h, mu_a, h, a, now))
    adjusted = {side: qm.careful_probability(p, prior['result'][side], h['total'], a['total']) for side, p in raw_ft.items()}
    best_side = max(adjusted, key=adjusted.get)
    if adjusted[best_side] >= .60:
        out.append(make_pick(match, league, 'result' + best_side, adjusted[best_side], mu_h, mu_a, h, a, now))
    return out


def settle_pick(pick, match):
    score = completed_score(match)
    if not score:
        return False
    h, a = score
    if pick['marketType'] == 'goals25':
        win = h + a >= 3
    elif pick['marketType'] == 'resultFT':
        actual = 'Home win' if h > a else ('Draw' if h == a else 'Away win')
        win = actual == pick['tip']
    else:
        return False
    pick['status'] = 'won' if win else 'lost'
    pick['finalScore'] = f'{h}–{a}'
    return True


def create_feed(fixtures_by_league, now, history=None):
    history = dict(history or {})
    all_by_id = {}
    for code, matches in fixtures_by_league.items():
        if code not in LEAGUES:
            continue
        for match in matches:
            if match.get('id') is not None:
                all_by_id[str(match['id'])] = match
            for pick in forecast(match, LEAGUES[code], matches, now):
                if pick['id'] not in history:
                    history[pick['id']] = pick
    for pick in history.values():
        if pick.get('status') == 'pending':
            match = all_by_id.get(str(pick.get('fixtureId')))
            if match:
                settle_pick(pick, match)
    cutoff = now - dt.timedelta(days=MAX_AGE_DAYS)
    filtered = {}
    for key, p in history.items():
        try:
            when = dt.datetime.fromisoformat(p['kickoff'].replace('Z', '+00:00'))
        except (KeyError, ValueError):
            continue
        if when >= cutoff:
            filtered[key] = p
    picks = sorted(filtered.values(), key=lambda p: p['kickoff'])
    return filtered, picks


def main():
    key = os.getenv('FOOTBALL_DATA_ORG_KEY', '').strip()
    if not key:
        raise RuntimeError('Missing FOOTBALL_DATA_ORG_KEY repository secret (different from API_SPORTS_KEY)')
    now = dt.datetime.now(dt.timezone.utc)
    fixtures = {}
    for index, code in enumerate(LEAGUES):
        if index:
            time.sleep(6.2)  # conservative: under free tier's 10 calls/min
        try:
            fixtures[code] = fetch_competition(code, key)
        except RuntimeError as error:
            if code in CORE_LEAGUES:
                raise  # Preserve the previous feed if a core league cannot load.
            print(f'{code}: optional competition unavailable ({error}); skipping')
            continue
        print(f'{code}: {len(fixtures[code])} fixtures returned')
    archive_path = ROOT / 'free_history.json'
    if archive_path.exists():
        saved = json.loads(archive_path.read_text(encoding='utf-8'))
        history = saved.get('picks') or {}
    else:
        history = {}
    updated, picks = create_feed(fixtures, now, history)
    meta = {
        'automated': True,
        'updatedAt': now.isoformat().replace('+00:00', 'Z'),
        'selectedLeagues': [LEAGUES[code] for code in fixtures],
        'message': 'Experimental goals and 1X2 estimates from available competitions only. Some UEFA/international tournaments may be unavailable under the API plan or lack enough recent match history. No automated corners, PSL, squad or 2UP verification.',
    }
    payload = ('window.GOALGRID_META = ' + json.dumps(meta, ensure_ascii=False) + ';\n' +
               'window.GOALGRID_PICKS = ' + json.dumps(picks, ensure_ascii=False) + ';\n')
    # Only write after ALL requests succeed, preserving prior published picks on errors.
    (ROOT / 'data.js').write_text(payload, encoding='utf-8')
    archive_path.write_text(json.dumps({'picks': updated}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Published {len(picks)} recent picks ({sum(p["status"] == "pending" for p in picks)} pending); goal and FT result only.')


if __name__ == '__main__':
    main()
