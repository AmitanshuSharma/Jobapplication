# src/utils/normalizer.py
"""Location string normalization shared across crawlers and pipeline.

Inputs: raw location string (or None); optional alias dict {raw_lower: canonical}.
Outputs: canonical location string, or None if raw is None/empty.
No database access. No config import. Pure function.
"""
from __future__ import annotations


def normalize_location(
    raw: str | None,
    location_aliases: dict[str, str] | None = None,
) -> str | None:
    """Map a raw location string to a canonical form using provided aliases.

    Args:
        raw: Raw location string from source. May be None or empty.
        location_aliases: Mapping of {lowercase_raw: canonical}. Case-insensitive.

    Returns:
        Canonical location string with whitespace stripped, or None for empty input.
    """
    if not raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    if not location_aliases:
        return stripped
    return location_aliases.get(stripped.lower(), stripped)
