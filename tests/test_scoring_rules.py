"""Tests for src/scoring/rules.py — role match gate."""
import pytest

from src.scoring.rules import matches_role


def test_exact_match_returns_true():
    assert matches_role("Senior Data Engineer", ["Senior Data Engineer"]) is True


def test_partial_substring_match_returns_true():
    # Title contains the keyword as a substring
    assert matches_role("Senior Data Engineer - Platforms", ["Senior Data Engineer"]) is True


def test_match_is_case_insensitive():
    assert matches_role("SENIOR DATA ENGINEER", ["Senior Data Engineer"]) is True


def test_no_keyword_matches_returns_false():
    assert matches_role("Business Analyst", ["Senior Data Engineer", "Analytics Engineer"]) is False


def test_empty_title_returns_false():
    assert matches_role("", ["Senior Data Engineer"]) is False


def test_empty_keyword_list_returns_false():
    assert matches_role("Senior Data Engineer", []) is False


def test_second_keyword_in_list_matches():
    assert matches_role("Analytics Engineer", ["Senior Data Engineer", "Analytics Engineer"]) is True
