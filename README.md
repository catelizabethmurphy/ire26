# Tracking the college basketball prop‑betting market

This is a demo repo for my IRE talk on how I collected and cleaned the player
prop‑betting data behind my March Madness reporting. It has the scraping code, an R
notebook that walks the loading‑and‑cleaning pipeline, a written methodology, and one
sample game so you can see what the data looks like. It does not have the full dataset
I collected — that's large, and this repo is meant to show the method, not host the
archive. The sample game runs everything end‑to‑end.

**Start with [`sample_analysis/sample_analysis.Rmd`](sample_analysis/sample_analysis.Rmd)** —
the notebook that goes step by step from raw scraped files to one clean,
row‑per‑prop table: load the feeds, standardize the names, teams, and markets every
site spells differently, and merge them on a shared key. It runs top to bottom on the
sample game with no credentials or network. [`METHODOLOGY.md`](METHODOLOGY.md) is the
prose companion, and it also covers the parts of the broader project that aren't in
this minimal repo — rosters, box scores, the legal‑eligibility analysis, and the
harassment reporting.

To keep this public version clean and reproducible, **the prop data comes from one
provider — RotoWire, using both its free and paid feeds** — plus the ESPN schedule for
game context (seeds, round, spread). The two feeds describe the same bets differently,
on purpose: it's the clearest way to show why the standardization step matters. The
same method extends to any other book (see the methodology).

## What this is about

A player prop is a bet on one player's stat line rather than on who wins —
"Cameron Boozer over 22.5 points." Sportsbooks and daily‑fantasy apps put up dozens per
game, and during the tournament that turned into a flood of bets on the names of mostly
teenage and early‑twenties players. I scraped those lines off several sites a few times
a day, then standardized and merged them so each line could be tied to a real game.

## Where the data comes from

This demo uses three sources:

| Source | What it gives me | Access |
| --- | --- | --- |
| RotoWire (public) | Props aggregated across sportsbooks — **a prop source** | Public |
| RotoWire (subscription) | Props incl. the **DFS apps** (PrizePicks, Underdog, …) — **a prop source** | Paid (one‑game sample) |
| ESPN | Schedule, seeds, regions, point spreads — game context | Public |

The full reporting also pulled DraftKings and BettingPros (more props), ESPN box scores
(to grade bets), team rosters (a player → team bridge and the social handles), and U.S.
Census data (the eligibility analysis). Those aren't in this minimal repo — see
[`METHODOLOGY.md`](METHODOLOGY.md).

## Layout

```
ire26/
├── sample_analysis/
│   ├── sample_analysis.Rmd   start here: the loading + cleaning pipeline (R)
│   └── sample_data/          one game (Duke vs. Siena): raw RotoWire + ESPN, plus the cleaned output
├── METHODOLOGY.md            prose companion to the notebook
├── scrapers/                 Python/Selenium scrapers: RotoWire public, RotoWire subscription, ESPN schedule
├── index.html, main.js, styles.css   the IRE session resource page
├── config/                   older pip setup, kept for reference
├── pyproject.toml / uv.lock  Python deps (I use uv)
└── .env.example              credential template (only the subscription scraper needs it)
```

## What I left out, and why

- The social‑media comment data; that side of the project is reported separately.
- The full paid RotoWire feed — the scraper code is here and there's a one‑game sample, but not the bulk archive.
- The full scraped corpus and the additional sources (DraftKings, BettingPros, box scores, rosters, eligibility tables). They're described in the methodology; you don't need them to follow the method.
- Credentials. They live in a `.env` that's never committed; see `.env.example`.

There's a [`sample_analysis/sample_data/README.md`](sample_analysis/sample_data/README.md)
that walks through the one game I did include.

## Running it

Analysis (R) — the main thing. Open `sample_analysis/sample_analysis.Rmd` in RStudio
and knit it, or run:

```r
install.packages(c("tidyverse", "janitor", "lubridate", "stringi", "rvest", "fs", "hms", "rmarkdown"))
rmarkdown::render("sample_analysis/sample_analysis.Rmd")
```

As written it reads the sample game in `sample_analysis/sample_data/`, so it runs
end‑to‑end with no credentials and no network. `METHODOLOGY.md` explains the same
pipeline in plain English.

Scrapers (Python + Selenium), if you want to pull fresh data:

```bash
# install uv: https://github.com/astral-sh/uv
uv sync
uv run python3 scrapers/espn_schedule_scraper.py        # public, no login
uv run python3 scrapers/rotowire_public_data_scraper.py
# the subscription downloader needs a .env (see .env.example)
```

Chrome and ChromeDriver are handled automatically by `webdriver-manager`.
