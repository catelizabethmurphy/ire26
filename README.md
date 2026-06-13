# Tracking the college basketball prop‑betting market

This is a demo repo for my IRE talk on how I collected and cleaned the player
prop‑betting data behind my March Madness reporting. It has the scraping and
analysis code, a written walkthrough of how it all fits together, and one sample
game so you can see what the data looks like. It does not have the full dataset I
collected — that's large, partly from a paid subscription I can't republish, and
the harassment side of the project involved comments with real people's names in
them. So this is the method, not the archive.

**[`METHODOLOGY.md`](METHODOLOGY.md) is the main document.** It's a tour of
what's in here and what each part does, from the scrapers through to the cleaned,
merged table.

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
| ESPN | Schedule, seeds, regions, point spreads | Public |
| RotoWire (public) | Props aggregated across books | Public |
| RotoWire (subscription) | Historical line movement | Paid |
| DraftKings | Live sportsbook player props | Public |
| BettingPros | Opening lines + current odds across many books | Public |
| Box scores | Final per‑player stats (what actually happened) | Public |
| Rosters | Player → team lookup | Public |
| U.S. Census | State population by age (eligibility analysis) | Public API |

## Layout

```
ire26/
├── METHODOLOGY.md      read this first
├── scrapers/           one Python/Selenium scraper per source
├── analysis/
│   ├── props.Rmd       the clean + merge pipeline (R)
│   └── eligibility.Rmd who can legally bet, by state and age
├── data/
│   ├── sample/         one game (Duke vs. Siena), raw inputs + merged output
│   └── eligibility/    the public tables the eligibility notebook uses
├── config/             older pip setup, kept for reference
├── pyproject.toml      Python deps (I use uv)
└── .env.example        credential template (only the subscription scraper needs it)
```

## What I left out, and why

- The social‑media comment data, which has real usernames and names in it.
- The paid RotoWire feed — the scraper code is here, the bulk data isn't.
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

Analysis (R): open `analysis/props.Rmd` in RStudio. As written it reads the full
data tree, so to run it against the sample you'd point the `dir_ls(...)` paths at
`data/sample/`. It's mainly here to show the cleaning and merge logic;
`METHODOLOGY.md` explains it in plain English.

If you scrape any of these sites yourself, check their terms of service first.
