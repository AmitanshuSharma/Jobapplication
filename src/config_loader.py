"""
config_loader.py — Centralized configuration loader for the Job Intelligence Platform.

Purpose:
    Loads config/config.yaml (non-secret operational values) and config/.env
    (secrets), validates that all required keys are present, and exposes a
    singleton config dict to all other modules via get_config().

Inputs:
    config_path — path to config.yaml (default: PROJECT_ROOT/config/config.yaml)
    env_path    — path to .env file   (default: PROJECT_ROOT/config/.env)

Outputs:
    dict — merged config containing all YAML values plus secrets from .env,
           keyed by their original YAML key or env var name.

Forbidden imports: sqlite3, requests, streamlit, any src/ module.
"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "config.yaml"
DEFAULT_ENV_PATH = _PROJECT_ROOT / "config" / ".env"

_config: dict | None = None

_REQUIRED_YAML_KEYS = [
    "database_path",
    "schedule_interval_minutes",
    "log_level",
    "log_directory",
    "request_timeout_seconds",
    "max_retries",
    "retry_backoff_seconds",
    "user_agent",
    "notification_threshold",
    "role_mismatch_penalty",
    "remote_location_bonus",
    "company_tier_1_bonus",
    "company_tier_2_bonus",
    "accepted_locations",
    "accepted_role_keywords",
    "positive_keywords",
    "negative_keywords",
    "company_tier_1",
    "company_tier_2",
    "greenhouse_board_tokens",
    "lever_company_ids",
    "workday_urls",
]

_REQUIRED_ENV_KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "EMAIL_ADDRESS",
    "EMAIL_PASSWORD",
    "SMTP_HOST",
    "SMTP_PORT",
]


def load_config(
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    env_path: Path | str = DEFAULT_ENV_PATH,
) -> dict:
    """Load config.yaml and .env, validate all required keys, return merged dict.

    Collects every missing YAML key and env var before raising, so the caller
    sees the full list of problems in a single error rather than one at a time.

    Args:
        config_path: Path to config.yaml. Defaults to PROJECT_ROOT/config/config.yaml.
        env_path: Path to the .env file containing secrets. Defaults to
                  PROJECT_ROOT/config/.env.

    Returns:
        dict containing all YAML config values plus secrets merged from .env.
        Secrets are stored at their uppercase env var names (e.g. TELEGRAM_BOT_TOKEN).

    Raises:
        FileNotFoundError: If config_path does not exist.
        KeyError: If any required keys are missing; all missing keys reported together.
    """
    global _config

    config_path = Path(config_path)
    env_path = Path(env_path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Copy config/config.yaml.example to config/config.yaml and fill in your values."
        )

    # override=True ensures .env values take precedence over any existing shell vars.
    load_dotenv(env_path, override=True)

    with config_path.open() as f:
        # safe_load returns None for an empty file; treat that as an empty dict.
        data = yaml.safe_load(f) or {}

    # Collect all missing keys before raising so every problem is visible at once.
    errors = []
    for key in _REQUIRED_YAML_KEYS:
        if key not in data:
            errors.append(f"YAML key missing: {key}")
    for key in _REQUIRED_ENV_KEYS:
        if not os.environ.get(key):
            errors.append(f"Env var missing: {key}")

    if errors:
        issue_list = "\n  - ".join(errors)
        raise KeyError(
            f"Config validation failed — {len(errors)} issue(s) found:\n  - {issue_list}"
        )

    # Merge secrets into the config dict under their original env var names.
    for key in _REQUIRED_ENV_KEYS:
        data[key] = os.environ[key]

    _config = data
    return _config


def get_config() -> dict:
    """Return the cached config singleton loaded by load_config().

    Args:
        None

    Returns:
        dict: The loaded and validated configuration.

    Raises:
        RuntimeError: If load_config() has not been called yet in this process.
    """
    if _config is None:
        raise RuntimeError("Config not loaded. Call load_config() first.")
    return _config


if __name__ == "__main__":
    cfg = load_config()
    print("Config loaded successfully.")
    print(f"  YAML source : {DEFAULT_CONFIG_PATH.relative_to(_PROJECT_ROOT)}")
    print(f"  Env source  : {DEFAULT_ENV_PATH.relative_to(_PROJECT_ROOT)}")
    print(f"  YAML keys   : {len(_REQUIRED_YAML_KEYS)}")
    print(f"  Env vars    : {len(_REQUIRED_ENV_KEYS)}")
