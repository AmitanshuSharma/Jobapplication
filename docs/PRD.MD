# Product Requirements Document — Job Intelligence Platform

---

## 1. Functional Requirements

### Crawling

- The system must crawl company career pages directly, via Greenhouse API, Lever API, and Workday pages.
- The following companies must be crawled as high-priority targets: Atlassian, Adobe, ServiceNow, Walmart Global Tech, Target, Expedia Group, PayPal, Salesforce, Intuit, Uber, Microsoft, SAP, Databricks, Tiger Analytics, Tredence, Fractal Analytics, LatentView Analytics.
- Crawling must run daily without manual intervention.
- Each crawl run must store raw job data for the following fields per job record: title, company, location, description, experience range, detected tech stack keywords, source URL, ATS job ID.
- Deduplication must be applied on ingestion using either (source_url + ATS job ID) or a hash of (company + title + location).
- A job already in the database must not create a duplicate record on re-crawl.

### Scoring

- Every ingested job must receive a numeric relevance score.
- Positive score contributors and their weights:
  - Databricks: +10
  - PySpark: +10
  - Platform Engineering: +10
  - Spark: +8
  - Kafka: +8
  - Streaming: +8
  - Distributed Systems: +8
  - CDC pipelines: +7
  - Delta Lake: +7
  - Lakehouse: +7
  - DBT: +6
  - Snowflake: +6
  - Azure: +6
  - AWS: +6
  - BigQuery: +5
  - Airflow: +5
  - Remote: +5
  - Scala: +4
  - Python: +4
  - SQL: +3
- Negative score contributors and their weights:
  - Presales: -15
  - Support: -12
  - Solution Architect: -10
  - Delivery Manager: -10
  - Project Manager: -10
  - Client Partner: -10
  - Business Analyst: -8
  - Engagement Lead: -8
  - Transformation Consultant: -8
  - PowerBI: -5
  - Tableau: -5
  - Talend: -5
  - Ab Initio: -5
  - SSIS: -5
  - Informatica PowerCenter: -5
- Only jobs matching target role keywords must be considered for scoring. Target role keywords: "Senior Data Engineer", "Lead Data Engineer", "Staff Data Engineer", "Data Platform Engineer", "Data Engineering Lead", "Big Data Engineer", "Principal Data Engineer", "Analytics Engineer", "Senior Analytics Engineer".
- Roles outside the target role keyword list must receive a scoring penalty sufficient to prevent them from surfacing in alerts or the High Priority dashboard view.

### Notifications

- The system must send a Telegram notification for each newly discovered job with a score at or above the configured threshold.
- The system must send an Email notification for each newly discovered job with a score at or above the configured threshold.
- Telegram is the primary notification channel; Email is required.
- A notification must fire only on first discovery of a job. Score recalculations must not trigger re-notification.
- The notification threshold is configurable. The default value is 20.
- Notification content must include at minimum: job title, company, location, score, and source URL.

### Dashboard

- The dashboard must display jobs grouped into the following pipeline views: Applied, Pending, High Priority, Referral-Needed, Rejected.
- The dashboard must allow manual tagging of any job record.
- The dashboard must allow manual status updates for any job record.
- The dashboard must allow export of job records to CSV and Excel formats.
- Each job record displayed must include all referral tracking fields: company, role, applied date, referral status, recruiter contacted, follow-up date.

### Deduplication

- Deduplication must be enforced at the time of ingestion.
- The deduplication key is either (source_url + ATS job ID) if both are available, or a hash of (company + title + location) as a fallback.

---

## 2. User Workflows

### Daily Discovery Workflow

1. The crawl job runs automatically each day.
2. New job postings are fetched from all configured sources.
3. Each job is deduplicated against existing records.
4. Each new job is scored using the keyword scoring model.
5. Jobs meeting or exceeding the score threshold receive a Telegram and Email notification.
6. All ingested jobs (regardless of score) are stored in the database.

### Review and Triage Workflow

1. The user opens the dashboard.
2. The user navigates to the High Priority view to see top-scoring new matches.
3. The user reviews job title, company, location, score, and description.
4. The user updates the job status (e.g., Pending to Applied, or to Rejected).
5. The user applies a tag if needed (e.g., "referral-needed", "strong-fit").

### Referral Tracking Workflow

1. The user identifies a job where a referral is desired.
2. The user sets the status to Referral-Needed in the dashboard.
3. The user fills in recruiter contacted and follow-up date fields for the record.
4. The user updates referral status once contact is made or a referral is confirmed.

### Export Workflow

1. The user selects a pipeline view or applies filters on the dashboard.
2. The user triggers export.
3. The system generates a CSV or Excel file containing the visible records with all tracked fields.

---

## 3. Core Features

- **Career Page Crawler**: Fetches job postings from direct company career pages, Greenhouse API, Lever API, and Workday pages on a daily schedule.
- **Keyword Scoring Engine**: Assigns a numeric score to each job based on the defined positive and negative keyword weights applied to the job title and description.
- **Deduplication Engine**: Prevents duplicate job records from being created using (source_url + ATS job ID) or hash-based fallback.
- **Telegram Notifier**: Sends a structured alert to a configured Telegram chat for each qualifying new job.
- **Email Notifier**: Sends a structured alert to a configured email address for each qualifying new job.
- **Score Threshold Filter**: Suppresses alerts and high-priority views for jobs scoring below the configurable threshold (default: 20).
- **Job Database**: Persists all ingested job records and their full field set using SQLite.
- **Dashboard — Pipeline Views**: Displays jobs across five status buckets: Applied, Pending, High Priority, Referral-Needed, Rejected.
- **Dashboard — Manual Controls**: Allows the user to update job status and apply tags directly from the dashboard.
- **Dashboard — Referral Fields**: Displays and allows editing of all referral tracking fields on each job record.
- **Dashboard — Export**: Allows the user to export visible job records to CSV or Excel.
- **Scheduler**: Runs the daily crawl and notification pipeline automatically without manual invocation.

---

## 4. Optional Features

The following features are explicitly out of scope for Version 1 but are candidates for future versions.

- **AI-based Job Description Summarization**: Automatically generate a concise summary of a job description using a language model.
- **Resume-to-Job Match Percentage**: Compute a match score between the user's resume and a job description and surface this alongside the keyword score.
- **Auto-highlighting of Role Categories**: Automatically classify and label job records into role categories (streaming, platform engineering, leadership) based on description content.
- **Daily Digest Email**: Send a single daily summary email listing all new qualifying matches discovered in the last 24 hours.
- **Chrome Extension**: Browser extension to manually capture and add a job posting to the platform while browsing a career page.
- **LinkedIn Referral Finder**: Identify LinkedIn connections at a target company who could provide a referral for a given job.
- **GitHub Project Matching**: Match the user's GitHub projects against job description keywords and surface alignment indicators on the dashboard.

---

## 5. Constraints

- The platform must operate entirely on a local machine. No paid cloud infrastructure is required or permitted in Version 1.
- The database must be SQLite.
- The scheduler must use the Python schedule library during development and cron for production automation.
- FastAPI is not included in Version 1.
- LinkedIn scraping is not included in Version 1.
- The system is single-user only. No multi-user access, authentication layer, or user management is required.
- The notification threshold must be configurable by the user. The default value is 20.
- No job must generate more than one notification event, regardless of how many times it is re-scored.
- All personally identifiable configuration (Telegram token, email credentials, score threshold) must be stored in a local configuration file and must not be hardcoded.
- Locations outside the accepted list (Gurugram, Gurgaon, Noida, Pune, Hyderabad, Remote, India Remote, Hybrid) must not generate alerts, even if the job otherwise scores above the threshold.
- Jobs outside preferred locations remain stored in the database
but are not eligible for notifications.
- Gurgaon and Gurugram must be treated as the same location.

---

## 6. Out-of-Scope Features

- Mass application or automated job submission of any kind.
- Auto-apply or one-click apply functionality.
- Multi-user access or SaaS deployment.
- Resume building or generation.
- Cover letter generation.
- LinkedIn automation of any kind, including profile scraping or connection messaging.
- Recruiter CRM features beyond the referral tracking fields defined in this document.
- Roles outside the defined target role keyword list — these must be penalized in scoring, not surfaced.
- Any paid external API or cloud service.
- FastAPI or any REST API layer.
- Real-time crawling or event-driven triggers — crawling is daily batch only.
- Browser automation for sites not reachable via direct HTTP requests or supported ATS APIs (Greenhouse, Lever, Workday).
- Salary negotiation tooling or compensation benchmarking.
- Interview preparation or calendar scheduling features.
### Company Prioritization

- Each target company must have a configurable priority score.
- Higher-priority companies should rank above lower-priority companies when overall job scores are similar.
- Company priorities must be configurable without code changes.