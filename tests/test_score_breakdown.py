"""Tests for score breakdown JSON parsing logic in score_breakdown.py."""
import pytest

from src.dashboard.components.score_breakdown import parse_score_breakdown

_VALID_JSON = (
    '{"role_match": true, '
    '"components": [{"label": "PySpark", "points": 10}, '
    '{"label": "Remote Bonus", "points": 5}], '
    '"final_score": 15, '
    '"threshold_at_ingestion": 20}'
)


def test_parse_valid_breakdown_returns_dict():
    result = parse_score_breakdown(_VALID_JSON)
    assert result is not None
    assert isinstance(result, dict)


def test_parse_valid_breakdown_has_expected_keys():
    result = parse_score_breakdown(_VALID_JSON)
    assert result["role_match"] is True
    assert result["final_score"] == 15
    assert result["threshold_at_ingestion"] == 20
    assert len(result["components"]) == 2


def test_parse_valid_breakdown_components_have_label_and_points():
    result = parse_score_breakdown(_VALID_JSON)
    for comp in result["components"]:
        assert "label" in comp
        assert "points" in comp


def test_parse_none_returns_none():
    assert parse_score_breakdown(None) is None


def test_parse_empty_string_returns_none():
    assert parse_score_breakdown("") is None


def test_parse_invalid_json_returns_none():
    assert parse_score_breakdown("not-json{{{") is None


def test_parse_non_dict_json_returns_none():
    assert parse_score_breakdown("[1, 2, 3]") is None


def test_parse_negative_score():
    json_str = (
        '{"role_match": false, '
        '"components": [{"label": "Role Mismatch Penalty", "points": -50}], '
        '"final_score": -50, '
        '"threshold_at_ingestion": 20}'
    )
    result = parse_score_breakdown(json_str)
    assert result["final_score"] == -50
    assert result["role_match"] is False
