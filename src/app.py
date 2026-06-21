import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from load import load_and_clean, NIGHT_START, NIGHT_END
from analysis import (
    oblast_union_hours,
    ukraine_union_hours,
    ukraine_alert_count,
    union_night_hours,
    alerts_by_weekday,
    alerts_by_hour,
    alerts_by_month,
    alerts_by_season,
    alerts_by_year,
    yearly_union_hours,
    daily_time_series,
    oblast_raion_treemap,
    raion_union_hours,
    coverage_metric,
    RAION_DENSE_START,
)

st.set_page_config(
    page_title="Air Raid Alerts in Ukraine",
    page_icon="\U0001F6A8",
    layout="wide",
)

# ── Load data ────────────────────────────────────────────────────────────────

df, report = load_and_clean()


# ── Cached aggregation wrappers ──────────────────────────────────────────────
# Each interval-merge over the ~158k-row table costs ~1–2 s, and several run per
# rerun. These wrappers key on cheap, hashable params (year range / oblast /
# metric) and slice the session-constant `df` internally, so repeated widget
# interactions hit the cache instead of recomputing. (Analysis funcs stay
# Streamlit-free; the caching lives here in the UI layer.)

def _slice_years(yr):
    return df[(df["year"] >= yr[0]) & (df["year"] <= yr[1])]


def _work_df(yr, oblast, raion_detail):
    f = _slice_years(yr)
    if raion_detail:
        return f[
            (f["oblast"] == oblast)
            & (f["level"].isin(["raion", "hromada"]))
            & (f["started_at"] >= RAION_DENSE_START)
        ]
    return f


@st.cache_data(show_spinner=False)
def cx_headline(yr, oblast):
    f = _slice_years(yr)
    s = f if oblast is None else f[f["oblast"] == oblast]
    if s.empty:
        return 0.0, 0, 0.0, 0.0
    return (
        ukraine_union_hours(s),
        ukraine_alert_count(s),
        float(s["duration_min"].mean()),
        union_night_hours(s, None, NIGHT_START, NIGHT_END),
    )


@st.cache_data(show_spinner=False)
def cx_oblast_union(yr):
    return oblast_union_hours(_slice_years(yr))


@st.cache_data(show_spinner=False)
def cx_treemap(yr, metric):
    return oblast_raion_treemap(_slice_years(yr), metric)


@st.cache_data(show_spinner=False)
def cx_raion_union(yr, oblast):
    return raion_union_hours(_slice_years(yr), oblast)


@st.cache_data(show_spinner=False)
def cx_daily(yr, oblast, raion_detail, metric):
    wd = _work_df(yr, oblast, raion_detail)
    return daily_time_series(wd, None if raion_detail else oblast, metric)


@st.cache_data(show_spinner=False)
def cx_yearly(yr, oblast, raion_detail):
    wd = _work_df(yr, oblast, raion_detail)
    result = yearly_union_hours(wd, None if raion_detail else oblast)
    return result[(result["year"] >= yr[0]) & (result["year"] <= yr[1])]


@st.cache_data(show_spinner=False)
def cx_coverage(yr, oblast):
    return coverage_metric(_slice_years(yr), oblast)

# ── Sidebar ──────────────────────────────────────────────────────────────────

st.sidebar.title("Settings")

level_mode = st.sidebar.radio(
    "Analysis level",
    ["Oblast level", "Raion level"],
    help=(
        "Oblast level: full timeline, all sub-levels merged up to oblast. "
        "Raion level: per-raion detail for one oblast (raion data is dense "
        "from Dec 2025 onward)."
    ),
)
is_raion_mode = level_mode.startswith("Raion")

region_options = ["All of Ukraine"] + sorted(df["oblast"].unique())
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

# ── Derived scope ────────────────────────────────────────────────────────────

df_filtered = df[(df["year"] >= year_range[0]) & (df["year"] <= year_range[1])]

# Raion-detail view: a specific oblast in raion mode → work on that oblast's
# raion/hromada rows in the raion-dense period.
use_raion_detail = (
    is_raion_mode and oblast_filter is not None and oblast_filter != "Kyiv City"
)
if use_raion_detail:
    wd = df_filtered[
        (df_filtered["oblast"] == oblast_filter)
        & (df_filtered["level"].isin(["raion", "hromada"]))
        & (df_filtered["started_at"] >= RAION_DENSE_START)
    ]
    wd_oblast = None  # wd is already one oblast's raions
    region_label = f"{oblast_filter} — raions (Dec 2025+)"
else:
    wd = df_filtered
    wd_oblast = oblast_filter
    region_label = selected_region

# Hour-based breakdowns double-count overlapping regional alerts when the scope
# is the whole country, so they are only meaningful for a single region.
block_hours_breakdown = oblast_filter is None and not use_raion_detail

# ═════════════════════════════════════════════════════════════════════════════
# LANDING SUMMARY (always on top; adapts to the chosen region & date range)
# ═════════════════════════════════════════════════════════════════════════════

st.title("Air Raid Alerts in Ukraine")
st.caption(
    f"Data: {report['date_min'].strftime('%d %b %Y')} – "
    f"{report['date_max'].strftime('%d %b %Y')} | "
    f"Source: official Ukrainian air raid siren dataset"
)

# ── Headline metrics (for the selected region) ───────────────────────────────

total_hours, total_episodes, avg_duration_min, night_hours = cx_headline(
    year_range, oblast_filter
)

scope_caption = "All of Ukraine" if oblast_filter is None else oblast_filter
st.subheader(f"Summary — {scope_caption} ({year_range[0]}–{year_range[1]})")

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Total hours under alert",
    f"{total_hours:,.0f} h",
    help="Wall-clock hours under alert (interval union — overlaps merged, not double-counted).",
)
col2.metric(
    "Alert episodes",
    f"{total_episodes:,}",
    help="Distinct alert episodes (union of overlapping intervals).",
)
col3.metric("Avg alert duration", f"{avg_duration_min:.0f} min")
col4.metric(
    f"Night hours ({NIGHT_START}:00–{NIGHT_END:02d}:00)",
    f"{night_hours:,.0f} h",
    help=(
        f"Union alert-hours falling in the {NIGHT_START}:00–{NIGHT_END:02d}:00 "
        "Kyiv-time night window."
    ),
)

# ── Landing charts ───────────────────────────────────────────────────────────

unit_label = "hours under alert" if metric_key == "total_hours" else "alert episodes"

# All-Ukraine treemap — click an oblast to drill into its raions
tree_df = cx_treemap(year_range, metric_key)
fig_tree = px.treemap(
    tree_df,
    path=[px.Constant("Ukraine"), "oblast", "raion"],
    values="value",
    color="value",
    color_continuous_scale="OrRd",
    title=f"{unit_label.capitalize()} by oblast — click an oblast to see its raions",
)
fig_tree.update_traces(textinfo="label+value+percent parent", maxdepth=2)
fig_tree.update_layout(margin=dict(t=50, l=0, r=0, b=0), height=620)

if oblast_filter is not None:
    ids = list(fig_tree.data[0].ids)
    widths, colors = [], []
    for node in ids:
        parts = str(node).split("/")
        on_branch = oblast_filter in parts
        widths.append(4 if on_branch else 0.5)
        colors.append("#1c83e1" if on_branch else "rgba(0,0,0,0.1)")
    fig_tree.data[0].marker.line.width = widths
    fig_tree.data[0].marker.line.color = colors

st.plotly_chart(fig_tree, use_container_width=True)

if oblast_filter is not None:
    yr0 = cx_yearly(year_range, oblast_filter, False)
    if not yr0.empty:
        fig_yr = px.bar(
            yr0,
            x="year",
            y="union_hours",
            title=f"Total hours under alert per year — {oblast_filter}",
            labels={"union_hours": "Hours under alert", "year": "Year"},
            text_auto=".0f",
        )
        fig_yr.update_traces(marker_color="#83c9ff")
        fig_yr.update_layout(xaxis=dict(dtick=1), height=420)
        st.plotly_chart(fig_yr, use_container_width=True)

st.markdown("---")

# ═════════════════════════════════════════════════════════════════════════════
# INTERACTIVE EXPLORATION
# ═════════════════════════════════════════════════════════════════════════════

st.header("Interactive exploration")
st.subheader(f"{region_label} | {year_range[0]}–{year_range[1]} | {metric_label}")

BREAKDOWN_FUNCS = {
    "Weekday": (alerts_by_weekday, "weekday"),
    "Hour of day": (alerts_by_hour, "hour"),
    "Month": (alerts_by_month, "month"),
    "Season": (alerts_by_season, "season"),
    "Year": (alerts_by_year, "year"),
}

func, x_col = BREAKDOWN_FUNCS[breakdown_label]
breakdown_df = func(wd, wd_oblast)

# Resolve which metric the breakdown can honestly show.
if block_hours_breakdown and metric_key == "total_hours":
    st.info(
        "Hour-based breakdowns for **All of Ukraine** would double-count overlapping "
        "regional alerts, so they are not meaningful country-wide. Showing **alert "
        "counts** instead — pick a specific region for hour-based breakdowns."
    )
    bd_metric, bd_metric_label = "alert_count", "Alert count"
else:
    bd_metric, bd_metric_label = metric_key, metric_label

if breakdown_df.empty:
    st.info("No data for this selection.")
else:
    fig_break = px.bar(
        breakdown_df,
        x=x_col,
        y=bd_metric,
        title=f"{bd_metric_label} by {breakdown_label.lower()} ({region_label}, {year_range[0]}–{year_range[1]})",
        labels={bd_metric: bd_metric_label, x_col: breakdown_label},
        text_auto=".0f" if bd_metric == "total_hours" else True,
        color=bd_metric,
        color_continuous_scale="YlOrRd",
    )
    if breakdown_label == "Hour of day":
        fig_break.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig_break, use_container_width=True)

    safest_idx = breakdown_df[bd_metric].idxmin()
    danger_idx = breakdown_df[bd_metric].idxmax()
    unit = "alerts" if bd_metric == "alert_count" else "hours"
    s1, s2 = st.columns(2)
    s1.success(
        f"**Safest {breakdown_label.lower()}:** {breakdown_df.loc[safest_idx, x_col]} "
        f"({breakdown_df.loc[safest_idx, bd_metric]:,.0f} {unit})"
    )
    s2.error(
        f"**Most dangerous {breakdown_label.lower()}:** {breakdown_df.loc[danger_idx, x_col]} "
        f"({breakdown_df.loc[danger_idx, bd_metric]:,.0f} {unit})"
    )

# ── Oblast ranking (All of Ukraine, oblast mode) ─────────────────────────────
if oblast_filter is None and not is_raion_mode:
    st.subheader("Oblast ranking")
    obl_rank = cx_oblast_union(year_range)
    rank_metric = "alert_count" if metric_key == "alert_count" else "union_hours"
    rank_label = "Alert episodes" if metric_key == "alert_count" else "Hours under alert"
    obl_rank = obl_rank.sort_values(rank_metric, ascending=True)

    fig_rank = px.bar(
        obl_rank,
        x=rank_metric,
        y="oblast",
        orientation="h",
        title=f"{rank_label} by oblast ({year_range[0]}–{year_range[1]})",
        labels={rank_metric: rank_label, "oblast": ""},
        color=rank_metric,
        color_continuous_scale="YlOrRd",
        text_auto=".0f",
    )
    fig_rank.update_layout(height=700, yaxis=dict(dtick=1))
    st.plotly_chart(fig_rank, use_container_width=True)

st.markdown("---")

# ═════════════════════════════════════════════════════════════════════════════
# TIME SERIES (obeys the main metric selector — no separate switch)
# ═════════════════════════════════════════════════════════════════════════════

st.header("Time series")

ts_key = "count" if metric_key == "alert_count" else "hours"
ts = cx_daily(year_range, oblast_filter, use_raion_detail, ts_key)

if ts.empty:
    st.info("No data for this selection.")
else:
    y_label = "Alert episodes" if ts_key == "count" else "Hours under alert"
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
    fig_ts.update_layout(
        title=f"Daily {y_label.lower()} ({region_label}, {year_range[0]}–{year_range[1]})",
        xaxis_title="Date",
        yaxis_title=y_label,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig_ts, use_container_width=True)
    if ts_key == "hours":
        st.caption(
            "Daily hours are day-clipped union time (bounded by 24 h/day), so the "
            "series is correct even for All of Ukraine."
        )

# ── Weekday × Hour heatmap (obeys the main metric) ───────────────────────────

st.subheader("Weekday × Hour heatmap")

heat_subset = wd if wd_oblast is None else wd[wd["oblast"] == wd_oblast]

if block_hours_breakdown and metric_key == "total_hours":
    st.caption(
        "Showing alert **counts** — hour-bucketed hours would double-count "
        "country-wide. Pick a region for an hours heatmap."
    )
    heat_value_kind = "count"
else:
    heat_value_kind = metric_key

day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
if heat_subset.empty:
    st.info("No data for this selection.")
else:
    if heat_value_kind == "total_hours":
        heat_data = (
            heat_subset.groupby(["weekday", "hour"])["duration_min"].sum().div(60).reset_index(name="value")
        )
        color_label = "Hours (by start hour)"
        kind_word = "hours"
    else:
        heat_data = heat_subset.groupby(["weekday", "hour"]).size().reset_index(name="value")
        color_label = "Alert count"
        kind_word = "frequency"

    heat_pivot = heat_data.pivot(index="weekday", columns="hour", values="value").fillna(0)
    heat_pivot = heat_pivot.reindex(day_order)

    fig_heat = px.imshow(
        heat_pivot,
        labels=dict(x="Hour of day (Kyiv time, UTC+2/+3)", y="Weekday", color=color_label),
        title=f"Alert {kind_word} by weekday and hour ({region_label}, {year_range[0]}–{year_range[1]})",
        color_continuous_scale="YlOrRd",
        aspect="auto",
    )
    st.plotly_chart(fig_heat, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# RAION-LEVEL COVERAGE (raion mode, specific oblast)
# ═════════════════════════════════════════════════════════════════════════════

if is_raion_mode:
    st.markdown("---")
    st.header("Raion-level coverage")

    if oblast_filter is None or oblast_filter == "Kyiv City":
        st.warning(
            "Raion-level analysis needs a specific oblast (not 'All of Ukraine' or "
            "'Kyiv City', which has no raions). Pick one in the sidebar or on the map. "
            "All charts above will then switch to raion granularity for that oblast."
        )
    else:
        cov = cx_coverage(year_range, oblast_filter)
        if cov is None:
            st.info(f"No raion-level coverage data for {oblast_filter} in the raion-dense period.")
        else:
            st.metric(
                f"Coverage metric — {oblast_filter}",
                f"{cov:.2f}",
                help=(
                    "Time-weighted average share of the oblast's raions under alert "
                    "simultaneously (Dec 2025+). 1.0 = alerts are oblast-wide; lower = "
                    "alerts are localized to a few raions."
                ),
            )
