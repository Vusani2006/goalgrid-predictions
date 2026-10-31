"""Conservative experimental forecast utilities; no fitted calibration claims.

All priors must be computed from actual observed games that occurred before
kickoff. A lack of historical data is a reason to abstain, not to invent data.
"""
import datetime as dt
import math

GOAL_MINIMUM = 6
CORNER_MINIMUM = 6
GOAL_MAXIMUM = 12
CORNER_MAXIMUM = 12
DECAY_HALF_LIFE_DAYS = 70


def weighted_rates(observations, target_time, minimum, maximum=12):
    """Newest-first, exponential recency weighting; n is still raw observations."""
    ordered = sorted(observations, key=lambda row: row[0], reverse=True)[:maximum]
    if len(ordered) < minimum:
        return None
    weights = []
    for when, scored, conceded in ordered:
        age_days = max(0., (target_time - when).total_seconds() / 86400.)
        weights.append(0.5 ** (age_days / DECAY_HALF_LIFE_DAYS))
    denom = sum(weights)
    if denom <= 0:
        return None
    return {'for': sum(w * row[1] for w, row in zip(weights, ordered)) / denom,
            'against': sum(w * row[2] for w, row in zip(weights, ordered)) / denom,
            'n': len(ordered), 'effectiveN': denom * denom / sum(w*w for w in weights),
            'mostRecent': ordered[0][0].isoformat()}


def league_baseline(fixtures, stat_getter=None, min_games=20):
    """Average home and away team counts, using complete measured games only."""
    pairs = []
    for f in fixtures:
        if stat_getter is None:
            g = f.get('goals') or {}
            x, y = g.get('home'), g.get('away')
        else:
            x, y = stat_getter(f)
        if isinstance(x, bool) or isinstance(y, bool):
            continue
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x >= 0 and y >= 0:
            pairs.append((float(x), float(y)))
    if len(pairs) < min_games:
        return None
    n=len(pairs)
    return {'home': sum(x for x,y in pairs)/n, 'away':sum(y for x,y in pairs)/n,
            'n': n, 'totals': [x+y for x,y in pairs]}


def shrink(value, baseline, sample, prior_matches=5):
    return (sample*value + prior_matches*baseline)/(sample+prior_matches)


def venue_strength_expectation(home, away, prior=None):
    """Estimate using observed attack and conceded values with partial pooling.

    A league-wide baseline prevents naively treating one team's unusually high
    scoring run as its permanent skill. No empirical accuracy is assumed.
    """
    if not prior or min(prior['home'],prior['away']) <= 0:
        return ((home['for']+away['against'])/2, (away['for']+home['against'])/2)
    hp=prior['home']; ap=prior['away']
    # Geometric pooling is less explosive than multiplying estimated attack and
    # defence ratios, especially on 6-12 fixture samples.
    h_attack=shrink(home['for'],hp,home['effectiveN'])
    a_conceded=shrink(away['against'],hp,away['effectiveN'])
    a_attack=shrink(away['for'],ap,away['effectiveN'])
    h_conceded=shrink(home['against'],ap,home['effectiveN'])
    return (min(4.,max(.08,math.sqrt(h_attack*a_conceded))),
            min(4.,max(.08,math.sqrt(a_attack*h_conceded))))


def overdispersed_tail(cutoff, mean, totals):
    """Neg-binomial tail for corners if overdispersion is supported by data.

    Otherwise use a Poisson tail. A fitted dispersion parameter from <20
    observations is too fragile, so callers must supply >=20 real totals.
    """
    poisson = 1 - sum(math.exp(-mean) * mean**k/math.factorial(k) for k in range(cutoff))
    if len(totals) < 20 or mean <= 0:
        return max(0., min(1., poisson))
    avg=sum(totals)/len(totals)
    variance=sum((x-avg)**2 for x in totals)/(len(totals)-1)
    if variance <= avg * 1.10:
        return max(0., min(1., poisson))
    # Pool heavy-tail dispersion with the Poisson limit: suppress instability.
    raw_r = (avg*avg)/(variance-avg)
    r = max(2.0, min(60.0, raw_r*1.5))
    p = r/(r+mean)
    current = p**r
    cumulative = current
    for k in range(1,cutoff):
        current *= (k-1+r)/k*(1-p)
        cumulative += current
    return max(0., min(1., 1-cumulative))


def careful_probability(model_probability, base_probability, sample_home, sample_away):
    """Shrink toward observed league base rate until the team sample expands.

    This is a *heuristic* to reduce overconfident-looking forecasts. It must
    be validated, then replaced/tuned using time-ordered historical results.
    """
    n = min(sample_home, sample_away)
    contribution = max(.25, min(.85, (n-2)/12))
    return max(.01, min(.99, contribution*model_probability + (1-contribution)*base_probability))
