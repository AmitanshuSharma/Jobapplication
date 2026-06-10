"""Score breakdown display component.

parse_score_breakdown() is a pure function — testable without Streamlit.
render_score_breakdown() renders the Streamlit expander.
"""
from __future__ import annotations

import json
import logging

import streamlit as st

logger = logging.getLogger(__name__)


def parse_score_breakdown(json_str: str | None) -> dict | None:
    """Parse the score_breakdown JSON string stored in the jobs table.

    Returns the parsed dict on success, None on any failure.
    Never raises.

    Expected structure:
        {
            "role_match": bool,
            "components": [{"label": str, "points": int}, ...],
            "final_score": int,
            "threshold_at_ingestion": int
        }
    """
    if not json_str:
        return None
    try:
        data = json.loads(json_str)
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.debug("Failed to parse score_breakdown: %r", json_str[:80])
        return None


def render_score_breakdown(json_str: str | None) -> None:
    """Render score breakdown in a Streamlit expander.

    Shows each scoring component and final score.
    Displays a safe fallback message when json_str is None or malformed.
    """
    data = parse_score_breakdown(json_str)

    with st.expander("Score Breakdown"):
        if data is None:
            st.caption("Score breakdown unavailable.")
            return

        role_match = data.get("role_match", False)
        components = data.get("components", [])
        final_score = data.get("final_score", 0)
        threshold = data.get("threshold_at_ingestion")

        st.caption(f"Role match: {'Yes' if role_match else 'No'}")
        st.write("")

        for comp in components:
            label = comp.get("label", "")
            points = comp.get("points", 0)
            sign = "+" if points >= 0 else ""
            col_label, col_pts = st.columns([3, 1])
            col_label.text(label)
            col_pts.text(f"{sign}{points}")

        st.divider()
        footer = f"Final score: {final_score}"
        if threshold is not None:
            footer += f"   ·   Threshold at ingestion: {threshold}"
        st.caption(footer)
