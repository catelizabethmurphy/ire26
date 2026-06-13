# Tracking the College Basketball Prop‑Betting Market

### A reproducible methodology — IRE & NICAR demo

This repository accompanies a conference talk on how to **collect, clean, and
combine sports‑betting data** to report on the explosion of player prop bets
during the NCAA men's basketball tournament. It is a **methodology showcase**:
it contains the scraping and analysis *code*, a written walkthrough of the
*approach*, and one small *sample game* so you can see the data take shape — but
**not** the full multi‑gigabyte corpus this project collected.

> **Start with [`METHODOLOGY.md`](METHODOLOGY.md).** That is the main document.
> It explains every source, every cleaning decision, how the sources are merged,
> and the reporting angles each step opens up.

---

## What this project does

During March Madness 2026, this system captured **player prop bets** — wagers on
whether an individual player goes over/under a number (e.g. "Cameron Boozer
**over 22.5** points"). Prop lines were scraped from multiple sportsbooks and
daily‑fantasy apps several times a day, then merged with the official schedule,
team rosters, and final box scores so each betting line could be tied to a real
game and a real outcome.

The result is a single analysis‑ready table where one row = one prop line, with
columns for the player, team, seed, opponent, the book offering it, the line,
and how many independent sources confirmed it.

## Data sources

| Source | What it provides | Access |
| --- | --- | --- |
| **ESPN** | Tournament schedule, seeds, regions, point spreads | Public |
| **RotoWire (public)** | Player props aggregated across books | Public |
| **RotoWire (subscription)** | Historical line movement & lines feed | **Paywalled** |
| **DraftKings** | Live sportsbook player props | Public |
| **BettingPros** | Opening lines + current odds across many books | Public |
| **Box scores** | Final per‑player stats (the actual outcomes) | Public |
| **Team rosters** | Player → team lookup | Public |
| **U.S. Census** | State population by age (for eligibility analysis) | Public API |

## Repository layout

```
ire26/
├── METHODOLOGY.md      ← read this first: sources, cleaning, merging, story angles
├── README.md
├── scrapers/           Python (Selenium) collectors, one per source
├── analysis/
│   ├── props.Rmd       the full clean + merge pipeline (R)
│   └── eligibility.Rmd who is even allowed to bet these props, by state + age
├── .github/workflows/  GitHub Actions that ran the scrapers on a schedule
├── config/             legacy pip setup (kept for reference)
├── data/
│   ├── sample/         ONE game (Duke vs. Siena) — raw inputs + merged output
│   └── eligibility/    public state age/eligibility tables + census join output
├── pyproject.toml      Python deps (managed with uv)
└── .env.example        credential template (only the subscription scraper needs it)
```

## What is included vs. excluded — and why

**Included:** all scraper and analysis code, the automation, the written
methodology, and a single sample game so the data shape is concrete.

**Deliberately excluded** to protect privacy and respect data ownership:

- **Social‑media comment data.** The broader project analyzed harassment
  directed at players. That data contains real people's usernames and names, so
  it is not published here.
- **The RotoWire subscription feed.** This is paywalled, proprietary data; only
  the *code* that retrieves it (and the merged one‑game sample) is shown, not the
  bulk feed.
- **The full scraped corpus** (hundreds of thousands of rows). Not needed to
  understand or reproduce the method.
- **Credentials** (`.env`). Use `.env.example` as a template.

See [`data/sample/README.md`](data/sample/README.md) for a tour of the sample.

## Running it yourself

**Scrapers (Python + Selenium):**

```bash
# install uv: https://github.com/astral-sh/uv
uv sync
uv run python3 scrapers/espn_schedule_scraper.py      # public, no login
uv run python3 scrapers/rotowire_public_data_scraper.py
# the subscription downloader needs a .env (see .env.example)
```

Chrome/ChromeDriver are handled automatically by `webdriver-manager`.

**Analysis (R):** open `analysis/props.Rmd` in RStudio. As written it reads the
full data tree; to run against the sample, point the `dir_ls(...)` paths at
`data/sample/`. The notebook is primarily here to *show the cleaning and merge
logic* — see `METHODOLOGY.md` for a plain‑English walkthrough.

> ⚠️ **The GitHub Actions in `.github/workflows/` are scheduled scrapers.** They
> are included to document how collection was automated. If you fork this repo,
> **disable Actions** (or delete the `schedule:` blocks) unless you actually
> intend to start scraping.

---

*Built for an investigative reporting demo. Use responsibly and check each
site's terms of service before scraping.*
