# SOP — Screen 1: Show Build

Standard operating procedure for using the Show Build form in the Live
Event Ticketing POC. This screen builds a single event's seat manifest
(holds, pricing, pre-sale schedule) from a venue template, a previous
show, or your own edits, and exports it to `.xlsx`.

All data in the app is synthetic/illustrative — see the on-screen warning
banner and the "Assumptions used on this page" panel for what's assumed.

## 1. Launch the app

```
cd ~/Documents/Work/ticketing-poc
source .venv/bin/activate
streamlit run app.py
```

Open **Show Build** in the left sidebar.

## 2. The one rule to know: Parameters are staged, everything else is live

The form has two tiers of "editable":

| Area | Behavior |
|---|---|
| Venue, Stage configuration, Event name/date, On-sale date, "Start from a previous show" | **Staged.** Changing these does nothing until you click **🏗️ Build Show**. A banner ("Parameters changed — click Build Show...") appears whenever there's an unbuilt change. |
| Holds table, Partner ticket allocation + thresholds, Pricing table + demand slider, Pre-sale windows table | **Live.** Edits apply immediately — no button needed. The seat map, capacity metrics, and the Excel export always reflect your latest table edits. |

In short: **pick your show, then Build it. After that, fine-tune freely.**

## 3. Step-by-step

**Step 1 — Set the show parameters**
- **Venue**: pick from the dropdown (shows type and rough capacity).
- **Stage configuration**: options change based on venue; each shows a
  one-line description of what it excludes (e.g. "Upper bowl curtained
  off").
- **Event name**: free text (used only in the export filename/sheet).
- **Event date** / **Public on-sale date**: date pickers. On-sale date
  defaults to 75 days before the event date the first time you load the
  page, but doesn't auto-follow the event date after that — set it
  explicitly if you change the event date later.

**Step 2 (optional) — Start from a previous show at this venue**
- Open the expander, pick a past event from the dropdown (shows date,
  configuration used, and sell-through %).
- Click **Use as starting point →**. This sets the Stage configuration
  dropdown to match and stages the copy — it does **not** build yet.
- Note: this doesn't copy last time's numbers exactly. It applies a small
  variation (±20% on hold sizes, one price-scaling factor across all
  tiers, ±1 day on pre-sale timing) so it reads as "a real previous show,"
  not a clone. Details are in the Assumptions panel (Step 8).

**Step 3 — Click 🏗️ Build Show**
- This is the only action that regenerates the seat map, holds, pricing,
  and pre-sale schedule from whatever is currently staged.
- On first page load, it auto-builds once with the default selections so
  the page isn't empty — you don't need to click it before your very
  first look.

**Step 4 — Review the capacity summary**
- Below the Build button: **Total physical seats**, **Sellable (this
  configuration)**, **Held seats**, **Net available**.
- The subheader ("Built: [Venue] — [Configuration]") confirms what's
  currently built, independent of whatever the dropdowns above say if you
  haven't clicked Build again since changing them.

**Step 5 — Review/edit Holds**
- One row per **section**. Columns: **Include in Show** (checkbox),
  Section (fixed), **Total in Section** (fixed — the section's full seat
  count, for reference), then an editable count per hold type (Artist
  Hold / House Hold / Promoter Hold).
- Editing a count takes effect immediately — no Build click needed. The
  app keeps existing held seats where possible and only samples
  new/removed seats for the row you changed; it won't reshuffle holds
  elsewhere on the map.
- **Uncheck Include in Show** to pull an entire section out of this
  specific show — independent of the stage configuration. That section's
  seats grey out on the map, drop out of Sellable/Net Available, and show
  as "Not Sellable" in the export. Re-check it to bring it back.
- The **Source** caption above the table tells you where the current
  numbers came from (Template default / copied from a previous show /
  manually edited).

**Step 5b — Review/edit Partner ticket allocation**
- Just below the Holds table: one grid, one row per **(partner, section)**
  pair. Columns: **Partner** (editable text), **Section** (dropdown of
  this venue's sellable sections), **Tranche 1/2/3 Tickets** (editable
  counts).
- **Add rows** to allocate more partners or sections — use the blank row
  at the bottom of the grid, or its row menu. The same partner can appear
  in multiple rows (e.g. one row per section they're allocated in).
- All 3 tranches count as committed/held inventory right away — this
  screen records the allocation *plan* (how many tickets, released in up
  to 3 stages); it doesn't simulate which tranche is currently "live"
  against real sales (that's a job for a future Allotments screen).
- Below that, **Tranche release thresholds**: one row per tranche, editable
  **Sell-Through % Required** — the sell-through % that conventionally
  unlocks that tranche. Tranche 1 defaults to 0% (available from the
  start).
- Both grids apply immediately. Partner-held seats show on the seat map
  ("Partner Hold" color, hover shows which partner) and are exported to
  their own **Partner Holds** and **Tranche Thresholds** sheets.

**Step 6 — Review/edit Pricing zones**
- A **Demand estimator** slider (0.0x–10.0x, default 1.0x) sits above the
  table — it multiplies every section's base price to produce the final
  price actually used on the seat map and in the export.
- The table itself has **Base Price ($)** editable per section (Section/
  Tier are fixed). Below it, a read-only **Final Price ($)** table shows
  Base Price × the slider value, live.
- Note: Final Price is a *separate* table, not a column inside the same
  editable grid — Streamlit's grid widget can't reliably live-update a
  computed column inside itself when a slider elsewhere changes, so it's
  kept as an adjacent, always-fresh readout instead.

**Step 7 — Review/edit Pre-sale windows**
- One merged grid: **Window** (fixed), **Opens On** (computed), **Days
  before on-sale**, **Duration (hrs)**, **Allotment % (0–1)** (the last
  three editable).
- **Opens On** reflects Days-before-on-sale as of the last refresh (Build
  Show, or changing the Public on-sale date in Step 1) — editing
  Days-before-on-sale in this same grid updates the schedule used
  downstream (map/export) immediately either way, but that column's own
  display catches up on the next refresh rather than instantly. Same
  Streamlit limitation as Step 6.
- If allotment percentages don't sum to ~100%, a caption flags it — this
  is informational only, it won't block you.

**Step 8 — Review the seat map**
- Color-coded by pricing tier; held seats are marked with an "×" in a
  color specific to the hold type (Artist / Production Kill / House /
  Promoter). Sections excluded by the current stage configuration are
  greyed out.
- Hover any point for section/row/seat and price or hold status.
- Check **"Assumptions used on this page"** (expander below the map) for
  the exact hold-default percentages and previous-show jitter ranges in
  effect.

**Step 9 — Export**
- Click **Download show manifest (.xlsx)**.
- The file always reflects your current on-screen state — every table
  edit from Steps 5–7 is included automatically, no separate save step.
- Workbook has 8 sheets: **Event Info**, **Seat Manifest** (every seat,
  with status/final price/hold info, plus **On-Sale Date** and **Sale
  Window** — the public on-sale date/window, since presale windows aren't
  tied to specific seats in this model), **Pricing Zones** (final prices),
  **Holds**, **Presale Windows** (relabeled **On-Sale Date** / **Sale
  Window** to match the manifest), **Partner Holds** (the tranche
  allocation table), **Tranche Thresholds**.

## 4. Common tasks

- **Start over with a clean template**: change the Venue or Stage
  configuration dropdown (even to the same value and back, or pick a
  different one) — this resets the pending source back to "Template
  default" — then click Build Show.
- **Compare two configurations**: build one, note the numbers/export, then
  change Stage configuration, click Build Show again, and compare.
- **Undo a table edit**: there's no undo button — click Build Show again
  (if parameters are unchanged, re-clicking still regenerates the base
  template/previous-show data and discards table edits since the last
  build).

## 5. Troubleshooting

| Symptom | Likely cause |
|---|---|
| Seat map/numbers don't match the dropdowns | You changed a dropdown but haven't clicked **Build Show** yet — check for the "Parameters changed" banner. |
| Export doesn't include a table edit | Shouldn't happen — export always uses live table state. If it does, refresh the page and re-check. |
| "Allotment % ... not 100%" caption | Informational only; adjust the Pre-sale windows table if you want it to sum to 100%. |
| Page looks empty / errors on load | Restart the app (`streamlit run app.py`) — Streamlit's file watcher can lag behind code changes during development. |
