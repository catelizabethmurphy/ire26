# Methodology

This repo holds the code I used to collect and clean the college basketball player prop‑betting data behind my March Madness reporting, plus one sample game so you can see what the data actually looks like. This file is the prose companion to [`sample_analysis/sample_analysis.Rmd`](sample_analysis/sample_analysis.Rmd), the notebook that walks the loading‑and‑cleaning pipeline step by step and runs end‑to‑end on the sample.

First, what a "prop" is, since everything revolves around it. A player prop is a bet on one player's stat line instead of on who wins the game. "Cameron Boozer over 22.5 points" is a prop. Sportsbooks and daily‑fantasy apps put up dozens of them per game and during the tournament that became a flood of bets on the names of mostly teenage and early‑twenties players. That's what I set out to measure and none of it is something you can just download. I had to scrape it from sites that all describe the same players, teams and bets differently and then reconcile them.

## A note on scope for this public version

The full reporting pulled prop lines from several sources. **To keep this public version clean, auditable and reproducible, the prop data here comes from one provider: RotoWire** — but from *both* its feeds, the free public page and the paid subscription feed. Using two feeds is deliberate: the same bet shows up in both, spelled two different ways, so it's the clearest way to show what the standardization step is actually for. The one supporting source the cleaning step needs is **ESPN's schedule** — for the seeds, round, location and which team was favored, context the RotoWire data doesn't carry. The broader reporting also leaned on team rosters (the player‑to‑team bridge and the social handles) and ESPN box scores (what each player actually did), but those aren't part of this minimal sample.

That single‑source choice is a simplification, not a limitation of the method. The pipeline — scrape a JavaScript‑heavy site, standardize its names/teams/markets and join everything on a shared key — is **not specific to RotoWire**. It's exactly what you'd reuse to fold in DraftKings, BettingPros, PrizePicks, or any other book. RotoWire is just the worked example.

## What's in the repo

-   `sample_analysis/sample_analysis.Rmd` — the loading-and-cleaning notebook. To keep the demonstration simple it sticks to the basics: the prop data itself (RotoWire's public and paid feeds) plus the ESPN schedule needed to place each prop in a game, reconciled and standardized into one tidy row-per-prop table. It runs top to bottom on the sample game with no credentials or network. That clean table is the join point for everything else in the project — roster data, box scores, Census/eligibility tables, state legislative rules, the harassment data — but those merges live in the reporting, not in this notebook.
-   `sample_analysis/sample_data/` — the single game (Duke vs. Siena): the raw RotoWire public and paid feeds and the ESPN schedule, alongside the cleaned, merged result, so the pipeline is concrete.
-   `scrapers/` — the Python scrapers behind this sample: RotoWire public, RotoWire subscription, and ESPN schedules.
-   `index.html`, `main.js`, `styles.css` — the IRE session resource page that presents the findings.
-   `pyproject.toml` / `uv.lock`, `config/`, `.env.example` — setup and dependencies, explained just below.

I left the full scraped dataset out on purpose: it's large and this repo is meant to show the method, not host the archive. The single sample game runs everything end‑to‑end. See the last section for more.

## A note on AI assistance

I used AI coding tools to help build and debug the Python scrapers — wiring up the headless browser, dismissing cookie banners, handling lazy‑loaded content and writing the site‑specific parsers each source needed. That means you can too! But the reporting logic, the standardization rules, the analysis and every editorial judgment are mine and I spot‑checked the scraped output by hand against the live sites.

## Setup and dependencies

The Python side is managed with [uv](https://github.com/astral-sh/uv). `pyproject.toml` lists what the scrapers need: Selenium and webdriver‑manager for the browser automation, pandas for wrangling and datasette and sqlite‑utils, which are in there because I'd sometimes load the CSVs into a small SQLite database to poke at them. `uv.lock` pins every dependency to an exact version, so `uv sync` rebuilds the same environment on any machine.

`config/` is older setup I kept around for reference rather than because you need it. `requirements.txt` is the original pip dependency list from before I moved to uv and `setup.sh` is the bash script I used early on to install Python, datasette and sqlite‑utils by hand. Both are superseded by `uv sync` and `config/README.md` says as much.

`.env.example` is the credential template. Copy it to `.env` and fill in your RotoWire login if you want to run the subscription scraper; nothing else needs it and `.env` is gitignored so it never gets committed. The `.gitignore` also keeps the bulk data and the comment data out of the repo and `.gitattributes` just normalizes line endings.

## The scrapers

Everything in `scrapers/` is a Python script driving Selenium with headless Chrome. I went with Selenium because these are all heavy JavaScript pages — lines load in after the page does, there are cookie banners to dismiss, content that only appears when you scroll and so on. A plain `requests` grab gets you almost nothing. The scripts handle the cookie dialogs and lazy loading and retry when a page doesn't cooperate.

What each one pulls:

-   `espn_schedule_scraper.py` — the tournament schedule from ESPN: matchups, seeds, regions, rounds, tip times, the point spread and the game over/under. This is the backbone everything else hangs off of.
-   `rotowire_public_data_scraper.py` — RotoWire's public props page, which aggregates lines across several sportsbooks. This is the prop source used in the public notebook.
-   `rotowire_subscription_data_downloader.py` — the paid RotoWire feed. It's the one source I had that reaches the **daily‑fantasy apps** (PrizePicks, Underdog, Sleeper, Pick6) the public page never showed, and I scraped it repeatedly through the day to track how lines moved before tip. It's also the only scraper that logs in; it reads my username and password from a `.env` file, never from the code itself. The notebook uses a real one‑game Duke–Siena excerpt of this feed to show how it standardizes and merges against the public feed; the full subscription corpus isn't shipped.

The full project ran the same kind of scraper against more sources — DraftKings and BettingPros for props, plus ESPN box scores and team rosters for context (the rosters doubled as the first step in the harassment reporting). Those scrapers are left out of this minimal demo, but adding a source is just another script feeding the same standardization functions.

## How I ran them (GitHub Actions)

I scraped several times a day because of how these markets behave. Books post props as they create them, on their own schedule and then take them down once a game tips off, sometimes earlier. A prop I didn't catch before it came down was simply gone. Running through the day was how I tried to grab each line during the window it actually existed. Doing that by hand every day for three weeks wasn't realistic, so I automated it with GitHub Actions.

The setup was a set of scheduled workflows, one per source. Each one is a cron job that fires several times a day, spins up a fresh Ubuntu machine on GitHub's side, installs Chrome and my Python dependencies, runs the scraper and then commits the new data file straight back into the repo with a timestamp. I also left a manual trigger on each so I could kick one off whenever I needed to.

I used Actions specifically for a few reasons. It's free for public repos and there's no server for me to babysit. Committing the output back into the repo meant my data history was version‑controlled and sat right next to the code that produced it, so every scrape was dated and timestamped and I never had to think about where files were going.

I've kept the actual workflow files out of this demo repo, but that's the whole idea: scheduled jobs that scrape on a timer and commit the results back.

## The cleaning problem

The reason this project is mostly a cleaning project: every site names things differently. ESPN's spread data calls UConn `CONN`, RotoWire calls it `Connecticut` and the bracket calls it `UConn`. One book lists a market as `Reb+Ast`, another as `Rebounds + Assists`. A player shows up as `A.J. Dybantsa` in one place and `AJ Dybantsa` in another. Until all of that agrees, nothing lines up and nothing joins.

`sample_analysis.Rmd` handles this up front with a set of small functions that I run over every source before I try to combine anything:

-   `standardize_team_names()` and `match_school_abbreviations()` map team variants and ESPN abbreviations to one canonical name. In this one‑game sample they're minimal — strip the `@` off a road team, map `DUKE` and `SIE` to `Duke` and `Siena` — but at full scale they're long, explicit lists covering every team and abbreviation, written out so each rule is something an editor or fact‑checker can read and check.
-   `standardize_player_names()` strips suffixes like `Jr.` and `III`, removes accents and quoted nicknames, and (at full scale) hand‑patches the known cross‑site name mismatches, like `Solomon Ball` vs. `Solo Ball`.
-   `standardize_market_name()` collapses all the different ways books write a bet type into one vocabulary (`pts` becomes `points`, `3pt made` becomes `three_pointers_made` and so on).
-   `classify_platform_type()` tags each operator as a sportsbook, a daily‑fantasy app, or other. This one matters a lot, because the split between regulated sportsbooks and DFS apps is central to the reporting and to the eligibility analysis.

## Merging it into one table

The goal is a single tidy table where one row is one prop line from one operator.

The key that ties a prop to a game is a sorted team pairing:

``` r
game = paste(pmin(team_a, team_b), "vs.", pmax(team_a, team_b))
```

Sorting the two teams alphabetically means `Duke @ Siena` and `Siena vs. Duke` both come out as `"Duke vs. Siena"` no matter the home/away order or which scrape they came from. With that key in place, the props get joined to the ESPN schedule for seeds, region, round and the spread. (At full scale the same key joins in rosters to attach a player to a team, and box scores for what actually happened.)

RotoWire stores each sportsbook in its own column, so I pivot those into one row per book before combining. Then I dedupe on a `prop_id` I build from the player, book, market, seeds, teams and date. When several scrapes (or, in the full project, several sources) are stacked together, the same prop collapses to one row and I keep a count of how many saw it (`number_times_identified`) and which ones (`data_source`), so I can always trace a line back to where it came from. The cleaned, merged result for the sample game is in `sample_analysis/sample_data/cleaned_props_duke_siena.csv`.

## The eligibility analysis

The eligibility piece is a separate strand, built on a table I hand‑coded of state rules — which products are legal where and the minimum betting age — joined to Census population estimates by age (pulled through the `tidycensus` API). Those tables aren't part of this minimal sample. The output estimates how many people each product can legally reach, and in particular the large bloc of states where DFS‑style college "picks" are legal but regulated sportsbook college props are not. It's a way to put a number on the legal gray area these apps operate in.

## The questions I took to the data

`sample_analysis.Rmd` stops at the clean table — loading and reconciling the sources into one tidy row‑per‑prop file. The reporting is then a matter of asking that table questions. These are the ones behind what we have published (see [CNS Maryland](https://cnsmaryland.org/2026/04/06/march-madness-is-almost-over-abuse-from-bettors-likely-isnt/)) or will in the coming weeks.

-   What share of the opportunities to risk money on individual college athletes did state sportsbook restrictions actually apply to?
-   How many Americans can legally risk money on college athletes through the daily‑fantasy loophole — and how many of them live in states where sports betting isn't legal at all?
-   What share of all identified opportunities were on daily‑fantasy platforms like PrizePicks and Underdog rather than regulated sportsbooks?
-   How many prop‑like opportunities did those pick‑'em sites offer, and how did that compare to the top sportsbooks combined?
-   For every 100 opportunities a sportsbook offered, how many did the pick‑'em sites offer?
-   How many additional college players did the pick‑'em sites put bets on that never appeared at the top sportsbooks?

A few more questions the same table could answer — and a few anecdotes worth chasing — are in **How to go further** at the end.

## The sample game

`sample_analysis/sample_data/` is one first‑round game, Duke vs. Siena, a 1‑seed against a 16‑seed. I picked it on purpose: even a matchup the market priced as a 27.5‑point rout (the game itself stayed close, 71–65) was loaded with props, which is part of the point. The folder has the raw RotoWire public and paid feeds and the ESPN schedule in their original formats, alongside the cleaned, merged version, so you can pick a player and follow them from the messy inputs through to the final row. There's a README in that folder walking through it.

## What the data misses (it's an undercount)

I want to be straight about coverage: this is not every prop that was offered. It's a floor and it undercounts, for two reasons.

First, the takedowns. Books pull props once a game starts, so anything posted and removed between two of my scrapes, or only put up after my last run before tip‑off, never got captured. The scraping window and the betting window didn't line up perfectly and the gap is lost props.

Second, uneven coverage across sites. No single feed carries everything. This public version is RotoWire‑only: the public feed is **sportsbook‑only**, while the paid feed is what brings in the DFS apps (PrizePicks, Underdog, Sleeper, Pick6) that drove much of the action on college players. But RotoWire relays only the lines it chooses to, so even with both feeds the apps are undercounted — scraping them directly would surface more. The full project added more sources to chip away at this, but never closed the gap completely. So where a market or an operator existed on a site I wasn't capturing, it's just not in here.

Treat the counts as a minimum, not a complete tally.

## What I left out and why

-   I'm not republishing the full paid RotoWire feed. The code that pulls it is here, plus a one‑game sample; the bulk data isn't.
-   There's no social‑media comment data in this repo; that side of the project is reported separately.
-   I'm not shipping the full scraped corpus. It's big and you don't need it to understand how any of this works.
-   Credentials live in a `.env` file that's never committed. Use `.env.example` as the template.

One real caveat: matching on names is imperfect. Common names can collide, which is why I lean on the rosters to disambiguate, but it still needs spot‑checking. And before you scrape any of these sites yourself, read their terms of service.

## The fields in the cleaned data

Each row in the cleaned table is one prop line from one operator. The table is deliberately narrow — here is every field it carries:

| Field | What it holds |
|----|----|
| `tournament` | the competition; used to filter down to NCAA Tournament games |
| `round` | tournament round (1st Round, and so on) |
| `game` | the sorted‑team key, e.g. `Duke vs. Siena` — what every source joins on |
| `game_date` | date of the game |
| `player_name` | the player the bet is on, standardized |
| `player_team` | the player's team, standardized |
| `player_team_seed` | the player's team's tournament seed |
| `opponent_team` | the opposing team, standardized |
| `opponent_team_seed` | the opponent's tournament seed |
| `game_points_spread` | the point spread for the game |
| `favored_team` | which team the spread favored |
| `player_team_favored` | `TRUE`/`FALSE` — was the player's team the favorite? |
| `prop_platform` | the operator the line came from (e.g. `prizepicks`, `caesars`) |
| `prop_platform_type` | `sportsbook`, `dfs`, or `other` |
| `prop_market` | the bet type, standardized (e.g. `points`, `points_rebounds_assists`) |
| `prop_line` | the number the operator set — the over/under value |
| `prop_id` | the unique id for a bet (player + platform + market + seeds + teams + date); the dedupe key |
| `number_times_identified` | how many raw rows collapsed into this one — a confirmation count across scrapes and sources |
| `data_source` | which feed(s) the line came from |
| `file_date` | date of the scrape file(s) it came from |

A few things the sources carried that I deliberately leave out, worth knowing exist:

-   **The odds on each prop.** Some books give the price (the juice, like ‑115) next to each line; I keep the line itself, not how it was priced.
-   **Player position**, which the RotoWire feed and some books had.
-   **An "average line variance" figure** from the paid RotoWire feed. (Because I scraped that feed repeatedly through the day, the raw files also hold how each line drifted before tip; the cleaning step keeps only the line closest to tip‑off.)
-   **Internal IDs and profile URLs** (ESPN game IDs, player IDs, roster bio links) that were only ever plumbing.

## How to go further

This cleaning step is deliberately a starting point. The `game` key and `prop_id` are built so you can keep joining things onto the table, and the standardization functions take any new source. Here's where I'd point a reporter who wanted to push past this one‑game, RotoWire‑only sample.

### Add more betting sources

RotoWire is one provider. The full project also scraped **DraftKings** (two ways — a top‑props list and a game‑by‑game walk) and **BettingPros** (which carries opening lines and current odds across many books at once). Each is just another scraper feeding the same standardization functions, then `bind_rows`‑ed onto the pile and deduped on `prop_id`, so a line seen on three sites collapses to one row with `number_times_identified = 3`.

The bigger prize is the **DFS apps themselves** — PrizePicks, Underdog, Sleeper, Pick6, Fliff. RotoWire's paid feed relays *some* of their lines, but only the ones it chooses to carry and without each app's full board or pricing. Scraping the apps directly is the single biggest way to close the coverage gap, because they're where most of the action on college players lives — and, as the eligibility strand shows, where it reaches the most and youngest people.

### Add rosters to place name‑only bets

RotoWire hands you each player's team, so its rows drop into a game on their own. But the moment you add a source that gives only a name and a bet with no team — DraftKings and BettingPros both do — you need a **roster** as a bridge. A game is keyed on its pair of teams, so a name with no team can't be placed without first looking the name up: roster → team → game. The full project scrapes each school's official roster page for exactly this, which doubles as a cross‑check that every propped player is really on a tournament roster. (Common names still collide, so the join needs spot‑checking.)

### Add box scores to grade the bets

The clean table tells you a bet *existed*; it doesn't tell you how it *resolved*. ESPN's public game‑summary API returns every player's full stat line by game ID. Join that on the `game` and player keys and you can **grade** every prop over or under — the most obvious next join, since this cleaning step carries only `player_minutes`.

### Social handles and the harassment reporting

The roster pages do double duty. Alongside player names, schools link each player's **social accounts** — Instagram, X, TikTok, Facebook — right on the roster profile, so these are real, school‑listed handles rather than anything I had to guess at. Those handles are the first link in the harassment side of this reporting: the chain runs **handle → the player's posts → the comments on them**, which is how a specific abusive comment gets tied back to the specific (often teenage) athlete it targeted. The comment data isn't in this repo, but the handle collection is where that thread starts. If you take this on, be deliberate about commenter and victim data.

### Patterns worth chasing

A few questions the data is built to answer that I noticed while reporting but haven't fully pinned down — good places to start if you pick this up:

-   **Does March Madness look different from the regular season?** The tournament is a compressed, high‑attention window. Pointing the same scrapers at regular‑season college games would show whether the sheer volume — and the DFS‑vs‑sportsbook split — hold up once the spotlight is off.
-   **Does tip time change how many props a game draws?** Every scrape is timestamped and the schedule carries each game's tip time, so you can line the two up. My experience during the regular season was that games get more betting attention when they are the only game on. This sometimes meant random 10 p.m. West Coast games would have a bunch of props available, whereas a similar mid-major game at 4 p.m. on a Tuesday wouldn't.
-   **How did a line move before tip?** RotoWire actually has a separate dataset that identifies line movements, if you're into that sort of thing.
-   **How much did operators disagree?** With one row per operator, compare books and apps on the same player‑stat line and flag where they diverge most.

## What I'd do differently next time

Where "How to go further" is about extending the work, this is about my own process — things I'd change if I ran the same project again:

-   **Dig deeper into DFS sites that weren't captured by this analysis.** I started this work long before March Madness started; meaning I spent months preparing for the tournament — what to scrape, how to scrape it, how to clean it, how to merge it, how to contextualize it. Still, there are a number of sites that I learned about just a little too late to incorporate into this analysis.
-   **Look more at prediction markets**. Prediction markets are regulated differently from both DFS and sports betting, and while they didn't offer the same volume of trading opportunities on individual college players, college players would occasionally pop up on those platforms as well.
-   **Experimented more with women's college props.** These were far harder to track, because they rarely appeared on regulated sportsbooks, and they appeared only sporadically on more obscure DFS sites. But I still wish I had been able to capture more data on this.
-   **Analyze college football data.** This was more of a timing this, as this was a spring semester project. I've heard, at least anecdotally, that the prop bets available on college football are as ridiculous as the ones on college basketball, if not more so.
