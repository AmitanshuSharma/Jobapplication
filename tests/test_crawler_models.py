# tests/test_crawler_models.py
"""Tests for src/crawlers/models.py — JobDict structure and field access."""
from src.crawlers.models import JobDict


def test_job_dict_is_dict_subclass():
    assert issubclass(JobDict, dict)


def test_job_dict_with_required_fields_only():
    job: JobDict = {
        "title": "Senior Data Engineer",
        "company": "ACME",
        "source_url": "https://acme.com/jobs/1",
    }
    assert job["title"] == "Senior Data Engineer"
    assert job["company"] == "ACME"
    assert job["source_url"] == "https://acme.com/jobs/1"


def test_job_dict_with_all_optional_fields():
    job: JobDict = {
        "title": "Senior Data Engineer",
        "company": "ACME",
        "source_url": "https://acme.com/jobs/1",
        "ats_job_id": "gh_12345",
        "location": "Gurgaon",
        "location_normalized": "Gurugram",
        "description": "We use PySpark for large-scale data processing.",
        "date_posted": "2026-06-01",
        "source_name": "greenhouse",
    }
    assert job["ats_job_id"] == "gh_12345"
    assert job["location"] == "Gurgaon"
    assert job["location_normalized"] == "Gurugram"
    assert job["description"] == "We use PySpark for large-scale data processing."
    assert job["date_posted"] == "2026-06-01"
    assert job["source_name"] == "greenhouse"


def test_job_dict_optional_fields_can_be_none():
    job: JobDict = {
        "title": "Senior Data Engineer",
        "company": "ACME",
        "source_url": "https://acme.com/jobs/1",
        "ats_job_id": None,
        "location": None,
        "location_normalized": None,
        "description": None,
        "date_posted": None,
        "source_name": None,
    }
    assert job["ats_job_id"] is None
    assert job["location"] is None
    assert job["location_normalized"] is None
    assert job["description"] is None
    assert job["date_posted"] is None
    assert job["source_name"] is None


def test_job_dict_is_plain_dict():
    job: JobDict = {
        "title": "t",
        "company": "c",
        "source_url": "u",
    }
    assert isinstance(job, dict)
