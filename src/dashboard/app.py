"""Streamlit dashboard entry point.

Run with: streamlit run src/dashboard/app.py

Loads config once at startup, runs migrations, renders sidebar navigation,
and delegates to the selected view module.

Imports db.migrations directly for startup schema initialization.
This is an approved narrow exception per DECISIONS.md.
"""
import streamlit as st

from src.config_loader import load_config
from src.db.migrations import run_migrations
from src.dashboard import data_loader
from src.dashboard.views import (
    analytics,
    applied,
    high_priority,
    inbox,
    referrals,
    rejected,
    settings,
)

st.set_page_config(
    page_title="Job Intelligence",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

_PAGES = [
    "Inbox",
    "High Priority",
    "Applied",
    "Rejected",
    "Referrals",
    "Analytics",
    "Settings",
]

_VIEW_MODULES = {
    "Inbox": inbox,
    "High Priority": high_priority,
    "Applied": applied,
    "Rejected": rejected,
    "Referrals": referrals,
    "Analytics": analytics,
    "Settings": settings,
}

_BADGE_VIEWS = {"Inbox", "High Priority", "Applied", "Rejected", "Referrals"}


@st.cache_resource
def _load_config():
    """Load config once per process lifecycle. Cached by st.cache_resource."""
    return load_config()


def _sidebar(config: dict) -> str:
    """Render sidebar and return the selected page name."""
    counts = data_loader.get_badge_counts(config)

    with st.sidebar:
        st.markdown("**Job Intelligence**")
        st.divider()

        labels = []
        for page in _PAGES:
            if page in _BADGE_VIEWS:
                count = counts.get(page, 0)
                label = f"{page}  {count}" if count else page
            else:
                label = page
            labels.append(label)

        selected_label = st.radio(
            "Navigation",
            options=labels,
            label_visibility="collapsed",
            key="nav_radio",
        )

    # Map label back to page name
    for page, label in zip(_PAGES, labels):
        if label == selected_label:
            return page
    return "Inbox"


def main():
    config = _load_config()
    run_migrations(config["database_path"])
    page = _sidebar(config)
    _VIEW_MODULES[page].render(config)


if __name__ == "__main__":
    main()
