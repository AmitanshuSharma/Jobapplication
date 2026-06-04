# Job Intelligence Platform — Version 1 Roadmap

---

## Phase 1 — Repository and Configuration Foundation

### Objective

Establish the project repository structure, dependency management, environment isolation, and a centralized configuration system that all subsequent phases depend on.

### Inputs

- Project name and description
- Preferred stack: Python, SQLite, Streamlit, Telegram, BeautifulSoup, Playwright, Requests
- Hard rules from CLAUDE.md and RULES.md

### Deliverables

- Directory structure with top-level folders: `src/`, `tests/`, `data/`, `docs/`, `scripts/`
- `requirements.txt` with all runtime dependencies pinned to specific versions
- `requirements-dev.txt` with test and development dependencies
- `config.yaml` containing all configurable values: database path, scoring thresholds, accepted locations, Telegram credentials placeholder, email credentials placeholder
- `src/config_loader.py` module that reads `config.yaml` and exposes a typed configuration object
- `.env.example` documenting all required environment variables
- `.gitignore` covering Python artifacts, `.env`, `data/`, and `*.db` files
- `README.md` with project purpose, setup steps, and how to run

### Success Criteria

- Running `python src/config_loader.py` completes without error and prints the loaded config values
- All required config keys are present in `config.yaml` and accessible via `config_loader.py`
- No credentials or secrets exist anywhere except `.env` or `.env.example`
- `.gitignore` prevents `*.db`, `.env`, and `data/` from being tracked
- `pip install -r requirements.txt` succeeds in a clean virtual environment

---

## Phase 2 — Database Schema and Data Layer

### Objective

Define the complete SQLite database schema for all job and referral fields, and implement a data access layer with parameterized queries for all read and write operations.

### Inputs

- Phase 1: `config_loader.py` for database path resolution
- Job fields specification: title, company, location, description, experience_range, tech_stack_matched, source_url, ats_job_id, score, status, tags, notified, date_posted, first_seen_at
- Referral fields specification: company, role, applied_date, referral_status, recruiter_contacted, follow_up_date
- Deduplication rules: (source_url + ats_job_id) or hash(company + title + location)

### Deliverables

- `src/db/schema.sql` containing all `CREATE TABLE IF NOT EXISTS` statements for `jobs`, `referrals`, and a `schema_version` table
- `src/db/migrations.py` module that applies `schema.sql` to a given database path and records the schema version
- `src/db/jobs_repository.py` with functions: `insert_job`, `get_job_by_id`, `get_jobs_by_status`, `update_job_status`, `update_job_tags`, `mark_notified`, `job_exists_by_dedup_key`
- `src/db/referrals_repository.py` with functions: `insert_referral`, `get_referral_by_id`, `update_referral_status`, `get_all_referrals`
- All queries use parameterized statements exclusively

### Success Criteria

- Running `python src/db/migrations.py` creates the database file at the path specified in `config.yaml` with all tables present
- `job_exists_by_dedup_key` returns `True` when a duplicate is inserted and `False` for new records
- All repository functions can be called against an in-memory SQLite database in a test script without error
- No raw string interpolation appears in any SQL query in the codebase
- Schema version is recorded in the `schema_version` table after migration runs

---

## Phase 3 — Scoring Engine

### Objective

Implement a standalone scoring module that evaluates a job record against configured keyword, location, and company criteria and returns a numeric score and a pass/fail gate result.

### Inputs

- Phase 1: `config_loader.py` for scoring configuration (keywords, location list, company bonuses, threshold)
- Phase 2: Job field structure for input validation
- Scoring formula: `keyword_score + location_bonus + company_bonus = final_score`
- Role match gate: must pass before scoring proceeds
- Default threshold: 20

### Deliverables

- `src/scoring/scorer.py` with a `score_job(job_dict, config) -> dict` function that returns `final_score`, `keyword_score`, `location_bonus`, `company_bonus`, and `passed_threshold` fields
- `src/scoring/rules.py` containing the role match gate logic as a separate, independently callable function
- Threshold value read from config, not hardcoded
- Score breakdown dictionary returned alongside the final score

### Success Criteria

- A job with no matching keywords, location, or company returns a score of 0 and `passed_threshold: False`
- A job matching all configured keywords, an accepted location, and a bonus company returns a score greater than the threshold and `passed_threshold: True`
- Changing the threshold value in `config.yaml` to 0 causes all scored jobs to return `passed_threshold: True`
- A job that fails the role match gate returns `passed_threshold: False` regardless of score
- `scorer.py` has no database imports or file I/O

---

## Phase 4 — Crawler Framework

### Objective

Build a base crawler interface and shared HTTP utilities that all source-specific crawlers in later phases will extend, enforcing a consistent contract for fetching, parsing, and yielding job records.

### Inputs

- Phase 1: `config_loader.py` for request headers and rate limit settings
- Phase 2: Job field structure that crawlers must populate
- Approved libraries: Requests, BeautifulSoup, Playwright

### Deliverables

- `src/crawlers/base_crawler.py` defining an abstract `BaseCrawler` class with abstract methods `fetch()` and `parse()`, and a concrete `run()` method that calls both in sequence and returns a list of job dicts
- `src/crawlers/http_client.py` with a shared `get(url, headers, timeout)` function that handles retries, rate limiting, and returns a `Response` object or raises a typed exception
- `src/crawlers/exceptions.py` defining `CrawlerFetchError` and `CrawlerParseError` exception classes
- `src/crawlers/playwright_utils.py` with a `render_page(url) -> str` function for JavaScript-rendered pages

### Success Criteria

- Any class that extends `BaseCrawler` without implementing `fetch()` or `parse()` raises `TypeError` on instantiation
- `http_client.get()` raises `CrawlerFetchError` when the target URL returns a non-200 status code
- `playwright_utils.render_page()` returns an HTML string when pointed at a static local HTML file served via a local process
- `BaseCrawler.run()` returns a list (empty or populated) without raising an exception when `fetch()` and `parse()` are implemented
- No crawler module imports from `src/db/` directly

---

## Phase 5 — Greenhouse Integration

### Objective

Implement a crawler for the Greenhouse public job board API that fetches open roles from configured company board tokens, parses job fields, deduplicates against the database, scores each result, and persists new jobs.

### Inputs

- Phase 2: `jobs_repository.py` for persistence and deduplication
- Phase 3: `scorer.py` for scoring each fetched job
- Phase 4: `BaseCrawler`, `http_client.py`
- Greenhouse API base URL: `https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs`
- Company board tokens stored in `config.yaml`

### Deliverables

- `src/crawlers/greenhouse_crawler.py` implementing `BaseCrawler` with `fetch()` calling the Greenhouse API and `parse()` mapping response fields to the job schema
- `src/pipeline/ingest.py` with an `ingest_jobs(jobs: list, source: str)` function that deduplicates, scores, and inserts new jobs using the repository layer
- Board tokens read exclusively from `config.yaml`

### Success Criteria

- Pointing the crawler at a locally mocked Greenhouse API response produces correctly structured job dicts with all required fields populated
- A job already present in the database (matched by `ats_job_id` + `source_url`) is not re-inserted
- A new job that passes the score threshold is inserted with `notified = False` and the correct score values
- A new job that fails the score threshold is still inserted but with `passed_threshold` recorded appropriately
- No board tokens or API URLs are hardcoded in `greenhouse_crawler.py`

---

## Phase 6 — Lever Integration

### Objective

Implement a crawler for Lever public job postings that fetches open roles from configured company posting URLs, parses job fields, deduplicates, scores, and persists new jobs using the shared ingest pipeline.

### Inputs

- Phase 2: `jobs_repository.py`
- Phase 3: `scorer.py`
- Phase 4: `BaseCrawler`, `http_client.py`
- Phase 5: `ingest.py`
- Lever posting URL pattern: `https://api.lever.co/v0/postings/{company}?mode=json`
- Company identifiers stored in `config.yaml`

### Deliverables

- `src/crawlers/lever_crawler.py` implementing `BaseCrawler` with `fetch()` and `parse()` targeting the Lever postings API
- Company identifiers and the Lever base URL read exclusively from `config.yaml`
- `parse()` maps Lever response fields to the shared job schema

### Success Criteria

- Pointing the crawler at a locally mocked Lever API response produces correctly structured job dicts with all required fields populated
- Deduplication via `job_exists_by_dedup_key` prevents duplicate Lever jobs from being inserted on repeated runs
- `lever_crawler.py` reuses `ingest.py` from Phase 5 rather than containing its own insert logic
- No company identifiers or API URLs are hardcoded in `lever_crawler.py`
- `lever_crawler.py` passes the same structural checks as `greenhouse_crawler.py`

---

## Phase 7 — Workday Integration

### Objective

Implement a crawler for Workday-hosted career pages that uses Playwright to render JavaScript-heavy pages, extracts job listings, and processes them through the shared ingest pipeline.

### Inputs

- Phase 2: `jobs_repository.py`
- Phase 3: `scorer.py`
- Phase 4: `BaseCrawler`, `playwright_utils.py`, `http_client.py`
- Phase 5: `ingest.py`
- Workday company career page URLs stored in `config.yaml`
- No invented selectors: only selectors confirmed against real Workday pages are used

### Deliverables

- `src/crawlers/workday_crawler.py` implementing `BaseCrawler` with `fetch()` using `playwright_utils.render_page()` and `parse()` using BeautifulSoup
- Target Workday URLs read exclusively from `config.yaml`
- HTML selectors documented with a comment explaining where each selector was verified

### Success Criteria

- Pointing the crawler at a locally saved Workday HTML snapshot produces correctly structured job dicts
- `workday_crawler.py` does not call `playwright_utils.render_page()` more than once per configured URL per run
- Deduplication prevents re-insertion of jobs already present in the database
- All Workday URLs are sourced from `config.yaml` with no hardcoded values in the crawler
- `CrawlerParseError` is raised when the expected HTML structure is not found

---

## Phase 8 — Notification System

### Objective

Implement a notification module that sends Telegram messages and emails for newly discovered jobs that meet the score threshold and match accepted locations, with a guard ensuring each job is notified exactly once.

### Inputs

- Phase 2: `jobs_repository.py` for reading unnotified jobs and calling `mark_notified`
- Phase 3: Score threshold from config
- Phase 1: `config_loader.py` for Telegram bot token, chat ID, email credentials, and accepted locations
- Telegram Bot API accessed via direct HTTP calls only

### Deliverables

- `src/notifications/telegram_notifier.py` with a `send_telegram(message: str, config) -> bool` function using direct HTTP POST to the Telegram Bot API
- `src/notifications/email_notifier.py` with a `send_email(subject: str, body: str, config) -> bool` function using Python's `smtplib`
- `src/notifications/dispatcher.py` with a `dispatch_new_jobs(config)` function that queries unnotified jobs above the threshold in accepted locations, sends both notifications, and calls `mark_notified` only on successful send
- Notification content includes: job title, company, location, source URL, and score

### Success Criteria

- A job with `notified = False`, score above threshold, and an accepted location triggers both a Telegram message and an email when `dispatch_new_jobs` is called with mocked send functions
- A job with `notified = True` is not re-notified on a subsequent call to `dispatch_new_jobs`
- A job below the score threshold is not notified even if `notified = False`
- A job in a non-accepted location is not notified
- `mark_notified` is not called when the send function returns `False`

---

## Phase 9 — Dashboard Foundation

### Objective

Build the Streamlit dashboard with navigation, data loading from the database, and five read-only job list views: Applied, Pending, High Priority, Referral-Needed, and Rejected.

### Inputs

- Phase 2: `jobs_repository.py` and `referrals_repository.py`
- Phase 1: `config_loader.py` for database path
- Streamlit library

### Deliverables

- `src/dashboard/app.py` as the Streamlit entry point with sidebar navigation
- `src/dashboard/views/applied.py`, `pending.py`, `high_priority.py`, `referral_needed.py`, `rejected.py` — each rendering a filtered job table for its respective status
- `src/dashboard/data_loader.py` with functions that call the repository layer and return DataFrames for each view
- All five views accessible from the sidebar with no page errors

### Success Criteria

- Running `streamlit run src/dashboard/app.py` starts the server without error
- Each of the five views renders a table when jobs with the corresponding status exist in the database
- Each view renders an empty table (not an error) when no matching jobs exist
- The dashboard reads from the database path specified in `config.yaml`
- No database queries appear directly in view files; all queries go through `data_loader.py`

---

## Phase 10 — Pipeline Management Features

### Objective

Add manual status update and manual tagging capabilities to the dashboard so users can change a job's status and add or remove tags directly from the interface.

### Inputs

- Phase 9: Dashboard views and `data_loader.py`
- Phase 2: `update_job_status` and `update_job_tags` from `jobs_repository.py`

### Deliverables

- `src/dashboard/components/status_editor.py` rendering a status dropdown and a save button for a selected job
- `src/dashboard/components/tag_editor.py` rendering a text input for comma-separated tags and a save button for a selected job
- Both components call repository functions directly and refresh the view on save
- Valid status values enforced by a fixed list matching the schema

### Success Criteria

- Selecting a job and changing its status via the dropdown updates the `status` field in the database and reflects the change on page refresh
- Entering tags for a job and saving updates the `tags` field and the change is visible on the next load
- An invalid status value cannot be submitted through the dropdown (constrained by the UI control)
- Status and tag updates do not affect any other field on the job record
- The tag editor accepts an empty string and clears existing tags in the database

---

## Phase 11 — Referral Tracking

### Objective

Add a referral tracking section to the dashboard where users can create referral records, update their status, and view all referrals in a dedicated table.

### Inputs

- Phase 2: `referrals_repository.py` with `insert_referral`, `update_referral_status`, `get_all_referrals`
- Phase 9: Dashboard navigation structure

### Deliverables

- `src/dashboard/views/referrals.py` rendering the referral table with all fields: company, role, applied_date, referral_status, recruiter_contacted, follow_up_date
- `src/dashboard/components/referral_form.py` with a form for creating a new referral record with all required fields
- `src/dashboard/components/referral_status_editor.py` for updating referral_status and follow_up_date on an existing record
- Referral view accessible from the sidebar alongside the five job views

### Success Criteria

- Submitting the referral form with all required fields creates a new record in the `referrals` table
- The referral table reflects the new record immediately after submission
- Updating `referral_status` via the editor saves the change to the database
- Updating `follow_up_date` via the editor saves the change to the database
- The referral view renders an empty table (not an error) when no referral records exist

---

## Phase 12 — Export System

### Objective

Implement export functionality that allows the user to download the current job list or referral list as a CSV or Excel file from within the dashboard.

### Inputs

- Phase 9: `data_loader.py` DataFrames
- Phase 11: Referral data from `data_loader.py`
- Python `csv` module and `openpyxl` library

### Deliverables

- `src/export/exporter.py` with functions: `export_jobs_csv(jobs_df) -> bytes`, `export_jobs_excel(jobs_df) -> bytes`, `export_referrals_csv(referrals_df) -> bytes`, `export_referrals_excel(referrals_df) -> bytes`
- `src/dashboard/components/export_controls.py` rendering download buttons in the dashboard using Streamlit's `st.download_button`
- Export controls accessible from the Applied, Pending, and High Priority views, and from the Referral view

### Success Criteria

- Clicking the CSV download button for jobs produces a valid `.csv` file containing all columns from the displayed DataFrame
- Clicking the Excel download button for jobs produces a valid `.xlsx` file that opens without error
- Clicking the CSV download button for referrals produces a valid `.csv` file with all referral fields
- Export functions in `exporter.py` operate on DataFrames passed as arguments and perform no database calls
- Exporting an empty DataFrame produces a file with only the header row, not an error

---

## Phase 13 — Scheduling and Automation

### Objective

Implement a scheduler that runs all configured crawlers in sequence on a defined interval, using Python schedule in the development environment and documented cron configuration for production.

### Inputs

- Phase 5: `greenhouse_crawler.py`
- Phase 6: `lever_crawler.py`
- Phase 7: `workday_crawler.py`
- Phase 8: `dispatcher.py`
- Phase 1: `config_loader.py` for schedule interval settings
- Python `schedule` library

### Deliverables

- `src/scheduler/runner.py` with a `run_pipeline()` function that calls all three crawlers in sequence and then calls `dispatch_new_jobs`
- `src/scheduler/main.py` that uses the `schedule` library to call `run_pipeline()` at the interval defined in `config.yaml`
- `docs/cron_setup.md` documenting the exact cron command to use in production with the expected working directory and Python path
- Schedule interval configurable in `config.yaml` with a default of 60 minutes

### Success Criteria

- Running `python src/scheduler/main.py` starts a loop that calls `run_pipeline()` at the configured interval without exiting
- Changing the interval value in `config.yaml` and restarting `main.py` causes the new interval to take effect
- `run_pipeline()` can be called directly as a standalone function without the scheduler loop
- `docs/cron_setup.md` contains a working cron expression and command that can be copied and pasted without modification
- A failure in one crawler during `run_pipeline()` logs the error and continues to the next crawler rather than halting the pipeline

---

## Phase 14 — Testing and Quality Assurance

### Objective

Write a complete automated test suite covering all modules, using in-memory SQLite for database tests and mocked network calls for all crawler and notification tests.

### Inputs

- All modules from Phases 1 through 13
- `pytest` and `pytest-mock` in `requirements-dev.txt`
- Rules from RULES.md: no production database in tests, all network calls mocked

### Deliverables

- `tests/test_config_loader.py` verifying config loading and missing key behavior
- `tests/test_db_migrations.py` verifying schema creation and version recording on in-memory SQLite
- `tests/test_jobs_repository.py` verifying all repository functions against in-memory SQLite
- `tests/test_referrals_repository.py` verifying all referral repository functions
- `tests/test_scorer.py` verifying all scoring rules, gate logic, and threshold behavior
- `tests/test_greenhouse_crawler.py` verifying parse output against a fixture JSON file, with HTTP mocked
- `tests/test_lever_crawler.py` verifying parse output against a fixture JSON file, with HTTP mocked
- `tests/test_workday_crawler.py` verifying parse output against a fixture HTML file, with Playwright mocked
- `tests/test_dispatcher.py` verifying notification gate logic with send functions mocked
- `tests/test_ingest.py` verifying deduplication and insert behavior
- `tests/test_exporter.py` verifying CSV and Excel output structure
- `tests/fixtures/` directory containing all fixture files used by crawler tests

### Success Criteria

- Running `pytest tests/` from the project root completes with zero failures and zero errors
- No test opens a file at the production database path defined in `config.yaml`
- No test makes a real HTTP or Playwright network call
- Each test file covers only the module it is named after
- Test coverage for `scorer.py` and all repository modules is 100 percent of defined functions

---

## Phase 15 — Release Candidate

### Objective

Verify end-to-end system behavior, finalize all documentation, and confirm the platform is ready for regular daily use as a complete Version 1 release.

### Inputs

- All deliverables from Phases 1 through 14
- `README.md` from Phase 1
- `docs/cron_setup.md` from Phase 13

### Deliverables

- Updated `README.md` with complete setup instructions, all configuration keys documented, and instructions for running the dashboard and scheduler
- `docs/DECISIONS.md` recording the rationale for each major architectural choice made during Version 1
- `docs/RULES.md` confirming all hard constraints enforced during development
- `docs/E2E_CHECKLIST.md` covering: run migrations, run one crawler with mocked data, verify job in database, verify notification dispatched, open dashboard, verify job visible, change status, export CSV
- All files in `src/` import without error when running `python -c "import src.<module>"` for each top-level module
- No placeholder values, TODO comments, or hardcoded secrets anywhere in the codebase

### Success Criteria

- Every item in `docs/E2E_CHECKLIST.md` can be checked off against the actual running system
- `pytest tests/` passes with zero failures on a clean checkout after `pip install -r requirements.txt` and `pip install -r requirements-dev.txt`
- The Streamlit dashboard starts and all six views (five job views plus referrals) are reachable with no unhandled exceptions
- `python src/scheduler/runner.py` calls all three crawlers and the dispatcher in sequence and completes without error when all external calls are mocked
- `README.md` contains enough information to set up and operate the platform on a new machine without referring to any other document
