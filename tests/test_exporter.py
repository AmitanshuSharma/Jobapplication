"""Tests for src/export/exporter.py."""
import io

import pandas as pd
import pytest

from src.export.exporter import (
    export_jobs_csv,
    export_jobs_excel,
    export_referrals_csv,
    export_referrals_excel,
)

_JOBS_DF = pd.DataFrame([
    {"id": 1, "title": "Senior DE", "company": "Acme", "score": 35},
    {"id": 2, "title": "Lead DE", "company": "Beta", "score": 28},
])

_REFERRALS_DF = pd.DataFrame([
    {"id": 1, "company": "Acme", "role": "DE", "referral_status": "Pending"},
])

_EMPTY_JOBS_DF = pd.DataFrame(columns=["id", "title", "company", "score"])
_EMPTY_REFERRALS_DF = pd.DataFrame(columns=["id", "company", "role", "referral_status"])


def test_export_jobs_csv_returns_bytes():
    result = export_jobs_csv(_JOBS_DF)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_export_jobs_csv_contains_header():
    result = export_jobs_csv(_JOBS_DF)
    text = result.decode("utf-8")
    assert "title" in text
    assert "company" in text
    assert "Senior DE" in text


def test_export_jobs_csv_empty_dataframe_produces_header_only():
    result = export_jobs_csv(_EMPTY_JOBS_DF)
    text = result.decode("utf-8")
    lines = [l for l in text.strip().split("\n") if l]
    assert len(lines) == 1
    assert "title" in lines[0]


def test_export_jobs_excel_returns_bytes():
    result = export_jobs_excel(_JOBS_DF)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_export_jobs_excel_is_parseable():
    result = export_jobs_excel(_JOBS_DF)
    df = pd.read_excel(io.BytesIO(result))
    assert list(df.columns) == list(_JOBS_DF.columns)
    assert len(df) == 2


def test_export_jobs_excel_empty_dataframe():
    result = export_jobs_excel(_EMPTY_JOBS_DF)
    df = pd.read_excel(io.BytesIO(result))
    assert len(df) == 0
    assert list(df.columns) == list(_EMPTY_JOBS_DF.columns)


def test_export_referrals_csv_returns_bytes():
    result = export_referrals_csv(_REFERRALS_DF)
    assert isinstance(result, bytes)
    assert "Acme" in result.decode("utf-8")


def test_export_referrals_excel_is_parseable():
    result = export_referrals_excel(_REFERRALS_DF)
    df = pd.read_excel(io.BytesIO(result))
    assert list(df.columns) == list(_REFERRALS_DF.columns)
