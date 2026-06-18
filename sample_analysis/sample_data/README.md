# Sample data — one game: Duke vs. Siena (1st Round, 2026‑03‑19)

These files are a single‑game slice of the project so you can see the pipeline in
[`../sample_analysis.Rmd`](../sample_analysis.Rmd) take shape — from messy raw
inputs to one clean table. **It is a demonstration sample, not the full dataset**,
and `sample_analysis.Rmd` runs end‑to‑end on exactly these files.

The matchup is a No. 1 (Duke) vs. No. 16 (Siena) — a deliberate choice: even a game
the market priced as a 27.5‑point rout (it stayed closer, 71–65) was loaded with
player props, which is itself a story.

## The "before" — raw inputs (each source's native format)

| File | Source | Note |
| --- | --- | --- |
| `raw_rotowire_public_data_duke_siena.csv` | RotoWire (public) | **a prop source** — sportsbooks only; one column per book (`draftkings_line`, `fanduel_line`, …); a wide shape that gets pivoted long |
| `raw_rotowire_subscription_data_duke_siena.csv` | RotoWire (paid) | **a prop source** — long shape; this is where the **DFS apps** (PrizePicks, Underdog, Sleeper, Pick6) show up, alongside some sportsbooks like `caesars-sb`; markets like `PTS+REB+AST`. A real one‑game excerpt of the paid feed, scraped repeatedly through the day; overlaps the public feed so you can watch the dedupe work |
| `raw_espn_schedule_duke_siena.csv` | ESPN | seeds, region, spread (`-27.5`), game total, venue — the schedule spine |

Notice how differently the two RotoWire feeds name the same books, players, and
markets — that is exactly the reconciliation problem the standardization functions
solve, and the cleanest place to see it.

> **RotoWire‑only here.** The full project also pulled DraftKings and BettingPros;
> those are left out of this public version to keep the prop pipeline to one
> provider. The RotoWire files above are a single‑game excerpt, not the full
> scraped corpus. See the repo README.

## The "after" — merged output

| File | What it is |
| --- | --- |
| `cleaned_props_duke_siena.csv` | The cleaned, one‑row‑per‑prop table with `prop_id`, `number_times_identified`, and `data_source` provenance. (This is the equivalent output from the full multi‑source pipeline; `sample_analysis.Rmd` rebuilds the RotoWire‑only version live from the raw files above.) |

Open `cleaned_props_duke_siena.csv` and trace a single player (e.g. **Cameron
Boozer**) back through the raw files to see how the standardized names, the
sorted‑team `game` key, and the `prop_id` dedupe all line up.
