# Apes Nation Football Prediction — Free + VIP Premium (R150/month)

**Version:** public predictions + an optional private-membership backend.

- **Free:** public research and daily forecasts for up to seven leagues: Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Primeira Liga and South African PSL.
- **VIP Premium:** **R150/month**, showing an optional member registration/sign-in form and a **database-authorized private research board**. The private board is empty until the API publisher is connected and picks meet its data thresholds.
- **Five markets:** over 2.5 goals; full-time corners over 8.5; first-half corners over 3.5; full-time result 1X2; and a model for who *ever takes a two-goal lead* (which is not the same as every bookmaker's “2UP” early payout promotion).
- **Critical status:** The website is **not yet deployed**; automated publishing requires credentials, GitHub Actions and Netlify; **payment checkout is NOT connected**; no members have been charged or activated. Price advertised ≠ working checkout.

## Setup checklist

For iPhone-specific instructions start with **START_HERE_IPHONE.txt**. For production setup:

### 1. Upload website and connect Netlify (recommended for paid VIP service)

Upload extracted files to the root of the GitHub repository, including the **hidden** `.github/workflows/publish-predictions.yml` and new `netlify.toml` and `build_site.sh`. Do **not** upload just the ZIP. Keep API and database secrets out of public files.

Create a free Netlify account and choose **Add new project → Import an existing project → GitHub**. Select `Vusani2006/goalgrid-predictions`. Netlify will read `netlify.toml` and run `bash build_site.sh`, publishing only `dist/` (the public HTML/CSS/JS assets). Make sure deploys are enabled for pushes to the default `main` branch. It will first publish an empty, honest predictions board until the data updater succeeds. Free Netlify credits have usage limits. GitHub Pages is **not** suitable as the paid VIP business host under GitHub's commercial-use restrictions.

### 2. Connect API-Football daily forecasting

Set the GitHub Actions repository secret `API_SPORTS_KEY` to your API-Football key (GitHub: **Settings → Secrets and variables → Actions → New repository secret**). In GitHub **Actions**, run the **Generate daily Apes Nation football predictions** workflow once by hand. The automation cron is **05:17 UTC / approximately 07:17 SAST** daily, subject to delays or disabled scheduled runs. The script saves predictions to `data.js` and GitHub; connected Netlify normally auto-deploys on pushes. Verify BOTH GitHub Action success AND Netlify's actual deploy log/live website before relying on automatic posting. Your GitHub workflow permission must allow writing repository contents.

API-Football Free was advertised at **100 requests/day** in October 2026; this script caps at 85 calls per run. Data coverage and free-season access vary. The model declines unsupported markets instead of making up statistics; **no qualifying fixtures = no new tips**. These estimates are experimental and have NOT been validated with live match data using your account.

The public board reads `data.js`. Its prediction settlement history is stored in `history.json`. Do NOT paste VIP picks into these publicly accessible files.

### 3. Enable secure VIP sign-in (Supabase)

A static website cannot secure premium content by hiding cards or adding an HTML password. This project implements an **optional private backend with Supabase Auth and row-level security (RLS)**. You need a Supabase project and a few configuration steps:

1. Register at https://supabase.com and create a project.
2. Open Supabase → SQL Editor, paste `supabase.sql` and run it. This creates `vip_memberships` and `vip_predictions`, with RLS that permits VIP research access only for authenticated, active, nonexpired subscribers.
3. Copy your project URL and **public anon/publishable key** from Supabase's project settings. Set `supabaseUrl` and `supabaseAnonKey` in `config.js`. These *public client credentials* may be in the repo because access is enforced by RLS. **Never place a `service_role` key here.**
4. In Supabase Auth → URL Configuration, set your website's correct URL and allow that URL for email confirmation redirects. Email/password auth needs confirmation depending on Supabase project settings. Test signup, confirmation, login, logout, denied unauthorized access and expired subscriptions.
5. To let the daily GitHub Action **privately publish** extra predictions, create two more **GitHub Actions repository secrets**: `SUPABASE_URL` (project URL) and `SUPABASE_SERVICE_ROLE_KEY` (private backend secret). Never post the latter in the repo, screenshot or support chat.
6. The scheduled Python updater will then reserve **up to one additional selection per match with at least two supported tips, provided that selection passes the stricter sample and model-estimate gates**, save it **only** to Supabase, and save remaining picks publicly. New picks are chosen from actual supported statistical input. Unsupported markets may be absent. Previously published free picks stay free.
7. It will also attempt to settle private predictions with verified match and goal-event data. Some selections remain pending if the provider cannot verify results.

**Important:** No VIP picks are embedded in HTML, JavaScript, public `data.js`, `history.json` or published GitHub commits. The service-role key belongs only in GitHub Secrets; the browser fetches the private table through Supabase using each member's session, and Supabase RLS decides access.


### Owner account — permanent free VIP access (one account only)

The site-owner account has **permanent, complimentary VIP access**. This entitlement is **not a free trial** and never expires; visitors and other accounts cannot grant it to themselves. The database enforces a single owner using a singleton `site_owner` table. Public users can only read whether their own authenticated UUID matches the owner; updates are restricted to trusted administration. The RLS policy for private picks permits **either** the owner **or** a paid member with a verified, nonexpired active membership.

1. **First** run the current `supabase.sql` in Supabase SQL Editor. It safely creates the owner table and policies in addition to regular memberships.
2. Configure Supabase Auth on the site; register and verify **your personal owner account**.
3. In Supabase dashboard go to **Authentication → Users** and copy the UUID belonging to **your actual account**, not a GitHub username and not a visitor's email.
4. Run the **commented OWNER SETUP SQL command at the end of `supabase.sql`**, replacing `REPLACE_WITH_YOUR_OWN_SUPABASE_AUTH_USER_UUID` with your UUID. This is a trusted dashboard operation; **never** put that UUID/SQL grant command in the website source or offer it to visitors.
5. Sign in on the site with your owner account. It should display **APES NATION OWNER — permanent complimentary VIP access** and show protected picks if any exist. Verify an ordinary new test account cannot read the protected table.

**Security note:** An email address, a client-side flag, or the label "owner" is not permission to see premium data; Supabase verifies the authenticated ID and RLS controls the actual database access. Your account still needs strong login credentials. Only you can obtain this free-owner privilege by assigning your actual UUID in the dashboard; other members still need verified R150/month payments after checkout is implemented.

### 4. Membership and payment — still a required integration

The VIP **price is R150/month**. This package has **no live pay button** and cannot automatically collect payment, activate subscriptions, cancel payments, or process recurring renewals. Connecting login alone does **not** enable paid checkout.

A suggested South African payment provider is [Payfast](https://payfast.io/). Its dashboard supports a **Subscribe Now** button for a recurring monthly amount, and custom integrations support transaction notifications (ITN). Before asking anybody to pay, use a backend payment handler to **verify** payment notifications (including signature, origin, paid amount, merchant account, uniqueness and status), correctly link the payment to a member account, grant a time-limited entitlement, renew on successful recurrent charges and revoke access for cancellation/nonpayment/refund. **Do not grant access on a return-URL visit, a screenshot, or a form submission.** Manual confirmation and activation is an interim admin process only; it is not a replacement for automated subscription reconciliation.

The SQL file includes an explicitly marked **manual test/admin activation** command for a verified UUID. **Do not test with a real paid customer unless you have a clear way to collect, cancel and refund payments and meet applicable requirements.** Test manually without real money first.

### 5. Feature verification

- Public site renders from `index.html` and shows Free R0, VIP R150/month.
- When `config.js` is blank, no broken fake login is shown; it clearly instructs the owner to finish setup.
- Once Supabase is configured, a user can sign up, verify email and sign in. **Authenticated alone ≠ VIP.**
- `vip_memberships` permits a user to view **only their own** status; users cannot self-activate. `site_owner` is similarly read-only for the matching owner, with at most one owner allowed.
- `vip_predictions` is readable **only** to the singleton site owner OR to a user with an active, future-dated membership. Clients have no public insert/update/delete permission.
- GitHub Action gets its private API credentials from repository Secrets. `.github/workflows/publish-predictions.yml` must be uploaded or the schedule won't exist. Confirm the Netlify project is connected to the correct repo and branch.
- No automatic billing or subscription management code is included. Do not market checkout as active.

### 6. Test models locally (developer)

Run `python3 -m unittest -v test_auto_predict.py` in the project folder. The publisher runs in Python 3.11+:

```sh
API_SPORTS_KEY=*** python3 auto_predict.py
```

Without `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`, all valid published picks remain on the Free board; VIP predictions are not generated privately until the database is connected. With both secrets set, eligible selections are split between public and protected storage. API quota still applies. The upload script does not call APIs unless run with valid credentials.

## Data and risk limitations

The model uses recency-weighted venue-specific league match scores and historical corners, only when observations are supplied. At least six prior home and six away league matches, plus at least twenty historical league fixtures with complete observations, are required per market. It uses league-relative empirical shrinkage, goal Poisson assumptions and a provisional overdispersion adjustment for corners; percentages are experimental and **not externally calibrated/backtested**. Squad research now checks provider-reported unavailability, confirmed lineup information where available, historical starting-XI samples, and descriptive playing-style measures (shots, possession, corners). Confirmed lineup and roster data may be unavailable, especially on the free API plan. Absences can trigger abstention from 1X2/2UP or from all markets; the code does not apply unvalidated numerical player-effect multipliers. Historical with/without averages are descriptive correlations, not proof of player impact. A single 07:17 morning run will usually happen before starting lineups are published; obtaining reliable near-kickoff XI checks requires an additional manually triggered run or better data/automation quota. First-half corners are skipped unless the provider clearly identifies the first-half values; never assume full-time corner data is the first-half figure. Missing event timelines leave ambiguous 2UP outcomes pending. A private VIP prediction is not inherently more likely to win than a public one.

This service is football analysis, not guaranteed winnings or financial advice. Label all gambling-related content accurately and check South African law, consumer requirements and payment provider policies before launch. Never bet money you can't afford to lose. 18+.


## New: model-quality upgrade (experimental, not proven more accurate)

**This version replaces the previous four-match, naive averaging calculator.** The changes aim to reduce fragile or overconfident-looking predictions. There is **no factual basis yet to claim an increase in real prediction accuracy**. The API key was not available during development, so live-league data were not tested.

- The most recent twelve league matches at the correct venue are sorted by **actual kickoff**, not by API response order. Historical observations are recency-weighted with a 70-day half-life.
- At least **six observed home games and six observed away games** are needed for a market. A league reference requires at least **twenty observed completed fixtures**. No reference, no pick.
- Observed attack/defence values are pulled toward the measured league scoring/corner baseline rather than treating a small hot streak as permanent. These shrinkage weights are experimental until tuned with a genuine out-of-sample dataset.
- Goal score/2UP models still use simplified independent-Poisson assumptions. Corners use a cautious negative-binomial tail only if measured league overdispersion supports it. Do not call any of these numbers calibrated probabilities.
- Selection cutoffs have been raised; having **no predictions** on a day is acceptable and more honest than inventing low-data recommendations.
- Only one extra VIP pick per match is considered **if** there are at least two supported picks, the VIP candidate has at least eight prior games per venue, and its *experimental model estimate* is at least 67%. A high number does not prove real skill.
- `archive_history.json` accumulates real completed fixtures as the daily updater runs. `backtest.py` creates `backtest_data.js` after each successful update with a strictly chronological walk-forward **historical simulation**, not an actual published-picks record. The website shows historical scores only after 50 settled simulated selections **per market**. It excludes 2UP without an authenticated goal-event timeline. A model may fail testing and need further tuning.
- You can reproduce the tests on a laptop with `python -m unittest -v test_auto_predict.py`, and run a local archived-data evaluation using `python backtest.py`. The automated GitHub workflow runs both the updater and archived evaluation daily, then commits their outputs.

**Recommended before accepting paying VIP customers:** Collect at least 100 real, *timestamped, previously published* predictions **per market**, settle each accurately, compare success to stated probabilities and ideally a league-specific baseline. Report performance separately for Premier League, La Liga, Serie A, Bundesliga, Ligue 1, Primeira Liga and PSL whenever sample size permits. Revisit model thresholds only on older training matches, then validate on newer holdout matches. Be clear that high hit rate does not imply positive betting returns without odds and fees.


## Brand and repository name
The **public website name is now Apes Nation Football Prediction**. You can keep your existing GitHub repository URL `https://github.com/Vusani2006/goalgrid-predictions`; the repository does **not** have to be renamed for this website to work. Internal variables named `GOALGRID_*` remain unchanged for compatibility; visitors see the new name.



## Hosting note
For a R150/month VIP subscription business, Netlify is the recommended host and GitHub is used only for code + scheduled data updates. GitHub Pages disallows hosting an online business as a free Pages website. See: https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits. The production website should NOT use GitHub Pages.
