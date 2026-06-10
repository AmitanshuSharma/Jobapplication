"""Analytics view — read-only metrics and charts.

KPIs (max 4): Total jobs, High Priority, Applied, Avg score (HP).
Charts (stacked vertically, full width):
  1. Jobs discovered per day — last 30 days (bar)
  2. Score distribution — histogram (bar)
  3. Status breakdown — horizontal bar (Altair)
  4. Top 10 companies — horizontal bar (Altair)

All bars use #1f2937. No pie charts. No animations.
"""
import altair as alt
import streamlit as st

from src.dashboard import data_loader


def render(config: dict) -> None:
    """Render the Analytics view."""
    st.subheader("Analytics")

    data = data_loader.load_analytics_data(config)

    # ── KPIs ──────────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total jobs", data["total_jobs"])
    col2.metric("High priority", data["high_priority_count"])
    col3.metric("Applied", data["applied_count"])
    col4.metric("Avg score (HP)", data["avg_score_hp"])

    st.divider()

    # ── Chart 1: Jobs per day ─────────────────────────────────────────────
    st.caption("Jobs discovered per day — last 30 days")
    jobs_per_day = data["jobs_per_day"]
    if not jobs_per_day.empty:
        st.bar_chart(jobs_per_day.set_index("date")["count"])
    else:
        st.caption("No data for the last 30 days.")

    # ── Chart 2: Score distribution ───────────────────────────────────────
    st.caption("Score distribution")
    score_dist = data["score_distribution"]
    if not score_dist.empty:
        st.bar_chart(score_dist.set_index("bin_label")["count"])
    else:
        st.caption("No score data.")

    # ── Chart 3: Status breakdown ─────────────────────────────────────────
    st.caption("Pipeline status")
    status_counts = data["status_counts"]
    if not status_counts.empty:
        chart = (
            alt.Chart(status_counts)
            .mark_bar(color="#1f2937")
            .encode(
                x=alt.X("count:Q", title="Count"),
                y=alt.Y("status:N", sort="-x", title=None),
            )
            .properties(height=140)
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No status data.")

    # ── Chart 4: Top companies ────────────────────────────────────────────
    st.caption("Top companies by job count (score ≥ 0)")
    top_companies = data["top_companies"]
    if not top_companies.empty:
        chart = (
            alt.Chart(top_companies)
            .mark_bar(color="#1f2937")
            .encode(
                x=alt.X("count:Q", title="Jobs"),
                y=alt.Y("company:N", sort="-x", title=None),
            )
            .properties(height=max(140, len(top_companies) * 22))
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.caption("No company data.")
