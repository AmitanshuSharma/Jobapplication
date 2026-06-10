"""Export DataFrames to CSV or Excel bytes.

Inputs: pandas DataFrame.
Outputs: bytes (CSV or xlsx).
No database access. No Streamlit imports.
"""
import io

import pandas as pd


def export_jobs_csv(jobs_df: pd.DataFrame) -> bytes:
    """Return UTF-8 CSV bytes for the given jobs DataFrame."""
    return jobs_df.to_csv(index=False).encode("utf-8")


def export_jobs_excel(jobs_df: pd.DataFrame) -> bytes:
    """Return xlsx bytes for the given jobs DataFrame."""
    buf = io.BytesIO()
    jobs_df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def export_referrals_csv(referrals_df: pd.DataFrame) -> bytes:
    """Return UTF-8 CSV bytes for the given referrals DataFrame."""
    return referrals_df.to_csv(index=False).encode("utf-8")


def export_referrals_excel(referrals_df: pd.DataFrame) -> bytes:
    """Return xlsx bytes for the given referrals DataFrame."""
    buf = io.BytesIO()
    referrals_df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()
