"""Load, clean, and normalize the air raid alerts CSV."""

import os
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

KYIV_TZ = ZoneInfo("Europe/Kyiv")

# Near-front-line hromadas with permanent/continuous sirens spanning months.
# Excluded by identity, not by a duration threshold.
PERMANENT_SIREN_HROMADAS = {
    "Lypetska terytorialna hromada",
    "Vovchanska terytorialna hromada",
}

NIGHT_START = 22
NIGHT_END = 6


def _find_csv() -> str:
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    csvs = [f for f in os.listdir(data_dir) if f.endswith(".csv")]
    if len(csvs) != 1:
        raise FileNotFoundError(
            f"Expected exactly 1 CSV in data/, found {len(csvs)}: {csvs}"
        )
    return os.path.join(data_dir, csvs[0])


def _build_cleaning_report(
    raw_count: int,
    duplicates_dropped: int,
    unclosed_dropped: int,
    zero_duration_dropped: int,
    permanent_sirens_dropped: int,
    permanent_siren_names: list[str],
    negative_duration_count: int,
    final_count: int,
    date_min: pd.Timestamp,
    date_max: pd.Timestamp,
) -> dict:
    return {
        "raw_count": raw_count,
        "duplicates_dropped": duplicates_dropped,
        "unclosed_dropped": unclosed_dropped,
        "zero_duration_dropped": zero_duration_dropped,
        "permanent_sirens_dropped": permanent_sirens_dropped,
        "permanent_siren_names": permanent_siren_names,
        "negative_duration_count": negative_duration_count,
        "final_count": final_count,
        "date_min": date_min,
        "date_max": date_max,
    }


@st.cache_data
def load_and_clean() -> tuple[pd.DataFrame, dict]:
    """Load CSV, clean, derive columns. Returns (df, cleaning_report)."""
    path = _find_csv()
    df = pd.read_csv(path)
    raw_count = len(df)

    # --- Deduplicate exact duplicate rows ---
    before_dedup = len(df)
    df = df.drop_duplicates()
    duplicates_dropped = before_dedup - len(df)

    # --- Parse timestamps as UTC ---
    df["started_at"] = pd.to_datetime(df["started_at"], utc=True)
    df["finished_at"] = pd.to_datetime(df["finished_at"], utc=True)

    # --- Drop unclosed alerts (finished_at is NaT) ---
    unclosed_mask = df["finished_at"].isna()
    unclosed_dropped = int(unclosed_mask.sum())
    df = df[~unclosed_mask].copy()

    # --- Compute duration ---
    df["duration_min"] = (
        df["finished_at"] - df["started_at"]
    ).dt.total_seconds() / 60

    # --- Flag negative durations ---
    negative_duration_count = int((df["duration_min"] < 0).sum())

    # --- Drop zero-duration alerts ---
    zero_mask = df["duration_min"] == 0
    zero_duration_dropped = int(zero_mask.sum())
    df = df[~zero_mask].copy()

    # --- Exclude permanent sirens by identity ---
    perm_mask = df["hromada"].isin(PERMANENT_SIREN_HROMADAS)
    permanent_sirens_dropped = int(perm_mask.sum())
    permanent_siren_names = sorted(
        df.loc[perm_mask, "hromada"].unique().tolist()
    )
    df = df[~perm_mask].copy()

    # --- Kyiv local time columns (DST-aware, not hardcoded offset) ---
    started_kyiv = df["started_at"].dt.tz_convert(KYIV_TZ)
    df["weekday"] = started_kyiv.dt.day_name()
    df["hour"] = started_kyiv.dt.hour
    df["month"] = started_kyiv.dt.month
    df["year"] = started_kyiv.dt.year
    df["season"] = started_kyiv.dt.month.map(
        {12: "Winter", 1: "Winter", 2: "Winter",
         3: "Spring", 4: "Spring", 5: "Spring",
         6: "Summer", 7: "Summer", 8: "Summer",
         9: "Autumn", 10: "Autumn", 11: "Autumn"}
    )
    df["started_at_kyiv"] = started_kyiv
    df["finished_at_kyiv"] = df["finished_at"].dt.tz_convert(KYIV_TZ)

    # --- Reset index ---
    df = df.reset_index(drop=True)

    report = _build_cleaning_report(
        raw_count=raw_count,
        duplicates_dropped=duplicates_dropped,
        unclosed_dropped=unclosed_dropped,
        zero_duration_dropped=zero_duration_dropped,
        permanent_sirens_dropped=permanent_sirens_dropped,
        permanent_siren_names=permanent_siren_names,
        negative_duration_count=negative_duration_count,
        final_count=len(df),
        date_min=df["started_at"].min(),
        date_max=df["started_at"].max(),
    )

    # Console log
    print("=== Data Cleaning Report ===")
    for k, v in report.items():
        print(f"  {k}: {v}")

    return df, report
