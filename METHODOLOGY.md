# Methodology

This repo holds the code I used to collect and clean the college basketball
player prop‑betting data behind my March Madness reporting, plus one sample game
so you can see what the data actually looks like. This file is a tour of what's
in here and what each piece does.

First, what a "prop" is, since everything revolves around it. A player prop is a
bet on one player's stat line instead of on who wins the game. "Cameron Boozer
over 22.5 points" is a prop. Sportsbooks and daily‑fantasy apps put up dozens of
them per game, and during the tournament that became a flood of bets on the
names of mostly teenage and early‑twenties players. That's what I set out to
measure, and none of it is something you can just download. I had to scrape it
from several sites that all describe the same players, teams, and bets
differently, and then reconcile them.

## What's in the repo

- `scrapers/` — one Python script per site I pulled from.
- `analysis/props.Rmd` — the R notebook that cleans every source and merges them
  into a single table. This is where most of the real work lives.
- `analysis/eligibility.Rmd` — a separate, smaller analysis of who can legally
  place these bets, by state and age.
- `data/sample/` — a single game (Duke vs. Siena) carried from raw scraper output
  through to the cleaned, merged result, so the pipeline is concrete.
- `data/eligibility/` — the small public tables the eligibility notebook uses.
- `config/`, `pyproject.toml`, `.env.example` — setup.

I left the full scraped dataset out on purpose. It's large, a chunk of it came
from a paid subscription I can't redistribute, and the harassment side of the
project involved social‑media comments with real people's names in them. None of
that belongs in a public demo. See the last section for more.

## The scrapers

Everything in `scrapers/` is a Python script driving Selenium with headless
Chrome. I went with Selenium because these are all heavy JavaScript pages —
lines load in after the page does, there are cookie banners to dismiss, content
that only appears when you scroll, and so on. A plain `requests` grab gets you
almost nothing. The scripts handle the cookie dialogs and lazy loading and retry
when a page doesn't cooperate.

What each one pulls:

- `espn_schedule_scraper.py` — the tournament schedule from ESPN: matchups,
  seeds, regions, rounds, tip times, and the point spread. This is the backbone
  everything else hangs off of.
- `rotowire_public_data_scraper.py` — RotoWire's public props page, which
  aggregates lines across several books.
- `rotowire_subscription_data_downloader.py` — the paid RotoWire feed. It's the
  one source I had that carries historical line movement, meaning how a line
  opened and moved over the hours before a game, which none of the public sites
  expose. It's also the only scraper that logs in; it reads my username and
  password from a `.env` file, never from the code itself.
- `draftkings_scraper.py` and `draftkings_props_by_game_scraper.py` — DraftKings'
  live player props, one sorted by top props and one walked game by game.
- `bettingpros_scraper.py` — BettingPros, which is useful because it carries both
  opening lines and current odds across a lot of books at once.
- `march_madness_box_scores_scraper.py` — the actual box scores, so I can see
  what each player really did and compare it to the line.
- `roster_scraper.py` — team rosters pulled from each school's official athletics
  site. Along with player names, it grabs the social media handles linked on each
  player's roster profile (Instagram, X, TikTok, Facebook). I used it two ways,
  both explained further down: as a player‑to‑team lookup for the betting data,
  and as the first step in the harassment reporting.

## How I ran them (GitHub Actions)

I scraped several times a day because of how these markets behave. Books post
props as they create them, on their own schedule, and then take them down once a
game tips off, sometimes earlier. A prop I didn't catch before it came down was
simply gone. Running through the day was how I tried to grab each line during the
window it actually existed. Doing that by hand every day for three weeks wasn't
realistic, so I automated it with GitHub Actions.

The setup was a set of scheduled workflows, one per source. Each one is a cron
job that fires several times a day, spins up a fresh Ubuntu machine on GitHub's
side, installs Chrome and my Python dependencies, runs the scraper, and then
commits the new data file straight back into the repo with a timestamp. I also
left a manual trigger on each so I could kick one off whenever I needed to.

I used Actions specifically for a few reasons. It's free for public repos and
there's no server for me to babysit. Committing the output back into the repo
meant my data history was version‑controlled and sat right next to the code that
produced it, so every scrape was dated and timestamped and I never had to think
about where files were going.

I've kept the actual workflow files out of this demo repo, but that's the whole
idea: scheduled jobs that scrape on a timer and commit the results back.

## The cleaning problem

The reason this project is mostly a cleaning project: every site names things
differently. ESPN's spread data calls UConn `CONN`, RotoWire calls it
`Connecticut`, and the bracket calls it `UConn`. One book lists a market as
`Reb+Ast`, another as `Rebounds + Assists`. A player shows up as `A.J. Dybantsa`
in one place and `AJ Dybantsa` in another. Until all of that agrees, nothing
lines up and nothing joins.

`props.Rmd` handles this up front with a set of small functions that I run over
every source before I try to combine anything:

- `standardize_team_names()` and `match_school_abbreviations()` map every team
  variant and every ESPN abbreviation to one canonical name. These are long,
  explicit lists on purpose — each rule is something an editor or fact‑checker
  can read and check.
- `standardize_player_names()` strips suffixes like `Jr.` and `III`, removes
  accents and quoted nicknames, and patches the handful of known name mismatches
  by hand (a player listed as `Solomon Ball` on one site and `Solo Ball` on
  another, for example).
- `standardize_market_name()` collapses all the different ways books write a bet
  type into one vocabulary (`pts` becomes `points`, `3pt made` becomes
  `three_pointers_made`, and so on).
- `classify_platform_type()` tags each operator as a sportsbook, a daily‑fantasy
  app, or other. This one matters a lot, because the split between regulated
  sportsbooks and DFS apps is central to the reporting.
- `missing_game_info()` is a small, dated lookup that fills in the matchup for
  the few rows where a source dropped it. I'd rather correct those in code, where
  the fix is documented and visible, than quietly edit a spreadsheet.

## Merging it into one table

The goal is a single tidy table where one row is one prop line from one operator.

The key that ties a prop to a game is a sorted team pairing:

```r
game = paste(pmin(team_a, team_b), "vs.", pmax(team_a, team_b))
```

Sorting the two teams alphabetically means `Duke @ Siena` and `Siena vs. Duke`
both come out as `"Duke vs. Siena"` no matter the home/away order or which scrape
they came from. With that key in place, each props source gets joined to the
ESPN schedule (for seeds, region, round, and the spread), to the rosters (to
attach a player to a team), and to the box scores (for what actually happened).

The roster join is there for a specific reason. The RotoWire feeds already told
me each player's team and opponent, so they dropped into a game on their own. But
DraftKings and BettingPros only gave me a player's name and the bet, not the
team. Since a game is keyed on its pair of teams, a name with no team can't be
placed in a game, which means no seed, no spread, no round, and no way to line it
up against the box score. The roster table is the bridge: look up the name, get
the team, and now the player belongs to a game.

A couple of the feeds store each sportsbook in its own column, so I pivot those
into one row per book before combining. Then I stack all the sources together
and dedupe on a `prop_id` I build from the player, book, market, seeds, teams,
and date. The same prop scraped off three different sites collapses to one row,
but I keep a count of how many sources saw it (`number_times_identified`) and the
list of which ones (`data_source`), so I can always trace a line back to where it
came from. The cleaned result for the sample game is in
`data/sample/cleaned_props_duke_siena.csv`.

## The columns, and the ones I dropped

The cleaned table is deliberately narrow. Each row carries the game context
(tournament, round, the `game` key, date, both teams and their seeds, the point
spread, and which side was favored), the player, the bet (the book as
`prop_platform`, whether it's a sportsbook or DFS app as `prop_platform_type`,
the market, and the line), the provenance fields (`prop_id`,
`number_times_identified`, `data_source`, `file_date`), and `player_minutes` from
the box score.

That's a choice, and it leaves a fair amount on the cutting room floor. The
sources carried more than I kept, and it's worth knowing it exists:

- **The odds on each prop.** DraftKings and BettingPros gave me the price (the
  juice, like ‑115) next to each line, but I only kept the line itself. So I have
  the number a book set without how it was priced.
- **The game total.** I kept each game's point spread but dropped the over/under
  on the game itself, which ESPN had right there.
- **The full box‑score stat line** (see below) — I carried only minutes.
- **Player position**, which BettingPros and the RotoWire feed both had.
- **An "average line variance" figure** from the paid RotoWire feed, which is its
  own measure of how much books disagreed on a line, plus the whole line‑movement
  history that feed carries (opening line, previous line, the size of each move).
- **Internal IDs and profile URLs** (ESPN game IDs, player IDs, roster bio links)
  that were only ever plumbing.

## Box scores

`march_madness_box_scores_scraper.py` is the one collector that isn't a browser
scrape. It calls ESPN's public game‑summary API by game ID and pulls the full box
score for each tournament game: every player's minutes, points, rebounds
(offensive and defensive), assists, steals, blocks, turnovers, fouls, and full
shooting splits (field goals, threes, and free throws made and attempted), plus
jersey number.

Here's an honest gap. When I merged the box scores into the props table I only
carried `player_minutes` through. Minutes alone is already useful — it flags
props posted on players who barely got off the bench — but the rest of the stat
line is sitting right there in the scraped data. That's exactly what you'd join
in to grade every prop against what the player actually did, over or under. It's
the first thing in the "what I'd do differently" section at the end.

## The eligibility analysis

`eligibility.Rmd` is a separate, smaller piece. It joins a table I built of state
rules — which operators are legal where, and the minimum betting age — against
Census population estimates by age (pulled through the `tidycensus` API). The
output estimates how many people in each state can legally place these bets, and
by extension how many are reached by DFS apps in places where they'd be too young
or where sportsbooks aren't legal at all. It's a way to put a number on the legal
gray area these apps operate in.

## The sample game

`data/sample/` is one first‑round game, Duke vs. Siena, a 1‑seed against a
16‑seed. I picked a blowout on purpose: even a game decided by 27 points was
loaded with props, which is part of the point. The folder has the raw output from
each public source in its own original format alongside the cleaned, merged
version, so you can pick a player and follow them from the messy inputs through to
the final row. There's a README in that folder walking through it.

## The social handles and the harassment reporting

The roster scraper does double duty, and the second job is the harassment side of
this project.

`roster_scraper.py` works off `team_roster_links.csv`, which is just each
tournament team paired with the URL of its official men's basketball roster page.
The scraper visits each of those pages — they mostly run on a handful of common
platforms like Sidearm Sports and WordPress — and for every player it pulls the
name plus whatever social accounts the school linked on that player's profile. In
practice that's the Instagram, X, TikTok, and Facebook handles a program puts on
its own roster page, so these are the players' real, school‑listed accounts
rather than anything I had to guess at.

I needed those handles to report on the abuse players were getting. The Instagram
handle is what let me find a player's account and their posts, and the comments on
those posts are where the harassment lived. So the chain runs handle → the
player's posts → the comments on them, which is how a given comment gets tied back
to the specific player it was aimed at. The comment data itself isn't in this
repo, for the privacy reasons below, but the handle collection here is the first
link in that chain.

## What the data misses (it's an undercount)

I want to be straight about coverage: this is not every prop that was offered.
It's a floor, and it undercounts, for two reasons.

First, the takedowns. Books pull props once a game starts, so anything posted and
removed between two of my scrapes, or only put up after my last run before
tip‑off, never got captured. The scraping window and the betting window didn't
line up perfectly, and the gap is lost props.

Second, uneven coverage across sites. The sources don't all carry the same
markets. BettingPros, for one, only posted lines for points and rebounds, so for
any book I could only see through BettingPros, anything beyond points and
rebounds was invisible to me. And some apps simply offered far more than I could
keep up with — Fliff alone had a huge number of props I had no realistic way to
track in full. So where a market existed on a site I wasn't capturing directly,
it's just not in here.

Treat the counts as a minimum, not a complete tally.

## What I left out, and why

- I'm not republishing the paid RotoWire feed. The code that pulls it is here;
  the bulk data isn't.
- There's no social‑media comment data in this repo. The harassment reporting
  used comments that contain real usernames and real names, and that's not
  something to post publicly. If you do similar work, be careful with commenter
  and victim data and publish as little of it as you can.
- I'm not shipping the full scraped corpus. It's big and you don't need it to
  understand how any of this works.
- Credentials live in a `.env` file that's never committed. Use `.env.example`
  as the template.

One real caveat: matching on names is imperfect. Common names can collide, which
is why I lean on the rosters to disambiguate, but it still needs spot‑checking.
And before you scrape any of these sites yourself, read their terms of service.

## What I'd do differently next time

A few things I'd change if I ran this again:

- **Join the whole box‑score line, not just minutes.** I scraped every player's
  full stat line and then only used minutes. Pulling points, rebounds, assists,
  and the rest into the table would let me grade every prop against the real
  result automatically, which is the obvious next step and the one I most regret
  leaving undone.
- **Keep the odds, not just the line.** Capturing the price on each prop would let
  me see how a book juiced a given over/under, not only where it set the number.
- **Scrape more often and closer to tip‑off.** Props get pulled when a game
  starts, and my fixed schedule left gaps. Tightening the cadence near tip, or
  triggering off the schedule instead of a fixed clock, would catch more lines
  before they vanish.
- **Go after the DFS apps directly.** Reaching some books only through an
  aggregator capped me at points and rebounds and meant apps like Fliff were badly
  undercounted. Scraping those apps on their own would close most of the coverage
  gap.
- **Keep the game total** alongside the spread, since ESPN already had it.
- **Lean less on names for identity.** Where the sources expose stable player IDs,
  using those instead of name matching would cut down on collisions between
  players with common names.
