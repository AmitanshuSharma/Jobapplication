# Scoring and Ranking System
# Job Intelligence Platform — Version 1

---

## 1. Scoring Philosophy

This document defines the complete scoring and ranking system for the Job Intelligence Platform. The system is deterministic and rule-based. No machine learning, no AI-based inference, and no probabilistic logic is used in Version 1.

Every job receives a numeric score computed from a fixed set of rules applied to its title, description, location, and company. Scores are always computed and stored, regardless of whether the job will trigger a notification. Notification eligibility is a separate gate evaluated after scoring.

The scoring system serves one purpose: surface the highest-signal Data Engineering roles quickly and correctly, so the user can act on them without reviewing noise.

Design principles:

- Scores are reproducible. The same job record will always produce the same score.
- Scores are explainable. Each point added or subtracted can be traced to a specific rule.
- Scoring and notification are decoupled. A job can be scored but not eligible for notification (wrong location, below threshold).
- All weights and thresholds are configurable. Default values are defined here and in the platform config file.

---

## 2. Role Matching Rules

Role matching is the first scoring stage.

Jobs are evaluated against the accepted role keyword list using a case-insensitive substring match against the job title.

Accepted role keywords (from config: `ACCEPTED_ROLE_KEYWORDS`):

- Senior Data Engineer
- Lead Data Engineer
- Staff Data Engineer
- Data Platform Engineer
- Data Engineering Lead
- Big Data Engineer
- Principal Data Engineer
- Analytics Engineer
- Senior Analytics Engineer

Partial matches are accepted (e.g., "Senior Data Engineer - Platforms" matches "Senior Data Engineer").

### Role Mismatch Penalty

If a job does not match any accepted role keyword, it is not excluded from the database.

Instead, the job receives a configurable role mismatch penalty.

Default:

ROLE_MISMATCH_PENALTY = -50

This penalty is applied before notification eligibility is evaluated.

The purpose is to retain potentially relevant opportunities while ensuring non-target roles remain unlikely to exceed the notification threshold.

Examples:

- Data Engineer → eligible for normal scoring
- Senior Data Platform Developer → receives role mismatch penalty but remains visible
- Business Analyst → receives role mismatch penalty and additional negative keyword penalties

Jobs that receive the role mismatch penalty remain stored, searchable, and visible within the dashboard.

---

## 3. Positive Keywords and Weights

After a job passes role matching, the job description is scanned for positive signal keywords. Each keyword found contributes its defined weight to the raw score. Multiple keywords can match; their weights are summed. The same keyword is counted at most once per job, even if it appears multiple times in the description.

Matching is case-insensitive. Matching is substring-based against the full description text.

Default positive keyword weights (from config: `POSITIVE_KEYWORDS`):

| Keyword              | Weight |
|----------------------|--------|
| Databricks           | +10    |
| PySpark              | +10    |
| Platform Engineering | +10    |
| Spark                | +8     |
| Kafka                | +8     |
| Streaming            | +8     |
| Distributed Systems  | +8     |
| CDC pipelines        | +7     |
| Delta Lake           | +7     |
| Lakehouse            | +7     |
| DBT                  | +6     |
| Snowflake            | +6     |
| Azure                | +6     |
| AWS                  | +6     |
| BigQuery             | +5     |
| Airflow              | +5     |
| Scala                | +4     |
| Python               | +4     |
| SQL                  | +3     |

All values in this table are overridable via config. New keywords can be added to config without changing scoring logic.

---

## 4. Negative Keywords and Weights

Negative keywords penalize roles that are likely unsuitable regardless of their positive signal. They are applied to the job title first, then to the job description. Penalties are summed across all matched negative keywords. The same keyword is counted at most once per job.

A job that accumulates enough negative weight may fall below the notification threshold or produce a negative total score. The job is still stored and scored; it is not automatically excluded. Role exclusion applies only at the role match gate in Section 2.

Default negative keyword weights (from config: `NEGATIVE_KEYWORDS`):

| Keyword                   | Weight |
|---------------------------|--------|
| Presales                  | -15    |
| Support                   | -12    |
| Solution Architect        | -10    |
| Delivery Manager          | -10    |
| Project Manager           | -10    |
| Client Partner            | -10    |
| Business Analyst          | -8     |
| Engagement Lead           | -8     |
| Transformation Consultant | -8     |
| PowerBI                   | -5     |
| Tableau                   | -5     |
| Talend                    | -5     |
| Ab Initio                 | -5     |
| SSIS                      | -5     |
| Informatica PowerCenter   | -5     |

All values are overridable via config. Negative keywords found in the job title carry the full penalty, identical to when found in the description. There is no title-specific multiplier in Version 1.

---

## 5. Location Rules

Location rules determine two things: whether a location bonus is applied to the score, and whether the job is eligible to trigger a notification.

Accepted locations (from config: `ACCEPTED_LOCATIONS`):

- Gurugram
- Gurgaon (treated as equivalent to Gurugram; normalized to Gurugram at ingestion)
- Noida
- Pune
- Hyderabad
- Remote
- India Remote
- Hybrid

Location matching is case-insensitive substring match against the job's location field.

**Location bonus:** If a job location matches Remote or India Remote, a bonus of +5 is added to the raw score (from config: `REMOTE_LOCATION_BONUS`, default: 5). No other accepted location receives a bonus. No penalty is applied to non-remote accepted locations.

**Non-accepted locations:** A job with a location that does not match any accepted location string is stored and scored normally, but is flagged as `location_ineligible`. Jobs flagged `location_ineligible` will never trigger a notification, regardless of their score.

No negative score penalty is applied for a non-accepted location. The location ineligibility flag is a notification gate, not a score modifier — with one exception: the Remote bonus is only applied when the location is explicitly accepted as Remote or India Remote.

Per Rule 6.3 (RULES.md): Notifications must only fire for accepted locations regardless of score. This constraint is enforced at the notification dispatch layer, not during score computation.

---

## 6. Company Priority Rules

Company priority adds a bonus to the raw score to surface roles at high-signal employers. The bonus is applied after keyword scoring and before the final score is written to the database.

Companies are organized into two tiers. Tier values are configurable (from config: `COMPANY_TIERS`).

**Tier 1 — Product and Engineering-focused** (from config: `COMPANY_TIER_1_BONUS`, default: +8):

- Atlassian
- Adobe
- ServiceNow
- Walmart Global Tech
- Target
- Expedia Group
- PayPal
- Salesforce
- Intuit
- Uber
- Microsoft
- SAP
- Databricks

**Tier 2 — Analytics ecosystem** (from config: `COMPANY_TIER_2_BONUS`, default: +5):

- Tiger Analytics
- Tredence
- Fractal Analytics
- LatentView Analytics

Company matching is case-insensitive exact match against the normalized company name field. Partial matching is not used to avoid false positives.

A job at a company not listed in any tier receives no company bonus. There is no company penalty in Version 1.

If a company appears in both tiers due to a config error, the higher bonus (Tier 1) is applied.

Per Rule 4.11 (RULES.md): Company priority must contribute to ranking, its values must be configurable, and its logic must be documented in this file. This section satisfies that requirement.

---

## 7. Notification Threshold Rules

The notification threshold is the minimum score a job must reach before a notification is dispatched. This threshold controls alert volume and is the primary knob for tuning signal-to-noise ratio.

Default threshold (from config: `NOTIFICATION_THRESHOLD`, default: 20).

Notification eligibility requires all three conditions to be true simultaneously:

1. The job passed the role match gate (Section 2).
2. The job's location is accepted — not flagged `location_ineligible` (Section 5).
3. The job's final score is greater than or equal to `NOTIFICATION_THRESHOLD`.

If any condition is false, no notification is sent. The job is still stored with its computed score and its eligibility status.

Scoring is always performed and stored for every job that passes role matching, regardless of notification eligibility. This allows the user to browse scored-but-ineligible jobs through the dashboard.

A job that was previously below threshold is not re-notified if the threshold is later lowered, unless the job is explicitly reprocessed. Notification state is tracked per job in the database via the `notified` field.

---

## 8. Ranking Formula

The final score for a job is the sum of all applicable components:

```
final_score = keyword_score + location_bonus + company_bonus
```

Where:

- `keyword_score` = sum of matched positive keyword weights minus sum of matched negative keyword weights
- `location_bonus` = `REMOTE_LOCATION_BONUS` (+5) if location is Remote or India Remote, else 0
- `company_bonus` = `COMPANY_TIER_1_BONUS` (+8) if Tier 1, `COMPANY_TIER_2_BONUS` (+5) if Tier 2, else 0

There is no normalization, no scaling, and no weighting of the total. The score is a raw integer sum. Scores can be negative if negative keyword penalties dominate.

When presenting jobs in ranked order, jobs are sorted by `final_score` descending. Higher scores appear first.

**Illustrative example:**

A job with PySpark (+10), Databricks (+10), Kafka (+8), Remote location bonus (+5), and company in Tier 1 (+8):

```
final_score = (10 + 10 + 8) + 5 + 8 = 41
```

This job is above the notification threshold of 20 and would trigger an alert.

---
## Score Explanation Rules

Every stored score must include a score explanation record.

The explanation must list every matched scoring component and its contribution.

Example:

PySpark                +10
Databricks             +10
Kafka                  +8
Remote Bonus           +5
Tier 1 Company Bonus   +8

Final Score: 41

The score explanation exists for transparency, debugging, and dashboard display.

Users must be able to understand exactly why a job received a given score.

Score explanations are informational only and do not affect ranking logic.

---

## 9. Tie-Breaking Rules

When two or more jobs share an identical `final_score`, the following tiebreaking sequence is applied in order. The first rule that produces a strict ordering terminates the sequence.

1. **Company tier:** Jobs at Tier 1 companies rank above Tier 2. Tier 2 ranks above no-tier.

2. **Location preference:** Jobs at Remote or India Remote locations rank above jobs at other accepted locations.

3. **Recency:** Jobs with a more recent `date_posted` value rank above older ones. If `date_posted` is null for one or both jobs, jobs with a non-null date rank above jobs with a null date. If both are null, recency does not differentiate them.

4. **Ingestion order:** Jobs with a lower `id` value (earlier ingested) rank above jobs with a higher `id` value. This produces a stable, reproducible sort.

No randomization is used at any tiebreaking step.

---

## 10. Future Scoring Extensions

The following extensions are out of scope for Version 1. They are listed here to inform future design. None of these may be implemented until explicitly approved per Rule 3.6 (RULES.md).

1. **Experience level weighting:** Apply a bonus based on seniority level (senior, staff, principal) parsed from the job title.

2. **Salary range scoring:** Add a bonus proportional to the offered compensation range, for sources that provide structured salary data.

3. **Recency decay:** Apply a time-based score decay for jobs older than a configurable number of days (e.g., posted more than 14 days ago), applied at sort time only to preserve score determinism.

4. **Source reliability weighting:** Apply a per-source multiplier to account for relative signal quality across job boards and APIs.

5. **Keyword co-occurrence bonuses:** Award additional points when high-signal keywords appear together in the same sentence or paragraph.

6. **Negative keyword title multiplier:** Apply a higher penalty (e.g., 1.5x) when a negative keyword appears in the job title versus only in the description.

7. **User feedback loop:** Allow the user to score or dismiss jobs manually, feeding corrections into keyword weight adjustments over time.

8. **ML-based scoring model:** Replace or augment rule-based scoring with a trained classifier. Explicitly deferred to a later version per the design constraints stated in Section 1.


## Default Configuration Values

NOTIFICATION_THRESHOLD = 20

REMOTE_LOCATION_BONUS = 5

COMPANY_TIER_1_BONUS = 8

COMPANY_TIER_2_BONUS = 5

ROLE_MISMATCH_PENALTY = -50

All values above are configurable and may be changed through configuration files without modifying scoring logic.

---