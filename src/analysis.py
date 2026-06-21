"""Pure analysis functions. No Streamlit imports."""

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Core: interval union
# ---------------------------------------------------------------------------

def merge_intervals(starts: list, ends: list) -> list[tuple]:
    """Merge overlapping/touching time intervals into non-overlapping unions.

    Returns list of (start, end) tuples representing the merged intervals.
    """
    if not starts:
        return []

    intervals = sorted(zip(starts, ends), key=lambda x: x[0])
    merged = [intervals[0]]

    for s, e in intervals[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    return merged


def total_hours_from_merged(merged: list[tuple]) -> float:
    """Sum duration in hours from merged interval list."""
    return sum(
        (e - s).total_seconds() / 3600 for s, e in merged
    )


# ---------------------------------------------------------------------------
# Mode A: oblast-level analysis (union across all levels for each oblast)
# ---------------------------------------------------------------------------

def oblast_union_hours(df: pd.DataFrame) -> pd.DataFrame:
    """For each oblast, compute union-merged total alert hours.

    Uses ALL rows (oblast/raion/hromada) for each oblast — the oblast column
    is always populated, so rollup is just grouping by it.
    """
    results = []
    for oblast, grp in df.groupby("oblast"):
        merged = merge_intervals(
            grp["started_at"].tolist(), grp["finished_at"].tolist()
        )
        hours = total_hours_from_merged(merged)
        alert_count = len(merged)
        results.append({
            "oblast": oblast,
            "union_hours": hours,
            "alert_count": alert_count,
        })
    return pd.DataFrame(results)


def ukraine_union_hours(df: pd.DataFrame) -> float:
    """Total wall-clock hours where *somewhere* in Ukraine was under alert."""
    merged = merge_intervals(
        df["started_at"].tolist(), df["finished_at"].tolist()
    )
    return total_hours_from_merged(merged)


def ukraine_alert_count(df: pd.DataFrame) -> int:
    """Number of distinct alert episodes across all of Ukraine (union)."""
    merged = merge_intervals(
        df["started_at"].tolist(), df["finished_at"].tolist()
    )
    return len(merged)


def summed_regional_burden(df: pd.DataFrame) -> float:
    """Sum of each oblast's own union-duration. Additive across oblasts."""
    obl = oblast_union_hours(df)
    return obl["union_hours"].sum()


# ---------------------------------------------------------------------------
# Grouping / breakdown helpers
# ---------------------------------------------------------------------------

def _group_intervals_by(
    df: pd.DataFrame,
    group_col: str,
    oblast: str | None = None,
) -> pd.DataFrame:
    """Group alerts and compute both count and union-hours per group value.

    For time-of-day / weekday / month etc. we can't do a true interval union
    across the group (a single alert spans multiple hours/days). Instead:
    - count: number of alerts whose Kyiv-local start falls in the group
    - avg_duration_min: mean raw duration of those alerts
    - total_hours: sum of raw durations (NOT union — union across time-bins
      is undefined since one alert spans multiple bins)
    """
    subset = df if oblast is None else df[df["oblast"] == oblast]
    grouped = subset.groupby(group_col).agg(
        alert_count=("duration_min", "count"),
        avg_duration_min=("duration_min", "mean"),
        total_hours=("duration_min", lambda x: x.sum() / 60),
    ).reset_index()
    return grouped


def alerts_by_weekday(df: pd.DataFrame, oblast: str | None = None) -> pd.DataFrame:
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    result = _group_intervals_by(df, "weekday", oblast)
    result["weekday"] = pd.Categorical(result["weekday"], categories=day_order, ordered=True)
    return result.sort_values("weekday").reset_index(drop=True)


def alerts_by_hour(df: pd.DataFrame, oblast: str | None = None) -> pd.DataFrame:
    return _group_intervals_by(df, "hour", oblast).sort_values("hour").reset_index(drop=True)


def alerts_by_month(df: pd.DataFrame, oblast: str | None = None) -> pd.DataFrame:
    return _group_intervals_by(df, "month", oblast).sort_values("month").reset_index(drop=True)


def alerts_by_season(df: pd.DataFrame, oblast: str | None = None) -> pd.DataFrame:
    season_order = ["Winter", "Spring", "Summer", "Autumn"]
    result = _group_intervals_by(df, "season", oblast)
    result["season"] = pd.Categorical(result["season"], categories=season_order, ordered=True)
    return result.sort_values("season").reset_index(drop=True)


def alerts_by_year(df: pd.DataFrame, oblast: str | None = None) -> pd.DataFrame:
    return _group_intervals_by(df, "year", oblast).sort_values("year").reset_index(drop=True)


def yearly_union_hours(df: pd.DataFrame, oblast: str | None = None) -> pd.DataFrame:
    """Per-year union hours, with intervals CLIPPED at year boundaries.

    We union the scope's intervals once, then split each merged interval at
    Jan-1 boundaries and attribute its hours to the correct calendar year (Kyiv
    local). Clipping is what keeps a year's total bounded by the hours in that
    year — without it, an interval spanning New Year leaks into the wrong year and
    a country-wide union can read as >8760 h ("more than a year"), which is wrong.
    """
    subset = df if oblast is None else df[df["oblast"] == oblast]
    if subset.empty:
        return pd.DataFrame(columns=["year", "union_hours"])

    merged = merge_intervals(
        subset["started_at_kyiv"].tolist(), subset["finished_at_kyiv"].tolist()
    )
    acc: dict = {}
    for s, e in merged:
        cur = s
        while cur < e:
            y = cur.year
            year_end = pd.Timestamp(year=y + 1, month=1, day=1, tz=cur.tz)
            seg_end = min(e, year_end)
            acc[y] = acc.get(y, 0.0) + (seg_end - cur).total_seconds() / 3600
            cur = seg_end
    return pd.DataFrame(sorted(acc.items()), columns=["year", "union_hours"])


# ---------------------------------------------------------------------------
# Time series: daily aggregation with rolling average
# ---------------------------------------------------------------------------

def daily_time_series(
    df: pd.DataFrame,
    oblast: str | None = None,
    metric: str = "count",
) -> pd.DataFrame:
    """Daily alert count or hours with 7-day rolling average.

    Both metrics are computed on the *union* of intervals for the scope, so the
    series is correct even for "All of Ukraine" (overlapping regional alerts are
    merged, never double-counted):
    - 'count': number of distinct union episodes whose Kyiv-local start is that day.
    - 'hours': day-clipped union hours (each merged interval is split at local
      midnight and its hours attributed to the day they fall in). This is bounded
      by 24 h/day by construction, which the naive row-sum was not.

    metric: 'count' or 'hours'
    """
    subset = df if oblast is None else df[df["oblast"] == oblast]
    empty = pd.DataFrame(columns=["date", "value", "rolling_7d"])
    if subset.empty:
        return empty

    merged = merge_intervals(
        subset["started_at_kyiv"].tolist(), subset["finished_at_kyiv"].tolist()
    )
    if not merged:
        return empty

    if metric == "count":
        acc: dict = {}
        for s, _e in merged:
            d = s.date()
            acc[d] = acc.get(d, 0) + 1
    else:
        acc = {}
        one_day = pd.DateOffset(days=1)  # calendar day (DST-aware), not fixed 24h
        for s, e in merged:
            cur = s
            while cur < e:
                day_start = cur.normalize()
                next_midnight = day_start + one_day  # true next local midnight
                seg_end = min(e, next_midnight)
                acc[day_start.date()] = (
                    acc.get(day_start.date(), 0.0)
                    + (seg_end - cur).total_seconds() / 3600
                )
                cur = seg_end

    daily = pd.DataFrame({"date": list(acc.keys()), "value": list(acc.values())})
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date")

    date_range = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    daily = (
        daily.set_index("date")
        .reindex(date_range, fill_value=0)
        .rename_axis("date")
        .reset_index()
    )

    daily["rolling_7d"] = daily["value"].rolling(7, min_periods=1).mean()
    return daily


def oblast_raion_treemap(df: pd.DataFrame, metric: str = "total_hours") -> pd.DataFrame:
    """Long-form data for a two-level (oblast -> raion) drill-down treemap.

    Each leaf is one (oblast, raion) with its OWN union value, so a raion never
    double-counts its overlapping oblast/raion/hromada rows. The treemap sums
    leaves to the oblast box; that oblast total approximates (but is not exactly)
    the true oblast union, because oblast-wide rows can overlap raion rows across
    levels. Rows with no raion (oblast-level alerts) are grouped as "(oblast-wide)".

    metric: 'total_hours' (union hours) or 'alert_count' (union episodes).
    """
    rows = []
    for oblast, grp in df.groupby("oblast"):
        # Oblast-wide rows (empty raion) are merged INTO each raion's intervals
        # so their time is distributed across raions rather than shown separately.
        obl_wide = grp[grp["raion"].fillna("").eq("")]
        raion_rows = grp[grp["raion"].fillna("").ne("")]
        if raion_rows.empty:
            merged = merge_intervals(
                grp["started_at"].tolist(), grp["finished_at"].tolist(),
            )
            value = len(merged) if metric == "alert_count" else total_hours_from_merged(merged)
            rows.append({"oblast": oblast, "raion": oblast, "value": value})
            continue
        for raion_label, sub in raion_rows.groupby("raion"):
            combined = pd.concat([sub, obl_wide])
            merged = merge_intervals(
                combined["started_at"].tolist(), combined["finished_at"].tolist(),
            )
            value = len(merged) if metric == "alert_count" else total_hours_from_merged(merged)
            rows.append({"oblast": oblast, "raion": raion_label, "value": value})
    return pd.DataFrame(rows)


def union_night_hours(
    df: pd.DataFrame,
    oblast: str | None = None,
    night_start: int = 22,
    night_end: int = 3,
) -> float:
    """Union alert-hours that fall inside the night window [night_start, night_end).

    Unions the scope's intervals first (no double-count), then sums, per merged
    interval, the overlap with each day's two night sub-windows:
    [00:00, night_end) and [night_start, 24:00). Computed on Kyiv-local time.
    """
    subset = df if oblast is None else df[df["oblast"] == oblast]
    if subset.empty:
        return 0.0
    merged = merge_intervals(
        subset["started_at_kyiv"].tolist(), subset["finished_at_kyiv"].tolist()
    )
    one_day = pd.DateOffset(days=1)  # calendar day (DST-aware), not fixed 24h
    total = 0.0
    for s, e in merged:
        cur = s
        while cur < e:
            day_start = cur.normalize()
            next_midnight = day_start + one_day  # true next local midnight
            seg_end = min(e, next_midnight)
            windows = (
                (day_start, day_start + pd.Timedelta(hours=night_end)),
                (day_start + pd.Timedelta(hours=night_start), next_midnight),
            )
            for ws, we in windows:
                ov_s = max(cur, ws)
                ov_e = min(seg_end, we)
                if ov_e > ov_s:
                    total += (ov_e - ov_s).total_seconds() / 3600
            cur = seg_end
    return total


# ---------------------------------------------------------------------------
# Mode B: raion-level analysis
# ---------------------------------------------------------------------------

RAION_DENSE_START = pd.Timestamp("2025-12-01", tz="UTC")


def raion_union_hours(df: pd.DataFrame, oblast: str) -> pd.DataFrame:
    """Per-raion union hours within a single oblast.

    Restricted to raion-dense period by default.
    """
    subset = df[
        (df["oblast"] == oblast)
        & (df["level"].isin(["raion", "hromada"]))
        & (df["started_at"] >= RAION_DENSE_START)
    ]
    if subset.empty:
        return pd.DataFrame(columns=["raion", "union_hours", "alert_count"])

    # Roll hromada rows up to their raion
    results = []
    for raion, grp in subset.groupby("raion"):
        if pd.isna(raion):
            continue
        merged = merge_intervals(
            grp["started_at"].tolist(), grp["finished_at"].tolist()
        )
        results.append({
            "raion": raion,
            "union_hours": total_hours_from_merged(merged),
            "alert_count": len(merged),
        })
    return pd.DataFrame(results)


def coverage_metric(df: pd.DataFrame, oblast: str) -> float | None:
    """Time-weighted fraction of an oblast's raions under alert.

    Only meaningful in the raion-dominant period. Returns None if no data.
    """
    subset = df[
        (df["oblast"] == oblast)
        & (df["level"] == "raion")
        & (df["started_at"] >= RAION_DENSE_START)
    ]
    if subset.empty:
        return None

    raions = subset["raion"].dropna().unique()
    n_raions = len(raions)
    if n_raions == 0:
        return None

    total_raion_hours = 0
    for raion, grp in subset.groupby("raion"):
        merged = merge_intervals(
            grp["started_at"].tolist(), grp["finished_at"].tolist()
        )
        total_raion_hours += total_hours_from_merged(merged)

    oblast_sub = df[
        (df["oblast"] == oblast) & (df["started_at"] >= RAION_DENSE_START)
    ]
    oblast_merged = merge_intervals(
        oblast_sub["started_at"].tolist(), oblast_sub["finished_at"].tolist()
    )
    oblast_hours = total_hours_from_merged(oblast_merged)

    if oblast_hours == 0:
        return None
    return total_raion_hours / (n_raions * oblast_hours)


# ---------------------------------------------------------------------------
# Mode B calibration: compare raion rollup vs oblast union
# ---------------------------------------------------------------------------

def calibration_check(df: pd.DataFrame) -> pd.DataFrame:
    """Compare Mode A (oblast union) vs Mode B (raion rollup to oblast)
    for the raion-dense period. Returns per-oblast comparison."""
    post = df[df["started_at"] >= RAION_DENSE_START]

    results = []
    for oblast in sorted(post["oblast"].unique()):
        # Mode A: union of ALL levels for this oblast
        obl_all = post[post["oblast"] == oblast]
        merged_a = merge_intervals(
            obl_all["started_at"].tolist(), obl_all["finished_at"].tolist()
        )
        hours_a = total_hours_from_merged(merged_a)

        # Mode B: union of raion+hromada rows rolled up to oblast
        obl_raion = post[
            (post["oblast"] == oblast)
            & (post["level"].isin(["raion", "hromada"]))
        ]
        if obl_raion.empty:
            hours_b = 0.0
        else:
            merged_b = merge_intervals(
                obl_raion["started_at"].tolist(), obl_raion["finished_at"].tolist()
            )
            hours_b = total_hours_from_merged(merged_b)

        diff_pct = ((hours_b - hours_a) / hours_a * 100) if hours_a > 0 else 0.0

        results.append({
            "oblast": oblast,
            "mode_a_hours": round(hours_a, 1),
            "mode_b_hours": round(hours_b, 1),
            "diff_pct": round(diff_pct, 1),
        })

    return pd.DataFrame(results)


def pre_post_comparison(df: pd.DataFrame) -> pd.DataFrame:
    """Compare per-oblast alert hours in a 6-month window before vs after
    the raion-dense boundary to detect implausible jumps."""
    boundary = RAION_DENSE_START
    pre_start = boundary - pd.DateOffset(months=6)

    pre = df[(df["started_at"] >= pre_start) & (df["started_at"] < boundary)]
    post = df[(df["started_at"] >= boundary) & (df["started_at"] < boundary + pd.DateOffset(months=6))]

    results = []
    all_oblasts = sorted(set(pre["oblast"].unique()) | set(post["oblast"].unique()))
    for oblast in all_oblasts:
        pre_obl = pre[pre["oblast"] == oblast]
        post_obl = post[post["oblast"] == oblast]

        merged_pre = merge_intervals(
            pre_obl["started_at"].tolist(), pre_obl["finished_at"].tolist()
        ) if not pre_obl.empty else []
        merged_post = merge_intervals(
            post_obl["started_at"].tolist(), post_obl["finished_at"].tolist()
        ) if not post_obl.empty else []

        h_pre = total_hours_from_merged(merged_pre)
        h_post = total_hours_from_merged(merged_post)
        ratio = (h_post / h_pre) if h_pre > 0 else float("inf")

        results.append({
            "oblast": oblast,
            "pre_hours": round(h_pre, 1),
            "post_hours": round(h_post, 1),
            "ratio": round(ratio, 2),
        })

    return pd.DataFrame(results)
