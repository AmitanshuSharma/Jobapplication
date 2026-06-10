"""Settings view — read-only display of non-secret config values.

Secret keys (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, EMAIL_ADDRESS,
EMAIL_PASSWORD, SMTP_HOST, SMTP_PORT) are masked as '***'.
No write path. No database access.
"""
import streamlit as st

_SECRET_KEYS = frozenset({
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "EMAIL_ADDRESS",
    "EMAIL_PASSWORD",
    "SMTP_HOST",
    "SMTP_PORT",
})


def render(config: dict) -> None:
    """Render the Settings view.

    Args:
        config: Loaded config dict. Secret keys are displayed as '***'.
    """
    st.subheader("Settings")
    st.caption("Read-only. Edit config/config.yaml and config/.env to change values.")

    display_config = {
        k: ("***" if k in _SECRET_KEYS else v)
        for k, v in config.items()
    }

    st.json(display_config)
