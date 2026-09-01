"""
Synthetic data generator for the live-event ticketing POC.

Everything a real venue operator would configure by hand in Excel is
represented here as data: physical seats, stage configurations, pricing
zones, holds, pre-sale windows, and event history. Nothing here is real —
venue names, cities, artist names, and all figures are illustrative.

DESIGN NOTE FOR SWAPPING IN REAL DATA LATER
--------------------------------------------
The physical seat map for a venue is generated ONCE from SECTION_TEMPLATES
and stays fixed. A stage configuration never moves seats — it only decides
which section CATEGORIES are sellable for a given show layout (e.g. an
"in-the-round" config sells the sections behind the stage that an
"end stage" config excludes). This mirrors how a real venue's seating
chart is fixed by the building, while the on-sale manifest changes show
to show. When replacing with the client's real structure, keep this split:
physical seats vs. per-show sellability.

All the constants below (VENUES, SECTION_TEMPLATES, STAGE_CONFIG_TEMPLATES,
PRICE_TABLE, HOLD_TYPE_DEFAULTS, PRESALE_WINDOW_TEMPLATES) are the knobs to
edit when swapping in a real client's venues.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from datetime import date, timedelta

# ===========================================================================
# ASSUMPTION: default RNG seed. Re-running build_all(seed=42) always produces
# the same synthetic world, which matters for a demo — numbers on screen
# shouldn't shuffle every time the app reruns. Pass a different seed to
# regenerate a fresh illustrative dataset.
# ===========================================================================
DEFAULT_SEED = 42

TODAY = date(2026, 8, 31)  # ASSUMPTION: fixed "today" so history/on-sale dates are stable for the demo


# ===========================================================================
# VENUES
# ASSUMPTION: 5 fictional venues spanning theatre -> arena, sized roughly to
# the brief (2,500 / 8,000 / 18,000) plus two extra shapes (amphitheater,
# club) to broaden what stage configs can demonstrate. Capacities below are
# *targets*; actual generated seat counts land close but not exact, since
# they fall out of the row/seat formulas in SECTION_TEMPLATES (labelled
# "actual_capacity" wherever it's reported).
# ===========================================================================
VENUES = [
    {
        "venue_id": "VEN-THEATRE-01",
        "name": "The Regency Theatre",
        "city": "Castlemere",
        "venue_type": "theatre",
        "target_capacity": 2500,
        "layout": "fan",
    },
    {
        "venue_id": "VEN-HALL-01",
        "name": "Union Hall",
        "city": "Brackenfield",
        "venue_type": "hall",
        "target_capacity": 8000,
        "layout": "fan",
    },
    {
        "venue_id": "VEN-ARENA-01",
        "name": "Lakeside Arena",
        "city": "Dunwich Falls",
        "venue_type": "arena",
        "target_capacity": 18000,
        # ASSUMPTION: "stadium" = a rounded-rectangle bowl wrapped around a
        # rectangular playing surface (modelled on a classic NHL rink bowl,
        # e.g. UBS Arena — home of the New York Islanders — rather than a
        # full circle). Shape/proportions only: no real team name, logo, or
        # colors are used, since those belong to the Islanders/NHL, not OVG.
        "layout": "stadium",
    },
    {
        "venue_id": "VEN-AMPH-01",
        "name": "Harborview Pavilion",
        "city": "Elmsworth",
        "venue_type": "amphitheater",
        "target_capacity": 5000,
        "layout": "fan",
    },
    {
        "venue_id": "VEN-CLUB-01",
        "name": "The Foundry",
        "city": "Aldergrove",
        "venue_type": "club",
        "target_capacity": 1200,
        "layout": "fan",
    },
]

VENUES_BY_ID = {v["venue_id"]: v for v in VENUES}
STADIUM_VENUE_IDS = {v["venue_id"] for v in VENUES if v["layout"] == "stadium"}


# ===========================================================================
# PRICING TIERS
# ASSUMPTION: five generic tiers, reused across venues. Each venue maps its
# own section categories onto these tiers with its own price table below
# (a "platinum" seat at the theatre isn't priced the same as one at the
# arena). Colors are for the eventual Plotly seat map (Step 2) — kept here
# so pricing and color always travel together.
# ===========================================================================
TIER_COLORS = {
    "platinum": "#8E44AD",
    "gold": "#D4A017",
    "silver": "#7F8C8D",
    "bronze": "#A0522D",
    "ga": "#2E86AB",
    "obstructed": "#5C5C5C",
    "club": "#0B6E4F",
}

# venue_type -> {tier: price ($, illustrative)}
# ASSUMPTION: "club" only exists for the arena today (premium mid-bowl level,
# common in NHL/NBA-style arenas), but a price is defined for every venue
# type for schema completeness.
PRICE_TABLE = {
    "theatre": {"platinum": 165, "gold": 120, "silver": 90, "bronze": 65, "ga": 45, "obstructed": 40, "club": 140},
    "hall": {"platinum": 195, "gold": 140, "silver": 95, "bronze": 70, "ga": 55, "obstructed": 45, "club": 165},
    "arena": {"platinum": 350, "gold": 210, "silver": 130, "bronze": 85, "ga": 60, "obstructed": 50, "club": 275},
    "amphitheater": {"platinum": 180, "gold": 130, "silver": 95, "bronze": 70, "ga": 45, "obstructed": 35, "club": 155},
    "club": {"platinum": 85, "gold": 65, "silver": 50, "bronze": 40, "ga": 35, "obstructed": 30, "club": 75},
}


# ===========================================================================
# SECTION TEMPLATES — the physical seat map, per venue
#
# Coordinates are polar: each section is a wedge (angle_start -> angle_end,
# in degrees, 0 = center facing the stage, positive = stage-left) spanning a
# radius range (radius_start -> radius_end, arbitrary plotting units, stage
# at radius 0). Rows are laid out at even radius steps; if "fan" is True,
# each row has more seats than the last as it widens away from the stage
# (mimics real fan-shaped seating). "is_ga" sections still get seat-like
# coordinates so they can be scatter-plotted, but represent a headcount
# rather than assigned seats.
#
# "category" drives: (a) which stage configs make a section sellable,
# (b) hold-type defaults, (c) pricing tier lookup below via "tier".
# ===========================================================================
SECTION_TEMPLATES: dict[str, list[dict]] = {
    "VEN-THEATRE-01": [
        {"name": "Orchestra Center", "category": "orchestra_center", "tier": "platinum",
         "angle_start": -25, "angle_end": 25, "radius_start": 8, "radius_end": 26,
         "rows": 18, "base_seats_per_row": 22, "fan": True, "is_ga": False},
        {"name": "Orchestra Left", "category": "orchestra_side", "tier": "gold",
         "angle_start": -55, "angle_end": -25, "radius_start": 8, "radius_end": 26,
         "rows": 18, "base_seats_per_row": 8, "fan": True, "is_ga": False},
        {"name": "Orchestra Right", "category": "orchestra_side", "tier": "gold",
         "angle_start": 25, "angle_end": 55, "radius_start": 8, "radius_end": 26,
         "rows": 18, "base_seats_per_row": 8, "fan": True, "is_ga": False},
        {"name": "Mezzanine Center", "category": "mezzanine", "tier": "silver",
         "angle_start": -30, "angle_end": 30, "radius_start": 30, "radius_end": 40,
         "rows": 8, "base_seats_per_row": 31, "fan": True, "is_ga": False},
        {"name": "Mezzanine Left", "category": "mezzanine_side", "tier": "bronze",
         "angle_start": -50, "angle_end": -30, "radius_start": 30, "radius_end": 40,
         "rows": 8, "base_seats_per_row": 11, "fan": True, "is_ga": False},
        {"name": "Mezzanine Right", "category": "mezzanine_side", "tier": "bronze",
         "angle_start": 30, "angle_end": 50, "radius_start": 30, "radius_end": 40,
         "rows": 8, "base_seats_per_row": 11, "fan": True, "is_ga": False},
        {"name": "Balcony", "category": "balcony", "tier": "bronze",
         "angle_start": -45, "angle_end": 45, "radius_start": 44, "radius_end": 54,
         "rows": 12, "base_seats_per_row": 42, "fan": True, "is_ga": False},
    ],
    "VEN-HALL-01": [
        {"name": "Floor GA", "category": "floor_ga", "tier": "ga",
         "angle_start": -50, "angle_end": 50, "radius_start": 6, "radius_end": 24,
         "rows": 12, "base_seats_per_row": 70, "fan": True, "is_ga": True},
        {"name": "Lower Bowl A", "category": "lower_bowl", "tier": "gold",
         "angle_start": -110, "angle_end": -50, "radius_start": 24, "radius_end": 36,
         "rows": 14, "base_seats_per_row": 49, "fan": True, "is_ga": False},
        {"name": "Lower Bowl B", "category": "lower_bowl", "tier": "gold",
         "angle_start": 50, "angle_end": 110, "radius_start": 24, "radius_end": 36,
         "rows": 14, "base_seats_per_row": 49, "fan": True, "is_ga": False},
        {"name": "Lower Bowl Center", "category": "lower_bowl", "tier": "silver",
         "angle_start": -50, "angle_end": 50, "radius_start": 24, "radius_end": 36,
         "rows": 14, "base_seats_per_row": 77, "fan": True, "is_ga": False},
        {"name": "Upper Bowl A", "category": "upper_bowl", "tier": "bronze",
         "angle_start": -125, "angle_end": -70, "radius_start": 38, "radius_end": 50,
         "rows": 16, "base_seats_per_row": 56, "fan": True, "is_ga": False},
        {"name": "Upper Bowl B", "category": "upper_bowl", "tier": "bronze",
         "angle_start": 70, "angle_end": 125, "radius_start": 38, "radius_end": 50,
         "rows": 16, "base_seats_per_row": 56, "fan": True, "is_ga": False},
        {"name": "Rear Bowl", "category": "rear_bowl", "tier": "obstructed",
         "angle_start": 155, "angle_end": 205, "radius_start": 24, "radius_end": 40,
         "rows": 10, "base_seats_per_row": 63, "fan": True, "is_ga": False},
    ],
    # VEN-ARENA-01 is NOT here — it's a "stadium" layout venue, physically
    # generated from STADIUM_SECTION_TEMPLATES below instead of this
    # polar/fan model. See generate_seats() for the dispatch.
    "VEN-AMPH-01": [
        {"name": "Orchestra Reserved", "category": "reserved_pit", "tier": "platinum",
         "angle_start": -35, "angle_end": 35, "radius_start": 8, "radius_end": 20,
         "rows": 14, "base_seats_per_row": 70, "fan": True, "is_ga": False},
        {"name": "Terrace Reserved", "category": "terrace", "tier": "gold",
         "angle_start": -45, "angle_end": 45, "radius_start": 20, "radius_end": 30,
         "rows": 10, "base_seats_per_row": 99, "fan": True, "is_ga": False},
        {"name": "Lawn GA", "category": "lawn", "tier": "ga",
         "angle_start": -55, "angle_end": 55, "radius_start": 30, "radius_end": 48,
         "rows": 12, "base_seats_per_row": 133, "fan": True, "is_ga": True},
    ],
    "VEN-CLUB-01": [
        {"name": "Floor GA", "category": "ga_floor", "tier": "ga",
         "angle_start": -40, "angle_end": 40, "radius_start": 4, "radius_end": 16,
         "rows": 8, "base_seats_per_row": 42, "fan": True, "is_ga": True},
        {"name": "Riser GA", "category": "ga_riser", "tier": "ga",
         "angle_start": -40, "angle_end": 40, "radius_start": 16, "radius_end": 22,
         "rows": 4, "base_seats_per_row": 64, "fan": True, "is_ga": True},
        {"name": "VIP Loft", "category": "loft", "tier": "platinum",
         "angle_start": -30, "angle_end": 30, "radius_start": 23, "radius_end": 27,
         "rows": 3, "base_seats_per_row": 22, "fan": False, "is_ga": False},
    ],
}


# ===========================================================================
# STADIUM LAYOUT — a rounded-rectangle bowl wrapped around a rectangular
# playing surface, used for "stadium"-layout venues (currently just the
# arena). Modelled on a classic NHL arena bowl (shape/proportions only —
# see the "layout" comment on VEN-ARENA-01 above re: no real team branding).
#
# Coordinates: the playing surface is a rounded rectangle centered on the
# origin, half-length RINK_HALF_LENGTH along x, half-width RINK_HALF_WIDTH
# along y, with corners rounded by RINK_CORNER_RADIUS. "Stage End" is the
# short edge at x = +RINK_HALF_LENGTH (where a concert stage would be built
# for an end-stage show, same idea as the old "rear_bowl" exclusion — just
# on a rectangle instead of a circle). Each seating LEVEL (lower bowl, club,
# upper bowl) is a ring drawn at a "scale" factor applied to the rink's own
# half_l/half_w/corner_r (row 1.1x the rink's size, row 2 1.5x, etc) — a
# multiplicative scale rather than an additive offset, so every zone
# (including the short ends) grows at the same proportional rate as it
# moves outward. An additive offset would keep the straight edges a fixed
# length forever and only grow the corners, making the upper deck's ends
# look disproportionately tiny next to its sides.
# ===========================================================================
RINK_HALF_LENGTH = 34
RINK_HALF_WIDTH = 15
RINK_CORNER_RADIUS = 4
FLOOR_MARGIN = 2  # gap between the playing-surface wall and the first floor GA row


def _rounded_rect_zone_bounds(half_l: float, half_w: float, r: float):
    """Arc-length boundaries (start, end) of the 4 zones around a rounded
    rectangle of the given half-length/half-width/corner-radius, walking
    counterclockwise from the bottom of the +x ("stage end") edge."""
    stage_end_len = 2 * (half_w - r)
    corner_len = r * math.pi / 2
    side_straight_len = 2 * (half_l - r)
    side_len = side_straight_len + 2 * corner_len

    b0 = 0.0
    b1 = b0 + stage_end_len
    b2 = b1 + side_len
    b3 = b2 + stage_end_len
    b4 = b3 + side_len
    bounds = {
        "stage_end": (b0, b1),
        "side_a": (b1, b2),
        "far_end": (b2, b3),
        "side_b": (b3, b4),
    }
    return bounds, b4  # b4 == total perimeter


def _point_on_rounded_rect(t_len: float, half_l: float, half_w: float, r: float):
    """(x, y) at arc length t_len along the same walk used by
    _rounded_rect_zone_bounds (0 = bottom of the stage-end edge)."""
    stage_end_len = 2 * (half_w - r)
    corner_len = r * math.pi / 2
    side_straight_len = 2 * (half_l - r)

    t = t_len
    if t < stage_end_len:
        return half_l, -(half_w - r) + t
    t -= stage_end_len
    if t < corner_len:
        theta = t / r
        cx, cy = half_l - r, half_w - r
        return cx + r * math.cos(theta), cy + r * math.sin(theta)
    t -= corner_len
    if t < side_straight_len:
        return (half_l - r) - t, half_w
    t -= side_straight_len
    if t < corner_len:
        theta = math.pi / 2 + t / r
        cx, cy = -(half_l - r), half_w - r
        return cx + r * math.cos(theta), cy + r * math.sin(theta)
    t -= corner_len
    if t < stage_end_len:
        return -half_l, (half_w - r) - t
    t -= stage_end_len
    if t < corner_len:
        theta = math.pi + t / r
        cx, cy = -(half_l - r), -(half_w - r)
        return cx + r * math.cos(theta), cy + r * math.sin(theta)
    t -= corner_len
    if t < side_straight_len:
        return -(half_l - r) + t, -half_w
    t -= side_straight_len
    theta = 3 * math.pi / 2 + t / r
    cx, cy = half_l - r, -(half_w - r)
    return cx + r * math.cos(theta), cy + r * math.sin(theta)


# ASSUMPTION: capacities below were tuned (like the fan venues in Step 1) so
# the arena's actual generated capacity lands close to its ~18,000 target.
STADIUM_SECTION_TEMPLATES: dict[str, list[dict]] = {
    "VEN-ARENA-01": [
        {"name": "Floor GA", "category": "floor_ga", "tier": "gold", "shape": "floor",
         "rows": 22, "cols": 60, "is_ga": True},

        {"name": "Lower Bowl - Stage End", "category": "lower_bowl_stage_end", "tier": "platinum",
         "shape": "ring", "zone": "stage_end", "scale_start": 1.08, "scale_end": 1.55,
         "rows": 16, "seats_per_unit_length": 1.35, "is_ga": False},
        {"name": "Lower Bowl - Side A", "category": "lower_bowl_side_a", "tier": "platinum",
         "shape": "ring", "zone": "side_a", "scale_start": 1.08, "scale_end": 1.55,
         "rows": 16, "seats_per_unit_length": 1.35, "is_ga": False},
        {"name": "Lower Bowl - Far End", "category": "lower_bowl_far_end", "tier": "gold",
         "shape": "ring", "zone": "far_end", "scale_start": 1.08, "scale_end": 1.55,
         "rows": 16, "seats_per_unit_length": 1.35, "is_ga": False},
        {"name": "Lower Bowl - Side B", "category": "lower_bowl_side_b", "tier": "platinum",
         "shape": "ring", "zone": "side_b", "scale_start": 1.08, "scale_end": 1.55,
         "rows": 16, "seats_per_unit_length": 1.35, "is_ga": False},

        {"name": "Club Level - Stage End", "category": "club_stage_end", "tier": "club",
         "shape": "ring", "zone": "stage_end", "scale_start": 1.58, "scale_end": 1.68,
         "rows": 3, "seats_per_unit_length": 1.35, "is_ga": False},
        {"name": "Club Level - Side A", "category": "club_side_a", "tier": "club",
         "shape": "ring", "zone": "side_a", "scale_start": 1.58, "scale_end": 1.68,
         "rows": 3, "seats_per_unit_length": 1.35, "is_ga": False},
        {"name": "Club Level - Far End", "category": "club_far_end", "tier": "club",
         "shape": "ring", "zone": "far_end", "scale_start": 1.58, "scale_end": 1.68,
         "rows": 3, "seats_per_unit_length": 1.35, "is_ga": False},
        {"name": "Club Level - Side B", "category": "club_side_b", "tier": "club",
         "shape": "ring", "zone": "side_b", "scale_start": 1.58, "scale_end": 1.68,
         "rows": 3, "seats_per_unit_length": 1.35, "is_ga": False},

        {"name": "Upper Bowl - Stage End", "category": "upper_bowl_stage_end", "tier": "bronze",
         "shape": "ring", "zone": "stage_end", "scale_start": 1.75, "scale_end": 2.35,
         "rows": 18, "seats_per_unit_length": 1.46, "is_ga": False},
        {"name": "Upper Bowl - Side A", "category": "upper_bowl_side_a", "tier": "silver",
         "shape": "ring", "zone": "side_a", "scale_start": 1.75, "scale_end": 2.35,
         "rows": 18, "seats_per_unit_length": 1.46, "is_ga": False},
        {"name": "Upper Bowl - Far End", "category": "upper_bowl_far_end", "tier": "obstructed",
         "shape": "ring", "zone": "far_end", "scale_start": 1.75, "scale_end": 2.35,
         "rows": 18, "seats_per_unit_length": 1.46, "is_ga": False},
        {"name": "Upper Bowl - Side B", "category": "upper_bowl_side_b", "tier": "silver",
         "shape": "ring", "zone": "side_b", "scale_start": 1.75, "scale_end": 2.35,
         "rows": 18, "seats_per_unit_length": 1.46, "is_ga": False},
    ],
}


def _generate_ring_seats(venue_id: str, spec: dict, section_index: int) -> list[dict]:
    rows_out = []
    scales = np.linspace(spec["scale_start"], spec["scale_end"], spec["rows"])
    # ASSUMPTION: seat_id just needs to be unique, not a readable abbreviation of the
    # section name — word-initial abbreviations collided across sections here (e.g.
    # "Lower Bowl - Stage End" and "Lower Bowl - Side A" both truncate to "LB-S"),
    # so this uses the section's position in STADIUM_SECTION_TEMPLATES instead.
    section_abbr = f"S{section_index}"
    for row_idx, scale in enumerate(scales):
        half_l = RINK_HALF_LENGTH * scale
        half_w = RINK_HALF_WIDTH * scale
        r = RINK_CORNER_RADIUS * scale
        zone_bounds, _ = _rounded_rect_zone_bounds(half_l, half_w, r)
        t_start, t_end = zone_bounds[spec["zone"]]
        seats_in_row = max(2, round(spec["seats_per_unit_length"] * (t_end - t_start)))
        row_label = _row_label(row_idx)
        for seat_idx, t in enumerate(np.linspace(t_start, t_end, seats_in_row), start=1):
            x, y = _point_on_rounded_rect(t, half_l, half_w, r)
            seat_id = f"{venue_id}-{section_abbr}-{row_label}{seat_idx}"
            rows_out.append({
                "venue_id": venue_id, "section": spec["name"], "category": spec["category"],
                "tier": spec["tier"], "row_label": row_label, "seat_number": seat_idx,
                "seat_id": seat_id, "x": round(float(x), 2), "y": round(float(y), 2),
                "is_ga": spec["is_ga"],
            })
    return rows_out


def _generate_floor_seats(venue_id: str, spec: dict, section_index: int) -> list[dict]:
    rows_out = []
    x0, x1 = -(RINK_HALF_LENGTH - FLOOR_MARGIN), (RINK_HALF_LENGTH - FLOOR_MARGIN)
    y0, y1 = -(RINK_HALF_WIDTH - FLOOR_MARGIN), (RINK_HALF_WIDTH - FLOOR_MARGIN)
    xs = np.linspace(x0, x1, spec["cols"])
    ys = np.linspace(y0, y1, spec["rows"])
    section_abbr = f"S{section_index}"
    for row_idx, y in enumerate(ys):
        row_label = _row_label(row_idx)
        for seat_idx, x in enumerate(xs, start=1):
            seat_id = f"{venue_id}-{section_abbr}-{row_label}{seat_idx}"
            rows_out.append({
                "venue_id": venue_id, "section": spec["name"], "category": spec["category"],
                "tier": spec["tier"], "row_label": row_label, "seat_number": seat_idx,
                "seat_id": seat_id, "x": round(float(x), 2), "y": round(float(y), 2),
                "is_ga": spec["is_ga"],
            })
    return rows_out


def generate_seats_stadium(venue_id: str) -> pd.DataFrame:
    rows_out = []
    for section_index, spec in enumerate(STADIUM_SECTION_TEMPLATES[venue_id]):
        if spec["shape"] == "floor":
            rows_out.extend(_generate_floor_seats(venue_id, spec, section_index))
        else:
            rows_out.extend(_generate_ring_seats(venue_id, spec, section_index))
    return pd.DataFrame(rows_out)


def _section_specs_for_venue(venue_id: str) -> list[dict]:
    """Unified (name, category, tier) lookup regardless of layout — used by
    pricing/stage-config generation, which don't care about geometry."""
    if venue_id in STADIUM_VENUE_IDS:
        return STADIUM_SECTION_TEMPLATES[venue_id]
    return SECTION_TEMPLATES[venue_id]


# ===========================================================================
# STAGE CONFIGS
# ASSUMPTION: a stage config never adds/moves seats — it only excludes
# section CATEGORIES that aren't sellable for that layout (curtained off,
# behind the stage, etc). "excluded_categories" references the "category"
# field in SECTION_TEMPLATES above.
# ===========================================================================
STAGE_CONFIG_TEMPLATES: dict[str, list[dict]] = {
    "VEN-THEATRE-01": [
        {"config_id": "full_house", "name": "Full House", "excluded_categories": [],
         "description": "All levels open."},
        {"config_id": "orchestra_only", "name": "Orchestra Only (Reduced Cap)",
         "excluded_categories": ["mezzanine", "mezzanine_side", "balcony"],
         "description": "Mezzanine and balcony curtained off for a smaller show."},
        {"config_id": "balcony_closed", "name": "Balcony Closed",
         "excluded_categories": ["balcony"],
         "description": "Balcony closed; orchestra and mezzanine open."},
    ],
    "VEN-HALL-01": [
        {"config_id": "end_stage_full", "name": "End Stage - Full Bowl", "excluded_categories": ["rear_bowl"],
         "description": "Stage at one end; rear bowl behind stage not sellable."},
        {"config_id": "in_the_round", "name": "In-the-Round", "excluded_categories": [],
         "description": "Stage in center of floor; all sections sellable, including rear (obstructed pricing)."},
        {"config_id": "reduced_floor_lower", "name": "Reduced - Floor & Lower Bowl Only",
         "excluded_categories": ["upper_bowl", "rear_bowl"],
         "description": "Upper bowl curtained off for a smaller show."},
    ],
    "VEN-ARENA-01": [
        {"config_id": "end_stage", "name": "End Stage",
         "excluded_categories": [
             "lower_bowl_stage_end", "club_stage_end", "upper_bowl_stage_end",
         ],
         "description": "Stage built at one end of the bowl (like a concert over the ice); "
                         "seats directly behind it aren't sellable."},
        {"config_id": "in_the_round", "name": "In-the-Round / Center Stage",
         "excluded_categories": [],
         "description": "Stage at center floor; every zone of the bowl sellable, including "
                         "behind-stage (priced down accordingly)."},
        {"config_id": "reduced_upper_closed", "name": "Reduced - Upper Bowl Closed",
         "excluded_categories": [
             "upper_bowl_stage_end", "upper_bowl_side_a", "upper_bowl_far_end", "upper_bowl_side_b",
         ],
         "description": "Upper bowl curtained off for a smaller show; floor, lower bowl, and club stay open."},
    ],
    "VEN-AMPH-01": [
        {"config_id": "full_capacity", "name": "Full Capacity", "excluded_categories": [],
         "description": "Reserved seating and lawn both open."},
        {"config_id": "rain_plan", "name": "Rain Plan - Lawn Closed",
         "excluded_categories": ["lawn"],
         "description": "Lawn closed; reserved seating only."},
        {"config_id": "festival_ga", "name": "Festival - GA Only (Reserved Removed)",
         "excluded_categories": ["reserved_pit", "terrace"],
         "description": "Reserved seating pulled for a festival-style GA floor + lawn show."},
    ],
    "VEN-CLUB-01": [
        {"config_id": "standing_full", "name": "Standing Show (GA + Loft)", "excluded_categories": [],
         "description": "Floor, riser, and VIP loft all open."},
        {"config_id": "standing_no_loft", "name": "Standing Show (No Loft)",
         "excluded_categories": ["loft"],
         "description": "VIP loft not offered for this show."},
        {"config_id": "small_capacity", "name": "Small Capacity (Floor Only)",
         "excluded_categories": ["ga_riser", "loft"],
         "description": "Riser and loft closed off for a small/support-act show."},
    ],
}


# ===========================================================================
# HOLD TYPES
# ASSUMPTION: default hold sizes as a % of a config's sellable capacity.
# Applied per stage config when generating defaults for a fresh show. All
# holds sample from is_ga=False seats where possible so specific seat_ids
# are held; GA sections hold by sampling GA position rows (still specific
# seat_ids, but represents a headcount reduction rather than a named seat).
# ===========================================================================
HOLD_TYPE_DEFAULTS = {
    "artist_hold": {"pct_of_house": 0.015, "note": "Held for artist/tour comps and guest list."},
    "house_hold": {"pct_of_house": 0.01, "note": "Held by the venue for staff, sponsors, ADA companion seats."},
    "promoter_hold": {"pct_of_house": 0.01, "note": "Held by the promoter pending final marketing/allotment decisions."},
}


# ===========================================================================
# PARTNER HOLDS
# ASSUMPTION: each venue's city has 2 local partners (media/sponsor/
# community organizations) contractually held tickets on every show there —
# separate from the artist/house/promoter holds above. Ticket counts (split
# across up to 3 release tranches) and section assignment are fully
# editable on the Show Build screen; this list is just the starting roster
# (more partners/sections can be added there too).
# ===========================================================================
PARTNERS_BY_CITY = {
    "Castlemere": ["Castlemere Chamber of Commerce", "Riverside Radio 101.5"],
    "Brackenfield": ["Brackenfield Sports Network", "Union Square Business Alliance"],
    "Dunwich Falls": ["Dunwich Falls Tourism Board", "Falls Media Group"],
    "Elmsworth": ["Elmsworth Community Foundation", "Harborview Rotary Club"],
    "Aldergrove": ["Aldergrove Arts Council", "Foundry District Merchants"],
}


# ===========================================================================
# PRE-SALE WINDOW TEMPLATES
# ASSUMPTION: a generic sequence reused for every event. "days_before_onsale"
# is how many days before public on-sale the window OPENS; "duration_hours"
# is how long it stays open. "allotment_pct" is the % of total sellable
# inventory made available to that window (illustrative, not cumulative —
# unsold allotment rolls forward to the next window/public on-sale).
# ===========================================================================
PRESALE_WINDOW_TEMPLATES = [
    {"window_name": "Fan Club Presale", "order": 1, "days_before_onsale": 5, "duration_hours": 48,
     "access_type": "code", "allotment_pct": 0.10},
    {"window_name": "Credit Card Partner Presale", "order": 2, "days_before_onsale": 3, "duration_hours": 24,
     "access_type": "card_bin", "allotment_pct": 0.15},
    {"window_name": "Venue Members Presale", "order": 3, "days_before_onsale": 2, "duration_hours": 24,
     "access_type": "code", "allotment_pct": 0.08},
    {"window_name": "Public On-Sale", "order": 4, "days_before_onsale": 0, "duration_hours": 0,
     "access_type": "public", "allotment_pct": 0.67},
]


# ===========================================================================
# FAKE ARTIST / TOUR NAME GENERATOR (event history only)
# ===========================================================================
_ARTIST_FIRST = ["Midnight", "Electric", "Velvet", "Copper", "Neon", "Silver", "Crimson",
                  "Paper", "Northern", "Glass", "Amber", "Static", "Golden", "Hollow"]
_ARTIST_SECOND = ["Wolves", "Parade", "Static", "Horizon", "Mirrors", "Avenue", "Machine",
                   "Orchard", "Radio", "Tigers", "Harbor", "Echo", "Season", "Kings"]
_TOUR_SUFFIX = ["World Tour", "Live", "Homecoming Show", "Acoustic Sessions", "Farewell Tour",
                "Anniversary Show", "In Concert", "Unplugged"]


def _fake_artist_name(rng: np.random.Generator) -> str:
    return f"{rng.choice(_ARTIST_FIRST)} {rng.choice(_ARTIST_SECOND)}"


def _fake_event_name(rng: np.random.Generator) -> str:
    return f"{_fake_artist_name(rng)}: {rng.choice(_TOUR_SUFFIX)}"


# ===========================================================================
# SEAT MAP GENERATION
# ===========================================================================
def _row_label(index: int) -> str:
    """0 -> 'A', 25 -> 'Z', 26 -> 'AA', ... standard spreadsheet-style row labels."""
    label = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label


def generate_seats(venue_id: str) -> pd.DataFrame:
    """Generate the fixed physical seat map for a venue as a flat DataFrame."""
    if venue_id in STADIUM_VENUE_IDS:
        return generate_seats_stadium(venue_id)

    rows_out = []
    for section in SECTION_TEMPLATES[venue_id]:
        radii = np.linspace(section["radius_start"], section["radius_end"], section["rows"])
        for row_idx, radius in enumerate(radii):
            if section["fan"]:
                seats_in_row = max(2, round(section["base_seats_per_row"] * (radius / section["radius_start"])))
            else:
                seats_in_row = section["base_seats_per_row"]
            angles = np.linspace(section["angle_start"], section["angle_end"], seats_in_row)
            row_label = _row_label(row_idx)
            for seat_idx, angle_deg in enumerate(angles, start=1):
                theta = np.radians(angle_deg)
                x = radius * np.sin(theta)
                y = radius * np.cos(theta)  # stage at origin; y grows with distance from stage
                section_abbr = "".join(w[0] for w in section["name"].split())[:4].upper()
                seat_id = f"{venue_id}-{section_abbr}-{row_label}{seat_idx}"
                rows_out.append({
                    "venue_id": venue_id,
                    "section": section["name"],
                    "category": section["category"],
                    "tier": section["tier"],
                    "row_label": row_label,
                    "seat_number": seat_idx,
                    "seat_id": seat_id,
                    "x": round(float(x), 2),
                    "y": round(float(y), 2),
                    "is_ga": section["is_ga"],
                })
    return pd.DataFrame(rows_out)


# ===========================================================================
# STAGE CONFIGS (with computed capacity per config)
# ===========================================================================
def generate_stage_configs(venue_id: str, seats: pd.DataFrame) -> pd.DataFrame:
    rows_out = []
    for cfg in STAGE_CONFIG_TEMPLATES[venue_id]:
        sellable = seats[~seats["category"].isin(cfg["excluded_categories"])]
        rows_out.append({
            "venue_id": venue_id,
            "config_id": cfg["config_id"],
            "name": cfg["name"],
            "description": cfg["description"],
            "excluded_categories": ", ".join(cfg["excluded_categories"]) or "(none)",
            "capacity": len(sellable),
        })
    return pd.DataFrame(rows_out)


# ===========================================================================
# PRICING ZONES (section-level, venue-wide — same tier price regardless of
# which stage config is active; a config just determines sellability)
# ===========================================================================
def generate_pricing_zones(venue_id: str) -> pd.DataFrame:
    venue_type = VENUES_BY_ID[venue_id]["venue_type"]
    price_table = PRICE_TABLE[venue_type]
    rows_out = []
    seen_sections = set()
    for section in _section_specs_for_venue(venue_id):
        if section["name"] in seen_sections:
            continue
        seen_sections.add(section["name"])
        rows_out.append({
            "venue_id": venue_id,
            "section": section["name"],
            "category": section["category"],
            "tier": section["tier"],
            "price": price_table[section["tier"]],
            "color": TIER_COLORS[section["tier"]],
        })
    return pd.DataFrame(rows_out)


# ===========================================================================
# HOLDS — sampled per (venue, stage config) so each config gets its own
# illustrative default hold set, proportional to that config's capacity.
# ===========================================================================
def generate_holds(venue_id: str, config_id: str, seats: pd.DataFrame,
                    excluded_categories: list[str], rng: np.random.Generator) -> pd.DataFrame:
    sellable = seats[~seats["category"].isin(excluded_categories)]
    rows_out = []
    for hold_type, defaults in HOLD_TYPE_DEFAULTS.items():
        n_hold = max(1, round(len(sellable) * defaults["pct_of_house"]))
        sampled = sellable.sample(n=min(n_hold, len(sellable)), random_state=rng.integers(0, 2**31 - 1))
        for _, seat in sampled.iterrows():
            rows_out.append({
                "venue_id": venue_id,
                "config_id": config_id,
                "hold_type": hold_type,
                "section": seat["section"],
                "seat_id": seat["seat_id"],
                "source": "template default",
                "note": defaults["note"],
            })
        # avoid double-holding the same seat under a different hold type
        sellable = sellable.drop(sampled.index)
    return pd.DataFrame(rows_out)


# ===========================================================================
# PRE-SALE WINDOW TEMPLATES (generic — not tied to a venue or event date)
# ===========================================================================
def generate_presale_window_templates() -> pd.DataFrame:
    return pd.DataFrame(PRESALE_WINDOW_TEMPLATES)


def instantiate_presale_windows(public_onsale_date: date) -> pd.DataFrame:
    """Turn the generic templates into actual calendar dates for one event."""
    rows_out = []
    for w in PRESALE_WINDOW_TEMPLATES:
        start = public_onsale_date - timedelta(days=w["days_before_onsale"])
        rows_out.append({
            "window_name": w["window_name"],
            "order": w["order"],
            "start_date": start,
            "duration_hours": w["duration_hours"],
            "access_type": w["access_type"],
            "allotment_pct": w["allotment_pct"],
        })
    return pd.DataFrame(rows_out)


# ===========================================================================
# EVENT HISTORY — past shows per venue, so "start from previous show" has
# something to pull from in Step 2.
# ASSUMPTION: 5-8 past events per venue, spread over the last ~18 months,
# each using a randomly chosen stage config and a plausible sell-through.
# ===========================================================================
def generate_event_history(venue_id: str, stage_configs: pd.DataFrame,
                            rng: np.random.Generator, n_events: int = 6) -> pd.DataFrame:
    venue_type = VENUES_BY_ID[venue_id]["venue_type"]
    price_table = PRICE_TABLE[venue_type]
    avg_price = float(np.mean(list(price_table.values())))

    rows_out = []
    days_ago_pool = sorted(rng.choice(range(14, 545), size=n_events, replace=False), reverse=True)
    for i, days_ago in enumerate(days_ago_pool):
        event_date = TODAY - timedelta(days=int(days_ago))
        cfg = stage_configs.iloc[rng.integers(0, len(stage_configs))]
        sell_through = float(np.clip(rng.normal(0.82, 0.12), 0.35, 1.0))
        tickets_sold = round(cfg["capacity"] * sell_through)
        gross = round(tickets_sold * avg_price * rng.uniform(0.9, 1.1), 2)
        onsale_date = event_date - timedelta(days=int(rng.integers(45, 120)))
        rows_out.append({
            "event_id": f"{venue_id}-EVT-{i+1:03d}",
            "venue_id": venue_id,
            "event_name": _fake_event_name(rng),
            "event_date": event_date,
            "public_onsale_date": onsale_date,
            "config_id": cfg["config_id"],
            "config_name": cfg["name"],
            "capacity": int(cfg["capacity"]),
            "tickets_sold": int(tickets_sold),
            "sell_through_pct": round(sell_through, 3),
            "gross_revenue": gross,
        })
    return pd.DataFrame(rows_out).sort_values("event_date", ascending=False).reset_index(drop=True)


# ===========================================================================
# TOP-LEVEL BUILD
# ===========================================================================
def build_all(seed: int = DEFAULT_SEED) -> dict[str, pd.DataFrame]:
    """
    Generate the full synthetic world and return it as a dict of DataFrames,
    ready to drop into Streamlit session state:

        venues              - one row per venue
        seats               - one row per physical seat (all venues)
        stage_configs       - one row per (venue, stage config), with capacity
        pricing_zones       - one row per (venue, section), price + color
        holds               - one row per held seat, per (venue, stage config)
        presale_window_templates - generic 4-window sequence (not date-bound)
        event_history       - one row per past event, per venue
    """
    master_rng = np.random.default_rng(seed)

    all_seats = []
    all_configs = []
    all_pricing = []
    all_holds = []
    all_history = []

    for venue in VENUES:
        venue_id = venue["venue_id"]
        venue_rng = np.random.default_rng(master_rng.integers(0, 2**31 - 1))

        seats = generate_seats(venue_id)
        all_seats.append(seats)

        configs = generate_stage_configs(venue_id, seats)
        all_configs.append(configs)

        pricing = generate_pricing_zones(venue_id)
        all_pricing.append(pricing)

        for cfg in STAGE_CONFIG_TEMPLATES[venue_id]:
            holds = generate_holds(venue_id, cfg["config_id"], seats,
                                    cfg["excluded_categories"], venue_rng)
            all_holds.append(holds)

        history = generate_event_history(venue_id, configs, venue_rng)
        all_history.append(history)

    return {
        "venues": pd.DataFrame(VENUES),
        "seats": pd.concat(all_seats, ignore_index=True),
        "stage_configs": pd.concat(all_configs, ignore_index=True),
        "pricing_zones": pd.concat(all_pricing, ignore_index=True),
        "holds": pd.concat(all_holds, ignore_index=True),
        "presale_window_templates": generate_presale_window_templates(),
        "event_history": pd.concat(all_history, ignore_index=True),
    }


# ===========================================================================
# STANDALONE PREVIEW — run `python synthetic_data.py` to inspect the shape
# and a sample of every table before wiring it into the Streamlit app.
# ===========================================================================
if __name__ == "__main__":
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)

    world = build_all()

    print("=" * 78)
    print("VENUES")
    print("=" * 78)
    print(world["venues"])

    print("\n" + "=" * 78)
    print("SEATS — shape, and count by venue")
    print("=" * 78)
    print(f"shape: {world['seats'].shape}")
    print(world["seats"].groupby("venue_id").size().rename("actual_capacity"))
    print("\nsample rows:")
    print(world["seats"].sample(5, random_state=1))

    print("\n" + "=" * 78)
    print("STAGE CONFIGS")
    print("=" * 78)
    print(world["stage_configs"])

    print("\n" + "=" * 78)
    print("PRICING ZONES")
    print("=" * 78)
    print(world["pricing_zones"])

    print("\n" + "=" * 78)
    print("HOLDS — shape, and count by (venue, config, hold_type)")
    print("=" * 78)
    print(f"shape: {world['holds'].shape}")
    print(world["holds"].groupby(["venue_id", "config_id", "hold_type"]).size().rename("n_held"))

    print("\n" + "=" * 78)
    print("PRESALE WINDOW TEMPLATES")
    print("=" * 78)
    print(world["presale_window_templates"])
    print("\nexample instantiated for an on-sale date of 2026-11-01:")
    print(instantiate_presale_windows(date(2026, 11, 1)))

    print("\n" + "=" * 78)
    print("EVENT HISTORY")
    print("=" * 78)
    print(world["event_history"].drop(columns=["event_id"]))
