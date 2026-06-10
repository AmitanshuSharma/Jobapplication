"""Dashboard data gateway.

The only dashboard module permitted to import from src/db/.
All functions open a short-lived connection, execute repository calls, close.
No SQL written here. No Streamlit imports.

Inputs: config dict (requires: database_path, notification_threshold).
Outputs: pandas DataFrames or aggregated dicts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.db import jobs_repository, referrals_repository
from src.db.connection import get_connection
from src.db.migrations import run_migrations

logger = logging.getLogger(__name__)


def ensure_schema(config: dict) -> None:
    """Run migrations to ensure the schema is up to date. Safe to call on startup."""
    run_migrations(config["database_path"])


def _format_date(iso_str: str | None) -> str:
    """Format ISO-8601 UTC string to 'Jun 10' or 'Jun 10, 2025' for older dates."""
    if not iso_str:
        return ""
    try:
        iso = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        now = datetime.now(timezone.utc)
        if dt.year < now.year:
            return dt.strftime("%b %d, %Y")
        return dt.strftime("%b %d")
    except (ValueError, TypeError):
        return iso_str or ""


def _apply_date_formats(df: pd.DataFrame) -> pd.DataFrame:
    """Format date columns in-place for display. Does not mutate input."""
    df = df.copy()
    for col in ("first_seen_at", "date_posted", "follow_up_date", "applied_date"):
        if col in df.columns:
            df[col] = df[col].apply(_format_date)
    return df


def load_inbox_jobs(config: dict) -> pd.DataFrame:
    """Return jobs with status='Pending', sorted by score DESC."""
    conn = get_connection(config["database_path"])
    try:
        rows = jobs_repository.get_jobs_by_status("Pending", conn)
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame()
    return _apply_date_formats(pd.DataFrame(rows))


def load_high_priority_jobs(config: dict) -> pd.DataFrame:
    """Return jobs where score >= threshold and status not in (Applied, Rejected).
    Combines Pending and Referral-Needed rows, filters by threshold, sorts score DESC.
    """
    threshold = config["notification_threshold"]
    conn = get_connection(config["database_path"])
    try:
        pending = jobs_repository.get_jobs_by_status("Pending", conn)
        referral_needed = jobs_repository.get_jobs_by_status("Referral-Needed", conn)
    finally:
        conn.close()
    combined = pending + referral_needed
    if not combined:
        return pd.DataFrame()
    df = pd.DataFrame(combined)
    df = df[df["score"] >= threshold].sort_values("score", ascending=False)
    return _apply_date_formats(df.reset_index(drop=True))


def load_jobs_by_status(status: str, config: dict) -> pd.DataFrame:
    """Return all jobs with the given status, sorted by score DESC."""
    conn = get_connection(config["database_path"])
    try:
        rows = jobs_repository.get_jobs_by_status(status, conn)
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame()
    return _apply_date_formats(pd.DataFrame(rows))


def load_all_referrals(config: dict) -> pd.DataFrame:
    """Return all referrals sorted by follow_up_date ASC (NULLs last), updated_at DESC."""
    conn = get_connection(config["database_path"])
    try:
        rows = referrals_repository.get_all_referrals(conn)
    finally:
        conn.close()
    if not rows:
        return pd.DataFrame()
    return _apply_date_formats(pd.DataFrame(rows))


def get_badge_counts(config: dict) -> dict:
    """Return sidebar badge counts for all data views.

    Returns: {"Inbox": int, "High Priority": int, "Applied": int,
              "Rejected": int, "Referrals": int}
    """
    threshold = config["notification_threshold"]
    conn = get_connection(config["database_path"])
    try:
        pending = jobs_repository.get_jobs_by_status("Pending", conn)
        applied = jobs_repository.get_jobs_by_status("Applied", conn)
        referral_needed = jobs_repository.get_jobs_by_status("Referral-Needed", conn)
        rejected = jobs_repository.get_jobs_by_status("Rejected", conn)
        referrals = referrals_repository.get_all_referrals(conn)
    finally:
        conn.close()

    hp_count = sum(
        1 for j in (pending + referral_needed) if j["score"] >= threshold
    )

    return {
        "Inbox": len(pending),
        "High Priority": hp_count,
        "Applied": len(applied),
        "Rejected": len(rejected),
        "Referrals": len(referrals),
    }


def load_analytics_data(config: dict) -> dict:
    """Return pre-aggregated data for the Analytics view.

    Returns dict with keys:
        total_jobs: int
        high_priority_count: int
        applied_count: int
        avg_score_hp: float
        jobs_per_day: DataFrame  — columns: date (str), count (int), last 30 days
        score_distribution: DataFrame — columns: bin_label (str), count (int)
        status_counts: DataFrame — columns: status (str), count (int)
        top_companies: DataFrame — columns: company (str), count (int), top 10, score>=0
    """
    threshold = config["notification_threshold"]
    conn = get_connection(config["database_path"])
    try:
        pending = jobs_repository.get_jobs_by_status("Pending", conn)
        applied = jobs_repository.get_jobs_by_status("Applied", conn)
        referral_needed = jobs_repository.get_jobs_by_status("Referral-Needed", conn)
        rejected = jobs_repository.get_jobs_by_status("Rejected", conn)
    finally:
        conn.close()

    all_jobs = pending + applied + referral_needed + rejected
    _empty = pd.DataFrame

    if not all_jobs:
        return {
            "total_jobs": 0,
            "high_priority_count": 0,
            "applied_count": 0,
            "avg_score_hp": 0.0,
            "jobs_per_day": _empty(columns=["date", "count"]),
            "score_distribution": _empty(columns=["bin_label", "count"]),
            "status_counts": _empty(columns=["status", "count"]),
            "top_companies": _empty(columns=["company", "count"]),
        }

    df = pd.DataFrame(all_jobs)
    active = pending + referral_needed
    hp_jobs = [j for j in active if j["score"] >= threshold]
    avg_score_hp = (
        round(sum(j["score"] for j in hp_jobs) / len(hp_jobs), 1) if hp_jobs else 0.0
    )

    # Jobs per day — last 30 days
    df["_dt"] = pd.to_datetime(df["first_seen_at"], errors="coerce", utc=True)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent = df[df["_dt"] >= cutoff].copy()
    recent["date"] = recent["_dt"].dt.strftime("%b %d")
    jobs_per_day = (
        recent.groupby("date").size().reset_index(name="count")
        .sort_values("date")
    )

    # Score distribution — bins of width 10
    df["score_bin"] = (df["score"] // 10) * 10
    score_dist = (
        df.groupby("score_bin").size().reset_index(name="count")
        .assign(bin_label=lambda x: x["score_bin"].astype(str))
        .sort_values("score_bin")[["bin_label", "count"]]
    )

    # Status counts
    status_counts = (
        df.groupby("status").size().reset_index(name="count")
    )

    # Top 10 companies by job count (score >= 0 only)
    top_companies = (
        df[df["score"] >= 0]
        .groupby("company").size().reset_index(name="count")
        .sort_values("count", ascending=False)
        .head(10)
    )

    return {
        "total_jobs": len(df),
        "high_priority_count": len(hp_jobs),
        "applied_count": len(applied),
        "avg_score_hp": avg_score_hp,
        "jobs_per_day": jobs_per_day,
        "score_distribution": score_dist,
        "status_counts": status_counts,
        "top_companies": top_companies,
    }
