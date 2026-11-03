"""Optional corners forecasts based ONLY on real match-level corner observations.

CSV fields: fixture_id,utc_date,home_team_id,away_team_id,ft_home,ft_away,h1_home,h1_away,source_url
IDs must match football-data.org team and fixture IDs. No synthetic corners.
"""
import csv
import datetime as dt
import math

MIN_TEAM = 5
MIN_LEAGUE = 30

def load_corner_csv(path):
    if not path.exists():
        return {}
    output = {}
    with path.open(encoding='utf-8-sig', newline='') as fh:
        for row in csv.DictReader(fh):
            try:
                fixture_id = str(int(row['fixture_id']))
                date = dt.datetime.fromisoformat(row['utc_date'].replace('Z', '+00:00'))
                if date.tzinfo is None:
                    continue
                h, a = int(row['home_team_id']), int(row['away_team_id'])
                if not row.get('source_url','').startswith('https://'):
                    continue
                values = {}
                for prefix in ('ft', 'h1'):
                    fields = (row.get(prefix+'_home',''), row.get(prefix+'_away',''))
                    if all(str(v).strip() for v in fields):
                        x, y = (int(v) for v in fields)
                        if x < 0 or y < 0 or x > 40 or y > 40:
                            raise ValueError('Invalid corners')
                        values[prefix+'_total'] = x+y
                if not values:
                    continue
                output[fixture_id] = dict(date=date, home=h, away=a, source=row['source_url'], **values)
            except (ValueError, TypeError, KeyError):
                continue
    return output

def poisson_over(mean, threshold):
    cutoff = math.floor(threshold)
    return 1 - math.exp(-mean) * sum(mean**k/math.factorial(k) for k in range(cutoff+1))

def forecast_corners(match, league, records, now, kickoff, team_id, team_name):
    when = kickoff(match)
    if when is None or when < now or when > now+dt.timedelta(days=7):
        return []
    if match.get('status') not in ('SCHEDULED','TIMED'):
        return []
    home, away = team_id(match,'home'), team_id(match,'away')
    if home is None or away is None:
        return []
    # Restrict history to the same competition via explicit fixture IDs provided
    # in the feed's current league; no unrelated competitions are mixed.
    league_ids = match.get('_corner_league_ids')
    if not league_ids:
        return []
    past = [r for fid,r in records.items() if fid in league_ids and r['date'] < when]
    out=[]
    for field, market, thresholds in [('h1_total','corners1H',(3.5,4.5)),('ft_total','cornersFT',(8.5,9.5,10.5))]:
        sample = [r for r in past if field in r]
        home_rows=[r for r in sample if r['home']==home]
        away_rows=[r for r in sample if r['away']==away]
        if len(sample)<MIN_LEAGUE or len(home_rows)<MIN_TEAM or len(away_rows)<MIN_TEAM:
            continue
        mean=(sum(r[field] for r in home_rows)/len(home_rows) + sum(r[field] for r in away_rows)/len(away_rows))/2
        # Shrink venue estimate toward observed league mean.
        league_mean=sum(r[field] for r in sample)/len(sample)
        mean=0.7*mean+0.3*league_mean
        for threshold in thresholds:
            probability=poisson_over(mean,threshold)
            if probability < 0.60:
                continue
            label='FIRST-HALF CORNERS' if market=='corners1H' else 'FULL-TIME CORNERS'
            out.append({
                'id':f'FDORG-{match["id"]}-{market}-{str(threshold).replace(".", "_")}',
                'fixtureId':match['id'],'league':league,
                'home':team_name(match,'home'),'away':team_name(match,'away'),
                'kickoff':when.isoformat().replace('+00:00','Z'),
                'marketType':market,'market':label,'threshold':threshold,
                'tip':f'Over {threshold} corners','confidence':round(probability*100),
                'projectedTotal':round(mean,2),'status':'pending',
                'reason':f'Experimental corner-count model using observed match-level {"first-half" if market=="corners1H" else "full-time"} corners; not a validated probability.',
                'research':{'sampleHome':len(home_rows),'sampleAway':len(away_rows),'checkedAt':now.isoformat(),
                            'dataQuality':f'{len(sample)} historical matches with recorded corners for this competition; Poisson approximation.',
                            'note':'Requires independently verified corner statistics. Missing data produces no prediction. No guarantee of accuracy.',
                            'sources':list(dict.fromkeys(r['source'] for r in (home_rows+away_rows)))[:4]}
            })
    return out
