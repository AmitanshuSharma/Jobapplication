# Module Reference — Job Intelligence Platform V1

Status: Approved for V1 implementation.
Source documents: ARCHITECTURE.md, SCHEMA.md, SCORING.md, RULES.md, ROADMAP.md.

This document defines every module in the system. For each module: purpose, public interface, inputs, outputs, internal dependencies, allowed imports, and forbidden imports. All design decisions are grounded in the source documents above. Items not found in those documents are flagged explicitly.

---

## Cross-Cutting Rules (Summary)

These rules apply globally and are spelled out per module in the Forbidden Imports sections below.

| Rule | Source |
|---|---|
| No module outside `src/db/` may import `sqlite3` or execute SQL | RULES.md §4.9, ARCHITECTURE.md §5 |
| `scoring/scorer.py` and `scoring/rules.py` must have zero I/O imports | ARCHITECTURE.md §4, ROADMAP.md Phase 3 |
| Crawlers must not import from `pipeline/`, `db/`, `notifications/`, or `dashboard/` | ARCHITECTURE.md §4 interface contracts |
| `ingest.py` must not import from any crawler module | ARCHITECTURE.md §4 interface contracts |
| `data_loader.py` is the only dashboard file permitted to import from `src/db/` | ARCHITECTURE.md §4, §7 |
| Dashboard views and components must not import from `db/`, `scoring/`, `crawlers/`, or `notifications/` | ARCHITECTURE.md §7 |
| Notifiers must not import from `db/` | ARCHITECTURE.md §4 |
| `dispatcher.py` must not import from crawlers or dashboard | ARCHITECTURE.md §4 |

---

## Package: Root (`src/`)

---

### `config_loader.py`

**Purpose.** Loads `config.yaml` and `.env` and exposes a single typed config object; fails fast at startup if required keys are missing.

**Public Interface.**

- `load_config(config_path, env_path) -> dict`
  Accepts a path to `config.yaml` and a path to `.env`. Returns a dict containing all configuration values with secrets merged in from `.env`. Raises a descriptive `KeyError` or `ValueError` if any required key is absent.

- `get_config() -> dict`
  Proposed — confirm before implementing: whether this function caches and returns a module-level singleton, or whether callers always call `load_config` directly.

**Inputs.**
- Path to `config.yaml` — non-secret operational values: `database_path`, `schedule_interval_minutes`, `notification_threshold`, scoring weights, `accepted_locations`, `accepted_role_keywords`, `positive_keywords`, `negative_keywords`, `company_tier_1`, `company_tier_2`, `greenhouse_board_tokens`, `lever_company_ids`, `workday_urls`.
- Path to `.env` — secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`.

**Outputs.**
- Returns a dict. No file writes. No DB writes. No HTTP calls.
- Raises a named exception if a required key is missing (fail fast per ARCHITECTURE.md §2).

**Dependencies.** None (no other project modules imported).

**Allowed Imports.**
- `os` — environment variable access and path resolution.
- `pathlib` — path handling.
- `yaml` (PyYAML) — to parse `config.yaml`.
- `dotenv` (python-dotenv) — to load `.env`.

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Config loader has no database responsibility. |
| `requests` | Config loader performs no HTTP calls. |
| `streamlit` | Config loader runs in non-dashboard contexts (scheduler, tests). |
| Any `src/` module | Config loader is the root dependency; importing any other project module creates a circular dependency. |

---

## Package: `crawlers/`

---

### `crawlers/base_crawler.py`

**Purpose.** Defines the abstract `BaseCrawler` class that all source-specific crawlers must extend, enforcing a consistent `fetch` / `parse` / `run` contract.

**Public Interface.**

- `BaseCrawler` (abstract class)
  - `fetch(self) -> object` — abstract. Subclasses implement source-specific fetching. Return type is source-specific (raw response object or HTML string).
  - `parse(self, raw) -> list` — abstract. Accepts the raw output of `fetch` and returns a list of job dicts conforming to the job schema.
  - `run(self) -> list` — concrete. Calls `fetch()`, passes the result to `parse()`, returns the list of job dicts. Catches and logs exceptions from `fetch` and `parse` without re-raising, per RULES.md §5.8.

**Inputs.**
- Config dict passed at instantiation. Proposed — confirm before implementing: whether config is passed to `__init__` or accessed via a module-level `config_loader` import.

**Outputs.**
- `run()` returns a `list` (empty or populated) of job dicts. Never raises to the caller per RULES.md §5.8.

**Dependencies.**
- `crawlers.exceptions` — to catch and raise `CrawlerFetchError` and `CrawlerParseError`.

**Allowed Imports.**
- `abc` — to declare abstract methods.
- `logging` — for fetch and parse error logging.
- `crawlers.exceptions` — typed exceptions.

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Crawlers must not touch the database (ARCHITECTURE.md §2, RULES.md §4.9). |
| `pipeline.ingest` | Crawlers emit job dicts; they do not call ingest (ARCHITECTURE.md §4 interface contracts). |
| `db.*` | All DB access is forbidden outside `src/db/`. |
| `notifications.*` | Crawlers have no notification responsibility. |
| `dashboard.*` | Crawlers have no dashboard responsibility. |
| `scoring.*` | Crawlers do not score jobs; ingest does (ARCHITECTURE.md §2). |

---

### `crawlers/http_client.py`

**Purpose.** Provides a shared HTTP GET function with retry logic, rate limiting, and typed error raising for use by direct-HTTP crawlers.

**Public Interface.**

- `get(url, headers, timeout) -> Response`
  Accepts a URL string, an optional headers dict, and an optional timeout integer (seconds). Returns a `requests.Response` object on success. Raises `CrawlerFetchError` on non-200 status or network error. Implements retry and rate-limit delay internally.

**Inputs.**
- `url` — string URL to fetch.
- `headers` — dict of HTTP headers. Optional.
- `timeout` — integer seconds. Optional; falls back to a config default. Proposed — confirm before implementing: whether config is passed as a parameter or via a module-level import.

**Outputs.**
- Returns a `requests.Response` object on success.
- Raises `CrawlerFetchError` on any failure (non-200, timeout, connection error).
- Logs every fetch attempt (URL + timestamp) per RULES.md §5.7.

**Dependencies.**
- `crawlers.exceptions` — to raise `CrawlerFetchError`.

**Allowed Imports.**
- `requests` — HTTP client.
- `time` — for rate-limit delays.
- `logging` — to log fetch attempts and errors.
- `crawlers.exceptions` — typed exceptions.

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | HTTP client has no database responsibility. |
| `pipeline.*` | Not in scope. |
| `db.*` | All DB access forbidden outside `src/db/`. |
| `notifications.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `scoring.*` | Not in scope. |

---

### `crawlers/playwright_utils.py`

**Purpose.** Provides a `render_page` function that uses Playwright to load a JavaScript-rendered URL and return the final HTML string.

**Public Interface.**

- `render_page(url) -> str`
  Accepts a URL string. Launches a headless Playwright browser, loads the page, waits for JS to settle, and returns the rendered HTML as a string. Raises `CrawlerFetchError` if the page cannot be loaded.

**Inputs.**
- `url` — string URL to render.

**Outputs.**
- Returns a string of rendered HTML.
- Raises `CrawlerFetchError` on load failure.

**Dependencies.**
- `crawlers.exceptions` — to raise `CrawlerFetchError`.

**Allowed Imports.**
- `playwright.sync_api` — Playwright browser automation.
- `logging` — for fetch attempt logging per RULES.md §5.7.
- `crawlers.exceptions` — typed exceptions.

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | No database responsibility. |
| `requests` | Playwright is the fetch backend here; mixing is unnecessary. |
| `pipeline.*` | Not in scope. |
| `db.*` | All DB access forbidden outside `src/db/`. |
| `notifications.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `scoring.*` | Not in scope. |

---

### `crawlers/exceptions.py`

**Purpose.** Defines the typed exception classes used by all crawler modules to signal fetch and parse failures.

**Public Interface.**

- `CrawlerFetchError` — raised when an HTTP request or page render fails (non-200, timeout, connection error).
- `CrawlerParseError` — raised when parsing retrieved content fails (missing expected fields or HTML structure).

Both are subclasses of `Exception`. Both accept a message string and, optionally, the source URL.

**Inputs.** N/A — exception classes only.

**Outputs.** N/A — exception classes only.

**Dependencies.** None.

**Allowed Imports.**
- None beyond Python builtins.

**Forbidden Imports.**

| Import | Reason |
|---|---|
| Any `src/` module | Exception definitions must have no project-level dependencies to avoid circular imports. |

---

### `crawlers/greenhouse_crawler.py`

**Purpose.** Fetches and parses job listings from the Greenhouse public board API for configured board tokens and returns a list of job dicts.

**Public Interface.**

- `GreenhouseCrawler(config)` — subclass of `BaseCrawler`.
  - `fetch(self) -> list` — calls the Greenhouse API endpoint for each board token using `http_client.get`. Returns a list of raw API response dicts.
  - `parse(self, raw) -> list` — maps each raw Greenhouse response dict to the job schema. Raises `CrawlerParseError` when a required field is absent.
  - `run(self) -> list` — inherited from `BaseCrawler`.

**Inputs.**
- Config dict containing `greenhouse_board_tokens` (list of board token strings) and HTTP settings.

**Outputs.**
- `run()` returns a list of job dicts. Each dict includes at minimum: `title`, `company`, `source_url`, `ats_job_id`, `location`, `description`. No database writes. No notifications.

**Dependencies.**
- `crawlers.base_crawler` — inherits `BaseCrawler`.
- `crawlers.http_client` — for HTTP requests to the Greenhouse API.
- `crawlers.exceptions` — to raise `CrawlerParseError`.

**Allowed Imports.**
- `logging` — for fetch attempt and error logging.
- `crawlers.base_crawler`
- `crawlers.http_client`
- `crawlers.exceptions`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Crawlers must not touch the database. |
| `pipeline.ingest` | Crawlers emit data; they do not call ingest (ARCHITECTURE.md §4). |
| `db.*` | All DB access forbidden outside `src/db/`. |
| `scoring.*` | Scoring happens in ingest, not crawlers. |
| `notifications.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `playwright` | Greenhouse uses direct HTTP; Playwright is not needed here. |

---

### `crawlers/lever_crawler.py`

**Purpose.** Fetches and parses job postings from the Lever public postings API for configured company identifiers and returns a list of job dicts.

**Public Interface.**

- `LeverCrawler(config)` — subclass of `BaseCrawler`.
  - `fetch(self) -> list` — calls the Lever postings API for each company identifier using `http_client.get`. Returns a list of raw response dicts.
  - `parse(self, raw) -> list` — maps each raw Lever response dict to the job schema. Raises `CrawlerParseError` when a required field is absent.
  - `run(self) -> list` — inherited from `BaseCrawler`.

**Inputs.**
- Config dict containing `lever_company_ids` (list of company identifier strings) and HTTP settings.

**Outputs.**
- `run()` returns a list of job dicts including at minimum: `title`, `company`, `source_url`, `ats_job_id`, `location`, `description`. No database writes. No notifications.

**Dependencies.**
- `crawlers.base_crawler`
- `crawlers.http_client`
- `crawlers.exceptions`

**Allowed Imports.**
- `logging`
- `crawlers.base_crawler`
- `crawlers.http_client`
- `crawlers.exceptions`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Crawlers must not touch the database. |
| `pipeline.ingest` | Crawlers emit data; they do not call ingest. |
| `db.*` | All DB access forbidden outside `src/db/`. |
| `scoring.*` | Scoring happens in ingest. |
| `notifications.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `playwright` | Lever uses direct HTTP; Playwright is not needed here. |

---

### `crawlers/workday_crawler.py`

**Purpose.** Fetches and parses job listings from Workday-hosted career pages using Playwright for JS rendering and returns a list of job dicts.

**Public Interface.**

- `WorkdayCrawler(config)` — subclass of `BaseCrawler`.
  - `fetch(self) -> str` — calls `playwright_utils.render_page` for each configured Workday URL. Returns the rendered HTML string per URL.
  - `parse(self, raw) -> list` — parses the rendered HTML using BeautifulSoup to extract job fields. Raises `CrawlerParseError` when the expected HTML structure is not found (RULES.md §5.3, ROADMAP.md Phase 7).
  - `run(self) -> list` — inherited from `BaseCrawler`.

**Inputs.**
- Config dict containing `workday_urls` (list of Workday career page URL strings).

**Outputs.**
- `run()` returns a list of job dicts including at minimum: `title`, `company`, `source_url`, `location`, `description`. `ats_job_id` included if extractable from the page. No database writes. No notifications.

**Dependencies.**
- `crawlers.base_crawler`
- `crawlers.playwright_utils`
- `crawlers.exceptions`

**Allowed Imports.**
- `bs4` (BeautifulSoup) — HTML parsing.
- `logging`
- `crawlers.base_crawler`
- `crawlers.playwright_utils`
- `crawlers.exceptions`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Crawlers must not touch the database. |
| `pipeline.ingest` | Crawlers emit data; they do not call ingest. |
| `db.*` | All DB access forbidden outside `src/db/`. |
| `scoring.*` | Scoring happens in ingest. |
| `notifications.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `requests` / `http_client` | Workday uses Playwright; direct HTTP is not the extraction backend for this crawler. |

---

## Package: `pipeline/`

---

### `pipeline/ingest.py`

**Purpose.** Accepts a list of raw job dicts from a crawler, deduplicates against the database, scores each new job, and inserts new records via the repository layer.

**Public Interface.**

- `ingest_jobs(jobs, config) -> dict`
  Accepts a list of job dicts (as emitted by any crawler's `run()`) and the config dict. For each job dict: validates required fields (`title`, `company`, `source_url`), rejects and logs records missing any (RULES.md §4.3); normalizes location; checks deduplication via `jobs_repository.job_exists_by_dedup_key`; scores the job via `scorer.score_job`; calls `jobs_repository.insert_job` for new records. Returns a summary dict: `{"processed": int, "inserted": int, "skipped_duplicate": int, "rejected": int}`.

**Inputs.**
- `jobs` — list of job dicts from any crawler's `run()`. Fields: `title`, `company`, `source_url`, `ats_job_id` (may be None), `location` (may be None), `description` (may be None), `date_posted` (may be None), plus any additional source-specific fields.
- `config` — dict from `config_loader`. Used for scoring weights, `accepted_locations`, and `database_path`.

**Outputs.**
- Calls `jobs_repository.insert_job` for each new record (database write via repository).
- Logs each skip (duplicate) with title, company, source URL, and matched key type (SCHEMA.md §6).
- Logs each rejection (missing required field) with available fields.
- Returns a summary dict.

**Dependencies.**
- `scoring.scorer` — to call `score_job`.
- `db.jobs_repository` — to call `job_exists_by_dedup_key` and `insert_job`.

**Allowed Imports.**
- `hashlib` — to compute `dedup_hash` (SHA-256 per SCHEMA.md §6).
- `logging`
- `scoring.scorer`
- `db.jobs_repository`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | All DB access must go through `db.jobs_repository` (RULES.md §4.9). |
| `crawlers.*` | Ingest receives data from crawlers; it never imports from them (ARCHITECTURE.md §4 interface contracts). |
| `notifications.*` | Notification is a separate responsibility triggered by dispatcher (ARCHITECTURE.md §3). |
| `dashboard.*` | No dashboard dependency. |
| `streamlit` | Ingest runs in non-dashboard contexts. |

---

## Package: `scoring/`

---

### `scoring/scorer.py`

**Purpose.** Computes the final relevance score and score breakdown for a single job dict; pure function with zero I/O.

**Public Interface.**

- `score_job(job_dict, config) -> dict`
  Accepts a job dict (with at minimum `title`, `company`, `location_normalized`, `description`) and the config dict. Returns a result dict with keys: `final_score` (integer), `passed_threshold` (boolean), `score_breakdown` (dict matching the JSON structure in SCHEMA.md §8: `role_match`, `components`, `final_score`, `threshold_at_ingestion`).

**Inputs.**
- `job_dict` — dict with fields: `title`, `company`, `location_normalized` (may be None), `description` (may be None).
- `config` — dict containing: `notification_threshold`, `remote_location_bonus`, `company_tier_1_bonus`, `company_tier_2_bonus`, `role_mismatch_penalty`, `accepted_role_keywords`, `positive_keywords` (dict of keyword→weight), `negative_keywords` (dict of keyword→weight), `accepted_locations`, `company_tier_1` (list), `company_tier_2` (list).

**Outputs.**
- Returns `{"final_score": int, "passed_threshold": bool, "score_breakdown": dict}`.
- The `score_breakdown` dict: `role_match` (bool), `components` (list of `{"label": str, "points": int}`), `final_score` (int), `threshold_at_ingestion` (int). Structure per SCHEMA.md §8.
- No file writes. No database writes. No HTTP calls. No side effects.

**Dependencies.**
- `scoring.rules` — to call the role match gate.

**Allowed Imports.**
- `scoring.rules`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Scorer must have zero I/O (ARCHITECTURE.md §4, ROADMAP.md Phase 3). |
| `requests` | Zero I/O rule. |
| `subprocess` | Zero I/O rule. |
| `streamlit` | Zero I/O rule. |
| `db.*` | Zero I/O rule. |
| `notifications.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

### `scoring/rules.py`

**Purpose.** Implements the role match gate: a pure function that checks whether a job title matches any accepted role keyword.

**Public Interface.**

- `matches_role(title, accepted_role_keywords) -> bool`
  Accepts a job title string and a list of accepted role keyword strings. Returns `True` if the title contains any keyword (case-insensitive substring match per SCORING.md §2), `False` otherwise. No side effects.

**Inputs.**
- `title` — string job title.
- `accepted_role_keywords` — list of strings from config.

**Outputs.**
- Returns a boolean. No writes of any kind.

**Dependencies.** None.

**Allowed Imports.**
- None beyond Python builtins.

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Zero I/O rule (ARCHITECTURE.md §4). |
| `requests` | Zero I/O rule. |
| `subprocess` | Zero I/O rule. |
| `streamlit` | Zero I/O rule. |
| `db.*` | Zero I/O rule. |
| `notifications.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

## Package: `db/`

---

### `db/migrations.py`

**Purpose.** Applies the V1 schema (tables, indexes, constraints, WAL mode) to a SQLite database at startup and records the schema version.

**Public Interface.**

- `run_migrations(db_path) -> None`
  Accepts the path to the SQLite database file. Checks the `schema_version` table; if absent, applies the full V1 migration sequence (creates `jobs`, `referrals`, `schema_version` tables, all indexes, CHECK constraints, enables WAL mode, inserts the version row). If schema version already matches the latest, does nothing. Idempotent on a fresh database (SCHEMA.md §10).

**Inputs.**
- `db_path` — string path to the SQLite file (passed as a parameter from config).

**Outputs.**
- Creates or updates the database schema on disk.
- Inserts or updates the single row in `schema_version` with `version = 1` and `applied_at` = current UTC ISO-8601 timestamp.
- No return value on success; raises on failure.

**Dependencies.** None (no other project modules imported).

**Allowed Imports.**
- `sqlite3` — the only module in the system permitted to use raw SQLite.
- `logging`
- `datetime` — for UTC timestamp generation.
- `pathlib` — for path handling.

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `requests` | Migrations perform no HTTP calls. |
| `streamlit` | Migrations run in non-dashboard contexts. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

### `db/jobs_repository.py`

**Purpose.** Provides all read and write operations for the `jobs` table using parameterized SQL; the only module permitted to query or mutate job records.

**Public Interface.**

- `insert_job(job_record, db_path) -> int`
  Accepts a job record dict (all `jobs` table fields) and the database path. Inserts the record and returns the new row's integer `id`.

- `job_exists_by_dedup_key(source_url, ats_job_id, dedup_hash, db_path) -> bool`
  Accepts `source_url`, `ats_job_id` (may be None), `dedup_hash` (may be None), and the database path. Returns `True` if a matching record exists via the primary key or fallback, per SCHEMA.md §6.

- `get_job_by_id(job_id, db_path) -> dict | None`
  Accepts an integer job ID and the database path. Returns the full job record as a dict, or `None` if not found.

- `get_jobs_by_status(status, db_path) -> list`
  Accepts a status string and the database path. Returns a list of job record dicts where `status` matches. Used by `data_loader.py`.

- `get_unnotified_jobs(threshold, db_path) -> list`
  Accepts an integer score threshold and the database path. Returns job record dicts where `notified = 0`, `location_ineligible = 0`, and `score >= threshold`. Used by `dispatcher.py` (ARCHITECTURE.md §3, §6).

- `update_job_status(job_id, new_status, db_path) -> None`
  Updates only the `status` field for the given job ID.

- `update_job_tags(job_id, tags, db_path) -> None`
  Updates only the `tags` field for the given job ID.

- `mark_notified(job_id, db_path) -> None`
  Sets `notified = 1` for the given job ID. Never resets to 0 (RULES.md §6.1, SCHEMA.md §7).

**Inputs.**
- Job record dicts, integer IDs, status strings, tags strings, and `db_path` — all passed as parameters. Config is never imported; `db_path` is always explicit.

**Outputs.**
- `insert_job` returns the new integer row ID.
- `job_exists_by_dedup_key` returns a boolean.
- `get_job_by_id` returns a dict or `None`.
- `get_jobs_by_status` and `get_unnotified_jobs` return lists of dicts.
- `update_job_status`, `update_job_tags`, `mark_notified` return `None` (database write as side effect).

**Dependencies.** None (no other project modules imported).

**Allowed Imports.**
- `sqlite3`
- `logging`
- `datetime`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `requests` | Repository performs no HTTP calls. |
| `streamlit` | Repository runs in non-dashboard contexts. |
| `scoring.*` | Business logic must not be mixed into the data access layer (ARCHITECTURE.md §5). |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

### `db/referrals_repository.py`

**Purpose.** Provides all read and write operations for the `referrals` table using parameterized SQL.

**Public Interface.**

- `insert_referral(referral_record, db_path) -> int`
  Accepts a referral record dict (fields per SCHEMA.md §2: `company`, `role`, `applied_date`, `referral_status`, `recruiter_contacted`, `follow_up_date`, optionally `notes`) and the database path. Returns the new integer `id`.

- `get_referral_by_id(referral_id, db_path) -> dict | None`
  Returns the full referral record as a dict, or `None` if not found.

- `get_all_referrals(db_path) -> list`
  Returns a list of all referral record dicts. Proposed — confirm sort order before implementing.

- `update_referral_status(referral_id, referral_status, follow_up_date, db_path) -> None`
  Updates `referral_status`, `follow_up_date`, and `updated_at` for the given referral ID.

**Inputs.**
- Referral record dicts, integer IDs, status strings, date strings, and `db_path` — all passed as parameters.

**Outputs.**
- `insert_referral` returns the new integer row ID.
- `get_referral_by_id` returns a dict or `None`.
- `get_all_referrals` returns a list of dicts.
- `update_referral_status` returns `None` (database write; `updated_at` set to current UTC).

**Dependencies.** None (no other project modules imported).

**Allowed Imports.**
- `sqlite3`
- `logging`
- `datetime`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `requests` | Repository performs no HTTP calls. |
| `streamlit` | Repository runs in non-dashboard contexts. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `dashboard.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

## Package: `notifications/`

---

### `notifications/dispatcher.py`

**Purpose.** Queries unnotified eligible jobs, invokes both notifiers independently, and calls `mark_notified` if at least one channel succeeds.

**Public Interface.**

- `dispatch_new_jobs(config) -> dict`
  Accepts the config dict. Queries `jobs_repository.get_unnotified_jobs` for jobs where `notified = 0`, `location_ineligible = 0`, and `score >= NOTIFICATION_THRESHOLD`. For each qualifying job: calls `telegram_notifier.send_telegram` and `email_notifier.send_email` independently — both are always attempted regardless of the other's result. If at least one returns `True`, calls `jobs_repository.mark_notified`. If both return `False`, logs the failure with job ID and timestamp without marking notified (ARCHITECTURE.md §3, §6). Returns `{"eligible": int, "notified": int, "both_failed": int}`.

**Inputs.**
- `config` — dict from `config_loader`, containing `notification_threshold`, `database_path`, and all credential keys used by the notifiers.

**Outputs.**
- Calls `jobs_repository.mark_notified` for jobs where at least one channel succeeded (database write via repository).
- Logs failures with job ID and timestamp per RULES.md §6.6.
- Returns a summary dict.

**Dependencies.**
- `db.jobs_repository`
- `notifications.telegram_notifier`
- `notifications.email_notifier`

**Allowed Imports.**
- `logging`
- `db.jobs_repository`
- `notifications.telegram_notifier`
- `notifications.email_notifier`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | All DB access must go through `db.jobs_repository` (RULES.md §4.9). |
| `crawlers.*` | Dispatcher has no crawling responsibility (ARCHITECTURE.md §4). |
| `dashboard.*` | Dispatcher has no dashboard responsibility (ARCHITECTURE.md §4). |
| `pipeline.*` | Not in scope. |
| `scoring.*` | Eligibility uses stored score; re-scoring is not performed here (RULES.md §6.8). |
| `streamlit` | Dispatcher runs in scheduler context, not dashboard context. |

---

### `notifications/telegram_notifier.py`

**Purpose.** Formats a job notification payload and sends it to a Telegram chat via direct HTTP POST to the Telegram Bot API.

**Public Interface.**

- `send_telegram(job_record, config) -> bool`
  Accepts a job record dict (containing `title`, `company`, `location_normalized`, `score`, `source_url` per ARCHITECTURE.md §6) and the config dict (containing `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`). Formats the message and sends an HTTP POST to the Telegram Bot API. Returns `True` on success, `False` on any failure. Tokens must never be logged (RULES.md §6.5).

**Inputs.**
- `job_record` — dict with: `title`, `company`, `location_normalized`, `score`, `source_url`.
- `config` — dict with: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

**Outputs.**
- Makes one HTTP POST to the Telegram Bot API.
- Returns `True` (success) or `False` (failure).
- Logs failures without exposing tokens.

**Dependencies.** None (no other project modules imported).

**Allowed Imports.**
- `requests` — for the HTTP POST.
- `logging`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Notifiers must not access the database directly (ARCHITECTURE.md §4). |
| `db.*` | Notifiers must not import from `db/` (ARCHITECTURE.md §4 cross-cutting rules). |
| `dashboard.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `pipeline.*` | Not in scope. |
| `scoring.*` | Not in scope. |
| `smtplib` | Telegram notifier uses HTTP, not SMTP. Keep channels cleanly separated. |

---

### `notifications/email_notifier.py`

**Purpose.** Formats a job notification payload and sends it via SMTP using Python's standard `smtplib`.

**Public Interface.**

- `send_email(job_record, config) -> bool`
  Accepts a job record dict (containing `title`, `company`, `location_normalized`, `score`, `source_url`) and the config dict (containing `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`). Formats the subject and body, establishes an SMTP connection, and sends the message. Returns `True` on success, `False` on any failure. Credentials must never be logged (RULES.md §6.5).

**Inputs.**
- `job_record` — dict with: `title`, `company`, `location_normalized`, `score`, `source_url`.
- `config` — dict with: `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`.

**Outputs.**
- Sends one SMTP email.
- Returns `True` (success) or `False` (failure).
- Logs failures without exposing credentials.

**Dependencies.** None (no other project modules imported).

**Allowed Imports.**
- `smtplib`
- `email.mime.text` — for constructing the email message.
- `logging`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Notifiers must not access the database. |
| `db.*` | Notifiers must not import from `db/` (ARCHITECTURE.md §4). |
| `dashboard.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `pipeline.*` | Not in scope. |
| `scoring.*` | Not in scope. |
| `requests` | Email notifier uses SMTP, not HTTP. Keep channels cleanly separated. |

---

## Package: `dashboard/`

---

### `dashboard/app.py`

**Purpose.** Streamlit entry point: renders the sidebar navigation and delegates rendering to the appropriate view module based on the user's selection.

**Public Interface.**

- No importable functions. Run via `streamlit run src/dashboard/app.py`.
- Internally selects and calls each view module's `render()` function based on sidebar state.

**Inputs.**
- Config dict (via `config_loader`) for `database_path` and `notification_threshold`.
- Sidebar user interaction (Streamlit session state).

**Outputs.**
- Renders the Streamlit sidebar and one of six view modules. No database writes. No HTTP calls.

**Dependencies.**
- `config_loader`
- `dashboard.views.high_priority`
- `dashboard.views.applied`
- `dashboard.views.pending`
- `dashboard.views.referral_needed`
- `dashboard.views.rejected`
- `dashboard.views.referrals`

**Allowed Imports.**
- `streamlit`
- `config_loader`
- `dashboard.views.*`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | All DB access must go through `data_loader.py` → repository (RULES.md §4.9). |
| `db.*` | Only `data_loader.py` may import from `db/` in the dashboard (ARCHITECTURE.md §4). |
| `scoring.*` | Dashboard does not score jobs (ARCHITECTURE.md §7). |
| `crawlers.*` | Dashboard does not trigger crawls (ARCHITECTURE.md §7). |
| `notifications.*` | Dashboard does not trigger notifications (ARCHITECTURE.md §6). |
| `pipeline.*` | Not in scope. |

---

### `dashboard/data_loader.py`

**Purpose.** The only dashboard module permitted to import from `src/db/`; loads job and referral data from the repository layer and returns DataFrames for view rendering.

**Public Interface.**

- `load_high_priority_jobs(config) -> DataFrame`
  Returns a DataFrame of jobs with `score >= notification_threshold` and `status` not in `['Applied', 'Rejected']`, sorted by score descending. Proposed — confirm exact filter before implementing (ARCHITECTURE.md §7).

- `load_jobs_by_status(status, config) -> DataFrame`
  Accepts a status string and config dict. Returns a DataFrame of jobs where `status` matches.

- `load_all_referrals(config) -> DataFrame`
  Returns a DataFrame of all rows from the `referrals` table.

**Inputs.**
- `config` — dict containing `database_path` and `notification_threshold`.

**Outputs.**
- Returns `pandas.DataFrame` objects. No writes of any kind.

**Dependencies.**
- `db.jobs_repository`
- `db.referrals_repository`

**Allowed Imports.**
- `pandas`
- `db.jobs_repository`
- `db.referrals_repository`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | All DB access must go through the repository layer (RULES.md §4.9). |
| `scoring.*` | Data loading has no scoring responsibility. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |
| `streamlit` | `data_loader.py` is a pure data layer; Streamlit rendering belongs in view modules. |

---

### `dashboard/views/high_priority.py`

**Purpose.** Renders the High Priority view: jobs with score at or above threshold that are not Applied or Rejected, with status and tag editing controls.

**Public Interface.**

- `render(config) -> None`
  Accepts the config dict. Calls `data_loader.load_high_priority_jobs`, displays the DataFrame, and embeds `status_editor`, `tag_editor`, and `export_controls` components.

**Inputs.** `config` — dict.

**Outputs.** Renders Streamlit UI. No direct database writes.

**Dependencies.**
- `dashboard.data_loader`
- `dashboard.components.status_editor`
- `dashboard.components.tag_editor`
- `dashboard.components.export_controls`

**Allowed Imports.**
- `streamlit`
- `dashboard.data_loader`
- `dashboard.components.status_editor`
- `dashboard.components.tag_editor`
- `dashboard.components.export_controls`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Views must not access the database directly. |
| `db.*` | Only `data_loader.py` may import from `db/` in the dashboard. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

### `dashboard/views/applied.py`

**Purpose.** Renders the Applied view: jobs with `status = 'Applied'`, with status, tag, and referral field editing.

**Public Interface.**

- `render(config) -> None`
  Calls `data_loader.load_jobs_by_status('Applied', config)`, displays the DataFrame, and embeds `status_editor`, `tag_editor`, `referral_form`, and `export_controls`.

**Inputs.** `config` — dict.

**Outputs.** Renders Streamlit UI. No direct database writes.

**Dependencies.**
- `dashboard.data_loader`
- `dashboard.components.status_editor`
- `dashboard.components.tag_editor`
- `dashboard.components.referral_form`
- `dashboard.components.export_controls`

**Allowed Imports.**
- `streamlit`
- `dashboard.data_loader`
- `dashboard.components.status_editor`
- `dashboard.components.tag_editor`
- `dashboard.components.referral_form`
- `dashboard.components.export_controls`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Views must not access the database directly. |
| `db.*` | Only `data_loader.py` may import from `db/` in the dashboard. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

### `dashboard/views/pending.py`

**Purpose.** Renders the Pending view: jobs with `status = 'Pending'`, with status and tag editing.

**Public Interface.**

- `render(config) -> None`
  Calls `data_loader.load_jobs_by_status('Pending', config)`, displays the DataFrame, and embeds `status_editor`, `tag_editor`, and `export_controls`.

**Inputs.** `config` — dict.

**Outputs.** Renders Streamlit UI. No direct database writes.

**Dependencies.**
- `dashboard.data_loader`
- `dashboard.components.status_editor`
- `dashboard.components.tag_editor`
- `dashboard.components.export_controls`

**Allowed Imports.**
- `streamlit`
- `dashboard.data_loader`
- `dashboard.components.status_editor`
- `dashboard.components.tag_editor`
- `dashboard.components.export_controls`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Views must not access the database directly. |
| `db.*` | Only `data_loader.py` may import from `db/` in the dashboard. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

### `dashboard/views/referral_needed.py`

**Purpose.** Renders the Referral-Needed view: jobs with `status = 'Referral-Needed'`, with status, tag, and referral field editing.

**Public Interface.**

- `render(config) -> None`
  Calls `data_loader.load_jobs_by_status('Referral-Needed', config)`, displays the DataFrame, and embeds `status_editor`, `tag_editor`, `referral_form`, and `export_controls`.

**Inputs.** `config` — dict.

**Outputs.** Renders Streamlit UI. No direct database writes.

**Dependencies.**
- `dashboard.data_loader`
- `dashboard.components.status_editor`
- `dashboard.components.tag_editor`
- `dashboard.components.referral_form`
- `dashboard.components.export_controls`

**Allowed Imports.**
- `streamlit`
- `dashboard.data_loader`
- `dashboard.components.status_editor`
- `dashboard.components.tag_editor`
- `dashboard.components.referral_form`
- `dashboard.components.export_controls`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Views must not access the database directly. |
| `db.*` | Only `data_loader.py` may import from `db/` in the dashboard. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

### `dashboard/views/rejected.py`

**Purpose.** Renders the Rejected view: jobs with `status = 'Rejected'`, with a status undo control to return a job to Pending.

**Public Interface.**

- `render(config) -> None`
  Calls `data_loader.load_jobs_by_status('Rejected', config)`, displays the DataFrame, and embeds `status_editor` exposing only the Pending undo path (ARCHITECTURE.md §7, SCHEMA.md §9).

**Inputs.** `config` — dict.

**Outputs.** Renders Streamlit UI. No direct database writes.

**Dependencies.**
- `dashboard.data_loader`
- `dashboard.components.status_editor`

**Allowed Imports.**
- `streamlit`
- `dashboard.data_loader`
- `dashboard.components.status_editor`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Views must not access the database directly. |
| `db.*` | Only `data_loader.py` may import from `db/` in the dashboard. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |
| `export_controls` | Proposed — confirm before implementing: ARCHITECTURE.md §7 does not list export for the Rejected view. |

---

### `dashboard/views/referrals.py`

**Purpose.** Renders the Referrals view: all rows from the `referrals` table, with controls to create new records and update existing ones.

**Public Interface.**

- `render(config) -> None`
  Calls `data_loader.load_all_referrals(config)`, displays the DataFrame, and embeds `referral_form` and `referral_status_editor`.

**Inputs.** `config` — dict.

**Outputs.** Renders Streamlit UI. No direct database writes.

**Dependencies.**
- `dashboard.data_loader`
- `dashboard.components.referral_form`
- `dashboard.components.referral_status_editor`

**Allowed Imports.**
- `streamlit`
- `dashboard.data_loader`
- `dashboard.components.referral_form`
- `dashboard.components.referral_status_editor`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Views must not access the database directly. |
| `db.*` | Only `data_loader.py` may import from `db/` in the dashboard. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

### `dashboard/components/status_editor.py`

**Purpose.** Renders a status dropdown and save button for a selected job; writes the updated status through the repository when saved.

**Public Interface.**

- `render_status_editor(job_id, current_status, config) -> None`
  Accepts an integer job ID, the current status string, and the config dict. Renders a Streamlit selectbox constrained to the four allowed status values. On save, calls `jobs_repository.update_job_status`. Proposed — confirm before implementing: whether this component calls `st.rerun()` on save or leaves re-render to the caller.

**Inputs.**
- `job_id` — integer.
- `current_status` — string (one of the four allowed values).
- `config` — dict (for `database_path`).

**Outputs.**
- On save: calls `jobs_repository.update_job_status` (database write via repository).
- Renders Streamlit UI elements.

**Dependencies.**
- `db.jobs_repository`

**Allowed Imports.**
- `streamlit`
- `db.jobs_repository`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | All DB access must go through the repository layer. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |
| `dashboard.data_loader` | Components write; they do not load DataFrames. |

---

### `dashboard/components/tag_editor.py`

**Purpose.** Renders a text input for comma-separated tags and a save button for a selected job; writes the updated tags through the repository when saved.

**Public Interface.**

- `render_tag_editor(job_id, current_tags, config) -> None`
  Accepts an integer job ID, the current tags string (comma-separated or empty), and the config dict. Renders a Streamlit text input. On save, calls `jobs_repository.update_job_tags`. An empty input clears existing tags.

**Inputs.**
- `job_id` — integer.
- `current_tags` — comma-separated string or empty string.
- `config` — dict (for `database_path`).

**Outputs.**
- On save: calls `jobs_repository.update_job_tags` (database write via repository).
- Renders Streamlit UI elements.

**Dependencies.**
- `db.jobs_repository`

**Allowed Imports.**
- `streamlit`
- `db.jobs_repository`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | All DB access must go through the repository layer. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |
| `dashboard.data_loader` | Components write; they do not load DataFrames. |

---

### `dashboard/components/referral_form.py`

**Purpose.** Renders the form for creating a new referral record; inserts it through the referrals repository when submitted.

**Public Interface.**

- `render_referral_form(config) -> None`
  Accepts the config dict. Renders a Streamlit form with fields: `company` (required), `role`, `applied_date`, `referral_status`, `recruiter_contacted` (checkbox), `follow_up_date`. On submit, calls `referrals_repository.insert_referral`. Proposed — confirm exact required fields beyond `company` (per SCHEMA.md §2).

**Inputs.**
- `config` — dict (for `database_path`).
- User form input via Streamlit.

**Outputs.**
- On submit: calls `referrals_repository.insert_referral` (database write via repository).
- Renders Streamlit form elements.

**Dependencies.**
- `db.referrals_repository`

**Allowed Imports.**
- `streamlit`
- `db.referrals_repository`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | All DB access must go through the repository layer. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |
| `dashboard.data_loader` | Components write; they do not load DataFrames. |

---

### `dashboard/components/referral_status_editor.py`

**Purpose.** Renders controls to update `referral_status` and `follow_up_date` on an existing referral record.

**Public Interface.**

- `render_referral_status_editor(referral_id, current_status, current_follow_up_date, config) -> None`
  Accepts an integer referral ID, the current status string, the current follow-up date string (or None), and the config dict. Renders Streamlit inputs for `referral_status` and `follow_up_date`. On save, calls `referrals_repository.update_referral_status`.

**Inputs.**
- `referral_id` — integer.
- `current_status` — string or None.
- `current_follow_up_date` — ISO-8601 date string or None.
- `config` — dict (for `database_path`).

**Outputs.**
- On save: calls `referrals_repository.update_referral_status` (database write via repository).
- Renders Streamlit UI elements.

**Dependencies.**
- `db.referrals_repository`

**Allowed Imports.**
- `streamlit`
- `db.referrals_repository`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | All DB access must go through the repository layer. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |
| `dashboard.data_loader` | Components write; they do not load DataFrames. |

---

### `dashboard/components/export_controls.py`

**Purpose.** Renders Streamlit download buttons that call `exporter.py` to produce CSV or Excel bytes for the user.

**Public Interface.**

- `render_export_controls(df, label) -> None`
  Accepts a pandas DataFrame and a label string (e.g., `"jobs"` or `"referrals"`). Renders two `st.download_button` elements: one for CSV, one for Excel. Calls the corresponding export functions from `exporter.py`. Proposed — confirm before implementing: whether the label parameter selects the export function, or separate functions are provided per data type.

**Inputs.**
- `df` — pandas DataFrame of the current view's data.
- `label` — string identifying the data context.

**Outputs.**
- Renders Streamlit `st.download_button` elements. No database writes. No HTTP calls.

**Dependencies.**
- `export.exporter`

**Allowed Imports.**
- `streamlit`
- `export.exporter`
- `pandas` — DataFrame type reference.

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Components must not access the database. |
| `db.*` | Only `data_loader.py` may import from `db/` in the dashboard. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

## Package: `export/`

---

### `export/exporter.py`

**Purpose.** Converts DataFrames to CSV or Excel bytes for download; performs no database access.

**Public Interface.**

- `export_jobs_csv(jobs_df) -> bytes`
  Accepts a pandas DataFrame of job records. Returns UTF-8 encoded CSV bytes. An empty DataFrame produces a header-only file.

- `export_jobs_excel(jobs_df) -> bytes`
  Accepts a pandas DataFrame of job records. Returns valid `.xlsx` bytes. An empty DataFrame produces a valid Excel file with headers.

- `export_referrals_csv(referrals_df) -> bytes`
  Accepts a pandas DataFrame of referral records. Returns UTF-8 encoded CSV bytes.

- `export_referrals_excel(referrals_df) -> bytes`
  Accepts a pandas DataFrame of referral records. Returns valid `.xlsx` bytes.

**Inputs.**
- `jobs_df` or `referrals_df` — pandas DataFrame. DataFrames are passed by the caller; this module makes no database calls (ROADMAP.md Phase 12).

**Outputs.**
- Returns bytes in each function. No file system writes. No database writes. No HTTP calls.

**Dependencies.** None (no other project modules imported).

**Allowed Imports.**
- `pandas` — DataFrame serialization via `df.to_csv()` and `df.to_excel()`.
- `openpyxl` — Excel file generation (used internally by pandas `to_excel`).
- `io` — `BytesIO` for in-memory byte stream construction.

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Exporter has no database responsibility (ROADMAP.md Phase 12). |
| `db.*` | Exporter receives DataFrames; it does not query the database. |
| `streamlit` | Exporter is a pure transformation module; rendering belongs in components. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Not in scope. |
| `notifications.*` | Not in scope. |
| `pipeline.*` | Not in scope. |

---

## Package: `scheduler/`

---

### `scheduler/runner.py`

**Purpose.** Executes the full pipeline: runs all three crawlers, passes their output to `ingest_jobs`, then calls `dispatcher.dispatch_new_jobs`; isolates per-crawler failures so the pipeline continues.

**Public Interface.**

- `run_pipeline(config) -> dict`
  Accepts the config dict. Instantiates and calls `GreenhouseCrawler.run()`, `LeverCrawler.run()`, and `WorkdayCrawler.run()` in sequence. For each crawler, catches any exception, logs it with the crawler name and timestamp, and continues (RULES.md §5.8, ROADMAP.md Phase 13). Passes each crawler's output to `ingest.ingest_jobs`. After all crawlers complete, calls `dispatcher.dispatch_new_jobs(config)`. Returns a summary dict with per-crawler job counts and notification counts. Proposed — confirm exact return shape before implementing.

**Inputs.**
- `config` — dict from `config_loader`.

**Outputs.**
- Calls `ingest.ingest_jobs` for each crawler's output (triggers DB writes via ingest → repository).
- Calls `dispatcher.dispatch_new_jobs` (triggers notifications and DB writes via dispatcher → repository).
- Returns a summary dict.

**Dependencies.**
- `crawlers.greenhouse_crawler`
- `crawlers.lever_crawler`
- `crawlers.workday_crawler`
- `pipeline.ingest`
- `notifications.dispatcher`

**Allowed Imports.**
- `logging`
- `crawlers.greenhouse_crawler`
- `crawlers.lever_crawler`
- `crawlers.workday_crawler`
- `pipeline.ingest`
- `notifications.dispatcher`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | All DB access goes through repository via ingest and dispatcher (RULES.md §4.9). |
| `db.*` | Runner does not interact with the database directly. |
| `dashboard.*` | Runner has no dashboard responsibility. |
| `streamlit` | Runner runs in scheduler context. |
| `scoring.*` | Scoring is handled inside `ingest.py`. |

---

### `scheduler/main.py`

**Purpose.** Entry point for the scheduler loop; calls `runner.run_pipeline` at the configured interval.

**Public Interface.**

- No importable functions. Run via `python src/scheduler/main.py`.
- Calls `runner.run_pipeline(config)` on the interval defined by `schedule_interval_minutes` in config (RULES.md §3.5, ROADMAP.md Phase 13). Runs indefinitely until killed.

**Inputs.**
- Config dict from `config_loader` (loaded at startup).
- `schedule_interval_minutes` from config.

**Outputs.**
- Calls `runner.run_pipeline` on schedule. Logs each run start and completion.
- No return value (infinite loop).

**Dependencies.**
- `config_loader`
- `scheduler.runner`

**Allowed Imports.**
- `schedule` — scheduling library.
- `time` — for `time.sleep` in the schedule loop.
- `logging`
- `config_loader`
- `scheduler.runner`

**Forbidden Imports.**

| Import | Reason |
|---|---|
| `sqlite3` | Main has no database responsibility. |
| `db.*` | All DB access is downstream of runner. |
| `dashboard.*` | Not in scope. |
| `streamlit` | Not in scope. |
| `scoring.*` | Not in scope. |
| `crawlers.*` | Main orchestrates via runner, not directly via crawlers. |
| `pipeline.*` | Main orchestrates via runner, not directly via ingest. |
| `notifications.*` | Main orchestrates via runner, not directly via dispatcher. |

---

## Open Items — Confirm Before Implementing

| Item | Module | Reason Flagged |
|---|---|---|
| Whether `get_config()` returns a module-level singleton or callers always call `load_config` | `config_loader.py` | Not specified in source documents. |
| Whether config is passed to crawler `__init__` or accessed via module-level import | `base_crawler.py` | Affects testability; both patterns valid. |
| Whether config is passed as a parameter to `http_client.get` or via module-level import | `http_client.py` | Same as above. |
| Whether `db_path` in `migrations.py` is always a parameter or read from config internally | `migrations.py` | ROADMAP.md Phase 2 implies parameter. |
| Sort order for `get_all_referrals` | `referrals_repository.py` | Not specified in SCHEMA.md. |
| Whether `status_editor` calls `st.rerun()` on save | `status_editor.py` | Implementation-level Streamlit detail. |
| Exact required fields in `referral_form` beyond `company` | `referral_form.py` | SCHEMA.md §2 leaves several fields optional. |
| How `export_controls` selects between jobs/referrals export functions | `export_controls.py` | Not specified in ROADMAP.md Phase 12. |
| Exact return shape of `run_pipeline` | `runner.py` | Not specified in source documents. |
| `notes` field in `referrals` table | `referrals_repository.py` | SCHEMA.md §2 flags this as Proposed. |
| Whether dispatcher uses `passed_threshold` flag or live score comparison in its WHERE clause | `dispatcher.py` / `jobs_repository.py` | SCHEMA.md §7 flags this as Proposed. This document uses live score comparison, consistent with ARCHITECTURE.md §6. |
| Whether `export_controls` appears in the Rejected view | `views/rejected.py` | ARCHITECTURE.md §7 does not list it there; omitted from this document. |
