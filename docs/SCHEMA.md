# Database Schema — Job Intelligence Platform V1

Status: Approved for V1 implementation.
Companion documents: `ARCHITECTURE.md`, `SCORING.md`, `PRD.md`, `DECISIONS.md`, `CONFIG.md` (deferred).

SQLite is the only permitted database (DECISIONS.md). All schema changes must be versioned through `db/migrations.py`. No SQL may be written outside `src/db/` (RULES.md §4.9).

---

## 1. jobs Table

One row per discovered job. Written once at ingestion. Only the fields listed as user-editable (status, tags) are updated after insert — through the repository layer only.

### Identity

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `id` | INTEGER | No | autoincrement | Internal primary key. Used for stable tiebreaking (SCORING.md §9). |
| `source_url` | TEXT | No | — | Canonical URL of the job posting. Component of the primary dedup key. |
| `ats_job_id` | TEXT | Yes | NULL | ATS-provided job identifier (Greenhouse, Lever, Workday). Component of the primary dedup key when present. |
| `dedup_hash` | TEXT | Yes | NULL | SHA-256 hash of normalized `company + title + location_normalized`. Fallback dedup key when `ats_job_id` is absent. Populated only when `ats_job_id` is NULL. See §6. |

### Content

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `title` | TEXT | No | — | Job title as returned by the source. Records missing this field are rejected at ingestion (RULES.md §4.3). |
| `company` | TEXT | No | — | Company name as returned by the source. Required. |
| `location` | TEXT | Yes | NULL | Raw location string, preserved exactly as scraped (RULES.md §4.5). |
| `location_normalized` | TEXT | Yes | NULL | Normalized location string (e.g., "Gurgaon" → "Gurugram"). Used for notification payload and location matching. |
| `description` | TEXT | Yes | NULL | Full job description text. Used as the input for keyword scoring. |
| `experience_range` | TEXT | Yes | NULL | Experience requirement as returned by the source (e.g., "5–8 years"). Not parsed or scored in V1. |
| `tech_stack` | TEXT | Yes | NULL | Comma-separated list of tech keywords detected at ingestion. Informational only; scoring operates directly on `description`. |

### Scoring

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `score` | INTEGER | No | 0 | Final relevance score. Computed once at ingestion. Write-once; not recalculated on re-crawl (RULES.md §6.1). May be negative. |
| `score_breakdown` | TEXT | Yes | NULL | JSON blob containing the full scoring explanation. Structure defined in §8. Read-only after insert. |
| `passed_threshold` | INTEGER | No | 0 | Boolean (0/1). Snapshot: 1 if `score >= NOTIFICATION_THRESHOLD` at ingestion time. Does not update if the threshold is later changed. See §7. |

### Status

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `status` | TEXT | No | 'Pending' | User-managed pipeline state. Allowed values and transitions defined in §9. |
| `tags` | TEXT | Yes | NULL | Comma-separated free-text labels set by the user (e.g., `"strong-fit,referral-needed"`). See §7. |

### Notification

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `notified` | INTEGER | No | 0 | Boolean (0/1). Set to 1 by `dispatcher.mark_notified()` once at least one channel succeeds. Never reset to 0. |
| `location_ineligible` | INTEGER | No | 0 | Boolean (0/1). Set to 1 at ingestion if `location_normalized` does not match `ACCEPTED_LOCATIONS`. Jobs with this flag set never trigger notifications (SCORING.md §5, RULES.md §6.3). See §7. |

### Timestamps

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `first_seen_at` | TEXT | No | current UTC | ISO-8601 UTC timestamp. Set at insert time. Never updated on re-crawl. |
| `date_posted` | TEXT | Yes | NULL | Job posting date from the source. ISO-8601 where available. Used for tiebreaking (SCORING.md §9). NULL when the source does not provide it. |

---

## 2. referrals Table

One row per referral tracking record. Owned and edited entirely by the user through the dashboard. Independent of the `jobs` table — not foreign-keyed to `jobs.id` in V1 to allow referral records that do not yet correspond to a crawled job.

Proposed — confirm before implementing: whether to add a nullable `job_id` foreign key to `jobs.id` for optional linkage. Not specified in source documents.

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `id` | INTEGER | No | autoincrement | Internal primary key. |
| `company` | TEXT | No | — | Name of the company the referral targets. Required. |
| `role` | TEXT | Yes | NULL | Job title or role name for the referral. |
| `applied_date` | TEXT | Yes | NULL | ISO-8601 date when the user applied. Set by the user. |
| `referral_status` | TEXT | Yes | NULL | Current state of the referral (e.g., "Pending", "Confirmed", "Declined"). User-managed. Proposed — confirm allowed values before implementing. |
| `recruiter_contacted` | INTEGER | No | 0 | Boolean (0/1). Set to 1 by the user when a recruiter has been contacted. |
| `follow_up_date` | TEXT | Yes | NULL | ISO-8601 date for the next scheduled follow-up. Set by the user. |
| `notes` | TEXT | Yes | NULL | Proposed — confirm before implementing. Free-text notes. Not explicitly listed in source documents but implied by PRD §2 referral tracking workflow. |
| `created_at` | TEXT | No | current UTC | ISO-8601 UTC timestamp. Set at insert time. |
| `updated_at` | TEXT | No | current UTC | ISO-8601 UTC timestamp. Updated on every write. |

---

## 3. schema_version Table

Single-row table. Tracks the currently applied schema version. Read by `db/migrations.py` at startup to determine whether migrations need to run.

| Column | Type | Nullable | Default | Purpose |
|---|---|---|---|---|
| `version` | INTEGER | No | 1 | Current schema version number. Incremented by `migrations.py` each time a migration is applied. |
| `applied_at` | TEXT | No | current UTC | ISO-8601 UTC timestamp of when the current version was applied. |

There is exactly one row in this table at all times. It is inserted by the V1 migration and updated in place by subsequent migrations.

---

## 4. Indexes

| Index Name | Table | Columns | Unique | Query Pattern Served |
|---|---|---|---|---|
| `idx_jobs_source_url_ats_job_id` | jobs | `(source_url, ats_job_id)` | Yes | Primary dedup lookup in `pipeline/ingest.py` before insert. |
| `idx_jobs_dedup_hash` | jobs | `(dedup_hash)` | Yes | Fallback dedup lookup when `ats_job_id` is NULL. |
| `idx_jobs_status` | jobs | `(status)` | No | Dashboard view filters that load jobs by status. |
| `idx_jobs_score` | jobs | `(score DESC)` | No | High Priority view sort; notification eligibility query ordering; tiebreaking. |
| `idx_jobs_notified` | jobs | `(notified)` | No | Dispatcher query: `WHERE notified=0 AND score >= threshold AND location_ineligible=0`. |
| `idx_jobs_location_ineligible` | jobs | `(location_ineligible)` | No | Dispatcher eligibility filter (combined with `notified` and `score` in the same query). |
| `idx_jobs_first_seen_at` | jobs | `(first_seen_at DESC)` | No | Proposed — confirm before implementing. Recency sort for dashboard ordering. Not explicitly required by source documents. |

The unique indexes on `(source_url, ats_job_id)` and `(dedup_hash)` enforce the deduplication constraint at the database level in addition to the application-level check in `ingest.py`.

Note: because SQLite treats NULLs as distinct in unique indexes, `(source_url, ats_job_id)` does not protect against duplicates when `ats_job_id` is NULL. The `dedup_hash` unique index covers that case.

---

## 5. Constraints

### NOT NULL

`jobs`: `id`, `source_url`, `title`, `company`, `score`, `passed_threshold`, `status`, `notified`, `location_ineligible`, `first_seen_at`.

`referrals`: `id`, `company`, `recruiter_contacted`, `created_at`, `updated_at`.

`schema_version`: `version`, `applied_at`.

Records missing `title`, `company`, or `source_url` are rejected at ingestion before the database is touched (RULES.md §4.3).

### UNIQUE

- `(jobs.source_url, jobs.ats_job_id)` — primary dedup key.
- `jobs.dedup_hash` — fallback dedup key for records where `ats_job_id` is NULL.

`dedup_hash` is left NULL for records that have `ats_job_id`, so the two mechanisms do not conflict.

### CHECK

- `jobs.notified IN (0, 1)`
- `jobs.location_ineligible IN (0, 1)`
- `jobs.passed_threshold IN (0, 1)`
- `referrals.recruiter_contacted IN (0, 1)`
- `jobs.status IN ('Pending', 'Applied', 'Referral-Needed', 'Rejected')` — prevents invalid states from any code path.
- `jobs.score`: no range constraint. Scores may be negative (when penalties dominate). No upper bound.

---

## 6. Deduplication Strategy

Deduplication is enforced at the application layer in `pipeline/ingest.py` and backed by unique database indexes. Two mechanisms are used in a defined priority order.

### Primary Key: source_url + ats_job_id

When a crawled job has a non-null `ats_job_id`, the deduplication check queries for an existing row where both `source_url` and `ats_job_id` match. This is the preferred mechanism because both fields come directly from the ATS and are stable across re-crawls.

### Fallback Hash: hash(company + title + location_normalized)

When `ats_job_id` is absent or empty, a SHA-256 hash is computed from the concatenation of normalized `company`, `title`, and `location_normalized` (lowercased, stripped of leading/trailing whitespace). This hash is stored in `dedup_hash`. The unique index on `dedup_hash` enforces uniqueness.

`dedup_hash` is only populated for records where `ats_job_id` is NULL. Records with `ats_job_id` leave `dedup_hash` as NULL.

### Collision Handling

When either check finds an existing record, the incoming record is skipped. No update is made to the existing record's score, status, tags, or any field. The skip is logged at INFO level with: title, company, source URL, and which key type matched. No exception is raised; the pipeline continues to the next job.

Score drift when config changes are made is a known V1 limitation (ARCHITECTURE.md §10).

---

## 7. Field Descriptions

**`location_ineligible`**: Set at ingestion when `location_normalized` does not match any string in `ACCEPTED_LOCATIONS`. Permanently gates the job from notification, regardless of score. The job is still stored, scored, and visible in the dashboard. This flag is never changed after insert (RULES.md §6.3, SCORING.md §5).

**`dedup_hash`**: A SHA-256 hex digest of normalized company name + job title + normalized location. Used only when `ats_job_id` is absent. See §6.

**`score_breakdown`**: JSON text blob stored in a TEXT column. Contains the full scoring explanation. Defined in §8. Read-only after insert; never modified.

**`passed_threshold`**: Snapshot boolean set at ingestion. Records whether `score >= NOTIFICATION_THRESHOLD` at the moment of ingestion. Does not change if the threshold is reconfigured later. The dispatcher uses a live score comparison against the current threshold for notification eligibility, not this flag — `passed_threshold` is for dashboard display and reporting only. Proposed — confirm this dispatcher behavior before implementing.

**`notified`**: Set to 1 by `dispatcher.mark_notified()` when at least one notification channel succeeds. Once set to 1, never reset. Prevents re-notification on subsequent crawl runs (RULES.md §6.1, ARCHITECTURE.md §6).

**`tags`**: Comma-separated TEXT string of user-applied labels. No normalized tags table in V1 (ARCHITECTURE.md §10 deliberate simplification). Tags are written only through the repository layer. No database-level validation of individual tag values; that is the dashboard component's responsibility.

---

## 8. score_breakdown Storage Format

The `score_breakdown` column stores a JSON text blob. Produced by `scoring/scorer.py` at ingestion. Never modified after insert. Displayed in the dashboard for transparency (SCORING.md Score Explanation Rules).

### JSON Structure

Four top-level keys:

- `role_match` (boolean): Whether the job title matched any entry in `ACCEPTED_ROLE_KEYWORDS`. False means the role mismatch penalty was applied.
- `components` (array of objects): Each scoring component applied, in order. Each element has:
  - `label` (string): Human-readable component name (e.g., `"PySpark"`, `"Remote Bonus"`, `"Tier 1 Company Bonus"`, `"Role Mismatch Penalty"`).
  - `points` (integer): Signed integer contribution to the final score. Positive for bonuses, negative for penalties.
- `final_score` (integer): Sum of all `points` values. Must equal `jobs.score`.
- `threshold_at_ingestion` (integer): Value of `NOTIFICATION_THRESHOLD` at scoring time. Stored for auditability because the threshold is configurable.

`components` must be non-empty for every record. A job with zero keyword matches must still emit at least the role match or mismatch entry.

### Examples (prose)

**Senior Data Engineer at Atlassian, remote, with PySpark + Databricks + Kafka:**
- `role_match`: true
- components: PySpark +10, Databricks +10, Kafka +8, Remote Bonus +5, Tier 1 Company Bonus +8
- `final_score`: 41
- `threshold_at_ingestion`: 20

**Business Analyst at untiered company, US location, Tableau in description:**
- `role_match`: false
- components: Role Mismatch Penalty −50, Business Analyst −8, Tableau −5
- `final_score`: −63
- `threshold_at_ingestion`: 20

---

## 9. Status Values

`jobs.status` tracks the user's personal pipeline state for each job. Changes are user-initiated only via the dashboard status dropdown. No automated process changes a job's status (ARCHITECTURE.md §7).

| Value | Meaning |
|---|---|
| `Pending` | Default. Job ingested and scored. User has not yet reviewed or acted on it. |
| `Applied` | User has submitted an application. |
| `Referral-Needed` | User wants a referral before or instead of applying directly. |
| `Rejected` | User has decided not to pursue the role, or has been rejected after applying. |

### Permitted Transitions

All transitions are user-initiated. No automatic or programmatic transitions exist.

- **From Pending**: → Applied, Referral-Needed, Rejected.
- **From Applied**: → Rejected (unsuccessful or withdrawn). → Pending (undo). → Referral-Needed (approach change).
- **From Referral-Needed**: → Applied (referral obtained), Pending (undo), Rejected.
- **From Rejected**: → Pending (undo). The Rejected view exposes this path explicitly (ARCHITECTURE.md §7).

No `Archived` or `Expired` status in V1. Proposed — confirm before implementing: whether soft-delete or archive is needed for old records.

---

## 10. Migration Assumptions

### Schema Versioning

`schema_version` holds a single row with the current integer version and the timestamp it was applied. `db/migrations.py` reads this row at startup. If the table does not exist, the database is treated as uninitialized and the full V1 migration is applied.

### V1 Migration Sequence

Applied in order:

1. Create `schema_version` table.
2. Create `jobs` table with all columns in §1.
3. Create `referrals` table with all columns in §2.
4. Create all indexes in §4.
5. Add all CHECK constraints in §5.
6. Enable WAL mode (`PRAGMA journal_mode=WAL`) to allow concurrent dashboard reads during scheduler writes (ARCHITECTURE.md §5).
7. Insert the single `schema_version` row: `version = 1`, current UTC timestamp.

The migration must be idempotent on a fresh database. `migrations.py` checks the `schema_version` value before executing any DDL and does not re-run already-applied steps.

### Schema Changes in V1

V1 does not support incremental column-level migrations. If the schema must change during V1 development: delete `data/jobs.db`, re-run migrations, re-ingest from scratch. Accepted V1 limitation (ARCHITECTURE.md §10). Acceptable for a local, single-user tool.

V2 candidates: additive `ALTER TABLE ADD COLUMN` migrations; a numbered migration script runner.

### What schema_version Tracks

The integer `version` matches the highest successfully applied migration. `migrations.py` compares it to the highest migration in its list and applies any that are missing in sequence. No rollback history, no partial-apply detection in V1.

---

## Source References

- `ARCHITECTURE.md §5` — tables list, WAL mode, write-back paths, V1 simplifications
- `SCORING.md` — scoring formula, role match gate, location rules, company tiers, tiebreaking
- `PRD.md` — required fields, dedup key definition, referral tracking fields, status views
- `DECISIONS.md` — SQLite confirmed, notification threshold default 20
- `RULES.md §4.2–4.9, §6.1, §6.3` — dedup key, required fields, raw value preservation, schema versioning, re-notification rules, location gate
