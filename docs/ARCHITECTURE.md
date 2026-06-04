# Architecture — Job Intelligence Platform V1

Status: Approved for V1 implementation.
Scope: Personal, local-first tool for finding, scoring, tracking, and alerting on Data Engineering job matches. Not a CRM. Not a mass-apply tool.

Companion documents (to be written separately): `SCHEMA.md`, `MODULES.md`, `CONFIG.md`.

---

## 1. High-Level Architecture Diagram

```
  config/config.yaml + config/.env
       |
       v
  config_loader.py
       |
       +-----------------------------------------------+
       |                                               |
       v                                               v
  scheduler/runner.py                         dashboard/app.py  (Streamlit)
       |                                               |
       +------------------+                    data_loader.py
       |                  |                            |
       v                  v                            v
  [Crawlers]          dispatcher.py          jobs_repository.py
  greenhouse          (Notification)         referrals_repository.py
  lever               |        |                       |
  workday             v        v                       |
       |          telegram   email                     |
       |          _notifier  _notifier                 |
       v                                               |
  pipeline/ingest.py                                   |
       |                                               |
       +-----> scoring/scorer.py                       |
       |             |                                 |
       +-----> db/jobs_repository.py <-----------------+
                     |
                     v
              data/jobs.db  (SQLite)
```

Crawlers fetch, ingest scores and deduplicates, writes hit SQLite, dispatcher reads SQLite for unnotified jobs, Streamlit reads SQLite for display. The scheduler orchestrates the crawl → ingest → dispatch sequence. The dashboard is read-biased with narrow write paths (status, tags, referrals) going back through the repository layer.

---

## 2. Component Responsibilities

**config_loader.py**
- Owns: loading `config/config.yaml` and `config/.env`, exposing a typed config object.
- Does NOT own: secrets storage, validation of external data.
- Validate required configuration keys at startup.
- Application startup must fail fast if required keys are missing.

**crawlers/base_crawler.py + http_client.py + playwright_utils.py**
- Owns: HTTP fetching (direct API or HTML), Playwright-based page rendering, rate limiting, retry, error classification.
- Supports two extraction modes — chosen per source: (a) direct HTML/API extraction via `http_client`, (b) JS-rendered extraction via `playwright_utils`.
- Source-specific extraction mode is decided per ATS during implementation, not at architecture time.
- Does NOT own: scoring, deduplication, database writes, notification.

**crawlers/greenhouse_crawler.py, lever_crawler.py, workday_crawler.py**
- Owns: source-specific fetch + parse logic, mapping raw responses to the job dict schema.
- Each crawler chooses its extraction mode (direct vs. Playwright) based on what the source actually requires.
- Does NOT own: insertion, scoring, cross-source logic.

**pipeline/ingest.py**
- Owns: deduplication check, calling scorer, calling `jobs_repository` to insert new records.
- Does NOT own: fetching, notification dispatch, dashboard logic.

**scoring/scorer.py + scoring/rules.py**
- Owns: role match gate, keyword scoring, location bonus, company bonus, score breakdown dict.
- Does NOT own: any I/O. Pure functions only.

**db/jobs_repository.py + db/referrals_repository.py + db/migrations.py + db/schema.sql**
- Owns: all SQL, parameterized queries, schema creation and versioning.
- Does NOT own: business logic, scoring, notification formatting.

**notifications/dispatcher.py**
- Owns: eligibility check (score + location + notified flag), invoking notifier modules, calling `mark_notified` per the success policy in §6.
- Does NOT own: scoring logic, message formatting detail.

**notifications/telegram_notifier.py + email_notifier.py**
- Owns: formatting the message payload and executing the send. Each notifier returns a clear success/failure result to the dispatcher.
- Does NOT own: eligibility decisions, database writes.

**dashboard/app.py + views/ + components/ + data_loader.py**
- Owns: rendering views, exposing status/tag/referral edit controls, triggering export.
- Does NOT own: direct SQL, scoring, notification triggering.

**export/exporter.py**
- Owns: converting DataFrames to CSV or Excel bytes.

**scheduler/runner.py + scheduler/main.py**
- Owns: sequencing crawlers then dispatcher, catching per-crawler failures without halting the pipeline.

---

## 3. Data Flow

```
1. CRAWL
   scheduler/runner.py invokes each crawler's .run()
   Each crawler: fetch (direct HTTP or Playwright) -> parse -> yield list[job_dict]

2. INGEST  (pipeline/ingest.py, per job_dict)
   a. Validate required fields (title, company, source_url). Reject + log if missing.
   b. Normalize location (e.g., Gurgaon -> Gurugram). Set location_ineligible flag.
   c. Check dedup key: (source_url + ats_job_id) or hash(company+title+location).
      Exists -> skip. New -> proceed.
   d. scorer.score_job() -> returns final_score, breakdown dict, passed_threshold bool.
   e. jobs_repository.insert_job() with full record, notified=False.

3. NOTIFY  (notifications/dispatcher.py, called once after all crawlers finish)
   a. Query jobs WHERE notified=0 AND score >= threshold AND location_ineligible=0.
   b. For each qualifying job:
      - Attempt telegram_notifier.send() -> bool
      - Attempt email_notifier.send() -> bool
      - If EITHER returns True: jobs_repository.mark_notified(job_id)
      - If BOTH fail: log job_id + timestamps + reasons; do NOT mark notified.

4. DASHBOARD  (on user request, read-path)
   data_loader.py -> jobs_repository -> SQLite -> DataFrame -> Streamlit view

5. WRITE-BACK  (user action)
   status / tag edit -> component -> jobs_repository.update_*()
   referral form     -> referrals_repository.insert_referral / update_referral

6. EXPORT
   DataFrame -> exporter.py -> bytes -> st.download_button
```

---

## 4. Module Boundaries

Proposed source layout:

```
config/
  config.yaml            # runtime — gitignored, never committed
  config.yaml.example    # template — committed
  .env                   # secrets — gitignored, never committed
  .env.example           # template — committed

src/
  config_loader.py

  crawlers/
    base_crawler.py          # abstract BaseCrawler
    http_client.py           # direct HTTP: get/post with retry + rate limit
    playwright_utils.py      # render_page() for JS-rendered sources
    exceptions.py            # CrawlerFetchError, CrawlerParseError
    greenhouse_crawler.py
    lever_crawler.py
    workday_crawler.py

  pipeline/
    ingest.py

  scoring/
    scorer.py
    rules.py

  db/
    schema.sql
    migrations.py
    jobs_repository.py
    referrals_repository.py

  notifications/
    dispatcher.py
    telegram_notifier.py
    email_notifier.py

  dashboard/
    app.py
    data_loader.py
    views/
      high_priority.py
      applied.py
      pending.py
      referral_needed.py
      rejected.py
      referrals.py
    components/
      status_editor.py
      tag_editor.py
      referral_form.py
      referral_status_editor.py
      export_controls.py

  export/
    exporter.py

  scheduler/
    runner.py
    main.py
```

Interface contracts that cross module lines:
- Crawlers emit `list[dict]` to `ingest.py`; crawlers never import ingest.
- `scorer.score_job(job_dict, config) -> dict` — scorer has no DB or I/O imports.
- `dispatcher.py` calls both repository and notifier functions; notifiers never call the repository.
- `data_loader.py` is the only dashboard file that imports from `src/db/`.
- `http_client` and `playwright_utils` are interchangeable extraction backends behind `base_crawler` — a crawler picks one; ingest is indifferent to which was used.

---

## 5. Database Responsibilities

SQLite is the only permitted database for V1 (per DECISIONS.md). All queries go through the repository layer — direct SQL outside `src/db/` is not permitted.

Three tables (full column-level schema lives in `SCHEMA.md`):
- **jobs** — one row per discovered job, including score, score_breakdown (JSON TEXT), status, tags, notified flag, location_ineligible flag, dedup keys, timestamps.
- **referrals** — referral tracking records owned by the user, independent of the jobs table.
- **schema_version** — single-row version + applied_at timestamp; incremented by `migrations.py`.

WAL mode is enabled at migration time to permit concurrent dashboard reads/writes during scheduler runs.

What the DB is NOT for: no API tokens, no user accounts, no session data, no test data. All tests use in-memory SQLite.

---

## 6. Notification Responsibilities

Telegram and email are both required channels (per DECISIONS.md). Default score threshold is 20 (configurable).

**Triggering conditions (all three must hold):**
1. `notified = 0` (first discovery only)
2. `location_ineligible = 0`
3. `score >= NOTIFICATION_THRESHOLD`

**Trigger point:** `dispatcher.dispatch_new_jobs(config)` is called by `runner.run_pipeline()` after all crawlers finish. The dashboard never triggers notifications.

**Success policy (confirmed):** A job is marked `notified = 1` if **at least one** of the two channels succeeds. Both channels are always attempted, independently — a failure in one does not skip the other. Only when **both** channels fail is the job left unnotified for retry on the next run. Rationale: prioritize delivery over duplicate-avoidance for this single-user tool.

**Payload (both channels):**
```
Job Title: {title}
Company:   {company}
Location:  {location_normalized}
Score:     {score}
Link:      {source_url}
```

**Telegram mechanics:** Direct HTTP POST to `https://api.telegram.org/bot{token}/sendMessage` via `requests`. No third-party Telegram library. Tokens never logged.

**Email mechanics:** Python `smtplib` with SMTP credentials from `.env`.

**Suppressed:**
- Already-notified jobs (re-runs never re-send).
- Location-ineligible jobs.
- Jobs below the score threshold.
- Score recalculations on existing records.

---

## 7. Dashboard Responsibilities

Streamlit single-page app with six sidebar-navigated views:

| View | Filter | Editable controls |
|---|---|---|
| High Priority | `score >= threshold`, not Applied/Rejected | status, tags |
| Pending | `status = Pending` | status, tags |
| Applied | `status = Applied` | status, tags, referral fields |
| Referral-Needed | `status = Referral-Needed` | status, tags, referral fields |
| Rejected | `status = Rejected` | status (undo) |
| Referrals | all rows in `referrals` | full referral form |

User actions:
- Change a job's status (dropdown).
- Add or clear comma-separated tags.
- Create a referral record.
- Update referral status and follow-up date.
- Download the current view as CSV or Excel.

Read-only fields: `score`, `score_breakdown`, `title`, `company`, `source_url`, `description`, `date_posted`, `first_seen_at`, `notified`.

The dashboard does NOT trigger crawls or notifications, does NOT execute SQL directly, and does NOT edit configuration.

---

## 8. Configuration Responsibilities

All configurable values are read from local config files. No hardcoded values for anything that could change (per RULES.md).

**`config/config.yaml`** — runtime, gitignored, never committed. Contains all non-secret operational values: `database_path`, `schedule_interval_minutes`, `notification_threshold`, scoring weights and penalties, `accepted_locations`, `accepted_role_keywords`, `positive_keywords`, `negative_keywords`, `company_tier_1`, `company_tier_2`, and source identifiers (`greenhouse_board_tokens`, `lever_company_ids`, `workday_urls`). Copy from `config/config.yaml.example` to create.

**`config/.env`** — runtime, gitignored, never committed, never logged. Contains all secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `EMAIL_ADDRESS`, `EMAIL_PASSWORD`, `SMTP_HOST`, `SMTP_PORT`. Copy from `config/.env.example` to create.

**`config/config.yaml.example`** and **`config/.env.example`** — committed templates documenting every required key. No real values. Users copy these files to create their runtime config.

**`config_loader.py`** is the single entry point. All modules import config through it; no module reads `config/config.yaml` or `config/.env` directly.

Detailed key-by-key documentation will live in `docs/CONFIG.md` (to be written later).

---

## 9. Testing Boundaries

| Module | Test approach |
|---|---|
| config_loader | Unit: valid YAML loads; missing key raises |
| db/migrations | Unit: in-memory SQLite; tables + version row created |
| jobs_repository | Unit: in-memory SQLite; insert, dedup, status update, mark_notified |
| referrals_repository | Unit: in-memory SQLite; insert, update, fetch |
| scoring/scorer | Unit: known input → expected score; boundary cases; threshold gate |
| scoring/rules | Unit: role match true/false on known titles |
| pipeline/ingest | Unit: mock scorer + mock repo; verify dedup gate and conditional insert |
| crawlers/* (direct HTTP) | Unit: fixture JSON/HTML → expected job_dict; HTTP mocked |
| crawlers/* (Playwright) | Unit: fixture HTML snapshot → expected job_dict; Playwright mocked |
| notifications/dispatcher | Unit: mock notifiers + mock repo; verify eligibility gates; verify mark_notified called when **either** notifier returns True and not called when both return False |
| notifications/* | Unit: payload formatting; send call mocked |
| export/exporter | Unit: known DataFrame → valid CSV bytes and valid xlsx bytes |

**Hard test isolation rules:**
- No test touches `data/jobs.db`.
- No test makes a live HTTP or Playwright request.
- All DB-touching tests use `sqlite:///:memory:`.

**Intentionally untested in V1:**
- Live end-to-end calls to Greenhouse/Lever/Workday endpoints.
- Streamlit UI rendering.
- Cron scheduling in production (verified manually).
- Real SMTP delivery (send function is always mocked).

---

## 10. Risks and Tradeoffs

**Workday selector brittleness.** JS-rendered pages vary by company and can change on platform updates. Mitigation: each parse is isolated; failures log `CrawlerParseError` with the URL and do not halt other crawlers. V2 candidate: snapshot-based change detection.

**Dual extraction modes add surface area.** Supporting both direct HTTP and Playwright means two backends to maintain. Accepted because some sources (likely Workday) genuinely require rendering, and direct extraction is materially simpler and faster where possible. Source-by-source decisions are deferred to implementation time after ATS verification.

**SQLite write contention.** Scheduler writes and dashboard writes can overlap. Mitigated by WAL mode enabled in `migrations.py`.

**Notification duplication risk.** Because a job is marked notified when **either** channel succeeds, a transient Telegram-only success followed by an email-only success on the next run is not possible (the job is already notified after the first run). The accepted tradeoff is the opposite case: if Telegram succeeds but the user only checks email, they may miss the alert until the next dashboard visit. Acceptable for a single-user tool.

**Score drift on config changes.** Scores are write-once at ingestion. Changing keyword weights does not re-score existing records. V1 limitation, documented in README. Re-scoring is a manual operation, not built in.

**Location matching false positives.** Substring matching could over-match (e.g., "Hybrid" matching "Hybrid-Remote"). Mitigation: keep `accepted_locations` conservative and normalize at ingestion.

**Config sprawl.** `config.yaml` will be large (keyword dicts, company tiers, ATS identifiers). Acceptable at single-user scale. Splitting into `config/scoring.yaml` + `config/sources.yaml` is a V2 candidate.

**Deliberate V1 simplifications:**
- No authentication (single-user local tool).
- No incremental schema migrations — V1 schema changes require drop-and-recreate.
- No Streamlit UI tests.
- No retry queue for failed notifications (next scheduled run is the retry).
- `tags` stored as a comma-separated TEXT column rather than a normalized tags table.
- `score_breakdown` stored as JSON TEXT rather than a normalized table.
- Dashboard components may write through repositories directly.

- No additional service layer is required in Version 1.