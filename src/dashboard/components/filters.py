"""Pre-filter controls rendered above the AgGrid table.

Provides score range number inputs and an optional Referral-Needed toggle.
AgGrid handles all column-level filtering; this covers top-level quick filters.

render_pre_filters() returns a filtered copy of the input DataFrame.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_pre_filters(
    df: pd.DataFrame,
    show_referral_toggle: bool = False,
) -> pd.DataFrame:
    """Render score range inputs (and optional Referral-Needed toggle) above the table.

    Args:
        df: Full DataFrame for the current view.
        show_referral_toggle: If True, render a 'Referral Needed only' checkbox.
                              Used only in the High Priority view.

    Returns:
        Filtered DataFrame. Original DataFrame is not mutated.
    """
    if df.empty or "score" not in df.columns:
        return df

    min_val = int(df["score"].min())
    max_val = int(df["score"].max())

    cols = st.columns([1, 1, 2] if not show_referral_toggle else [1, 1, 1, 1])

    with cols[0]:
        min_score = st.number_input(
            "Min score", value=min_val, step=1, key="filter_min_score"
        )
    with cols[1]:
        max_score = st.number_input(
            "Max score", value=max_val, step=1, key="filter_max_score"
        )

    referral_only = False
    if show_referral_toggle and "status" in df.columns:
        with cols[3]:
            referral_only = st.checkbox("Referral Needed only", key="filter_referral_only")

    filtered = df.copy()
    filtered = filtered[
        (filtered["score"] >= min_score) & (filtered["score"] <= max_score)
    ]
    if referral_only:
        filtered = filtered[filtered["status"] == "Referral-Needed"]

    return filtered.reset_index(drop=True)
