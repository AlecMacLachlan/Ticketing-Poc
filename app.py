"""Landing page for the Live Event Ticketing POC. Screens live under pages/."""

import streamlit as st

from branding import inject_brand_css, render_header

st.set_page_config(page_title="OVG Ticketing POC", page_icon="🏟️", layout="wide")
inject_brand_css(st)
render_header(st, "Discovery conversation draft")

st.warning(
    "**All venues, artists, partners, and figures in this app are synthetic "
    "and illustrative.** Nothing here comes from a real venue or a real "
    "Ticketmaster account. It exists to make assumptions concrete enough "
    "for you to correct them.",
    icon="⚠️",
)

st.markdown(
    """
This POC exists to ground a discovery conversation about two recurring
problems your team described:

**1. Show build takes too long, and nothing carries over.**
Setting up an event today takes up to a full day, 30–50 times a year per
venue — mostly in Excel, mostly rebuilt from zero each time. → **Screen 1:
Show Build**, in the sidebar.

**2. Secondary market allotments are decided ad hoc.**
How many seats go to each resale partner, and when more get released as a
show sells through, isn't applied consistently or easy to compare across
partners. → **Screen 2: Allotments** (coming next).

Use the sidebar to open a screen. Every default value you see is editable,
and is labelled with where it came from — a saved template, a previous
show, or your own edit — so nothing is a hidden assumption.
"""
)
