# Tracking the college basketball prop‑betting market

This is a demo repo for my IRE talk on how I collected and cleaned the player
prop‑betting data behind my March Madness reporting. It has the scraping code, a
single comprehensive R notebook that walks the whole pipeline and analysis, a
written methodology, and one sample game so you can see what the data looks like.
It does not have the full dataset I collected — that's large, and this repo is meant
to show the method, not host the archive. The sample game runs everything end‑to‑end.

**Start with [`analysis/analysis.Rmd`](analysis/analysis.Rmd)** — one notebook that
goes step by step from raw scraped files to a cleaned table of bets, grades every
bet against the real box score, and folds in the legal‑eligibility analysis. It
runs top to bottom on the sample game with no credentials or network.
[`METHODOLOGY.md`](METHODOLOGY.md) is the prose companion.

To keep this public version clean and reproducible, **the prop data comes from one
provider — RotoWire, using both its free and paid feeds** — with ESPN, rosters,
and box scores supporting it. The two feeds describe the same bets differently, on
purpose: it's the clearest way to show why the standardization step matters. The
same method extends to any other book (see the methodology).

## What this is about

A player prop is a bet on one player's stat line rather than on who wins —
"Cameron Boozer over 22.5 points." Sportsbooks and daily‑fantasy apps put up
dozens per game, and during the tournament that turned into a flood of bets on
the names of mostly teenage and early‑twenties players. I scraped those lines off
several sites a few times a day, then merged them with the schedule, rosters, and
final box scores so each line could be tied to a real game and a real outcome.

## Where the data comes from

| Source | What it gives me | Access |
| --- | --- | --- |
| RotoWire (public) | Props aggregated across sportsbooks — **a prop source** | Public |
| RotoWire (subscription) | Props incl. the **DFS apps** (PrizePicks, Underdog, …) — **a prop source** | Paid (one‑game sample) |
| ESPN | Schedule, seeds, regions, point spreads, game totals | Public |
| Rosters | Player → team bridge + social handles | Public |
| Box scores | Final per‑player stats (grade every bet) | Public |
| U.S. Census | State population by age (eligibility analysis) | Public API |

## Layout

```
ire26/
├── analysis/analysis.Rmd   start here: the full pipeline + analysis (R)
├── METHODOLOGY.md          prose companion to the notebook
├── scrapers/               one Python/Selenium scraper per source
├── data/
│   ├── sample/             one game (Duke vs. Siena), raw inputs + merged output
│   └── eligibility/        the public tables the eligibility analysis uses
├── config/                 older pip setup, kept for reference
├── pyproject.toml          Python deps (I use uv)
└── .env.example            credential template (only the subscription scraper needs it)
```

## What I left out, and why

- The social‑media comment data; that side of the project is reported separately.
- The full paid RotoWire feed — the scraper code is here and there's a one‑game sample, but not the bulk archive.
- The full scraped corpus. It's big and you don't need it to follow the method.
- Credentials. They live in a `.env` that's never committed; see `.env.example`.

There's a [`data/sample/README.md`](data/sample/README.md) that walks through the
one game I did include.

## Running it

Scrapers (Python + Selenium):

```bash
# install uv: https://github.com/astral-sh/uv
uv sync
uv run python3 scrapers/espn_schedule_scraper.py        # public, no login
uv run python3 scrapers/rotowire_public_data_scraper.py
# the subscription downloader needs a .env (see .env.example)
```

Chrome and ChromeDriver are handled automatically by `webdriver-manager`.

Analysis (R): open `analysis/analysis.Rmd` in RStudio and knit it, or run
`rmarkdown::render("analysis/analysis.Rmd")`. As written it reads the sample game
in `data/sample/` and the saved eligibility table in `data/eligibility/`, so it
runs end‑to‑end with no credentials and no network. `METHODOLOGY.md` explains the
same pipeline in plain English.

If you scrape any of these sites yourself, check their terms of service first.
