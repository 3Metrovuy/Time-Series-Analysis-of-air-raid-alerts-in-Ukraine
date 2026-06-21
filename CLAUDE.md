# CLAUDE.md — Air Raid Alerts Time Series Analysis (Ukraine)

This file instructs Claude Code on how to build this project. Read it fully before
writing any code. When a decision is ambiguous, prefer the rule written here over
your default; if something here is genuinely unspecified, ask before guessing.

---

## 1. Project goal

A Python tool that performs **time series analysis of air raid alerts in Ukraine**
and presents the results in an interactive **Streamlit** web app.

The point is to turn a flat log of alert intervals into readable, defensible answers
to questions like: *when and where is it most/least dangerous, and how has that
changed over time?* — measured by both **number of alerts** and **total hours under
alert** (these are different metrics and can disagree; always be explicit about which
one a given chart uses).

This is a 2-day project. Favor correctness, clear data handling, and a clean app over
breadth of features. Do not over-engineer.

---

## 2. Data source

- **File:** the official dataset CSV will be committed manually to the repo by the
  user (do not scrape, do not call any API, do not fetch from Telegram). Expect it at
  `data/official_data_en.csv`. If the exact filename differs, read whatever single
  CSV is in `data/`.
- **Origin:** `Vadimkin/ukrainian-air-raid-sirens-dataset` (official subset). All
  timestamps in the file are **UTC**.
- **Verified schema** (confirmed against the actual file — 7 columns):

  | column | meaning |
  |---|---|
  | `oblast` | region name, always present (e.g. `Kharkivska oblast`) |
  | `raion` | district name, blank for oblast-level rows |
  | `hromada` | community name, blank unless the row is hromada-level |
  | `level` | granularity of THIS row: one of `oblast`, `raion`, `hromada` |
  | `started_at` | alert start, UTC, e.g. `2022-03-15 16:10:34+00:00` |
  | `finished_at` | alert end, UTC |
  | `source` | always `official` in this file |

  Still run `df.head()` / dtypes as the first action to confirm nothing changed, but
  build to this schema. One row = one alert interval at the level given by `level`.
- **Key consequence:** the parent oblast is **already in every row** (`oblast` column),
  so there is **no raion→oblast lookup to build** — rolling a raion/hromada row up to
  its oblast is just reading the `oblast` field. (The earlier plan assumed a single
  `region` string needing a mapping table; that was wrong.)
- **Time range:** the file runs from **15 March 2022** to the present (~272k rows).
  Analyze from the true start; do NOT clip to 2023.

### Granularity is mixed — and present from day one (critical — do not skip)

The dataset is **three-tier**: rows exist at `oblast`, `raion`, AND `hromada` level,
distinguished by the `level` column. Mixed levels are present **throughout the whole
timeline**, not only after Dec 2025 — even early-2022 rows include hromada-level
entries. What changed in **Dec 2025** is that finer-grained (raion) alerts became the
*dominant* mode, where before, oblast-level rows dominated.

**Why this matters:** naively counting "alerts per oblast" across all rows
double-counts — a single oblast-wide threat can appear as one `oblast` row, or as
several `raion`/`hromada` rows for the same oblast at overlapping times. Counting all
rows inflates exactly the periods (and oblasts) with finer reporting, silently breaking
year-over-year trends.

This project therefore has **two analysis modes**, both built:

#### Mode A — Oblast level (simple, the default; spans the whole timeline)

Roll everything up to oblast so the entire 2022→now timeline is on one consistent
scale. Because the `oblast` column is always populated, rollup needs no lookup table.
- For each oblast, take the **union of all its intervals across every level**
  (`oblast` + `raion` + `hromada` rows for that oblast) — see §3a for the union rule.
  The oblast is "under alert" if ANY row for it (at any level) is active.
- **Do NOT use a "≥50% of raions" threshold.** Rationale (a deliberate rejected
  alternative worth recording in the reflection): a fractional threshold has no
  physical meaning (one raion with a power plant ≠ three rural ones), and worse, it
  destroys backward comparability — the early timeline is dominated by whole-oblast
  rows that would always count, so an identical later threat firing in 4 of 9 raions
  would count as zero and produce a fake cliff caused purely by the rule. "Any sub-unit
  active" is the only definition consistent across the whole timeline.
- Accept that "any sub-unit" slightly overstates *area* coverage in finer-grained
  periods, and document that in the data-notes panel. To preserve the "how much of the
  oblast was affected" signal without a meaningless threshold, ALSO compute an optional
  **coverage metric**: the time-weighted fraction of an oblast's raions under alert
  (continuous 0–1, only well-defined in the raion-dominant period). Show it where
  useful; never use it as a binary gate.

Mode A answers all cross-time questions ("safest weekday in Kharkivska oblast",
year-over-year trends, etc.) on these unioned oblast-level intervals.

#### Mode B — Raion level (detailed; raion-dominant period only)

Structure: **oblast is the parent, raions are children** ("folder / subfolder" model).
Anything that applies at oblast level fans out to each raion. When the user picks
Kharkivska oblast in this mode, show per-raion results (e.g. most dangerous day in a
period computed separately for each raion, plus the oblast rollup), using rows where
`level` is `raion` (and optionally `hromada` rolled up to raion).

Important honesty constraint: **dense raion-level data only exists from ~Dec 2025
onward.** Earlier years have sparse-to-no raion rows, so Mode B cannot meaningfully
answer "most dangerous raion in 2024" — the app must make this explicit and restrict
Mode B's date range to the period where raion data is actually dense, rather than
silently returning empty or misleading results.

#### Mode B calibration check (run ONCE, during calibration — not every run)

The raion-level approach needs to be **validated once**, when it is first built /
calibrated — not re-run on every analysis afterward. Treat this as a one-time gate:
prove the strategy is sound, record the verdict, then trust it and stop re-checking.

During that single calibration pass:
- Roll the Mode B raion-level results up to oblast and **compare against Mode A**
  (the oblast-level union) for the same overlapping period. They should be close — the
  union of raion intervals should approximate the oblast-level "under alert" time.
- Compare the raion-dominant period against earlier years for the same oblasts: do
  per-oblast alert counts / hours jump by an implausible factor purely at the Dec-2025
  boundary? A modest rise is real; a 5–10× cliff is an artifact of granularity.
- **If consistent:** record the comparison numbers and the "strategy holds" verdict
  once (in the data-notes panel and/or a comment), and from then on Mode B runs
  normally without repeating the comparison.
- **If the data looks crazy** (large unexplained discontinuity, raion rollup diverging
  sharply from the oblast union): **do NOT silently proceed.** Surface it — show the
  specific divergent numbers, explain what looks wrong, and **propose concrete
  alternative strategies** (e.g. cap Mode B to oblast-union only, weight by coverage,
  exclude hromada-level rows from the union, or treat the two eras separately) for the
  user to choose. The user decides; Claude Code flags and proposes.

Do this comparison only at calibration time (or if the user explicitly asks to
re-validate). Normal Mode A / Mode B analysis runs must NOT redo the before-vs-after
comparison as routine work.

---

## 3. Duration & "time under alert" (read before any duration code)

### 3a. The overlap problem and the union rule

Alert duration is NOT simply "sum of (finished_at − started_at) over rows" once you
aggregate across regions, because **alerts in different regions overlap in time** and
summing them double-counts. Example: Kharkiv 19:00–19:25 and Kyiv 19:15–onward — naive
summing counts the 19:15–19:25 overlap twice.

Rules, by scope:

- **Single oblast, "time under alert":** an oblast has many overlapping intervals
  (from `oblast`, `raion`, and `hromada` rows for that oblast, often overlapping in
  time). Compute total time as the **union of intervals** — merge overlapping/touching
  intervals across all levels, then sum the merged lengths. This is the standard "merge
  overlapping intervals" operation. The result is wall-clock time the oblast was under
  alert by *at least one* alert at any level.

- **Ukraine level, "time under alert":** likewise the **union across all regions** —
  total wall-clock time during which *somewhere in Ukraine* was under alert. Do not sum
  per-oblast totals.

- **Per-region burden (additive view):** keep a separate, simple metric = sum of each
  oblast's own union-duration. This IS meaningfully additive across oblasts and answers
  "summed regional alert-hours". 

**Make this explicit in the app:** because of the union rule, **Ukraine-level total
alert hours ≠ the sum of oblast totals** — by design. They answer different questions
("how long was *somewhere* under threat" vs "summed regional burden"). Every duration
chart must label which metric it uses so a screenshot is self-explanatory. When in
doubt about which to show, show both.

Implement the interval-union as one well-tested pure function (sort by start, sweep,
merge). This is the single most error-prone piece of logic in the project — give it a
tiny unit test with a hand-checked example.

---

## 4. Data cleaning rules (make every rule visible, not silent)

Cleaning decisions are graded. Each rule below must (a) be applied and (b) report what
it did (counts) somewhere the user can see — log to console AND surface a short
"data notes" summary in the app.

1. **Parse timestamps as UTC**, then derive a Kyiv-local column (see §5). Keep UTC as
   the source of truth.
2. **Unclosed / missing-end alerts:** detect rows where `finished_at` is missing/null.
   (Verified: the current file has **zero** such rows, so this should be a no-op — but
   keep the check, since the file updates daily and a future row could be unclosed.)
   Report the count; if any are found, **drop them** — do not impute a fake end. State
   the count in the data-notes panel even when it's zero.
3. **Permanent / occupied-territory sirens:** there are known never-ending sirens
   (Luhansk, Crimea). The official dataset is reported to already exclude these, but
   **verify**: if any region shows a single alert spanning months, flag it by name and
   exclude that specific known case. Exclude by *identity*, not by a duration threshold.
4. **DO NOT cap alert duration.** Long real alerts (e.g. a 30+ hour Kharkiv alert) are
   legitimate data and must be kept. Magnitude is signal, not noise.
5. **Compute `duration`** = `finished_at - started_at` (in minutes; expose hours where
   useful). Sanity-check for negative or zero durations and report any.

Put a concise, in-app **"Data notes & cleaning decisions"** expander listing: rows
loaded, rows dropped (unclosed), known sirens excluded, final row count, date range
covered. This doubles as documentation and as evidence of process.

---

## 5. Timezone (do not hardcode an offset)

All display/analysis of *time-of-day* and *weekday* must be in **Kyiv local time**.

- **Do NOT hardcode GMT+3.** Ukraine observes DST: EET (UTC+2) in winter, EEST (UTC+3)
  in summer. A fixed +3 corrupts every winter timestamp and breaks night-hours and
  time-of-day stats.
- Correct approach: timestamps are UTC → convert with the **`Europe/Kyiv`** zone
  (`tz_localize('UTC').tz_convert('Europe/Kyiv')` or zoneinfo). This handles DST
  automatically.
- Derive `weekday`, `hour`, `month`, `year`, `season`, and a `is_night` flag from the
  **Kyiv-local** timestamp, not UTC.
- Define "night" explicitly (e.g. 22:00–06:00 Kyiv) and put the definition in a
  constant so it's easy to find and justify.

---

## 6. Analysis features

### 6a. Landing summary (shown first, no input required)

A clean header section of headline numbers and a couple of overview charts:

- **Total hours under air alert** (whole country, whole period).
- **Night-hours share:** how many of those hours fell in the night window (§5).
  Present the raw stat rigorously; the "this many hours Ukrainians could have slept"
  line is allowed but as a clearly-labeled *human-impact callout*, not as a headline
  metric. Keep it removable.
- **Average alert duration** in Ukraine.
- **Pie/treemap:** total alert duration share by oblast.
- **Bar chart:** total alert duration per year for all of Ukraine.

Keep this section readable at a glance — big numbers + 2 charts, not a wall.

### 6b. Interactive exploration (the key feature: variability)

Let the user choose what to see. At minimum:

- **Region selector:** all of Ukraine, or a specific oblast.
- **Year / date-range selector.**
- **Metric selector:** count of alerts vs total hours under alert.
- **Breakdown selector:** by weekday / by hour-of-day / by month / by season / by year.

From those inputs, answer the core questions:
- safest / most dangerous **weekday**, **month**, **season**, **year**
- safest / most dangerous **time of day**
- most / least affected **oblast**

Each result should state the metric used and the date range, so a screenshot is
self-explanatory.

### 6c. At least one true time-series view

The task is *time series* analysis — at least one chart must have a real time axis:
- alerts (or alert-hours) **per day over time**, with a **7-day rolling average**, is
  the minimum. A weekday × hour heatmap is a strong optional addition.

---

## 7. Tech & libraries

- **Python 3.11+**, **pandas** for all data manipulation.
- **Streamlit** for the UI. Note: Streamlit *is* a real web app — it generates the web
  UI from Python. We use it deliberately to spend our time on correct analysis, not on
  hand-rolling a frontend. A custom HTML/React frontend is out of scope for 2 days.
- **Plotly** preferred for interactive charts (hover, zoom); **matplotlib** acceptable
  for static ones. Either is fine — don't mix needlessly.
- Use **`@st.cache_data`** on the load+clean function so the CSV isn't re-parsed on
  every widget interaction.
- Keep dependencies minimal and pinned in `requirements.txt`.

---

## 8. Repo structure (suggested)

```
.
├── CLAUDE.md
├── README.md            # human-facing: what it is, how to run, data source, decisions
├── requirements.txt
├── data/
│   └── official_data_en.csv   # committed manually by user
├── src/
│   ├── load.py          # load + clean + normalize-to-oblast + tz convert (cached)
│   ├── analysis.py      # pure pandas functions: metrics, group-bys, rolling avg
│   └── app.py           # Streamlit UI; imports from load/analysis only
└── reflection.txt       # ~100-word reflection (see §10)
```

Keep **analysis logic pure and separate** from the Streamlit UI: `analysis.py`
functions take a dataframe + params and return a dataframe/number, with no Streamlit
calls. This makes the logic testable and the app thin. Add a couple of lightweight
assertions or a tiny test for the trickiest function (the raion→oblast interval union).

---

## 8b. Session logging (required)

Maintain an `ai_log.md` file in the repo root as you work. After each user prompt,
append:
- the user's prompt (verbatim or near-verbatim), and
- a short summary of your response / what you decided and why.

Do **not** log every code diff or intermediate edit — only the prompt and your
answer/decision per turn. Keep it readable as a narrative of the session.

This is a best-effort convenience copy. The **authoritative** AI log for submission is
the full conversation export from the Claude Code interface itself; `ai_log.md` is a
secondary, human-readable record, not a replacement for that export.

---

## 9. Engineering principles

- **Verify the data before building on it.** Read the real columns/dtypes/head of the
  CSV first; don't assume schema. If reality differs from §2, adapt and note it.
- Prefer **adaptive, skip-and-continue** handling over hard crashes: if a region name
  is unmapped, log it and continue rather than aborting the whole run.
- Identify and fix the **specific** problem rather than rewriting working code from
  scratch.
- Comment the *why* behind each cleaning/normalization choice — these comments are part
  of the deliverable's quality.
- Concise, readable code over clever code.

---

## 10. Deliverables (this is a hiring task — process is graded)

1. **Working code** in the repo (this project).
2. **AI interaction log** — exported separately by the user. Build in a way that
   produces a good log: propose, get challenged, correct, iterate. Don't silently
   accept first drafts.
3. **`reflection.txt`** (~100 words, plain text) answering: what went wrong, how the
   approach was adjusted, why the final version is better than the first attempt.
   Good honest material to draw on: choosing the clean official dataset over scraping;
   catching the Dec-2025 oblast→raion granularity break; rejecting a blanket duration
   cap in favor of identity-based exclusion of permanent sirens; fixing the GMT+3 →
   Europe/Kyiv DST bug; using interval-union (not naive summing) for overlapping alert
   durations; rejecting a "≥50% of raions" threshold for backward-comparability reasons;
   and validating the raion-level approach against the oblast baseline once during
   calibration before trusting it (the Mode B calibration check).

Done = the app runs with `streamlit run src/app.py`, loads the committed CSV, shows the
summary + interactive views, and the data-notes panel honestly reports the cleaning.
