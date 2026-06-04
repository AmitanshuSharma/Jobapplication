# Development and Implementation Rules
# Job Intelligence Platform — Version 1

These rules are mandatory. All contributors and agents must follow them without exception.
Rules override convenience. If a rule conflicts with a proposed shortcut, the rule wins.

---

## 1. Planning Rules

1.1. A written plan must exist before any code is written. Implementation without a prior plan is not permitted.

1.2. Plans must be broken into phases or steps, each with a clear objective and defined output.

1.3. Plans must identify dependencies between components before implementation begins.

1.4. Plans must list risks and how they will be mitigated.

1.5. Plans must define acceptance criteria that can be verified after implementation.

1.6. No architectural change may be made unless it is explicitly included in the plan and approved before implementation.

1.7. If a task is ambiguous, clarification must be requested before planning begins. Do not assume intent.

1.8. All plans must reference existing project documentation (CLAUDE.md, DECISIONS.md, PRD.md, VISION.md) where relevant.

1.9. Plans must state which existing modules will be affected. No silent side effects are permitted.

1.10. A plan that contradicts a confirmed decision in DECISIONS.md is invalid and must be revised before proceeding.

---

## 2. Coding Rules

2.1. Each module must have a single, clearly stated responsibility. Multi-purpose modules are not permitted.

2.2. All functions must have clear, descriptive names that reflect exactly what they do.

2.3. Functions should generally remain under 50–75 lines.
Longer functions require justification.

2.4. All configuration values (tokens, credentials, thresholds, accepted locations) must be read from a local config file. Hardcoded configuration values are not permitted.

2.5. Every external input (scraped data, API response, user input) must be validated before it is stored or used.

2.6. Missing data must not be guessed or inferred. If a required field is missing, the record must be flagged or skipped, and the absence logged.

2.7. All database writes must use parameterized queries. String formatting or f-strings must not be used to build SQL statements.

2.8. Code must run on a local machine without requiring cloud services, paid APIs, or internet-dependent infrastructure.

2.9. All imports must be from the Python standard library or from libraries listed in requirements.txt. Unlisted libraries must not be imported.

2.10. Every decision made in code that is not obvious must include a brief inline comment explaining the reason.

---

## 3. Architecture Rules

3.1. The system is local-first and single-user. No multi-user, multi-tenant, or cloud-hosted architecture is permitted in Version 1.

3.2. SQLite is the only permitted database for Version 1. No other database engine may be introduced without a confirmed decision documented in DECISIONS.md.

3.3. FastAPI is not included in Version 1. The dashboard must use Streamlit only.

3.4. LinkedIn scraping is not included in Version 1. Only company career pages, Greenhouse API, Lever API, and Workday pages are permitted sources.

3.5. The Python schedule library must be used for scheduling during development. Cron must be used for production automation. No other scheduling mechanism is permitted.

3.6. No architecture change may be introduced without a written proposal, a stated reason, and an explicit confirmation documented before implementation.

3.7. Components must communicate through well-defined interfaces. Direct coupling between unrelated modules is not permitted.

3.8. The system must not depend on any paid service, paid API, or paid cloud infrastructure.

3.9. All file paths and database paths must be relative to the project root or read from configuration. Absolute hardcoded paths are not permitted.

3.10. New modules must be added as small, focused files. Monolithic files that combine unrelated functionality are not permitted.

---

## 4. Data Rules

4.1. Every job record must include all required fields: title, company, location, description, experience range, tech stack keywords, source URL, and ATS job ID.

4.2. Deduplication must use the defined key: (source_url + ATS job ID) when available, or hash(company + title + location) as fallback. No other deduplication strategy is permitted without a confirmed decision.

4.3. Jobs with missing optional fields may be stored.
Jobs missing critical fields (title, company, source URL) must be rejected.

4.4. Locations must be validated against the accepted locations list before a record is processed for scoring or notification. Records with locations outside the accepted list must be stored but must not trigger alerts.

4.5. No data transformation may silently discard or alter source values. Original scraped values must be preserved alongside any normalized values.

4.6. Scores must be computed using the defined scoring logic only. Ad hoc or experimental scoring must not affect stored scores without a plan and review.

4.7. The database schema must be defined in a single migrations or schema file. Schema changes must be versioned and documented.

4.8. No test data, dummy data, or placeholder data may be written to the production database.

4.9. All database reads and writes must go through the defined data access layer. Direct SQL outside the data layer is not permitted in application logic.

4.10. Data from external sources must be treated as untrusted. It must be sanitized and validated before storage.

4.11. Company priority must contribute to ranking.

Company priority values must be configurable.

Company priority logic must be documented in SCORING.md.
---

## 5. Crawling Rules

5.1. Crawlers must only target sources explicitly listed in the PRD: company career pages, Greenhouse API, Lever API, and Workday pages.

5.2. API selectors, endpoints, and response field names must be verified against live or documented API responses before being used in code. Invented or assumed selectors are not permitted.

5.3. Workday page selectors must be verified against the actual page structure before use. No selector may be written based on assumption alone.

5.4. Every crawler must handle HTTP errors explicitly. A non-200 response must be logged and must not cause a silent failure or partial write.

5.5. Rate limiting must be implemented for all crawlers. No crawler may make requests without a delay or back-off mechanism.

5.6. Crawlers must not store a job record until the full record has been retrieved and validated.

5.7. Crawlers must log the source URL and timestamp for every fetch attempt, regardless of success or failure.

5.8. Crawler failures must not crash the main process. Each crawler must run in isolation and report its status.

5.9. No crawler may be deployed to production without a test run against a known source that verifies field extraction.

5.10. Adding a new source requires a plan that identifies the source type, the fields available, the deduplication key, and the fetch mechanism, all confirmed before implementation.

---

## 6. Notification Rules

6.1. A notification must fire only on first discovery of a job record. Re-scoring or re-crawling an existing record must not trigger a new notification.

6.2. The score threshold for notifications is configurable. The default value is 20. The threshold must be read from the config file, not hardcoded.

6.3. Notifications must only fire for jobs with locations in the accepted locations list. Jobs outside the accepted list must not trigger notifications regardless of score.

6.4. The notification system must check the database before sending to confirm that a notification has not already been sent for the given job ID. Duplicate notifications are not permitted.

6.5. All notification credentials (Telegram token, chat ID, email credentials) must be read from the local config file. They must never be hardcoded or logged.

6.6. Notification failures must be logged with the job ID and timestamp. A failed notification must not prevent the system from continuing.

6.7. The notification payload must include: job title, company, location, score, and source URL. Incomplete notifications are not permitted.

6.8. The notification module must not contain scoring logic. Scoring and notification are separate responsibilities.

6.9. Any change to the notification threshold or accepted locations list must be made in the config file only. Code must not be modified to change these values.

6.10. Notification channels (Telegram, email) must be implemented as separate, interchangeable modules. Adding or removing a channel must not require changes to the scoring or crawling modules.

---

## 7. Documentation Rules

7.1. Every module must have a docstring at the top that states its purpose, its inputs, and its outputs.

7.2. Every public function must have a docstring that states what it does, its parameters, and its return value.

7.3. All confirmed architectural and implementation decisions must be recorded in DECISIONS.md before they are implemented.

7.4. Any deviation from the rules in this document must be documented with a reason before the deviation is permitted.

7.5. The README must reflect the current state of the project. It must be updated whenever a new module is added or a significant behavior changes.

7.6. Configuration file keys must be documented in a dedicated section of the README or in a separate CONFIG.md file. Undocumented config keys are not permitted.

7.7. The scoring logic must be documented in a dedicated section of the project documentation. Score weights and criteria must be explicit and verifiable.

7.8. Documentation must describe actual behavior, not intended or future behavior. Aspirational documentation is not permitted.

7.9. When a rule in this document is referenced in a plan or review, the rule number must be cited explicitly.

7.10. Documentation files must not contain implementation code. They are for explanations, decisions, and references only.

---

## 8. Testing Rules

8.1. Every module must have at least one test that verifies its primary function with valid input.

8.2. Every module must have at least one test that verifies its behavior with invalid or missing input.

8.3. Tests must not write to the production database. All tests must use a separate test database or in-memory SQLite.

8.4. Tests must not make live HTTP requests to external sources. Network calls must be mocked.

8.5. A crawler must not be merged until a test confirms it correctly extracts all required fields from a representative response.

8.6. The deduplication logic must have a test that verifies duplicate records are not inserted when the same (source_url + ATS job ID) or hash(company + title + location) is encountered.

8.7. The notification logic must have a test that verifies a notification is not sent twice for the same job ID.

8.8. The scoring logic must have a test that verifies a known input produces the expected score.

8.9. All tests must pass before any code is merged or considered complete. A plan that cannot be tested is not complete.

8.10. Test files must be named to match the module they test and placed in a dedicated tests directory. Inline tests in production modules are not permitted.

---

## 9. Review Rules

9.1. Every implementation must be reviewed against its acceptance criteria before it is marked complete.

9.2. Every implementation must be reviewed against this RULES.md document before it is marked complete.

9.3. A review must verify that no new dependencies were introduced without being added to requirements.txt.

9.4. A review must verify that no configuration values were hardcoded.

9.5. A review must verify that the module does not exceed its stated responsibility.

9.6. A review must verify that all required fields are validated before data is stored.

9.7. A review must verify that deduplication logic is in place and was tested.

9.8. A review must verify that notification logic does not re-fire on re-discovery of an existing record.

9.9. A review must confirm that the DECISIONS.md file reflects any new confirmed decisions made during the implementation.

9.10. A review is not complete until all checklist items in this section have been explicitly addressed. Partial reviews are not accepted.

---

## 10. Forbidden Behaviors

10.1. Do not guess missing data. If a field is missing, flag or skip the record. Do not fill in placeholder or inferred values.

10.2. Do not invent API endpoints, response field names, CSS selectors, or library interfaces. All of these must be verified against real documentation or live responses before use.

10.3. Do not introduce paid services, paid APIs, or paid cloud infrastructure in Version 1.

10.4. Do not change the architecture without a written proposal confirmed before implementation.

10.5. Do not add FastAPI, LinkedIn scraping, or any component explicitly excluded by DECISIONS.md.

10.6. Do not write to the production database during testing.

10.7. Do not send a notification more than once for the same job record.

10.8. Do not hardcode credentials, tokens, thresholds, or accepted locations in code.

10.9. Do not merge or finalize any implementation that has not passed its tests and its review checklist.

10.10. Do not write code that has no corresponding plan. Implementation without a prior written plan is a violation of these rules.
