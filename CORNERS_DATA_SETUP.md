# First-half and full-time corners — real data only

The website supports all requested markets: 1X2, Over 2.5 goals, first-half Over 3.5/4.5 corners, and full-time Over 8.5/9.5/10.5 corners.

**Important:** football-data.org v4 fixture/results endpoints do **not** supply the needed first-half/full-time corner statistics. This package does not invent them. The corners markets will show no picks until `corners_history.csv` contains enough real records.

## How to enable corners

Populate `corners_history.csv` with legitimately sourced match-level observations, one row per finished match. Fields:

`fixture_id,utc_date,home_team_id,away_team_id,ft_home,ft_away,h1_home,h1_away,source_url`

- `fixture_id`, `home_team_id`, `away_team_id`: **football-data.org** IDs, not another provider's IDs.
- `utc_date`: ISO timestamp, for example `2026-10-01T19:00:00Z`.
- `ft_home`, `ft_away`: actual full-time corners won by each team.
- `h1_home`, `h1_away`: actual first-half corners won by each team.
- `source_url`: HTTPS link documenting the observations.
- Leave missing half-time or full-time values blank; never fill them with estimates.

The model requires at least 30 completed matches with the relevant corner field in a competition, and at least five matching home-venue and away-venue team observations. It uses a simple Poisson approximation and **is not calibrated**. Matches must appear in the current competition fixture feed to count. Historical fixtures beyond the current feed may require a separate verified data ingestion integration.

The automated GitHub Action reads the CSV from your repository each day; it does **not** scrape or fetch corner statistics automatically. Only add observations you have rights to use. For settlement, include corner observations for completed forecast fixtures, too.

No corner picks is the correct result when observations are unavailable. Do not advertise corners as live automated data until a legitimate provider is connected.
