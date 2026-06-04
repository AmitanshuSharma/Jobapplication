-- schema_version: single row tracks applied migration version.
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER NOT NULL,
    applied_at TEXT    NOT NULL
);

-- jobs: one row per discovered job. Written once at ingestion.
-- status validation is enforced at the application layer, not here (RULES.md §2.5).
CREATE TABLE IF NOT EXISTS jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url          TEXT    NOT NULL,
    ats_job_id          TEXT,
    dedup_hash          TEXT,
    title               TEXT    NOT NULL,
    company             TEXT    NOT NULL,
    location            TEXT,
    location_normalized TEXT,
    description         TEXT,
    experience_range    TEXT,
    tech_stack          TEXT,
    score               INTEGER NOT NULL DEFAULT 0,
    score_breakdown     TEXT,
    passed_threshold    INTEGER NOT NULL DEFAULT 0,
    status              TEXT    NOT NULL DEFAULT 'Pending',
    tags                TEXT,
    notified            INTEGER NOT NULL DEFAULT 0,
    location_ineligible INTEGER NOT NULL DEFAULT 0,
    first_seen_at       TEXT    NOT NULL,
    date_posted         TEXT,
    source_name         TEXT,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    CHECK (notified IN (0, 1)),
    CHECK (location_ineligible IN (0, 1)),
    CHECK (passed_threshold IN (0, 1))
);

-- referrals: user-managed referral tracking, optionally linked to a job.
-- job_id is a nullable FK to jobs.id (DECISIONS.md: referral-first workflows allowed).
CREATE TABLE IF NOT EXISTS referrals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id              INTEGER REFERENCES jobs(id),
    company             TEXT    NOT NULL,
    role                TEXT,
    applied_date        TEXT,
    referral_status     TEXT,
    recruiter_contacted INTEGER NOT NULL DEFAULT 0,
    follow_up_date      TEXT,
    notes               TEXT,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    CHECK (recruiter_contacted IN (0, 1))
);

-- Primary dedup key. SQLite treats NULLs as distinct in unique indexes, so rows
-- with ats_job_id=NULL are not protected here — dedup_hash covers those.
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_source_url_ats_job_id
    ON jobs (source_url, ats_job_id);

-- Fallback dedup key for jobs where ats_job_id is NULL.
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_dedup_hash
    ON jobs (dedup_hash);

-- Dashboard status-filter queries.
CREATE INDEX IF NOT EXISTS idx_jobs_status
    ON jobs (status);

-- High Priority sort and notification eligibility ordering.
CREATE INDEX IF NOT EXISTS idx_jobs_score
    ON jobs (score DESC);

-- Composite index for dashboard views that filter by status and sort by score.
CREATE INDEX IF NOT EXISTS idx_jobs_status_score
    ON jobs (status, score DESC);

-- Dispatcher query: WHERE notified=0 AND location_ineligible=0 AND score>=N.
CREATE INDEX IF NOT EXISTS idx_jobs_notified
    ON jobs (notified);

CREATE INDEX IF NOT EXISTS idx_jobs_location_ineligible
    ON jobs (location_ineligible);

-- Recency sort for dashboard ordering.
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen_at
    ON jobs (first_seen_at DESC);
