# tests/test_utils_normalizer.py
"""Tests for src/utils/normalizer.py — normalize_location pure function."""
from src.utils.normalizer import normalize_location


def test_none_input_returns_none():
    assert normalize_location(None) is None


def test_empty_string_returns_none():
    assert normalize_location("") is None


def test_whitespace_only_returns_none():
    assert normalize_location("   ") is None


def test_passthrough_when_no_aliases_provided():
    assert normalize_location("Gurugram") == "Gurugram"


def test_passthrough_when_aliases_is_none():
    assert normalize_location("Gurugram", location_aliases=None) == "Gurugram"


def test_passthrough_when_aliases_is_empty_dict():
    assert normalize_location("Gurugram", location_aliases={}) == "Gurugram"


def test_alias_mapped_to_canonical_form():
    aliases = {"gurgaon": "Gurugram"}
    assert normalize_location("Gurgaon", location_aliases=aliases) == "Gurugram"


def test_alias_match_is_case_insensitive():
    aliases = {"gurgaon": "Gurugram"}
    assert normalize_location("GURGAON", location_aliases=aliases) == "Gurugram"
    assert normalize_location("gurgaon", location_aliases=aliases) == "Gurugram"
    assert normalize_location("Gurgaon", location_aliases=aliases) == "Gurugram"


def test_unknown_location_returned_stripped():
    aliases = {"gurgaon": "Gurugram"}
    assert normalize_location("Bengaluru", location_aliases=aliases) == "Bengaluru"


def test_leading_trailing_whitespace_stripped_before_lookup():
    assert normalize_location("  Remote  ") == "Remote"


def test_alias_applied_after_stripping_whitespace():
    aliases = {"gurgaon": "Gurugram"}
    assert normalize_location("  Gurgaon  ", location_aliases=aliases) == "Gurugram"


def test_second_alias_mapped_independently():
    aliases = {"gurgaon": "Gurugram", "bombay": "Mumbai"}
    assert normalize_location("Bombay", location_aliases=aliases) == "Mumbai"
    assert normalize_location("Gurgaon", location_aliases=aliases) == "Gurugram"
