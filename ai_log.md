# AI Session Log

## Turn 1
*User:* Read the CLAUDE.md file and propose a list of steps to complete the project.

**Response:** Proposed a 5-phase, 21-step plan covering: setup & data verification, data loading & cleaning, analysis logic, Streamlit app, and polish/deliverables.

## Turn 2
*User:* Let's start with Phase 1.

**Response:** Created `data/` and `src/` directories, moved `official_data_en.csv` into `data/`, created `requirements.txt`. Discovered Python wasn't on PATH — asked user to install.

## Turn 3
*User:* I have Python installed via uv.

**Response:** Found Python 3.12 via `uv python list`. Created venv, installed dependencies. Verified CSV schema:
- 271,894 rows, 7 columns matching expected schema
- Date range: 2022-03-15 to 2026-06-21
- 25 unique oblasts (including Kyiv City)
- 3 levels: oblast (130k), raion (107k), hromada (35k)
- 0 unclosed alerts (finished_at never null)
- 4 zero-duration rows (to drop during cleaning)
- 4 suspected permanent sirens: Lypetska hromada (14,497h) and Vovchanska hromada (10,525h) in Kharkivska oblast — each appears twice (duplicate rows). These are known near-front-line areas with continuous alerts, to be excluded by identity.
- Luhanska oblast: only 2 rows, max 88h — not a permanent siren issue.
- Nikopolskyi raion (Dnipropetrovska) has legitimately long alerts (up to 631h) — these are real and should NOT be capped.

## Turn 4
*User:* Let's go for Phase 2, but don't create the is_night column. Also show top 7 longest alerts (besides Luhansk and Crimea).

**Response:** Built `src/load.py` with full cleaning pipeline:
- Deduplication removed 113,845 exact duplicate rows (dataset was ~42% duplicated)
- 0 unclosed alerts, 2 zero-duration dropped, 6 permanent siren rows dropped (Lypetska + Vovchanska hromadas)
- Final clean dataset: 158,041 rows
- Timezone: proper `Europe/Kyiv` via zoneinfo (DST-aware), derived weekday/hour/month/year/season columns
- Skipped `is_night` column per user request
- Built `src/analysis.py` with `merge_intervals()` and `total_hours_from_merged()` — the interval-union logic
- Wrote 7 unit tests for interval-union (all pass)
- Top 7 longest alerts: Lypetska (14,497h) and Vovchanska (10,525h) are permanent sirens → excluded. Nikopolskyi raion alerts (up to 631h) are legitimate near-front-line alerts → kept.

## Turn 5
*User:* Confirmed duplicate finding is correct (raw CSV is indeed doubled). Proceed with Phase 3. Run calibration check for post-Dec 2025 raion fractionalization.

**Response:** Built full `src/analysis.py` with:
- Mode A functions: `oblast_union_hours`, `ukraine_union_hours`, `summed_regional_burden`
- Grouping: `alerts_by_weekday/hour/month/season/year`, `yearly_union_hours`
- Time series: `daily_time_series` with 7-day rolling average
- Mode B functions: `raion_union_hours`, `coverage_metric`
- Calibration: `calibration_check`, `pre_post_comparison`

**Calibration results (strategy holds):**
1. Mode A vs Mode B in raion-dense period: 23/24 oblasts show 0.0% divergence (perfect match). Only exception: Kyiv City (-100%) — it has no raions, only oblast-level rows, so Mode B correctly returns 0. This is expected, not a bug.
2. Pre vs Post Dec 2025 (6-month windows): mean ratio 1.11x, no oblast flagged with implausible jumps (>5x or <0.2x). Largest ratio is Zaporizka at 2.01x — a real increase, not an artifact. Most oblasts are between 0.7–1.8x.
**Verdict: raion-level approach is validated. No discontinuity artifacts detected.**

## Turn 6
*User:* Let's build the Streamlit app.

**Response:** Built `src/app.py` — full Streamlit app with:
- **Landing summary:** 4 headline metrics (total hours 31,743h, 4,699 episodes, avg 127 min, night-hours share), treemap of oblast hours, yearly bar chart
- **Interactive exploration:** sidebar with region/year/metric/breakdown selectors, bar charts with safest/most dangerous callouts, oblast ranking bar chart
- **Time series:** daily count/hours with 7-day rolling average, weekday x hour heatmap
- **Mode B:** raion detail for selected oblast (Dec 2025+), coverage metric, calibration check expander
- **Data notes:** full cleaning report and key decisions in an expander
- All charts use Plotly for interactivity. Every chart labels its metric and date range.
- Smoke-tested all code paths — no errors. Server starts cleanly on port 8501.

## Turn 7
*User:* Do Phase 5 but don't write reflections — user will write them. Asked about best way to share screenshots for UI corrections.

**Response:** Created `README.md` with project description, quick start, data source, key decisions, and structure. Created placeholder `reflection.txt`. Advised user that both CLI and Claude desktop app support screenshots, but the desktop app is smoother for image-heavy feedback.

## Turn 8
*User:* Sent 10 UI corrections via screenshots.

**Response:** Confirmed 3 blocking decisions first: (8) remove BOTH calibration + data-notes panels (user override of the CLAUDE.md "data notes required" deliverable — flagged, user chose to remove); (10) add clickable Ukraine map *alongside* the dropdown; (3/5) for All-of-Ukraine + Hours, hide hour-based breakdowns and fall back to counts. Then implemented all 10:
- Night window 22:00→03:00; headline now shows absolute **union** night-hours (added `union_night_hours`).
- Diagnosed the "8879h in 2025" bug: country-wide yearly union saturates near hours-in-a-year. Removed the yearly bar from landing; it now appears under the weekday breakdown only for a single region.
- Treemap is now a 2-level oblast→raion **drill-down** (click to expand), date-range aware, with the selected oblast border-highlighted; in raion mode it shows the chosen oblast's per-raion union (full width).
- Rewrote `daily_time_series` to use union (day-clipped hours, episode-start counts) so the series is bounded/correct even for All-of-Ukraine; time-series now obeys the main metric (removed its own switch).
- Heatmap obeys the metric; raion section keyed off the metric; coverage metric got a full formula explanation.
- Renamed "Mode A/B" → "Oblast level / Raion level".
- Added Ukraine oblast choropleth (`assets/ukraine_oblasts.geojson`, ISO-code join) with click-to-select callback, alongside the dropdown.

**Then the app froze (critical bug, fixed same turn).** Root cause: the day-stepping loops in `daily_time_series`/`union_night_hours` added a fixed `Timedelta(days=1)` to tz-aware timestamps — on a DST fall-back (25h) day, `midnight+24h` lands before the true next midnight so `cur` stopped advancing → infinite loop (and the All-of-Ukraine union spans many DST transitions). Fixed by stepping with `pd.DateOffset(days=1)` (calendar/DST-aware). Verified: each path runs ~1–2s (daily-hours max=25.0, correctly the fall-back day); bare-mode app run exit 0. Also added `@st.cache_data` wrappers in app.py for the ~158k-row interval merges so widget interactions stay snappy.

## Turn 9
*User:* Second round of 7 UI corrections (screenshots).

**Response:** Implemented all 7:
1. Map now drawn from the full geojson incl. **Crimea** (grey base layer for context/silhouette; no data, not selectable).
2. Map **locked** — `dragmode=False` + `config={scrollZoom:False, displayModeBar:False, doubleClick:False}` (clicks still fire selection).
3. **Removed the sidebar dropdown**; the map (in an expander labelled with the current region) is now the sole region selector, with two buttons for "All of Ukraine" / "Kyiv City" (which has no polygon). Region read from `st.session_state.region_select`, set by the map `on_select` callback and button `on_click` callbacks.
4. Oblast treemap now `maxdepth=1` → only oblasts show; raions revealed on click (drill-down).
5. Heatmap axis relabeled "Hour of day (Kyiv time zone)" — the "Kyiv" was the timezone, not the region (region is in the title); clarified.
6. Removed the long in-app coverage explanation (kept the metric + a short tooltip); explained the formula to the user in chat instead.
7. Restored the two-column landing: **total-hours-per-year bar (blue, left)** + **treemap (right)**; removed the duplicate yearly chart from the interactive section.

**Also fixed `yearly_union_hours`:** it now unions then **clips intervals at year boundaries** (Kyiv local), so a year is bounded by the hours in that year. This removes the earlier ">8760h / 366 days" artifact and makes the yearly bar honest even for All-of-Ukraine — which is what allowed bringing it back to the landing. Verified: compile OK, bare-mode app run exit 0, no exceptions.

## Turn 10
*User:* Two reverts — (1) landing back to the first variant (rectangle treemap LEFT, total-hours bar RIGHT); (2) go back to the dropdown to choose an oblast.

**Response:** Removed the map-as-selector entirely (map expander, `on_click`/`on_select` callbacks, `DATASET_OBLAST_TO_ISO`/`ISO_TO_OBLAST`, `load_geojson`, and the now-unused `json`/`os` imports). Restored the sidebar `selectbox` region dropdown. Swapped the landing columns so the treemap is on the left and the blue total-hours-per-year bar on the right. Kept the geojson asset on disk. Verified compile OK + bare-mode run exit 0.

## Turn 11
*User:* Four final tweaks: (1) treemap should show oblasts first, highlight selected in blue, drill to raions only on click; (2) heatmap hour label needs a UTC reference; (3) total-hours bar should appear ONLY when a region is chosen, not on all-Ukraine ("the other way around", "as before"); (4) remove the two grey caption texts under the landing charts.

**Response:**
1. Fixed the treemap drill-down: the bug was `path=[px.Constant("Ukraine"), …]` + `maxdepth=1`, which collapses to a single "Ukraine" box. Dropped the constant root → `path=["oblast","raion"]` + `maxdepth=1` shows oblasts first, raions on click. Strengthened the selected-oblast highlight to a thick blue border (`#1c83e1`, width 6).
2. Heatmap x-label → "Hour of day (Kyiv time, UTC+2/+3)" (honest about DST while giving the UTC anchor the user asked for).
3. Clarified via AskUserQuestion: bar only for a chosen region. Restructured the landing — **All of Ukraine = full-width treemap only (no bar)**; **a region chosen = treemap (left, highlighted) + that region's per-year total-hours bar (right)**.
4. Removed both landing chart captions.
Verified: compile OK, bare-mode run exit 0.

## Turn 12
*User:* Confirmed the drill-down behavior (all-Ukraine → oblasts → click expands to raions, no need to switch to Raion level; selected oblast painted blue, chart shows all of Ukraine), and asked to change the rectangle chart into a round "pie" chart while keeping the same features.

**Response:** Swapped both `px.treemap`s for `px.sunburst` (the round, hierarchical equivalent — a plain pie can't drill down). Same `path=["oblast","raion"]`, `maxdepth=1`, blue selected-oblast highlight, and colour scale, so all behaviors carry over: oblasts first, click a slice to expand into raions, selected oblast highlighted blue, chart shows all of Ukraine. Verified compile OK + bare-mode run exit 0.
