"""Evidence-only squad and playing-style research for Apes Nation Football Prediction.

This module deliberately does NOT assume that an empty injury response means everyone
is fit, infer pressing intensity from possession, or treat historical correlations as
causal player effects. It contains no API credentials or networking.
"""
from collections import Counter
import datetime as dt


STAT_TYPES = {
    'Ball Possession': 'possession',
    'Total Shots': 'shots',
    'Shots on Goal': 'shotsOnTarget',
    'Total passes': 'passes',
}


def number(value, percent=False):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace('%', '')
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 and (not percent or n <= 100) else None


def extra_match_stats(rows):
    """Fetch observed FULL-TIME statistical counts by team ID only."""
    out = {stat: {} for stat in STAT_TYPES.values()}
    for row in rows if isinstance(rows, list) else []:
        team_id = (row.get('team') or {}).get('id')
        if team_id is None:
            continue
        for metric in row.get('statistics') or []:
            name = STAT_TYPES.get(metric.get('type'))
            if not name:
                continue
            n = number(metric.get('value'), percent=(name == 'possession'))
            if n is not None:
                out[name][str(team_id)] = n
    return out


def lineup_for_team(raw, team_id):
    """Use only explicit startXI and substitutes from a provider lineup response."""
    for entry in raw if isinstance(raw, list) else []:
        if (entry.get('team') or {}).get('id') != team_id:
            continue
        starters = {}
        bench = {}
        for key, bucket in [('startXI', starters), ('substitutes', bench)]:
            for item in entry.get(key) or []:
                player = item.get('player') or {}
                pid = player.get('id')
                if pid is not None:
                    bucket[str(pid)] = str(player.get('name') or f'Player {pid}')
        if not starters:
            return None
        return {'starters': starters, 'bench': bench,
                'formation': entry.get('formation') or None,
                'coach': (entry.get('coach') or {}).get('name') or None}
    return None


def missing_status(item):
    """API returns 'Missing Fixture' or 'Questionable' in type field."""
    reason = str(item.get('type') or '').lower()
    if reason == 'missing fixture':
        return 'missing'
    if reason == 'questionable':
        return 'questionable'
    return 'unverified'


def injuries_by_team(rows, home_id, away_id):
    result = {str(home_id): [], str(away_id): []}
    for row in rows if isinstance(rows, list) else []:
        tid = str((row.get('team') or {}).get('id'))
        if tid not in result:
            continue
        player = row.get('player') or {}
        pid = player.get('id')
        if pid is None:
            continue
        result[tid].append({'id': str(pid), 'name': str(player.get('name') or 'Unknown player'),
                            'status': missing_status(row),
                            'reason': str(row.get('reason') or '')[:80]})
    return result


def observed_lineups(fixtures, team_id, lineup_cache, kickoff, max_games=12):
    eligible = []
    for match in fixtures:
        fix = match.get('fixture') or {}
        if fix.get('status', {}).get('short') != 'FT':
            continue
        try:
            when = dt.datetime.fromisoformat(fix['date'])
        except (ValueError, KeyError):
            continue
        if when >= kickoff or team_id not in [(match.get('teams') or {}).get(s, {}).get('id') for s in ('home','away')]:
            continue
        line = lineup_for_team(lineup_cache.get(str(fix['id'])), team_id)
        if line:
            eligible.append((when, match, line))
    eligible.sort(key=lambda x: x[0], reverse=True)
    return eligible[:max_games]


def core_starters(observed, min_appearances=4):
    """A core starter is defined only by observed startXI appearances."""
    if len(observed) < 6:
        return {}
    counter = Counter()
    names = {}
    for _, _, lineup in observed[:8]:
        for pid, name in lineup['starters'].items():
            counter[pid] += 1
            names[pid] = name
    threshold = max(min_appearances, int(len(observed[:8]) * 0.6))
    return {pid: {'name': names[pid], 'starts': count, 'sample': len(observed[:8])}
            for pid, count in counter.items() if count >= threshold}


def with_without(observed, player_id, team_id, min_each=3):
    """Historical goals when the player STARTED vs DID NOT START, not causal effect."""
    started = []
    not_started = []
    for _, fixture, lineup in observed:
        home = (fixture.get('teams') or {}).get('home', {}).get('id') == team_id
        g = fixture.get('goals') or {}
        own = g.get('home') if home else g.get('away')
        conceded = g.get('away') if home else g.get('home')
        if not isinstance(own, int) or not isinstance(conceded, int):
            continue
        (started if str(player_id) in lineup['starters'] else not_started).append((own, conceded))
    if len(started) < min_each or len(not_started) < min_each:
        return None
    def summarize(rows):
        return {'matches': len(rows), 'scored': round(sum(x for x,y in rows)/len(rows),2),
                'conceded': round(sum(y for x,y in rows)/len(rows),2)}
    return {'started': summarize(started), 'didNotStart': summarize(not_started),
            'warning': 'Descriptive averages only; opponent strength, tactics and player substitutions can distort this comparison.'}


def playing_style(fixtures, team_id, cached_stats, kickoff, limit=8):
    """Return transparent metric profile; never infer pressing from possession alone."""
    latest = []
    for match in fixtures:
        fix = match.get('fixture') or {}
        if fix.get('status', {}).get('short') != 'FT':
            continue
        try:
            when = dt.datetime.fromisoformat(fix['date'])
        except (KeyError, ValueError):
            continue
        if when >= kickoff:
            continue
        teams = match.get('teams') or {}
        if team_id not in [teams.get('home', {}).get('id'), teams.get('away', {}).get('id')]:
            continue
        if str(fix['id']) not in cached_stats:
            continue
        stats = cached_stats[str(fix['id'])]
        record = {'date': when}
        for metric in ('possession','shots','shotsOnTarget','cornersFT'):
            v = (stats.get(metric) or {}).get(str(team_id))
            if isinstance(v, (int, float)):
                record[metric] = v
        latest.append(record)
    latest.sort(key=lambda x:x['date'], reverse=True)
    latest = latest[:limit]
    ret = {'sampleMatches': len(latest), 'stats': {}}
    for metric in ('possession','shots','shotsOnTarget','cornersFT'):
        values = [entry[metric] for entry in latest if metric in entry]
        if len(values) >= 4:
            ret['stats'][metric] = {'average': round(sum(values)/len(values), 1), 'n': len(values)}
    descriptions = []
    poss = ret['stats'].get('possession')
    shots = ret['stats'].get('shots')
    corners = ret['stats'].get('cornersFT')
    if poss:
        val = poss['average']
        descriptions.append('possession-oriented' if val >= 55 else 'lower-possession' if val <= 45 else 'balanced possession')
    if shots:
        descriptions.append('high shot volume' if shots['average'] >= 13 else 'modest shot volume' if shots['average'] <= 9 else 'medium shot volume')
    if corners:
        descriptions.append(f'{corners["average"]:.1f} corners won per match')
    ret['description'] = ', '.join(descriptions) if descriptions else 'Insufficient verified statistics to classify playing style'
    return ret


def scout_fixture(fixture, fixtures, stat_cache, lineup_cache, injury_records=None, confirmed_lineups=None, squad_rosters=None):
    """Build a labeled, evidence-backed research report and risk flags for forecast."""
    kickoff = dt.datetime.fromisoformat(fixture['fixture']['date'])
    details = {'injuryData': 'available' if injury_records is not None else 'unavailable',
               'lineups': 'not confirmed', 'teams': {}, 'risk': [], 'cautionTeams': [],
               'disclaimer': 'With/without numbers describe past starts, not player-caused changes.'}
    for side in ('home', 'away'):
        team = fixture['teams'][side]
        tid = team['id']
        previous = observed_lineups(fixtures, tid, lineup_cache, kickoff)
        cores = core_starters(previous)
        styles = playing_style(fixtures, tid, stat_cache, kickoff)
        formations = Counter(line['formation'] for _, _, line in previous if line.get('formation'))
        styles['commonFormation'] = formations.most_common(1)[0][0] if formations else None
        injury = (injury_records or {}).get(str(tid), [])
        current = lineup_for_team(confirmed_lineups, tid)
        if current:
            details['lineups'] = 'at least one starting XI verified'
        key_out = []
        key_bench = []
        for item in injury:
            if item['id'] in cores and item['status'] == 'missing':
                key_out.append(item['name'])
        if current:
            key_bench = [v['name'] for pid,v in cores.items()
                         if pid not in current['starters'] and pid not in key_out and pid in current['bench']]
        if key_out or len(key_bench) >= 2:
            details['cautionTeams'].append(side)
        if len(key_out) >= 2 or (current and len(key_bench) >= 3):
            details['risk'].append(f'{team.get("name", f"Team {tid}")}: multiple usual starters missing or benched')
        comparisons = []
        for item in injury:
            if item['id'] not in cores or item['status'] != 'missing':
                continue
            outcome = with_without(previous, item['id'], tid)
            if outcome:
                comparisons.append({'player': item['name'], **outcome})
        details['teams'][side] = {
            'name': team.get('name', f'Team {tid}'), 'style': styles,
            'historicalLineupMatches': len(previous),
            'registeredSquadSize': len(squad_rosters[str(tid)]) if squad_rosters and str(tid) in squad_rosters else None,
            'coreStarters': len(cores),
            'injuries': injury[:20],
            'confirmedFormation': current.get('formation') if current else None,
            'lineupVerified': bool(current),
            'keyUnavailable': key_out,
            'keyBenched': key_bench,
            'withWithout': comparisons[:3],
        }
    return details
