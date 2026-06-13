# Sample data — one game: Duke vs. Siena (1st Round, 2026‑03‑19)

These files are a single‑game slice of the project so you can see the pipeline
described in [`../../METHODOLOGY.md`](../../METHODOLOGY.md) take shape — from
messy raw inputs to one clean, merged table. **It is a demonstration sample, not
the full dataset.**

The matchup is a No. 1 (Duke) vs. No. 16 (Siena) — a deliberate choice: even a
27.5‑point blowout was loaded with player props, which is itself a story.

## The "before" — raw inputs (each source's native format)

| File | Source | Note |
| --- | --- | --- |
| `raw_espn_schedule_duke_siena.csv` | ESPN | seeds, region, spread (`-27.5`), venue — the schedule spine |
| `raw_rotowire_public_duke_siena.csv` | RotoWire (public) | one column per book (`draftkings_line`, `fanduel_line`, …) — note the wide shape that gets pivoted long |
| `raw_bettingpros_duke_siena.csv` | BettingPros | matchup stored as the abbreviation `SIE at DUKE` |
| `raw_draftkings_duke_siena.csv` | DraftKings | props packed into a single pipe‑delimited `raw_data` field that must be split |
| `raw_box_scores_duke_siena.csv` | Box scores | the actual outcomes (minutes, points, rebounds…) for both teams |

Notice how differently each source names teams, players, and markets — that is
exactly the reconciliation problem the standardization functions solve.

> **Not included:** the RotoWire *subscription* feed (paywalled) and any
> social‑media comment data (contains personal information). See the repo README.

## The "after" — merged output

| File | What it is |
| --- | --- |
| `cleaned_props_duke_siena.csv` | The result of cleaning + merging every source above into the shared one‑row‑per‑prop schema, with `prop_id`, `number_times_identified`, `data_source` provenance, and `player_minutes` from the box score. |

Open `cleaned_props_duke_siena.csv` and trace a single player (e.g. **Cameron
Boozer**) back through the raw files to see how the standardized names, the
sorted‑team `game` key, and the `prop_id` dedupe all line up.
