# Project: Live Event Ticketing POC (Streamlit)

## Context
I'm building a proof of concept for a client conversation, not a
production system. The client is a live-event venue/promoter
operation. Today they do all of this manually in Excel and hand the
resulting file to Ticketmaster.

The POC exists to guide a discovery conversation. Its job is to be
specific enough that the client corrects my assumptions. So
assumptions must be VISIBLE on screen, not buried in code.

## Two problems it demonstrates

1. SHOW BUILD — Setting up an event takes up to a full day, 30-50
   times a year per venue. Most of the work repeats but nothing
   carries over. The POC shows a reusable template library.

2. SECONDARY MARKET ALLOTMENTS — Deciding how many seats go to each
   resale partner, and releasing more automatically when sell-through
   thresholds are hit. The POC shows rules applied consistently plus a
   fairness comparison across partners.

## Stack
- Python + Streamlit (no JavaScript)
- Plotly for seat map visualisation
- Pandas for allocation logic
- openpyxl for Excel export
- Session state only. No database, no login, no auth.

## Build order

### Step 1 — Synthetic data generator (do this first, standalone)
Create a module that generates realistic fake data:
- 4-5 venues of different sizes (e.g. 2,500 theatre / 8,000 hall /
  18,000 arena)
- Per venue: sections, rows, seats, with coordinates for plotting
- 2-3 stage configurations per venue (end stage, in-the-round,
  reduced capacity) that change which sections are sellable
- Hold types: artist holds, production kills, house holds, promoter
  holds
- Pricing zones mapped to sections
- Pre-sale windows: fan club, credit card partner, venue members,
  public on-sale
- A history of past events per venue so "start from last show" has
  something to pull from

Keep this in its own file with clear, editable constants. I need to
be able to swap in the client's real structure later.

### Step 2 — Screen 1: Show Build
- Dropdowns: venue, stage configuration, event date
- On selection, auto-populate seat map, default holds, pricing zones,
  pre-sale windows
- Plotly seat map, colour-coded by pricing zone, with held seats
  visually distinct
- Every default must be editable and must display WHERE it came from
  ("inherited from template", "copied from previous show")
- A "start from previous show at this venue" button
- A visible comparison: fields to fill from scratch vs. fields
  pre-populated, with an estimated time saved
- Export to .xlsx — this matters, the export is the deliverable they
  already hand to Ticketmaster

### Step 3 — Screen 2: Allotments
- Partner list (5-6 fake partners) with allocation rules per partner:
  percentage or fixed count, consignment vs. at-risk, price floor
- Bar chart of how inventory splits across partners
- A sell-through slider — as I drag it, trigger rules fire and
  release additional inventory, visibly
- A fairness comparison table so allocations can be checked side by
  side
- Export to .xlsx

## Constraints
- No styling work beyond Streamlit defaults until both screens
  function
- No real optimisation or ML. Transparent, readable rules only.
- All numbers clearly labelled as illustrative
- Comment the assumptions in the code so I can find and change them
  fast during the meeting

## Status
- [x] Step 1 — synthetic data generator (`synthetic_data.py`)
- [x] Step 2 — Screen 1: Show Build (`app.py`, `pages/1_Show_Build.py`, `ui_helpers.py`)
- [ ] Step 3 — Screen 2: Allotments

## Client branding (Oak View Group)
- `branding.py` + `assets/ovg_logo.png` — real OVG logo/colors pulled from
  oakviewgroup.com (black/white/gold, Oswald headings). Applied because OVG
  is who this POC is for, not for redistribution elsewhere.
- The arena's bowl shape/proportions are modelled on a classic NHL arena
  (e.g. UBS Arena, home of the Islanders — an actual OVG-operated building)
  at the user's request. Deliberately does NOT use the Islanders'/NHL's own
  name, logo, or colors — those are a different rights holder than OVG. If
  a fully-themed version is wanted later, flag it explicitly.
- Removed the "time to build this show" estimate panel from Screen 1 (user
  request) — `ui_helpers.py` no longer has time-estimate helpers.
- Screen 1 now stages parameter changes (venue/config/date/previous-show)
  and only regenerates the seat map/holds/pricing/pre-sale on an explicit
  "Build Show" click, instead of reacting live to every dropdown change.
- Brand colors corrected to OVG's actual palette (black/white/blue) — an
  earlier pass wrongly used gold, caught by the user against a live
  screenshot of oakviewgroup.com. `branding.py` now has no gold at all.
- Holds table restructured: one row per **section** (not per hold type),
  with a non-editable "Total in Section" capacity column and an "Include
  in Show" checkbox that pulls a whole section out of the show (greys it
  out on the map, drops it from sellable capacity, marks it "Not
  Sellable" in the export) — independent of the stage configuration.
- "Production Kill" hold type replaced with **Partner Holds**: each
  venue's city has 2 local partners (`PARTNERS_BY_CITY` in
  `synthetic_data.py`), shown on the seat map, exported to their own
  sheet(s).
  - v1 was a flat % of sellable capacity. **Superseded** — see below.
  - Current: **Partner ticket allocation** is one dynamic grid (add rows
    freely) of (Partner, Section, Tranche 1/2/3 Tickets) — Section is a
    dropdown of the venue's sellable sections. A separate **Tranche
    release thresholds** grid records the sell-through % meant to unlock
    each tranche. All 3 tranches count as committed/held inventory now —
    this only records the allocation *plan*; simulating which tranche is
    actually live against real sell-through belongs on a future
    Allotments screen (`resolve_partner_ticket_allocations` in
    `ui_helpers.py`).
- Holds table's Section/Total in Section were already `disabled=True`
  (confirmed, no change needed) when asked to make them read-only.
- **Demand estimator** slider (0–10x, default 1.0) on Pricing zones:
  multiplies each section's editable Base Price into a Final Price, which
  is what the seat map and export actually use. Implemented as an
  adjacent read-only table, not a column inside the same editable grid —
  Streamlit's `st.data_editor` only reads its `data=` argument on first
  mount; once a widget key exists, it ignores freshly-recomputed values
  for ANY column (including disabled ones) and ignores anything except
  actual user edits. A computed column inside the editable grid would
  freeze at its initial value and never move when the slider changes.
  Same constraint applies to the merged Pre-sale grid's "Opens On" column
  (documented in-page and in the SOP) — it only refreshes on remount
  (Build Show, or changing the on-sale date), not on every keystroke.
- Pre-sale windows: the two tables (editable schedule + read-only "Opens
  On" preview) are now merged into one grid, accepting the above
  staleness caveat.
- Export manifest gained **On-Sale Date** / **Sale Window** columns
  (constant per row — the public on-sale date/window, since presale
  windows aren't tied to specific seats in this data model) and 2 new
  sheets: **Partner Holds** (the tranche grid) and **Tranche Thresholds**.
  Presale Windows sheet relabeled to the same "On-Sale Date"/"Sale
  Window" terms as the manifest.
- Tried and reverted: coloring the slider track blue via CSS
  (`branding.py`) — BaseWeb's auto-generated classes made the "every div"
  selector paint the *entire* track solid blue (losing the filled/
  unfilled distinction), a regression vs. the default. Left as
  Streamlit's default red; only the tick-bar/value label text is
  brand-colored.

## Docs
- `SOP_Show_Build.md` — step-by-step usage instructions for Screen 1,
  written for whoever is running the demo (not necessarily the author).

## Running it
```
source .venv/bin/activate
streamlit run app.py
```
