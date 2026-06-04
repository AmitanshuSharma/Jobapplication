# Confirmed Decisions

## FastAPI
Not included in Version 1.

## LinkedIn Scraping
Not included in Version 1.

## Scheduler
Use Python schedule library during development.
Use cron for production automation.

## Notification Threshold
Configurable.
Default: 20.

## Database
SQLite is the primary database for Version 1.

## Architecture Style
Local-first single-user application.
# Architecture & Schema Decisions

## Notification Success Policy

A job is considered successfully notified if at least one notification channel succeeds.

Rules:

- Telegram success + Email success → mark notified
- Telegram success + Email failure → mark notified
- Telegram failure + Email success → mark notified
- Telegram failure + Email failure → do not mark notified

Jobs are retried only when all notification channels fail.

Rationale:
Prevent duplicate alerts while maximizing successful delivery.

---

## Configuration Documentation

Configuration documentation will be maintained in a dedicated:

docs/CONFIG.md

README.md contains only installation, setup, and usage instructions.

Rationale:
Separate operational configuration from user onboarding documentation.

---

## Playwright Usage Policy

Playwright is an approved dependency for Version 1.

Architecture must support both:

- Direct HTTP/API extraction
- Playwright-rendered extraction

Crawler implementation chooses the extraction strategy per source after ATS verification.

Playwright is optional and should only be used when direct extraction is insufficient.

Rationale:
Maintain flexibility while avoiding unnecessary browser automation.

---

## Referral Linking

referrals.job_id is approved as an optional nullable foreign key.

Rules:

- Referral records may exist without a linked job.
- Referral records may optionally reference jobs.id.
- The referral workflow must function whether a linked job exists or not.

Rationale:
Supports both referral-first and job-first workflows.

---

## Referral Notes

The referrals table includes:

notes TEXT NULL

Purpose:

- recruiter conversations
- follow-up reminders
- referral context
- miscellaneous tracking notes

Rationale:
Provides lightweight context without requiring additional tables.

---

## Threshold Evaluation Policy

The dispatcher always evaluates notification eligibility using the current value of:

NOTIFICATION_THRESHOLD

loaded from configuration.

The stored field:

passed_threshold

is a historical snapshot recorded at ingestion time and is used only for:

- dashboard display
- reporting
- auditing

It is not used for notification decisions.

Rationale:
Configuration changes should take effect immediately without requiring re-ingestion.

---

## Tag Storage Policy

Tags are stored as a comma-separated TEXT field.

Rules:

- Tag names may not contain commas.
- Empty string clears all tags.
- Tags remain user-managed metadata only.

Normalization into a separate tags table is out of scope for Version 1.

Rationale:
Keep schema simple for a single-user local application.

---

## Deduplication Priority

Deduplication checks occur in the following order:

1. ATS Job ID + Source URL
2. Source URL
3. SHA-256 hash(company + title + normalized location)

Application-level checks and database-level unique constraints must enforce the same priority.

Rationale:
Maximize duplicate detection across inconsistent ATS implementations.


---

# Module Implementation Decisions

## Configuration Access Pattern

get_config() returns a cached module-level singleton.

Rules:

- Configuration is loaded once during startup.
- Subsequent calls return the cached instance.
- Configuration files are not re-read during normal execution.

Rationale:
Avoid repeated disk reads and ensure consistent configuration across modules.

---

## Dependency Injection for Crawlers

Configuration must be passed through constructors.

Example:

GreenhouseCrawler(config)

Rules:

- No crawler may import config_loader directly.
- All crawler dependencies must be explicit constructor arguments.

Rationale:
Improves testing and prevents hidden dependencies.

---

## HTTP Client Configuration

http_client.get() receives configuration values as parameters.

Rules:

- No module-level configuration access.
- Timeout, retry count, and rate limit settings are passed explicitly.

Rationale:
Improves testability and predictability.

---

## Migration Database Path

run_migrations(db_path) always receives db_path as a parameter.

Rules:

- migrations.py never imports config_loader.
- Database location must always be explicit.

Rationale:
Keeps migration layer independent and testable.

---

## Referral Default Sorting

get_all_referrals() returns records sorted by:

1. follow_up_date ascending (nulls last)
2. updated_at descending

Rationale:
Upcoming actions should always appear first.

---

## Streamlit Refresh Policy

status_editor.py and other write-capable dashboard components must call:

st.rerun()

after successful save operations.

Rationale:
Immediately refresh UI state after modifications.

---

## Referral Form Requirements

Required fields:

- company

Optional fields:

- role
- applied_date
- referral_status
- recruiter_contacted
- follow_up_date
- notes
- job_id

Rationale:
Allow referral-first workflows without forcing unnecessary data entry.

---

## Export Control Strategy

export_controls.py receives:

render_export_controls(df, data_type)

where:

data_type ∈ {"jobs", "referrals"}

The parameter determines which export functions are called.

Rationale:
Simple explicit dispatch mechanism.

---

## Pipeline Summary Format

run_pipeline() returns:

{
    "greenhouse_jobs": int,
    "lever_jobs": int,
    "workday_jobs": int,
    "inserted_jobs": int,
    "duplicate_jobs": int,
    "rejected_jobs": int,
    "notifications_sent": int,
    "notification_failures": int
}

Rationale:
Provides complete operational visibility for logs and testing.

---

## Referral Notes Field

The referrals table includes:

notes TEXT NULL

Approved for Version 1.

Rationale:
Useful operational context without introducing additional tables.

---

## Dispatcher Threshold Policy

Dispatcher uses:

current NOTIFICATION_THRESHOLD

from configuration.

Dispatcher eligibility query:

notified = 0
AND location_ineligible = 0
AND score >= current_threshold

passed_threshold remains historical metadata only.

Rationale:
Threshold changes should take effect immediately.

---

## Rejected View Exports

The Rejected dashboard view includes export controls.

Users may export rejected jobs to CSV or Excel.

Rationale:
Rejected opportunities may still be useful for later analysis.

---
## Configuration Location

Runtime configuration files live under:

config/config.yaml
config/.env

Template files:

config/config.yaml.example
config/.env.example

All modules must load configuration from the config directory.

Rationale:
Keep configuration isolated from application code and project root clutter.

---

## Timestamp Ownership Policy

Repository layer exclusively owns:

- created_at
- updated_at

Caller layer exclusively owns:

- first_seen_at
- date_posted

Repositories must generate UTC timestamps internally and must not accept lifecycle timestamps from callers.

Rationale:
Maintain consistent record lifecycle tracking and prevent timestamp corruption.

---
## SQLite Mode

SQLite operates in WAL mode.

Rationale:
Support concurrent dashboard reads and scheduler writes.

---

## Timestamp Policy

All database timestamps use UTC ISO-8601 format with Z suffix.

Example:

2026-05-28T14:22:11Z

---

## Repository Ownership

Repositories own:

- created_at
- updated_at

Callers own:

- first_seen_at
- date_posted

Repositories must not mutate caller input dictionaries.

---
## Migration History Policy

Version 1 uses a single-row schema_version table.

Future versions may evolve to:

schema_version_history

with one row per migration.

Current implementation is approved because Version 1 only requires tracking the active schema version.

---
## Scoring Engine Ownership

rules.py owns:

- keyword weights
- role matching rules
- company tier helpers
- location helper logic

scorer.py owns:

- score calculation
- score breakdown generation
- final score assembly
- threshold evaluation support

Rationale:
Separate scoring configuration from scoring execution.

---
## Scoring Breakdown Format

score_breakdown contains:

- role_match
- matched_positive_keywords
- matched_negative_keywords
- components
- final_score
- threshold_at_ingestion

Rationale:
Provide complete transparency into scoring decisions and dashboard explanations.

---
## Crawler Parse Failure Policy

Concrete crawlers must use per-record isolation.

Malformed individual job records are:

- logged
- skipped
- excluded from results

Valid records from the same payload must still be returned.

CrawlerParseError is reserved for structural failures that make the entire payload unparseable.

Rationale:
One malformed listing must never prevent discovery of valid opportunities.
---
## Crawler Failure Policy

Concrete crawlers use per-record isolation.

Malformed records are:
- logged
- skipped
- excluded from results

Valid records from the same payload continue processing.

CrawlerParseError is reserved for payload-level structural failures.

---

## Shared Normalization

Location normalization is implemented in:

src/utils/normalizer.py

Normalization owns:
- string cleanup
- alias mapping
- canonical value generation

Business eligibility remains owned by the pipeline layer.

---

## HTTP Retry Policy

Retry:
- 429
- 500
- 502
- 503
- 504
- network failures

Backoff:

1s → 2s → 4s → 8s → 16s (cap)

Other HTTP failures are not retried.

---

## Greenhouse Description Handling

Greenhouse HTML content is converted to plain text using:

BeautifulSoup(...).get_text(separator=" ", strip=True)

before storage.

Rationale:
The scoring engine operates on normalized text rather than HTML.

---

## Greenhouse Company Attribution

The Greenhouse API does not include the owning company name.

fetch() injects an internal metadata field which parse() maps into the JobDict company field.

Rationale:
Maintain a deterministic parser while supporting multiple board tokens.

---
