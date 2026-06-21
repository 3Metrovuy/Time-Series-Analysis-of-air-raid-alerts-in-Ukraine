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
