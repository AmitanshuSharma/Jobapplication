# Vision

## Mission

Build a personal, local-first Job Intelligence Platform that automatically crawls targeted company career pages, scores Data Engineering roles against a personalized relevance model, and delivers timely alerts, so that I spend my time preparing for and applying to the right roles instead of hunting for them.

## Problem Statement

Entry-level Data Engineering openings at product-based companies are few, they're spread across dozens of career pages on different applicant tracking systems (Greenhouse, Lever, Workday), and they often close quickly. Checking each page by hand every day is slow and easy to miss, and generic job boards bury these roles under irrelevant listings. No existing tool combines targeted crawling, weighted scoring, alerting and application tracking in one local system built around one person's criteria.

## Target User

Me: a third-year B.Tech Computer Science student at JECRC University, Jaipur (graduating 2028), preparing for Data Engineering internships and entry-level roles at product-based companies. I need to catch relevant openings early, track where I've applied and who could refer me, and follow up on time.

The project is also a learning vehicle. Building it means working through real data engineering problems: pulling data from several source APIs, normalizing it into one schema, deduplicating records, scoring, scheduling runs, and serving the results on a dashboard.

## Success Criteria

- All target company career pages are crawled daily without manual effort.
- Only matches above the configured score threshold surface in alerts and the dashboard.
- Telegram and email notifications fire on new matches with no duplicate alerts.
- The dashboard gives clear visibility into each job's status, tags and referral contacts.
- Every job record includes referral tracking fields.
- The system runs fully on a local machine with no paid cloud infrastructure.
- Target companies are prioritized according to a configurable company ranking.

## Non-Goals

- Not a mass-apply or auto-apply tool.
- Not a multi-user platform or SaaS product.
- Not a CRM for managing recruiters broadly.
- Not a resume builder, cover letter generator or LinkedIn automation tool.
- Roles outside Data Engineering are penalized in scoring, not surfaced.
