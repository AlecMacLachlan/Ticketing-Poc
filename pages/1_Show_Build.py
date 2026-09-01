"""Screen 1 — Show Build.

Pick a venue + stage configuration + date, then click "Build Show" to get a
pre-populated seat map, holds, pricing, and pre-sale schedule. Every value
is editable and labelled with where it came from. Export to .xlsx at the
bottom.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from branding import inject_brand_css, render_header
from synthetic_data import (
    DEFAULT_SEED,
    HOLD_TYPE_DEFAULTS,
    PARTNERS_BY_CITY,
    PRESALE_WINDOW_TEMPLATES,
    STAGE_CONFIG_TEMPLATES,
    VENUES_BY_ID,
    build_all,
)
from ui_helpers import (
    HOLD_TYPE_LABELS,
    build_seat_map_figure,
    export_show_build_xlsx,
    resolve_holds_from_counts,
    resolve_partner_ticket_allocations,
    stable_seed,
)

st.set_page_config(page_title="Show Build", page_icon="🏟️", layout="wide")
inject_brand_css(st)
render_header(st, "Screen 1 — Show Build")


@st.cache_data
def _load_world():
    return build_all(seed=DEFAULT_SEED)


world = _load_world()
venues_df = world["venues"]
event_history_all = world["event_history"]

st.caption(
    "Illustrative demo data — venues, artists, and history below are synthetic, "
    "generated for this conversation."
)


# ===========================================================================
# BASE SHOW-BUILD GENERATION (template default, or copied from a previous
# show with a small illustrative variation applied)
# ===========================================================================
def _round_to_5(x: float) -> int:
    return int(round(x / 5.0) * 5)


def _generate_base_show_build(venue_id: str, config_id: str, source_tag: str):
    seats_venue = world["seats"][world["seats"]["venue_id"] == venue_id]
    excluded = next(
        c for c in STAGE_CONFIG_TEMPLATES[venue_id] if c["config_id"] == config_id
    )["excluded_categories"]

    if source_tag == "template":
        holds_df = world["holds"][
            (world["holds"]["venue_id"] == venue_id) & (world["holds"]["config_id"] == config_id)
        ].copy()
        holds_df["source"] = "Template default"
        pricing_df = world["pricing_zones"][world["pricing_zones"]["venue_id"] == venue_id].copy()
        pricing_df["source"] = "Template default"
        presale_df = pd.DataFrame(PRESALE_WINDOW_TEMPLATES).copy()
        presale_df["source"] = "Template default"
        return holds_df, pricing_df, presale_df, "Template default"

    event_id = source_tag.split(":", 1)[1]
    event_row = world["event_history"].set_index("event_id").loc[event_id]
    label = f"Copied from previous show: {event_row['event_name']} ({event_row['event_date']})"
    seed = stable_seed("prev_show_jitter", event_id)
    jitter_rng = np.random.default_rng(seed)

    sellable_pool_full = seats_venue[~seats_venue["category"].isin(excluded)]
    pool = sellable_pool_full.copy()
    holds_rows = []
    for hold_type, defaults in HOLD_TYPE_DEFAULTS.items():
        pct = defaults["pct_of_house"] * jitter_rng.uniform(0.8, 1.2)
        n = min(max(1, round(len(sellable_pool_full) * pct)), len(pool))
        sampled = pool.sample(n=n, random_state=int(jitter_rng.integers(0, 2**31 - 1)))
        for _, s in sampled.iterrows():
            holds_rows.append({
                "venue_id": venue_id, "config_id": config_id, "hold_type": hold_type,
                "section": s["section"], "seat_id": s["seat_id"], "source": label,
                "note": defaults["note"],
            })
        pool = pool.drop(sampled.index)
    holds_df = pd.DataFrame(holds_rows)

    price_factor = round(float(jitter_rng.uniform(0.9, 1.15)), 2)
    pricing_df = world["pricing_zones"][world["pricing_zones"]["venue_id"] == venue_id].copy()
    pricing_df["price"] = pricing_df["price"].apply(lambda p: _round_to_5(p * price_factor))
    pricing_df["source"] = f"{label} — prices scaled {price_factor:.2f}x vs. template"

    presale_df = pd.DataFrame(PRESALE_WINDOW_TEMPLATES).copy()
    day_jitter = jitter_rng.integers(-1, 2, size=len(presale_df))
    presale_df["days_before_onsale"] = (presale_df["days_before_onsale"] + day_jitter).clip(lower=0)
    alloc_jitter = jitter_rng.uniform(-0.03, 0.03, size=len(presale_df))
    adjusted = (presale_df["allotment_pct"] + alloc_jitter).clip(lower=0.02)
    presale_df["allotment_pct"] = (adjusted / adjusted.sum()).round(3)
    presale_df["source"] = label

    return holds_df, pricing_df, presale_df, label


# ===========================================================================
# SELECTION CONTROLS (staged — nothing below reacts to these until "Build
# Show" is clicked)
# ===========================================================================
def _reset_pending_to_template():
    st.session_state["sb_pending_source_tag"] = "template"


col1, col2 = st.columns(2)
with col1:
    sel_venue_id = st.selectbox(
        "Venue",
        venues_df["venue_id"],
        format_func=lambda vid: (
            f"{VENUES_BY_ID[vid]['name']} — {VENUES_BY_ID[vid]['city']} "
            f"({VENUES_BY_ID[vid]['venue_type'].title()}, ~{VENUES_BY_ID[vid]['target_capacity']:,} cap)"
        ),
        key="venue_select",
        on_change=_reset_pending_to_template,
    )

live_config_lookup = {c["config_id"]: c for c in STAGE_CONFIG_TEMPLATES[sel_venue_id]}
with col2:
    sel_config_id = st.selectbox(
        "Stage configuration",
        list(live_config_lookup.keys()),
        format_func=lambda cid: live_config_lookup[cid]["name"],
        key=f"config_select_{sel_venue_id}",
        on_change=_reset_pending_to_template,
    )
st.caption(f"**{live_config_lookup[sel_config_id]['name']}** — {live_config_lookup[sel_config_id]['description']}")

col3, col4, col5 = st.columns(3)
with col3:
    sel_event_name = st.text_input(
        "Event name", key="event_name_input", placeholder="e.g. Electric Wolves: World Tour"
    )
with col4:
    default_event_date = date.today() + timedelta(days=60)
    sel_event_date = st.date_input("Event date", value=default_event_date, key="event_date_input")
with col5:
    if "onsale_date_input" not in st.session_state:
        st.session_state["onsale_date_input"] = sel_event_date - timedelta(days=75)
    sel_onsale_date = st.date_input("Public on-sale date", key="onsale_date_input")


# ===========================================================================
# START FROM A PREVIOUS SHOW AT THIS VENUE (also just stages — still
# requires "Build Show" to apply)
# ===========================================================================
def _use_previous_show():
    ev_id = st.session_state.get("prev_event_select")
    if not ev_id:
        return
    ev_row = event_history_all.set_index("event_id").loc[ev_id]
    vid = st.session_state["venue_select"]
    st.session_state[f"config_select_{vid}"] = ev_row["config_id"]
    st.session_state["sb_pending_source_tag"] = f"event:{ev_id}"


with st.expander("Start from a previous show at this venue", expanded=False):
    venue_history = event_history_all[event_history_all["venue_id"] == sel_venue_id].sort_values(
        "event_date", ascending=False
    )
    if venue_history.empty:
        st.caption("No history recorded for this venue yet.")
    else:
        hist_lookup = venue_history.set_index("event_id")
        pcol1, pcol2 = st.columns([3, 1])
        with pcol1:
            st.selectbox(
                "Previous show",
                venue_history["event_id"],
                format_func=lambda eid: (
                    f"{hist_lookup.loc[eid, 'event_name']} — {hist_lookup.loc[eid, 'event_date']} "
                    f"({hist_lookup.loc[eid, 'config_name']}, "
                    f"{hist_lookup.loc[eid, 'sell_through_pct'] * 100:.0f}% sold)"
                ),
                key="prev_event_select",
            )
        with pcol2:
            st.write("")
            st.button("Use as starting point →", on_click=_use_previous_show, use_container_width=True)
        st.caption(
            "This copies that show's stage configuration, holds, pricing, and pre-sale schedule — "
            "with a small illustrative variation applied (see Assumptions below), not identical numbers. "
            "Click **Build Show** below to apply it."
        )


# ===========================================================================
# BUILD SHOW — nothing below this point reacts until the button is clicked
# (or on first load, which auto-builds once so the page isn't empty).
# ===========================================================================
pending_source_tag = st.session_state.get("sb_pending_source_tag", "template")
pending = {
    "venue_id": sel_venue_id,
    "config_id": sel_config_id,
    "event_name": sel_event_name,
    "event_date": sel_event_date,
    "onsale_date": sel_onsale_date,
    "source_tag": pending_source_tag,
}

if "sb_committed" not in st.session_state:
    st.session_state["sb_committed"] = dict(pending)

has_pending_changes = pending != st.session_state["sb_committed"]

st.divider()
build_clicked = st.button(
    "🏗️  Build Show",
    type="primary",
    use_container_width=True,
    help="Apply the parameters above — regenerates the seat map, holds, pricing, and pre-sale schedule below.",
)
if build_clicked:
    st.session_state["sb_committed"] = dict(pending)
    has_pending_changes = False

if has_pending_changes:
    st.info("Parameters changed — click **Build Show** to update everything below.", icon="⚠️")

committed = st.session_state["sb_committed"]
venue_id = committed["venue_id"]
config_id = committed["config_id"]
event_name = committed["event_name"]
event_date = committed["event_date"]
onsale_date = committed["onsale_date"]
source_tag = committed["source_tag"]

config_lookup = {c["config_id"]: c for c in STAGE_CONFIG_TEMPLATES[venue_id]}


# ===========================================================================
# REGENERATE BASE DATA ONLY WHEN THE BUILT CONTEXT CHANGES
# ===========================================================================
build_key = (venue_id, config_id, source_tag)
build_key_str = f"{venue_id}_{config_id}_{source_tag}"

if st.session_state.get("sb_build_key") != build_key:
    base_holds_df, base_pricing_df, base_presale_df, base_label = _generate_base_show_build(
        venue_id, config_id, source_tag
    )
    st.session_state["sb_build_key"] = build_key
    st.session_state["sb_base_holds_df"] = base_holds_df
    st.session_state["sb_base_pricing_df"] = base_pricing_df
    st.session_state["sb_base_presale_df"] = base_presale_df
    st.session_state["sb_base_label"] = base_label

base_holds_df = st.session_state["sb_base_holds_df"]
base_pricing_df = st.session_state["sb_base_pricing_df"]
base_presale_df = st.session_state["sb_base_presale_df"]
base_label = st.session_state["sb_base_label"]

seats_venue = world["seats"][world["seats"]["venue_id"] == venue_id]
excluded_categories = config_lookup[config_id]["excluded_categories"]


# ===========================================================================
# CAPACITY SUMMARY
# ASSUMPTION: c2-c4 are populated further down, after the Holds table, since
# "Sellable" now depends on which sections the user leaves checked there.
# Streamlit still renders them in this row's position — a column object can
# be written to later in the script and still lands in its original slot.
# ===========================================================================
st.divider()
st.subheader(f"Built: {VENUES_BY_ID[venue_id]['name']} — {config_lookup[config_id]['name']}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total physical seats", f"{len(seats_venue):,}")


# ===========================================================================
# EDITABLE HOLDS — one row per SECTION (not per hold type), so "Total in
# Section" and "Include in Show" are unambiguous section-level facts rather
# than repeated/inconsistent across 4 hold-type rows.
# ===========================================================================
sellable_sections = seats_venue.loc[
    ~seats_venue["category"].isin(excluded_categories), "section"
].unique().tolist()
section_totals = seats_venue.groupby("section").size()

counts_long = (
    base_holds_df.groupby(["hold_type", "section"], as_index=False)
    .size()
    .rename(columns={"size": "count"})
)
pivot = counts_long.pivot(index="section", columns="hold_type", values="count")
pivot = pivot.reindex(sellable_sections).fillna(0)
for ht in HOLD_TYPE_DEFAULTS:
    if ht not in pivot.columns:
        pivot[ht] = 0
pivot = pivot[list(HOLD_TYPE_DEFAULTS.keys())].astype(int)
pivot = pivot.rename(columns=HOLD_TYPE_LABELS)
pivot.index.name = "Section"
pivot = pivot.reset_index()
pivot.insert(1, "Total in Section", pivot["Section"].map(section_totals))
pivot.insert(0, "Include in Show", True)

hold_count_cols = [HOLD_TYPE_LABELS[ht] for ht in HOLD_TYPE_DEFAULTS]
holds_column_config = {
    "Include in Show": st.column_config.CheckboxColumn("Include in Show"),
    "Section": st.column_config.TextColumn("Section", disabled=True),
    "Total in Section": st.column_config.NumberColumn("Total in Section", disabled=True, format="%d"),
}
for label in hold_count_cols:
    holds_column_config[label] = st.column_config.NumberColumn(label, min_value=0, step=1)

st.markdown("**Holds**")
st.caption(f"Source: **{base_label}**")
st.caption(
    "Uncheck **Include in Show** to pull a whole section out of this show — it's greyed out on "
    "the seat map below and dropped from sellable capacity, regardless of the stage configuration."
)
edited_pivot = st.data_editor(
    pivot,
    key=f"holds_editor_{build_key_str}",
    hide_index=True,
    use_container_width=True,
    column_config=holds_column_config,
    column_order=["Include in Show", "Section", "Total in Section"] + hold_count_cols,
)
holds_edited = not edited_pivot[hold_count_cols].equals(pivot[hold_count_cols])
holds_label = f"Manually edited (started from: {base_label})" if holds_edited else base_label

manually_excluded_sections = edited_pivot.loc[~edited_pivot["Include in Show"], "Section"].tolist()

label_to_hold_type = {v: k for k, v in HOLD_TYPE_LABELS.items()}
edited_counts = edited_pivot.melt(
    id_vars=["Section"], value_vars=hold_count_cols, var_name="Hold Type Label", value_name="count"
)
edited_counts["hold_type"] = edited_counts["Hold Type Label"].map(label_to_hold_type)
edited_counts = edited_counts.rename(columns={"Section": "section"})[["hold_type", "section", "count"]]

holds_df = resolve_holds_from_counts(
    seats_venue, excluded_categories, base_holds_df, edited_counts,
    seed=stable_seed("holds_resolve", build_key_str, edited_counts["count"].tolist()),
)
# Sections pulled out of the show aren't part of sellable inventory, so any
# holds sampled there don't count either.
holds_df = holds_df[~holds_df["section"].isin(manually_excluded_sections)]

sellable_mask = (
    (~seats_venue["category"].isin(excluded_categories))
    & (~seats_venue["section"].isin(manually_excluded_sections))
)
sellable_capacity = int(sellable_mask.sum())
if manually_excluded_sections:
    st.caption(f"Pulled from this show: {', '.join(manually_excluded_sections)}")


# ===========================================================================
# PARTNER TICKET ALLOCATION — tranche-based release. Each row allocates a
# fixed ticket count from ONE section to ONE partner, split across up to 3
# tranches. All 3 tranches count as committed/held inventory here (removed
# from general sale) — this screen defines the allocation PLAN. Actually
# gating which tranche is "live" against real-time sell-through is a
# simulation better suited to a future Allotments screen; the thresholds
# below are recorded as part of the plan/export either way.
# ===========================================================================
city = VENUES_BY_ID[venue_id]["city"]
default_partners = PARTNERS_BY_CITY.get(city, [])
dropdown_sections = sorted(sellable_sections)
default_section = dropdown_sections[0] if dropdown_sections else ""

partner_alloc_base = pd.DataFrame({
    "Partner": default_partners,
    "Section": [default_section] * len(default_partners),
    "tranche_1": [10] * len(default_partners),
    "tranche_2": [10] * len(default_partners),
    "tranche_3": [10] * len(default_partners),
})

st.markdown("**Partner ticket allocation**")
st.caption(
    f"Local partners for {city}. Each row allocates a fixed number of tickets from one section, "
    "split across up to 3 release tranches (thresholds below). Add rows (blank row at the bottom, "
    "or the grid's row menu) for more partners or sections — same partner can appear in multiple rows."
)
partner_alloc_column_config = {
    "Partner": st.column_config.TextColumn("Partner"),
    "Section": st.column_config.SelectboxColumn("Section", options=dropdown_sections),
    "tranche_1": st.column_config.NumberColumn("Tranche 1 Tickets", min_value=0, step=1),
    "tranche_2": st.column_config.NumberColumn("Tranche 2 Tickets", min_value=0, step=1),
    "tranche_3": st.column_config.NumberColumn("Tranche 3 Tickets", min_value=0, step=1),
}
edited_partner_alloc = st.data_editor(
    partner_alloc_base,
    key=f"partner_alloc_editor_{build_key_str}",
    hide_index=True,
    use_container_width=True,
    num_rows="dynamic",
    column_config=partner_alloc_column_config,
    column_order=["Partner", "Section", "tranche_1", "tranche_2", "tranche_3"],
)
# Drop rows a user added but hasn't filled in yet.
edited_partner_alloc = edited_partner_alloc[
    edited_partner_alloc["Partner"].notna() & (edited_partner_alloc["Partner"].str.strip() != "")
    & edited_partner_alloc["Section"].notna()
].copy()
for col in ["tranche_1", "tranche_2", "tranche_3"]:
    edited_partner_alloc[col] = edited_partner_alloc[col].fillna(0).astype(int)

st.markdown("**Tranche release thresholds**")
st.caption(
    "Sell-through % of sellable capacity that must be reached before each tranche releases. "
    "Tranche 1 conventionally stays at 0% (available from the start)."
)
tranche_thresholds_base = pd.DataFrame({
    "Tranche": ["Tranche 1", "Tranche 2", "Tranche 3"],
    "threshold_pct": [0.0, 0.5, 0.75],
})
tranche_column_config = {
    "Tranche": st.column_config.TextColumn("Tranche", disabled=True),
    "threshold_pct": st.column_config.NumberColumn(
        "Sell-Through % Required", min_value=0.0, max_value=1.0, step=0.05, format="%.2f"
    ),
}
edited_thresholds = st.data_editor(
    tranche_thresholds_base,
    key=f"tranche_thresholds_editor_{build_key_str}",
    hide_index=True,
    use_container_width=True,
    column_config=tranche_column_config,
)

partner_holds_df = resolve_partner_ticket_allocations(
    seats_venue, set(holds_df["seat_id"]), manually_excluded_sections,
    edited_partner_alloc,
    seed=stable_seed("partner_tranche_holds", build_key_str, edited_partner_alloc.values.tolist()),
)
allocated_total = int(
    (edited_partner_alloc["tranche_1"] + edited_partner_alloc["tranche_2"] + edited_partner_alloc["tranche_3"]).sum()
)
if len(partner_holds_df) < allocated_total:
    st.caption(
        f"⚠️ Allocated {allocated_total:,} partner tickets across all rows, but only {len(partner_holds_df):,} "
        "could be seated (section capacity or overlap with other holds) — transparent, not blocked."
    )

# Combine into the one holds_df used everywhere below (map, metrics, export).
holds_df = pd.concat([holds_df, partner_holds_df], ignore_index=True)

c2.metric("Sellable (this configuration)", f"{sellable_capacity:,}")
c3.metric("Held seats", f"{len(holds_df):,}")
c4.metric("Net available", f"{sellable_capacity - len(holds_df):,}")


# ===========================================================================
# EDITABLE PRICING
# ASSUMPTION: "Final Price ($)" is shown as a separate read-only table right
# below the editable Base Price grid, rather than as a column inside the
# same grid. Streamlit's data_editor only reads its `data=` argument on
# first mount — once a widget key exists, it ignores freshly-recomputed
# values for ANY column (editable or disabled) and only reflects actual
# user edits. A computed column inside that same grid would freeze at its
# initial value and never move when the slider changes. Keeping it as an
# adjacent st.dataframe (which always redraws fresh) is the reliable way to
# get a genuinely live "Base Price x Demand Factor" column.
# ===========================================================================
st.markdown("**Pricing zones**")
st.caption(f"Source: **{base_pricing_df['source'].iloc[0]}**")
demand_factor = st.slider(
    "Demand estimator (multiplies base price to get final price)",
    min_value=0.0, max_value=10.0, value=1.0, step=0.1,
    key=f"demand_factor_{build_key_str}",
)
pricing_display = base_pricing_df[["section", "tier", "price"]].copy()
pricing_column_config = {
    "section": st.column_config.TextColumn("Section", disabled=True),
    "tier": st.column_config.TextColumn("Tier", disabled=True),
    "price": st.column_config.NumberColumn("Base Price ($)", min_value=0, step=5, format="$%d"),
}
edited_pricing = st.data_editor(
    pricing_display,
    key=f"pricing_editor_{build_key_str}",
    hide_index=True,
    use_container_width=True,
    column_config=pricing_column_config,
)
pricing_edited = not edited_pricing["price"].equals(pricing_display["price"])
pricing_label = (
    f"Manually edited (started from: {base_pricing_df['source'].iloc[0]})"
    if pricing_edited else base_pricing_df["source"].iloc[0]
)
if demand_factor != 1.0:
    pricing_label += f" — demand factor {demand_factor:.1f}x applied"

pricing_df = base_pricing_df.copy()
pricing_df["base_price"] = edited_pricing["price"].values
pricing_df["price"] = (pricing_df["base_price"] * demand_factor).round().astype(int)
pricing_df["source"] = pricing_label

st.caption(f"Final Price ($) = Base Price × {demand_factor:.1f} — this is what's used on the seat map and in the export.")
st.dataframe(
    pricing_df[["section", "tier", "base_price", "price"]].rename(columns={
        "section": "Section", "tier": "Tier", "base_price": "Base Price ($)", "price": "Final Price ($)",
    }),
    hide_index=True, use_container_width=True,
)


# ===========================================================================
# EDITABLE PRE-SALE WINDOWS
# ===========================================================================
st.markdown("**Pre-sale windows**")
st.caption(f"Source: **{base_presale_df['source'].iloc[0]}**")
presale_display = base_presale_df[["window_name", "days_before_onsale", "duration_hours", "allotment_pct"]].copy()
presale_display["start_date"] = presale_display["days_before_onsale"].apply(
    lambda d: onsale_date - timedelta(days=int(d))
)
presale_display = presale_display[
    ["window_name", "start_date", "days_before_onsale", "duration_hours", "allotment_pct"]
]
presale_column_config = {
    "window_name": st.column_config.TextColumn("Window", disabled=True),
    "start_date": st.column_config.DateColumn("Opens On", disabled=True),
    "days_before_onsale": st.column_config.NumberColumn("Days before on-sale", min_value=0, step=1),
    "duration_hours": st.column_config.NumberColumn("Duration (hrs)", min_value=0, step=1),
    "allotment_pct": st.column_config.NumberColumn("Allotment % (0-1)", min_value=0.0, max_value=1.0, step=0.01, format="%.2f"),
}
st.caption(
    "**Opens On** reflects Days-before-on-sale as of the last refresh (Build Show, or changing the "
    "Public on-sale date above). Editing Days-before-on-sale here updates the schedule used downstream "
    "immediately either way — this column's display just catches up on the next refresh."
)
edited_presale = st.data_editor(
    presale_display,
    key=f"presale_editor_{build_key_str}_{onsale_date.isoformat()}",
    hide_index=True,
    use_container_width=True,
    column_config=presale_column_config,
    column_order=["window_name", "start_date", "days_before_onsale", "duration_hours", "allotment_pct"],
)
presale_edit_cols = ["days_before_onsale", "duration_hours", "allotment_pct"]
presale_edited = not edited_presale[presale_edit_cols].equals(presale_display[presale_edit_cols])
presale_label = (
    f"Manually edited (started from: {base_presale_df['source'].iloc[0]})"
    if presale_edited else base_presale_df["source"].iloc[0]
)
presale_df = edited_presale.copy()
# Recompute fresh (not from the possibly-stale "Opens On" display column above) so
# downstream consumers (seat map, export) are always accurate.
presale_df["start_date"] = presale_df["days_before_onsale"].apply(lambda d: onsale_date - timedelta(days=int(d)))
presale_df["source"] = presale_label

allotment_sum = presale_df["allotment_pct"].sum()
if abs(allotment_sum - 1.0) > 0.02:
    st.caption(f"⚠️ Allotment % across windows sums to {allotment_sum:.0%}, not 100% — transparent, not blocked.")


# ===========================================================================
# SEAT MAP — colour-coded by pricing zone, held seats visually distinct
# ===========================================================================
st.divider()
st.subheader("Seat map")
st.plotly_chart(
    build_seat_map_figure(
        seats_venue, excluded_categories, holds_df, pricing_df,
        layout=VENUES_BY_ID[venue_id]["layout"],
        excluded_sections=manually_excluded_sections,
    ),
    use_container_width=True,
)


# ===========================================================================
# ASSUMPTIONS — visible on screen, not just in code
# ===========================================================================
st.divider()
with st.expander("Assumptions used on this page", expanded=False):
    hold_bullets = "\n".join(
        f"  - **{HOLD_TYPE_LABELS[ht]}**: ~{d['pct_of_house']*100:.1f}% of sellable capacity by default — {d['note']}"
        for ht, d in HOLD_TYPE_DEFAULTS.items()
    )
    st.markdown(
        f"""
- Default hold sizes, applied as a % of this configuration's sellable capacity:
{hold_bullets}
- **"Start from a previous show"** doesn't copy last time's numbers verbatim — it applies a small
  illustrative variation (±20% on hold sizes, a single 0.90x–1.15x price-scaling factor across all
  tiers, ±1 day on pre-sale window timing) to represent that no two shows are configured identically.
  Everything is still editable below regardless of where it came from.
- Editing a hold count keeps existing held seats where possible and only samples new/removed seats
  for the row you changed — it won't reshuffle holds elsewhere on the map.
- **Include in Show** (in the Holds table) is a manual, per-section override on top of the stage
  configuration — a section can be technically sellable under the configuration but still pulled from
  this specific show. It's reflected in sellable capacity, the seat map, and the export.
- **Partner ticket allocation**: each venue's city has 2 local partners contractually held tickets on
  every show there. Each row allocates a fixed ticket count from one section, split across up to 3
  release tranches — this screen records the allocation *plan*; simulating which tranche is actually
  "live" against real-time sell-through is a job for a future Allotments screen, not tracked here (all
  3 tranches count as held/committed inventory regardless). Partner allocations and tranche thresholds
  get their own sheets in the export, and partner-held seats show on the seat map.
- The arena's bowl shape/proportions are modelled on a classic NHL arena (e.g. UBS Arena, home of the
  New York Islanders) — geometry only, no real team name, logo, or colors.
- All prices, sell-through %, and revenue figures anywhere in this app are synthetic.
"""
    )


# ===========================================================================
# EXPORT
# ===========================================================================
st.divider()
st.subheader("Export")
st.caption("Mirrors the manifest handed to Ticketmaster today: event info, full seat manifest, pricing, holds, and pre-sale schedule.")

xlsx_bytes = export_show_build_xlsx(
    venue=VENUES_BY_ID[venue_id],
    config_name=config_lookup[config_id]["name"],
    event_name=event_name or "(untitled show)",
    event_date=event_date,
    onsale_date=onsale_date,
    seats_venue=seats_venue,
    excluded_categories=excluded_categories,
    holds_df=holds_df,
    pricing_df=pricing_df,
    presale_df=presale_df,
    excluded_sections=manually_excluded_sections,
    partner_allocations_df=edited_partner_alloc.rename(columns={
        "tranche_1": "Tranche 1 Tickets", "tranche_2": "Tranche 2 Tickets", "tranche_3": "Tranche 3 Tickets",
    }),
    tranche_thresholds_df=edited_thresholds.rename(columns={"threshold_pct": "Sell-Through % Required"}),
)
st.download_button(
    "Download show manifest (.xlsx)",
    data=xlsx_bytes,
    file_name=f"{VENUES_BY_ID[venue_id]['name'].replace(' ', '_')}_{event_date}_manifest.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
