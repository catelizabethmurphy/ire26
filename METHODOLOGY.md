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
- `rotowire_subscription_data_downloader.py` — the paid RotoWire feed, which has
  historical line movement. This is the only scraper that logs in; it reads my
  username and password from a `.env` file, never from the code itself.
- `draftkings_scraper.py` and `draftkings_props_by_game_scraper.py` — DraftKings'
  live player props, one sorted by top props and one walked game by game.
- `bettingpros_scraper.py` — BettingPros, which is useful because it carries both
  opening lines and current odds across a lot of books at once.
- `march_madness_box_scores_scraper.py` — the actual box scores, so I can see
  what each player really did and compare it to the line.
- `roster_scraper.py` — team rosters, which I use as a lookup to attach a player
  to a team when a props feed only gives me a name.

## How I ran them (GitHub Actions)

Lines move all day, so scraping once wasn't enough — I needed snapshots from
morning through tip‑off to see how the market shifted. Doing that by hand every
day for three weeks wasn't realistic, so I automated it with GitHub Actions.

The setup was a set of scheduled workflows, one per source. Each one is a cron
job that fires several times a day, spins up a fresh Ubuntu machine on GitHub's
side, installs Chrome and my Python dependencies, runs the scraper, and then
commits the new data file straight back into the repo with a timestamp. I also
left a manual trigger on each so I could kick one off whenever I needed to.

I used Actions specifically for a few reasons. It's free for public repos and
there's no server for me to babysit. Committing the output back into the repo
meant my data history was version‑controlled and sat right next to the code that
produced it, so every scrape was dated and I never had to think about where
files were going. And because each run was its own commit, I ended up with a
built‑in record of line movement over time without doing anything extra.

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

A couple of the feeds store each sportsbook in its own column, so I pivot those
into one row per book before combining. Then I stack all the sources together
and dedupe on a `prop_id` I build from the player, book, market, seeds, teams,
and date. The same prop scraped off three different sites collapses to one row,
but I keep a count of how many sources saw it (`number_times_identified`) and the
list of which ones (`data_source`), so I can always trace a line back to where it
came from. The cleaned result for the sample game is in
`data/sample/cleaned_props_duke_siena.csv`.

## Box scores

The box score scraper gives me each player's real minutes and stats. Joined onto
the props table, that's what lets me ask whether a player went over or under, and
whether a line was set anywhere near reality. The sample includes
`player_minutes`, which on its own already flags props posted on players who
barely got off the bench.

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
