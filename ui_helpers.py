"""
Shared UI-only helpers for the Streamlit app: display constants, the seat
map figure builder, and the .xlsx export.

Kept separate from synthetic_data.py on purpose — synthetic_data.py is the
swappable data layer (real venue structure could replace it later), this
module is presentation logic that stays regardless of where the data
comes from.
"""

from __future__ import annotations

import hashlib
from datetime import date
from io import BytesIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from synthetic_data import HOLD_TYPE_DEFAULTS


def stable_seed(*parts) -> int:
    """Deterministic seed from arbitrary parts — stable across reruns AND
    process restarts (unlike Python's built-in hash() on strings, which is
    randomized per-process). Used so 'random' choices in the app (which
    seats get added when a hold count is edited, how a copied show's
    numbers get jittered) don't reshuffle every time Streamlit reruns."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16)

# ===========================================================================
# HOLD DISPLAY CONSTANTS
# ASSUMPTION: colors chosen to be distinct from the pricing-tier palette in
# synthetic_data.TIER_COLORS so held seats never get mistaken for a pricing
# tier on the seat map. Marker symbol is 'x' on top of color, so the
# distinction still reads for colorblind users.
# ===========================================================================
HOLD_TYPE_COLORS = {
    "artist_hold": "#E63946",
    "house_hold": "#F4A261",
    "promoter_hold": "#2A9D8F",
    "partner_hold": "#9B5DE5",
}
HOLD_TYPE_LABELS = {
    "artist_hold": "Artist Hold",
    "house_hold": "House Hold",
    "promoter_hold": "Promoter Hold",
    "partner_hold": "Partner Hold",
}
NOT_SELLABLE_COLOR = "#D9D9D9"


# ===========================================================================
# SEAT MAP
# ===========================================================================
def build_seat_map_figure(seats_venue: pd.DataFrame, excluded_categories: list[str],
                           holds_df: pd.DataFrame, pricing_df: pd.DataFrame,
                           layout: str = "fan", excluded_sections: list[str] | None = None) -> go.Figure:
    held_lookup = (holds_df.set_index("seat_id")["hold_type"].to_dict()
                    if not holds_df.empty else {})
    partner_lookup = (holds_df.set_index("seat_id")["partner"].dropna().to_dict()
                       if not holds_df.empty and "partner" in holds_df.columns else {})
    tier_lookup = pricing_df.set_index("section")[["tier", "color", "price"]].to_dict("index")
    excluded_sections = excluded_sections or []

    fig = go.Figure()

    not_sellable_mask = (
        seats_venue["category"].isin(excluded_categories)
        | seats_venue["section"].isin(excluded_sections)
    )
    sellable = seats_venue[~not_sellable_mask].copy()
    sellable["hold_type"] = sellable["seat_id"].map(held_lookup)
    unheld = sellable[sellable["hold_type"].isna()]

    for section, grp in unheld.groupby("section"):
        info = tier_lookup.get(section, {"color": "#999999", "price": "?", "tier": "?"})
        fig.add_trace(go.Scattergl(
            x=grp["x"], y=grp["y"], mode="markers",
            marker=dict(size=4, color=info["color"]),
            name=f"{section} — ${info['price']} ({info['tier']})",
            legendgroup="sellable",
            hovertext=grp["section"] + " " + grp["row_label"] + grp["seat_number"].astype(str)
            + f"<br>${info['price']} ({info['tier']})",
            hoverinfo="text",
        ))

    held = sellable[sellable["hold_type"].notna()]
    for hold_type, grp in held.groupby("hold_type"):
        base_text = grp["section"] + " " + grp["row_label"] + grp["seat_number"].astype(str)
        if hold_type == "partner_hold":
            detail = "HELD — Partner Hold: " + grp["seat_id"].map(partner_lookup).fillna("")
        else:
            detail = f"HELD — {HOLD_TYPE_LABELS.get(hold_type, hold_type)}"
        fig.add_trace(go.Scattergl(
            x=grp["x"], y=grp["y"], mode="markers",
            marker=dict(size=4, color=HOLD_TYPE_COLORS.get(hold_type, "#333333"), symbol="x"),
            name=HOLD_TYPE_LABELS.get(hold_type, hold_type),
            legendgroup="holds",
            hovertext=base_text + "<br>" + detail,
            hoverinfo="text",
        ))

    not_sellable = seats_venue[not_sellable_mask]
    if not not_sellable.empty:
        fig.add_trace(go.Scattergl(
            x=not_sellable["x"], y=not_sellable["y"], mode="markers",
            marker=dict(size=4, color=NOT_SELLABLE_COLOR),
            name="Not sellable (configuration or unchecked section)",
            legendgroup="excluded",
            hoverinfo="skip",
            opacity=0.6,
        ))

    if layout == "stadium":
        # Stage end is the +x short edge (see synthetic_data's stadium layout note).
        # If that end is excluded from sale, the stage is physically there (end-stage
        # setup); otherwise (e.g. "in the round") the stage is at center floor instead.
        stage_end_excluded = any("stage_end" in c for c in excluded_categories)
        if stage_end_excluded:
            stage_x = seats_venue["x"].max() + 6
            fig.add_annotation(x=stage_x, y=0, text="STAGE", showarrow=False,
                                font=dict(size=13, color="white"), bgcolor="#333333",
                                bordercolor="#333333", borderpad=6, textangle=90)
        else:
            fig.add_annotation(x=0, y=0, text="STAGE", showarrow=False,
                                font=dict(size=13, color="white"), bgcolor="#333333",
                                bordercolor="#333333", borderpad=6)
    else:
        y_min = seats_venue["y"].min()
        fig.add_annotation(x=0, y=y_min - 6, text="STAGE", showarrow=False,
                            font=dict(size=13, color="white"), bgcolor="#333333",
                            bordercolor="#333333", borderpad=6)

    fig.update_layout(
        showlegend=True,
        xaxis=dict(visible=False, scaleanchor="y", scaleratio=1),
        yaxis=dict(visible=False, autorange="reversed"),
        height=650,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="top", y=-0.05, font=dict(size=10)),
        plot_bgcolor="white",
    )
    return fig


# ===========================================================================
# EXCEL EXPORT — mirrors the manifest a venue today hands to Ticketmaster.
# ===========================================================================
def export_show_build_xlsx(venue: dict, config_name: str, event_name: str,
                            event_date: date, onsale_date: date,
                            seats_venue: pd.DataFrame, excluded_categories: list[str],
                            holds_df: pd.DataFrame, pricing_df: pd.DataFrame,
                            presale_df: pd.DataFrame,
                            excluded_sections: list[str] | None = None,
                            partner_allocations_df: pd.DataFrame | None = None,
                            tranche_thresholds_df: pd.DataFrame | None = None) -> bytes:
    excluded_sections = excluded_sections or []
    held_lookup = (holds_df.set_index("seat_id")[["hold_type", "note"]].to_dict("index")
                   if not holds_df.empty else {})
    price_lookup = pricing_df.set_index("section")[["tier", "price"]].to_dict("index")

    # ASSUMPTION: presale windows aren't tied to specific seats in this data
    # model (they're a time/allotment-% concept, not a seat-level one), so
    # every sellable seat gets the same backstop reference: the public
    # on-sale date/window, i.e. the date it's guaranteed available by.
    manifest_rows = []
    for _, seat in seats_venue.iterrows():
        excluded = seat["category"] in excluded_categories or seat["section"] in excluded_sections
        hold_info = held_lookup.get(seat["seat_id"])
        if excluded:
            status = "Not Sellable"
        elif hold_info:
            status = f"Held — {HOLD_TYPE_LABELS.get(hold_info['hold_type'], hold_info['hold_type'])}"
        else:
            status = "Sellable"
        price_info = price_lookup.get(seat["section"], {})
        manifest_rows.append({
            "Section": seat["section"], "Row": seat["row_label"], "Seat": seat["seat_number"],
            "Seat ID": seat["seat_id"], "Tier": price_info.get("tier", ""),
            "Price": price_info.get("price", ""), "Status": status,
            "Hold Note": hold_info["note"] if hold_info else "",
            "On-Sale Date": onsale_date.isoformat(), "Sale Window": "Public On-Sale",
        })
    manifest_df = pd.DataFrame(manifest_rows)

    sellable_count = (
        (~seats_venue["category"].isin(excluded_categories))
        & (~seats_venue["section"].isin(excluded_sections))
    ).sum()
    info_df = pd.DataFrame([
        ("Venue", venue["name"]),
        ("City", venue["city"]),
        ("Stage Configuration", config_name),
        ("Event Name", event_name),
        ("Event Date", event_date.isoformat()),
        ("Public On-Sale Date", onsale_date.isoformat()),
        ("Total Physical Seats", int(len(seats_venue))),
        ("Sellable Capacity (this configuration)", int(sellable_count)),
        ("Held Seats", int(len(holds_df))),
        ("Generated (illustrative demo data)", date.today().isoformat()),
    ], columns=["Field", "Value"])

    # Same terminology as the new Seat Manifest columns ("On-Sale Date" / "Sale Window"),
    # so the two sheets read as one connected story rather than two vocabularies.
    presale_export = presale_df.copy()
    if "start_date" in presale_export.columns:
        presale_export["start_date"] = presale_export["start_date"].astype(str)
    presale_export = presale_export.rename(columns={"window_name": "Sale Window", "start_date": "On-Sale Date"})

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        info_df.to_excel(writer, sheet_name="Event Info", index=False)
        manifest_df.to_excel(writer, sheet_name="Seat Manifest", index=False)
        pricing_df[["section", "tier", "price", "source"]].to_excel(writer, sheet_name="Pricing Zones", index=False)
        if not holds_df.empty:
            holds_df[["hold_type", "section", "seat_id", "note", "source"]].to_excel(
                writer, sheet_name="Holds", index=False)
        presale_export.to_excel(writer, sheet_name="Presale Windows", index=False)
        if partner_allocations_df is not None and not partner_allocations_df.empty:
            partner_allocations_df.to_excel(writer, sheet_name="Partner Holds", index=False)
        if tranche_thresholds_df is not None and not tranche_thresholds_df.empty:
            tranche_thresholds_df.to_excel(writer, sheet_name="Tranche Thresholds", index=False)
    return buffer.getvalue()


# ===========================================================================
# HOLD COUNT EDITING
# The holds table is edited at the (hold_type, section) aggregate level —
# editing individual seat-by-seat holds isn't a realistic UI for a venue
# this size. resolve_holds_from_counts is a PURE function of the current
# target counts: given the same counts it always samples the same seats
# (seeded via stable_seed), so unrelated reruns (e.g. typing an event name)
# don't reshuffle which seats are held. Editing one row's count only
# changes that row's seats — everything else is left untouched.
# ===========================================================================
def resolve_holds_from_counts(seats_venue: pd.DataFrame, excluded_categories: list[str],
                               base_holds_df: pd.DataFrame, target_counts: pd.DataFrame,
                               seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    result_rows = []
    committed_ids: set[str] = set()

    for _, row in target_counts.iterrows():
        hold_type, section, target = row["hold_type"], row["section"], int(row["count"])
        if target <= 0:
            continue
        existing = base_holds_df[(base_holds_df["hold_type"] == hold_type) & (base_holds_df["section"] == section)]
        keep_n = min(target, len(existing))
        kept = existing.sample(n=keep_n, random_state=int(rng.integers(0, 2**31 - 1))) if keep_n else existing.iloc[0:0]
        for _, s in kept.iterrows():
            result_rows.append(s.to_dict())
            committed_ids.add(s["seat_id"])

        remaining = target - keep_n
        if remaining > 0:
            candidates = seats_venue[
                (seats_venue["section"] == section)
                & (~seats_venue["category"].isin(excluded_categories))
                & (~seats_venue["seat_id"].isin(committed_ids))
            ]
            add_n = min(remaining, len(candidates))
            if add_n > 0:
                added = candidates.sample(n=add_n, random_state=int(rng.integers(0, 2**31 - 1)))
                note = HOLD_TYPE_DEFAULTS[hold_type]["note"]
                for _, s in added.iterrows():
                    result_rows.append({
                        "venue_id": s["venue_id"], "config_id": None, "hold_type": hold_type,
                        "section": section, "seat_id": s["seat_id"],
                        "source": "Manually edited", "note": note,
                    })
                    committed_ids.add(s["seat_id"])

    return pd.DataFrame(result_rows, columns=["venue_id", "config_id", "hold_type", "section", "seat_id", "source", "note"])


# ===========================================================================
# PARTNER TICKET ALLOCATION
# Each row is a (partner, section) allocation split across up to 3 release
# tranches. Unlike the % model this replaced, allocation is a fixed ticket
# COUNT taken from one specific section (chosen in the UI via a dropdown).
# All 3 tranches are treated as committed/held here — this function defines
# the allocation PLAN; whether tranche 2/3 have actually "released" against
# live sell-through is a simulation for a future Allotments screen, not
# tracked here. Pure function of the current allocation table (seeded via
# stable_seed): editing one row only reshuffles that row's seats.
# ===========================================================================
def resolve_partner_ticket_allocations(seats_venue: pd.DataFrame, other_held_seat_ids: set,
                                        excluded_sections: list[str],
                                        allocation_rows: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    committed_ids: set[str] = set()
    result_rows = []

    for _, row in allocation_rows.iterrows():
        partner, section = row["Partner"], row["Section"]
        t1, t2, t3 = int(row["tranche_1"]), int(row["tranche_2"]), int(row["tranche_3"])
        total = t1 + t2 + t3
        if total <= 0 or section in excluded_sections:
            continue
        candidates = seats_venue[
            (seats_venue["section"] == section)
            & (~seats_venue["seat_id"].isin(other_held_seat_ids))
            & (~seats_venue["seat_id"].isin(committed_ids))
        ]
        n = min(total, len(candidates))
        if n <= 0:
            continue
        sampled = candidates.sample(n=n, random_state=int(rng.integers(0, 2**31 - 1)))
        for _, s in sampled.iterrows():
            result_rows.append({
                "venue_id": s["venue_id"], "config_id": None, "hold_type": "partner_hold",
                "section": section, "seat_id": s["seat_id"], "partner": partner,
                "source": "Partner allocation",
                "note": f"Held for partner: {partner} (tranches {t1}/{t2}/{t3})",
            })
            committed_ids.add(s["seat_id"])

    return pd.DataFrame(
        result_rows,
        columns=["venue_id", "config_id", "hold_type", "section", "seat_id", "partner", "source", "note"],
    )
