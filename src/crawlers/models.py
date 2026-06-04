# src/crawlers/models.py
"""Job dict type shared across all crawlers.

Inputs: N/A — type definition only.
Outputs: JobDict TypedDict for use in type annotations.
"""
from typing import Optional, TypedDict


class _RequiredJobFields(TypedDict):
    """Base class — required fields only. Use JobDict, not this class directly."""
    title: str
    company: str
    source_url: str


class JobDict(_RequiredJobFields, total=False):
    """Job record emitted by crawlers. title, company, source_url are required."""

    ats_job_id: Optional[str]
    location: Optional[str]
    location_normalized: Optional[str]
    description: Optional[str]
    date_posted: Optional[str]
    source_name: Optional[str]
