# Air Raid Alerts in Ukraine — Time Series Analysis

Interactive Streamlit app for analyzing air raid alert patterns across Ukraine,
built on the official Ukrainian air raid siren dataset.

## What it does

Turns a flat log of alert intervals into answers like:
- When and where is it most/least dangerous?
- How has alert activity changed over time?
- What's the safest weekday, hour, or season?

Measures both **number of alerts** and **total hours under alert** (interval-union,
not naive summing — overlapping alerts are merged).

## Quick start

```bash
# Clone and set up
git clone <repo-url>
cd Time-Series-Analysis-of-air-raid-alerts-in-Ukraine

# Create venv and install deps (using uv)
uv venv --python 3.12
uv pip install -r requirements.txt

# Run the app
.venv/Scripts/streamlit run src/app.py
```

Open http://localhost:8501 in your browser.

## Data source

**Dataset:** `Vadimkin/ukrainian-air-raid-sirens-dataset` (official subset).
The CSV should be placed at `data/official_data_en.csv`.

- 271,894 raw rows (158,041 after dedup + cleaning)
- 25 oblasts, March 2022 – present
- Three granularity levels: oblast, raion, hromada

## Key design decisions

- **Interval union** for duration metrics — overlapping alerts are merged, not
  double-counted. Ukraine-level total != sum of oblast totals (by design).
- **Kyiv local time** via `Europe/Kyiv` timezone (DST-aware, not hardcoded +3).
- **No duration cap** — long alerts (e.g. 631h near Nikopol) are legitimate data.
- **Permanent sirens excluded by identity** (Lypetska, Vovchanska hromadas), not
  by an arbitrary duration threshold.
- **Two analysis modes:** Mode A (oblast-level, full timeline) and Mode B
  (raion-level, Dec 2025+ only when raion data is dense).
- **Duplicates:** the source CSV contains the full dataset twice; exact-match
  dedup removes 113,845 rows.

## Project structure

```
├── CLAUDE.md            # AI instructions
├── README.md
├── requirements.txt
├── ai_log.md            # Session log
├── reflection.txt       # Post-project reflection
├── data/
│   └── official_data_en.csv
├── src/
│   ├── load.py          # Data loading, cleaning, caching
│   ├── analysis.py      # Pure analysis functions
│   └── app.py           # Streamlit UI
└── tests/
    └── test_intervals.py
```

## Tech stack

- Python 3.12, pandas, Streamlit, Plotly
