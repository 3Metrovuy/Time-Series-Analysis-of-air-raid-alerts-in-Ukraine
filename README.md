# Air Raid Alerts in Ukraine — Time Series Analysis

Interactive Streamlit app for analyzing air raid alert patterns across Ukraine,
built on the official Ukrainian air raid siren dataset.

## What it does

Turns a flat log of alert intervals into answers like:
- When and where is it most/least dangerous?
- How has alert activity changed over time?
- What's the safest weekday, hour, or season?

## How to start

```bash
# Clone
git clone https://github.com/3Metrovuy/Time-Series-Analysis-of-air-raid-alerts-in-Ukraine
cd Time-Series-Analysis-of-air-raid-alerts-in-Ukraine

python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt

streamlit run src/app.py
```

If you have the uv installed:

```bash
uv sync
uv run streamlit run src/app.py
```

Open http://localhost:8501 in your browser.

## Data source

**Dataset:** `Vadimkin/ukrainian-air-raid-sirens-dataset` (official subset).
The CSV should be placed at `data/official_data_en.csv`.

- 271,894 raw rows (158,041 after dedup + cleaning)
- 25 oblasts, March 2022 – present
- Three granularity levels: oblast, raion, hromada

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
