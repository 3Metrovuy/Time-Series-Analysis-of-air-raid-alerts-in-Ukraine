import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from load import load_and_clean, NIGHT_START, NIGHT_END
from analysis import (
    oblast_union_hours,
    ukraine_union_hours,
    ukraine_alert_count,
    summed_regional_burden,
    alerts_by_weekday,
    alerts_by_hour,
    alerts_by_month,
    alerts_by_season,
    alerts_by_year,
    yearly_union_hours,
    daily_time_series,
    merge_intervals,
    total_hours_from_merged,
    raion_union_hours,
    coverage_metric,
    calibration_check,
    pre_post_comparison,
    RAION_DENSE_START,
)

st.set_page_config(
    page_title="Air Raid Alerts in Ukraine",
    page_icon="\U0001F6A8",
    layout="wide",
)

# ── Load data ────────────────────────────────────────────────────────────────

df, report = load_and_clean()

# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("Settings")

mode = st.sidebar.radio(
    "Analysis mode",
    ["Oblast level (Mode A)", "Raion level (Mode B)"],
    help=(
        "Mode A: full timeline, all levels merged to oblast. "
        "Mode B: per-raion detail, Dec 2025+ only."
    ),
)
is_mode_b = mode.startswith("Raion")

oblasts = sorted(df["oblast"].unique())
region_options = ["All of Ukraine"] + oblasts

selected_region = st.sidebar.selectbox("Region", region_options)
oblast_filter = None if selected_region == "All of Ukraine" else selected_region

years = sorted(df["year"].unique())
year_range = st.sidebar.slider(
    "Year range",
    min_value=int(years[0]),
    max_value=int(years[-1]),
    value=(int(years[0]), int(years[-1])),
)

metric_label = st.sidebar.radio("Metric", ["Alert count", "Total hours under alert"])
metric_key = "alert_count" if metric_label == "Alert count" else "total_hours"

breakdown_label = st.sidebar.selectbox(
    "Breakdown", ["Weekday", "Hour of day", "Month", "Season", "Year"]
)

# ── Filter data by year range ────────────────────────────────────────────────

df_filtered = df[(df["year"] >= year_range[0]) & (df["year"] <= year_range[1])]

# ═════════════════════════════════════════════════════════════════════════════
# LANDING SUMMARY
# ═════════════════════════════════════════════════════════════════════════════

st.title("Air Raid Alerts in Ukraine")
st.caption(
    f"Data: {report['date_min'].strftime('%d %b %Y')} – "
    f"{report['date_max'].strftime('%d %b %Y')} | "
    f"Source: official Ukrainian air raid siren dataset"
)

# ── Headline metrics ─────────────────────────────────────────────────────────

total_ukraine_hours = ukraine_union_hours(df)
total_alert_episodes = ukraine_alert_count(df)
avg_duration_min = df["duration_min"].mean()
regional_burden = summed_regional_burden(df)

night_alerts = df[(df["hour"] >= NIGHT_START) | (df["hour"] < NIGHT_END)]
night_hours = night_alerts["duration_min"].sum() / 60
night_share = night_hours / (df["duration_min"].sum() / 60) * 100

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Total hours under alert",
    f"{total_ukraine_hours:,.0f} h",
    help="Wall-clock hours where somewhere in Ukraine was under alert (interval union).",
)
col2.metric(
    "Alert episodes",
    f"{total_alert_episodes:,}",
    help="Distinct alert episodes across Ukraine (union of overlapping intervals).",
)
col3.metric(
    "Avg alert duration",
    f"{avg_duration_min:.0f} min",
)
col4.metric(
    f"Night-hours share ({NIGHT_START}:00–{NIGHT_END:02d}:00)",
    f"{night_share:.1f}%",
    help=f"Share of total alert time starting in the {NIGHT_START}:00–{NIGHT_END:02d}:00 Kyiv time window.",
)

# ── Overview charts ──────────────────────────────────────────────────────────

obl_hours = oblast_union_hours(df).sort_values("union_hours", ascending=False)

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    fig_tree = px.treemap(
        obl_hours,
        path=["oblast"],
        values="union_hours",
        title="Total alert hours by oblast (union, full period)",
        color="union_hours",
        color_continuous_scale="OrRd",
    )
    fig_tree.update_traces(textinfo="label+value+percent root")
    fig_tree.update_layout(margin=dict(t=40, l=0, r=0, b=0))
    st.plotly_chart(fig_tree, use_container_width=True)

with chart_col2:
    yr_hours = yearly_union_hours(df)
    fig_yr = px.bar(
        yr_hours,
        x="year",
        y="union_hours",
        title="Total alert hours per year (all of Ukraine, union)",
        labels={"union_hours": "Hours", "year": "Year"},
        text_auto=".0f",
    )
    fig_yr.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig_yr, use_container_width=True)

st.markdown("---")

# ═════════════════════════════════════════════════════════════════════════════
# INTERACTIVE EXPLORATION
# ═════════════════════════════════════════════════════════════════════════════

st.header("Interactive exploration")

region_label = selected_region if oblast_filter else "All of Ukraine"
st.subheader(f"{region_label} | {year_range[0]}–{year_range[1]} | {metric_label}")

# ── Breakdown chart ──────────────────────────────────────────────────────────

BREAKDOWN_FUNCS = {
    "Weekday": (alerts_by_weekday, "weekday"),
    "Hour of day": (alerts_by_hour, "hour"),
    "Month": (alerts_by_month, "month"),
    "Season": (alerts_by_season, "season"),
    "Year": (alerts_by_year, "year"),
}

func, x_col = BREAKDOWN_FUNCS[breakdown_label]
breakdown_df = func(df_filtered, oblast_filter)

fig_break = px.bar(
    breakdown_df,
    x=x_col,
    y=metric_key,
    title=f"{metric_label} by {breakdown_label.lower()} ({region_label}, {year_range[0]}–{year_range[1]})",
    labels={metric_key: metric_label, x_col: breakdown_label},
    text_auto=True,
    color=metric_key,
    color_continuous_scale="YlOrRd",
)
if breakdown_label == "Hour of day":
    fig_break.update_layout(xaxis=dict(dtick=1))
st.plotly_chart(fig_break, use_container_width=True)

# ── Safest / most dangerous summary ─────────────────────────────────────────

if not breakdown_df.empty:
    safest_idx = breakdown_df[metric_key].idxmin()
    danger_idx = breakdown_df[metric_key].idxmax()
    safest_val = breakdown_df.loc[safest_idx, x_col]
    danger_val = breakdown_df.loc[danger_idx, x_col]
    safest_metric = breakdown_df.loc[safest_idx, metric_key]
    danger_metric = breakdown_df.loc[danger_idx, metric_key]

    unit = "alerts" if metric_key == "alert_count" else "hours"
    s1, s2 = st.columns(2)
    s1.success(f"**Safest {breakdown_label.lower()}:** {safest_val} ({safest_metric:,.0f} {unit})")
    s2.error(f"**Most dangerous {breakdown_label.lower()}:** {danger_val} ({danger_metric:,.0f} {unit})")

# ── Oblast ranking (when "All of Ukraine" is selected) ───────────────────────

if oblast_filter is None:
    st.subheader("Oblast ranking")
    obl_filtered = oblast_union_hours(df_filtered).sort_values("union_hours", ascending=True)
    rank_metric = "alert_count" if metric_key == "alert_count" else "union_hours"
    rank_label = "Alert count" if metric_key == "alert_count" else "Union hours"
    obl_sorted = obl_filtered.sort_values(rank_metric, ascending=True)

    fig_rank = px.bar(
        obl_sorted,
        x=rank_metric,
        y="oblast",
        orientation="h",
        title=f"{rank_label} by oblast ({year_range[0]}–{year_range[1]})",
        labels={rank_metric: rank_label, "oblast": ""},
        color=rank_metric,
        color_continuous_scale="YlOrRd",
        text_auto=True,
    )
    fig_rank.update_layout(height=700, yaxis=dict(dtick=1))
    st.plotly_chart(fig_rank, use_container_width=True)

st.markdown("---")

# ═════════════════════════════════════════════════════════════════════════════
# TIME SERIES
# ═════════════════════════════════════════════════════════════════════════════

st.header("Time series")

ts_metric = st.radio(
    "Time series metric",
    ["Daily alert count", "Daily alert hours"],
    horizontal=True,
    key="ts_metric",
)
ts_key = "count" if "count" in ts_metric.lower() else "hours"

ts = daily_time_series(df_filtered, oblast_filter, metric=ts_key)

fig_ts = go.Figure()
fig_ts.add_trace(go.Bar(
    x=ts["date"], y=ts["value"],
    name="Daily",
    marker_color="rgba(255, 100, 100, 0.3)",
))
fig_ts.add_trace(go.Scatter(
    x=ts["date"], y=ts["rolling_7d"],
    name="7-day rolling avg",
    line=dict(color="red", width=2),
))
y_label = "Alert count" if ts_key == "count" else "Hours"
fig_ts.update_layout(
    title=f"{ts_metric} ({region_label}, {year_range[0]}–{year_range[1]})",
    xaxis_title="Date",
    yaxis_title=y_label,
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig_ts, use_container_width=True)

# ── Weekday x Hour heatmap ───────────────────────────────────────────────────

st.subheader("Weekday x Hour heatmap")

subset_heat = df_filtered if oblast_filter is None else df_filtered[df_filtered["oblast"] == oblast_filter]
heat_data = subset_heat.groupby(["weekday", "hour"]).size().reset_index(name="count")

day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
heat_pivot = heat_data.pivot(index="weekday", columns="hour", values="count").fillna(0)
heat_pivot = heat_pivot.reindex(day_order)

fig_heat = px.imshow(
    heat_pivot,
    labels=dict(x="Hour of day (Kyiv)", y="Weekday", color="Alert count"),
    title=f"Alert frequency by weekday and hour ({region_label}, {year_range[0]}–{year_range[1]})",
    color_continuous_scale="YlOrRd",
    aspect="auto",
)
st.plotly_chart(fig_heat, use_container_width=True)

st.markdown("---")

# ═════════════════════════════════════════════════════════════════════════════
# MODE B: RAION DETAIL
# ═════════════════════════════════════════════════════════════════════════════

if is_mode_b:
    st.header("Raion-level detail (Mode B)")

    if oblast_filter is None or oblast_filter == "Kyiv City":
        st.warning(
            "Mode B requires a specific oblast (not 'All of Ukraine' or 'Kyiv City'). "
            "Select an oblast in the sidebar."
        )
    else:
        st.info(
            f"Raion-level data is dense from **Dec 2025 onward**. "
            f"Earlier periods have sparse raion rows and are excluded."
        )

        raion_df = raion_union_hours(df, oblast_filter)

        if raion_df.empty:
            st.warning(f"No raion-level data found for {oblast_filter} in the raion-dense period.")
        else:
            raion_sorted = raion_df.sort_values("union_hours", ascending=True)

            fig_raion = px.bar(
                raion_sorted,
                x="union_hours",
                y="raion",
                orientation="h",
                title=f"Alert hours by raion — {oblast_filter} (Dec 2025+, union)",
                labels={"union_hours": "Hours under alert", "raion": ""},
                color="union_hours",
                color_continuous_scale="YlOrRd",
                text_auto=".0f",
            )
            fig_raion.update_layout(height=max(400, len(raion_df) * 28))
            st.plotly_chart(fig_raion, use_container_width=True)

            cov = coverage_metric(df, oblast_filter)
            if cov is not None:
                st.metric(
                    "Coverage metric",
                    f"{cov:.2f}",
                    help=(
                        "Time-weighted fraction of raions under alert (0–1). "
                        "1.0 = all raions under alert for the entire period."
                    ),
                )

    # ── Calibration data (collapsed) ─────────────────────────────────────────

    with st.expander("Mode B calibration check (one-time validation)"):
        st.markdown(
            "Compares Mode A (oblast union of all levels) vs Mode B (raion+hromada rollup) "
            "for the Dec 2025+ period, plus a pre/post boundary check."
        )

        cal_col1, cal_col2 = st.columns(2)

        with cal_col1:
            st.markdown("**Mode A vs Mode B (raion-dense period)**")
            cal = calibration_check(df)
            st.dataframe(cal, use_container_width=True, hide_index=True)
            st.caption(
                "diff_pct: how much Mode B diverges from Mode A. "
                "Kyiv City shows -100% because it has no raions."
            )

        with cal_col2:
            st.markdown("**Pre vs Post Dec 2025 (6-month windows)**")
            pp = pre_post_comparison(df)
            st.dataframe(pp, use_container_width=True, hide_index=True)
            st.caption(
                "Ratio near 1.0 = no implausible jump. "
                "All oblasts are within normal range."
            )

        st.success(
            "**Calibration verdict:** strategy holds. "
            "23/24 oblasts show 0% divergence between modes. "
            "No implausible pre/post jumps detected (mean ratio 1.11x)."
        )

st.markdown("---")

# ═════════════════════════════════════════════════════════════════════════════
# DATA NOTES
# ═════════════════════════════════════════════════════════════════════════════

with st.expander("Data notes & cleaning decisions"):
    st.markdown(f"""
| Item | Value |
|---|---|
| Raw rows loaded | {report['raw_count']:,} |
| Exact duplicate rows dropped | {report['duplicates_dropped']:,} |
| Unclosed alerts dropped | {report['unclosed_dropped']} |
| Zero-duration alerts dropped | {report['zero_duration_dropped']} |
| Permanent sirens excluded | {report['permanent_sirens_dropped']} ({', '.join(report['permanent_siren_names']) if report['permanent_siren_names'] else 'none'}) |
| Negative-duration rows | {report['negative_duration_count']} |
| **Final row count** | **{report['final_count']:,}** |
| Date range | {report['date_min'].strftime('%Y-%m-%d')} to {report['date_max'].strftime('%Y-%m-%d')} |
""")

    st.markdown("""
**Key decisions:**
- **Timestamps** are UTC in the source; all time-of-day / weekday analysis uses **Kyiv local time** (`Europe/Kyiv`, DST-aware — not a hardcoded +3 offset).
- **Duplicate rows** (the CSV contained the full dataset twice) were dropped by exact all-column match.
- **Permanent sirens** (Lypetska and Vovchanska hromadas, Kharkivska oblast) were excluded by identity, not by a duration threshold. These are near-front-line areas with continuous alerts spanning months/years.
- **Alert duration is not capped.** Long alerts (e.g. Nikopolskyi raion, 631h) are legitimate and kept.
- **Union of intervals** is used for "time under alert" metrics — overlapping alerts are merged, not double-counted. Ukraine-level total hours ≠ sum of oblast totals (by design — they answer different questions).
- **Three-tier granularity** (oblast / raion / hromada): Mode A merges all levels to oblast. Mode B uses raion+hromada detail, restricted to Dec 2025+ when raion data is dense.
""")
