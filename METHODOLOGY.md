# Methodology

How to collect, clean, and combine college‑basketball prop‑betting data into a
single analysis‑ready table — and the reporting angles each step opens up.

This document is written so you can follow the *reasoning* without running any
code. Where it helps, it points to the exact function in
[`analysis/props.Rmd`](analysis/props.Rmd) or the scraper in
[`scrapers/`](scrapers/).

---

## 1. The reporting question

Player **prop bets** — wagers on an individual's stat line, e.g. *"Cameron
Boozer over 22.5 points"* — exploded during the NCAA tournament, including on
daily‑fantasy apps that take action in states where traditional sportsbooks are
illegal. To report on that market you need to answer questions like:

- How many props were offered on each game, and on which players?
- How did lines differ between sportsbooks and daily‑fantasy (DFS) operators?
- How did lines move as tip‑off approached?
- How did the lines compare to what players actually did?
- Who is even legally allowed to place these bets?

None of that is downloadable. It has to be assembled from several sites that
each describe teams, players, and markets *differently*. The hard part of this
story is not scraping — it is **reconciliation**.

## 2. Unit of analysis: one prop

The whole pipeline drives toward one tidy table where **one row = one prop
line** from one operator. The shared schema (see the final `select()` in
`props.Rmd`) is:

| Field | Meaning |
| --- | --- |
| `tournament`, `round`, `region` | from the ESPN schedule |
| `game`, `game_date` | normalized matchup + date |
| `player_name`, `player_team`, `player_team_seed` | who the prop is on |
| `opponent_team`, `opponent_team_seed` | who they played |
| `game_points_spread`, `favored_team`, `player_team_favored` | game context |
| `prop_platform` | the book/app (draftkings, prizepicks, …) |
| `prop_platform_type` | `sportsbook`, `dfs`, or `other` |
| `prop_market` | points, rebounds, assists, … (standardized) |
| `prop_line` | the number |
| `prop_id` | a deterministic key identifying this exact prop |
| `number_times_identified` | how many source rows confirmed it |
| `data_source`, `file_date` | provenance |
| `player_minutes` | from the box score — did they even play? |

`prop_id` is the linchpin. It is built deterministically from
`player + platform + market + seeds + teams + date`, so the *same* prop scraped
from three different sites collapses to one row — while preserving a count of how
many sources saw it.

## 3. The sources

| Source | Scraper | Public? | Why we use it |
| --- | --- | --- | --- |
| **ESPN** schedule | `espn_schedule_scraper.py` | ✅ | The spine: seeds, regions, rounds, spreads, dates |
| **RotoWire** (public) | `rotowire_public_data_scraper.py` | ✅ | Props aggregated across books |
| **RotoWire** (subscription) | `rotowire_subscription_data_downloader.py` | 🔒 paywalled | Historical line‑movement feed |
| **DraftKings** | `draftkings_scraper.py`, `draftkings_props_by_game_scraper.py` | ✅ | A major sportsbook's live props |
| **BettingPros** | `bettingpros_scraper.py` | ✅ | Opening lines + many books' current odds |
| **Box scores** | `march_madness_box_scores_scraper.py` | ✅ | The *actual outcomes* |
| **Rosters** | `roster_scraper.py` | ✅ | Player → team lookup |

All scrapers use **Selenium with headless Chrome** because these are
JavaScript‑heavy pages. They handle cookie banners, lazy‑loaded content, and
retries. The only one that authenticates is the RotoWire subscription
downloader, which reads `ROTOWIRE_USERNAME` / `ROTOWIRE_PASSWORD` from the
environment (never hard‑coded — see `.env.example`).

> **Why so many sources?** No single site is complete or trustworthy on its own.
> Cross‑referencing is both a data‑quality strategy (a prop confirmed by three
> sources is real) *and* a story engine (the *differences* between books are the
> story).

## 4. Collection cadence

Lines move all day, so the scrapers ran on a schedule via **GitHub Actions**
(see [`.github/workflows/`](.github/workflows/)), each run committing fresh,
timestamped files back to the repo to build a historical record:

- **~1:30 AM ET** — RotoWire (captures the *previous* day's games + results)
- **late morning → evening** — DraftKings and BettingPros every 1–2 hours
- **midday** — ESPN schedule for upcoming games

Capturing the same prop repeatedly across the day is what makes **line‑movement**
analysis possible later.

## 5. Cleaning — the reconciliation problem

Every site spells things differently. ESPN says `CONN`; RotoWire says
`Connecticut`; the bracket says `UConn`. One book lists `Reb+Ast`, another
`Rebounds + Assists`. A player is `A.J. Dybantsa` here and `AJ Dybantsa` there.
Until those agree, nothing joins. `props.Rmd` solves this with a set of small,
auditable standardization functions applied to *every* source before merging:

- **`standardize_team_names()`** — a long, explicit lookup mapping every variant
  to one canonical name (`Connecticut → UConn`, `Texas Christian → TCU`, …).
  Explicit and boring on purpose: each rule is reviewable and defensible.
- **`match_school_abbreviations()`** — maps ESPN's spread abbreviations
  (`DUKE`, `SIE`, `CONN`) to the same canonical names.
- **`standardize_player_names()`** — strips suffixes (`Jr.`, `III`), accents,
  and nicknames‑in‑quotes, then fixes known one‑off mismatches by hand
  (e.g. `Solomon Ball → Solo Ball`).
- **`standardize_market_name()`** — collapses market labels to a controlled
  vocabulary (`pts → points`, `3pt made → three_pointers_made`, `reb →
  rebounds`).
- **`classify_platform_type()`** — tags each operator as `sportsbook`, `dfs`
  (PrizePicks, Underdog, Sleeper, …), or `other`. **This single column powers
  the central story angle**: sportsbooks vs. daily‑fantasy.
- **`standardize_id()`** — strips punctuation/spacing so the composite `prop_id`
  is stable.
- **`missing_game_info()`** — a tiny, dated manual patch table for the handful of
  rows where a source omitted the matchup. Hand‑corrections are documented in
  code rather than done silently in a spreadsheet — that is the auditable way.

> **Reporting takeaway for the talk:** the credibility of the whole project
> lives in these functions. They are deterministic, version‑controlled, and
> readable, so any editor or fact‑checker can see *exactly* how a messy label
> became a clean one.

## 6. Merging — how the sources come together

The **canonical join key for a game** is a sorted team pair:

```r
game = paste(pmin(team_a, team_b), "vs.", pmax(team_a, team_b))
```

Sorting alphabetically means `Duke @ Siena` and `Siena vs. Duke` both become the
same `"Duke vs. Siena"` regardless of home/away or scrape order. With that key,
each prop source is joined to:

1. **ESPN schedule** on `game` → attaches round, region, seeds, spread, and
   resolves which team is favored and whether the prop's player is on the
   favored side.
2. **Rosters** on `player_name` → fills in the player's team where a props feed
   only gave a name (needed for DraftKings/BettingPros).
3. **Box scores** on `game + game_date + player + teams` → attaches
   `player_minutes` and (in the broader analysis) the actual stat line, so each
   line can be compared to reality.

Sources arrive in different shapes and are reshaped to the common schema before
binding — notably the scraped RotoWire and BettingPros feeds store each book in
its own `*_line` column, so they are **pivoted long** (`pivot_longer`) into one
row per book.

Finally, all sources are stacked and **deduplicated on `prop_id`**:

```r
bind_rows(all five sources) |>
  group_by(prop_id) |>
  mutate(number_times_identified = n(),
         data_source = paste(unique(data_source), collapse = ", ")) |>
  slice_head(n = 1)            # keep one row per prop, but remember who saw it
```

The output is [`data/sample/cleaned_props_duke_siena.csv`](data/sample/cleaned_props_duke_siena.csv)
(for the one sample game). `number_times_identified` and `data_source` are kept
as **provenance** — you can always trace a row back to which sites confirmed it.

## 7. Outcomes — comparing lines to reality

Box scores (`march_madness_box_scores_scraper.py`) provide each player's actual
minutes and stats. Joined onto the props table, they let you ask: *did the
player go over or under?* and *was the line "right"?* The merged sample includes
`player_minutes` so you can immediately spot props set on players who barely
played.

## 8. A second dataset: who can legally bet?

[`analysis/eligibility.Rmd`](analysis/eligibility.Rmd) joins a hand‑built table
of **state rules** (`data/eligibility/eligibility_age_by_state.csv` — which
operators are legal, and the minimum age) against **U.S. Census** population
estimates by age (via the `tidycensus` API). The output,
`eligible_population_by_state.csv`, estimates how many people in each state can
legally place college player‑prop bets — and, by subtraction, how many are
reached by DFS apps in states where they'd otherwise be too young or where
sportsbooks are banned. This turns "DFS operates in a legal gray area" into a
**number**.

## 9. Story angles this structure unlocks

Because everything lands in one tidy, sourced table, each cleaning/merging
decision is also a reporting lever:

- **Sportsbook vs. DFS** (`prop_platform_type`): are daily‑fantasy apps offering
  props in states where sportsbooks can't operate? Who do they reach?
- **Line movement** (repeated scrapes + `file_date`): which props moved most, and
  when? Sharp moves can signal where money — or information — went.
- **Cross‑book discrepancies** (`number_times_identified`, multiple
  `prop_platform`s per `prop_id`): where do books disagree on the same player?
- **Props vs. outcomes** (box‑score join): which lines were systematically too
  high or low? On which players?
- **Favorites vs. underdogs / seeds** (`player_team_favored`, seeds): are blowout
  games (like a 1‑vs‑16) still loaded with props?
- **Volume by player** (`props_per_player_tournament_wide` in the full project):
  which young, often teenage, athletes had the most action on their names — the
  bridge to the harassment‑of‑players reporting thread.
- **Legal reach** (eligibility join): how many people, by state and age, can
  actually place these bets?

## 10. Limitations and ethics

- **Terms of service.** Each site has its own ToS. Scrape responsibly, rate‑limit,
  and consult a lawyer/editor before publishing collected data.
- **Paywalled data is not redistributed.** Only the *code* for the RotoWire
  subscription feed is shown; the bulk feed itself is excluded.
- **No personal data here.** The broader project studied harassment aimed at
  players using social‑media comments containing real usernames and names. That
  data is **excluded** from this repo. If you do similar work, treat commenter
  and victim data with care and minimize what you publish.
- **Hand corrections are documented, not hidden.** Every manual fix lives in a
  named function in version control so it can be audited.
- **Names ≠ identity matches.** Player‑name joins can misfire on common names;
  rosters are used to disambiguate, but spot‑checking is still required.

---

*Questions about the method? The code in [`scrapers/`](scrapers/) and
[`analysis/`](analysis/) is the ground truth; this document is the map.*
