"""Shared AgGrid table component for all job views.

Renders a sortable, filterable, selectable table using streamlit-aggrid.
Returns the selected row as a dict, or None if nothing is selected.

Score coloring:
  score >= threshold  →  #238636 (green)
  score < 0           →  #da3633 (red)
  else                →  default

Title column is rendered as a clickable link to source_url.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode


def render_job_table(
    df: pd.DataFrame,
    columns: list[str],
    config: dict,
    key: str,
    height: int = 420,
) -> dict | None:
    """Render an AgGrid table with score coloring and single-row selection.

    Args:
        df: DataFrame produced by data_loader. Must contain all columns in `columns`.
        columns: Column names to display, in order.
        config: Config dict (requires notification_threshold).
        key: Unique string key per view to prevent session state bleed.
        height: Pixel height of the grid.

    Returns:
        The selected row as a dict, or None if no row is selected.
    """
    if df.empty:
        st.info("No jobs to display.")
        return None

    threshold = config["notification_threshold"]

    # Keep only the requested columns that actually exist in the DataFrame.
    display_cols = [c for c in columns if c in df.columns]
    # Always carry id and source_url for selection and linking; hide them if not in columns.
    carry_cols = [c for c in ["id", "source_url"] if c not in display_cols and c in df.columns]
    grid_df = df[display_cols + carry_cols].copy()

    gb = GridOptionsBuilder.from_dataframe(grid_df)
    gb.configure_default_column(
        resizable=True,
        sortable=True,
        filter=True,
        wrapText=False,
    )
    gb.configure_selection("single", use_checkbox=False)

    # Score column styling
    if "score" in display_cols:
        score_style = JsCode(f"""
            function(params) {{
                if (params.value >= {threshold}) {{
                    return {{'color': '#238636', 'fontWeight': '600'}};
                }} else if (params.value < 0) {{
                    return {{'color': '#da3633'}};
                }}
                return {{}};
            }}
        """)
        gb.configure_column("score", cellStyle=score_style, width=80)

    # Title column as clickable link (requires source_url in the row data)
    if "title" in display_cols and "source_url" in grid_df.columns:
        title_renderer = JsCode("""
            function(params) {
                var url = params.data.source_url || '#';
                return '<a href="' + url + '" target="_blank" '
                    + 'style="color:inherit;text-decoration:underline;">'
                    + params.value + '</a>';
            }
        """)
        gb.configure_column("title", cellRenderer=title_renderer, flex=3)

    # Hide carry columns from display
    for col in carry_cols:
        gb.configure_column(col, hide=True)

    grid_options = gb.build()

    response = AgGrid(
        grid_df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        allow_unsafe_jscode=True,
        theme="streamlit",
        height=height,
        fit_columns_on_grid_load=True,
        key=key,
    )

    selected_rows = response["selected_rows"]
    if selected_rows is not None and len(selected_rows) > 0:
        return dict(selected_rows[0])
    return None
