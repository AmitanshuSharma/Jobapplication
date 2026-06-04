# Scoring — Rules and Scorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete deterministic scoring layer — role match gate (`scoring/rules.py`) and full scoring pipeline (`scoring/scorer.py`) — with full test coverage and zero I/O.

**Architecture:** `rules.py` contains one pure function (`matches_role`) used as the role gate; it has no imports beyond builtins. `scorer.py` contains all orchestration: role gate → positive keyword scan (title then description) → negative keyword scan (title then description) → location bonus → company bonus → breakdown assembly. All weights and thresholds come from `config`; neither module reads files, calls databases, or makes HTTP requests. Tests use a `cfg` fixture and a `_job()` factory; no DB, no fixtures from Phase 2.

**Tech Stack:** Python 3, `pytest`, stdlib only (`scoring.rules` import in `scorer.py`).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/scoring/rules.py` | Create | `matches_role(title, accepted_role_keywords) -> bool` — role gate, zero imports |
| `src/scoring/scorer.py` | Create | `score_job(job_dict, config) -> dict` — full pipeline, imports only `scoring.rules` |
| `src/scoring/__init__.py` | Modify | Re-export `score_job` and `matches_role` |
| `tests/test_scoring_rules.py` | Create | 7 tests for `matches_role` |
| `tests/test_scoring_scorer.py` | Create | 32 tests for `score_job` |

---

## Scoring Flow (Reference)

```
score_job(job_dict, config)
  │
  ├─ 1. Role match gate
  │     rules.matches_role(title, accepted_role_keywords) → bool
  │     If False: append {"label": "Role Mismatch", "points": role_mismatch_penalty}
  │
  ├─ 2. Positive keyword scan  (config["positive_keywords"]: dict[str, int])
  │     Pass 1 — scan title;        add matched keywords to seen_positive set
  │     Pass 2 — scan description;  skip any keyword already in seen_positive
  │     Each matched keyword → append {"label": kw, "points": weight}
  │                           + append kw to matched_keywords list
  │
  ├─ 3. Negative keyword scan  (config["negative_keywords"]: dict[str, int])
  │     Pass 1 — scan title;        add matched keywords to seen_negative set
  │     Pass 2 — scan description;  skip any keyword already in seen_negative
  │     Each matched keyword → append {"label": kw, "points": weight (negative)}
  │                           + append kw to matched_keywords list
  │
  ├─ 4. Location bonus
  │     If "remote" in location_normalized.lower() → append {"label": "Remote Bonus", "points": remote_location_bonus}
  │
  ├─ 5. Company bonus
  │     Exact case-insensitive match against company_tier_1 → Tier 1 bonus
  │     elif match against company_tier_2 → Tier 2 bonus
  │     Tier 1 wins if company appears in both tiers (SCORING.md §6)
  │
  └─ 6. Assemble result
        final_score = sum(c["points"] for c in components)
        passed_threshold = final_score >= notification_threshold
        return {"final_score", "passed_threshold", "score_breakdown"}
```

## score_breakdown Format

```python
{
    "role_match": bool,              # True if title matched any accepted role keyword
    "matched_keywords": list[str],   # original-case keyword strings, positive + negative, in match order
    "components": [                  # every contributing item; zero-value items excluded
        {"label": "PySpark",            "points": 10},
        {"label": "Databricks",         "points": 10},
        {"label": "Kafka",              "points": 8},
        {"label": "Remote Bonus",       "points": 5},
        {"label": "Tier 1 Company",     "points": 8},
        {"label": "Role Mismatch",      "points": -50},  # only when role_match is False
        {"label": "Presales",           "points": -15},  # only when matched
    ],
    "final_score": int,              # redundant with top-level final_score; stored for serialization
    "threshold_at_ingestion": int,   # snapshot of notification_threshold at scoring time
}
```

---

## Task 1: scoring/rules.py

**Files:**
- Create: `src/scoring/rules.py`
- Create: `tests/test_scoring_rules.py`

- [ ] **Step 1: Write the failing tests in `tests/test_scoring_rules.py`**

```python
"""Tests for src/scoring/rules.py — role match gate."""
import pytest

from src.scoring.rules import matches_role


def test_exact_match_returns_true():
    assert matches_role("Senior Data Engineer", ["Senior Data Engineer"]) is True


def test_partial_substring_match_returns_true():
    # Title contains the keyword as a substring
    assert matches_role("Senior Data Engineer - Platforms", ["Senior Data Engineer"]) is True


def test_match_is_case_insensitive():
    assert matches_role("SENIOR DATA ENGINEER", ["Senior Data Engineer"]) is True


def test_no_keyword_matches_returns_false():
    assert matches_role("Business Analyst", ["Senior Data Engineer", "Analytics Engineer"]) is False


def test_empty_title_returns_false():
    assert matches_role("", ["Senior Data Engineer"]) is False


def test_empty_keyword_list_returns_false():
    assert matches_role("Senior Data Engineer", []) is False


def test_second_keyword_in_list_matches():
    assert matches_role("Analytics Engineer", ["Senior Data Engineer", "Analytics Engineer"]) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/tanshu/Jobapplication
python -m pytest tests/test_scoring_rules.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.scoring.rules'`

- [ ] **Step 3: Write `src/scoring/rules.py`**

```python
def matches_role(title: str, accepted_role_keywords: list[str]) -> bool:
    """Return True if title contains any accepted role keyword (case-insensitive substring match)."""
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in accepted_role_keywords)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_scoring_rules.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/scoring/rules.py tests/test_scoring_rules.py
git commit -m "feat: add scoring/rules.py — matches_role gate with 7 tests"
```

---

## Task 2: scoring/scorer.py

**Files:**
- Create: `src/scoring/scorer.py`
- Create: `tests/test_scoring_scorer.py`

- [ ] **Step 1: Write the failing tests in `tests/test_scoring_scorer.py`**

```python
"""Tests for src/scoring/scorer.py — full scoring pipeline. Zero I/O, no DB."""
import pytest

from src.scoring.scorer import score_job


@pytest.fixture
def cfg():
    """Minimal but representative config dict for scoring tests."""
    return {
        "notification_threshold": 20,
        "accepted_role_keywords": ["Senior Data Engineer", "Analytics Engineer"],
        "positive_keywords": {
            "PySpark": 10,
            "Databricks": 10,
            "Kafka": 8,
            "Python": 4,
        },
        "negative_keywords": {
            "Presales": -15,
            "Support": -12,
        },
        "accepted_locations": ["Remote", "India Remote", "Gurugram", "Noida"],
        "remote_location_bonus": 5,
        "company_tier_1": ["Atlassian", "Adobe"],
        "company_tier_2": ["Tiger Analytics"],
        "company_tier_1_bonus": 8,
        "company_tier_2_bonus": 5,
        "role_mismatch_penalty": -50,
    }


def _job(**overrides):
    """Minimal valid job dict. Does NOT set score fields — those are outputs, not inputs."""
    base = {
        "title": "Senior Data Engineer",
        "company": "SomeCompany",
        "location_normalized": "Remote",
        "description": "",
    }
    base.update(overrides)
    return base


# --- Return structure ---

def test_result_has_required_top_level_keys(cfg):
    result = score_job(_job(), cfg)
    assert "final_score" in result
    assert "passed_threshold" in result
    assert "score_breakdown" in result


def test_breakdown_has_required_keys(cfg):
    result = score_job(_job(), cfg)
    bd = result["score_breakdown"]
    assert "role_match" in bd
    assert "matched_keywords" in bd
    assert "components" in bd
    assert "final_score" in bd
    assert "threshold_at_ingestion" in bd


# --- Role match gate ---

def test_role_match_true_for_matching_title(cfg):
    result = score_job(_job(title="Senior Data Engineer"), cfg)
    assert result["score_breakdown"]["role_match"] is True


def test_role_match_false_for_non_matching_title(cfg):
    result = score_job(_job(title="Business Analyst"), cfg)
    assert result["score_breakdown"]["role_match"] is False


def test_role_mismatch_penalty_in_components_when_no_match(cfg):
    result = score_job(_job(title="Business Analyst", location_normalized=None), cfg)
    labels = [c["label"] for c in result["score_breakdown"]["components"]]
    assert "Role Mismatch" in labels
    mismatch = next(c for c in result["score_breakdown"]["components"] if c["label"] == "Role Mismatch")
    assert mismatch["points"] == -50


def test_no_role_mismatch_penalty_when_role_matches(cfg):
    result = score_job(_job(title="Senior Data Engineer"), cfg)
    labels = [c["label"] for c in result["score_breakdown"]["components"]]
    assert "Role Mismatch" not in labels


# --- Positive keyword scoring ---

def test_positive_keyword_in_description_scored(cfg):
    result = score_job(_job(description="We use PySpark for processing.", location_normalized=None), cfg)
    pyspark = [c for c in result["score_breakdown"]["components"] if c["label"] == "PySpark"]
    assert len(pyspark) == 1
    assert pyspark[0]["points"] == 10


def test_positive_keyword_in_title_scored(cfg):
    # "Python" appears in the title; it should be scored from the title pass
    result = score_job(_job(title="Senior Data Engineer - Python", location_normalized=None, description=""), cfg)
    python_entries = [c for c in result["score_breakdown"]["components"] if c["label"] == "Python"]
    assert len(python_entries) == 1
    assert python_entries[0]["points"] == 4


def test_positive_keyword_dedup_title_and_description(cfg):
    # "PySpark" appears in both title and description — must be counted only once
    result = score_job(
        _job(title="Senior Data Engineer PySpark", description="PySpark and Databricks.", location_normalized=None),
        cfg,
    )
    pyspark_entries = [c for c in result["score_breakdown"]["components"] if c["label"] == "PySpark"]
    assert len(pyspark_entries) == 1


def test_positive_keyword_repeated_in_description_counted_once(cfg):
    # "PySpark" mentioned three times in description — still one component entry
    result = score_job(
        _job(description="PySpark PySpark PySpark is great.", location_normalized=None),
        cfg,
    )
    pyspark_entries = [c for c in result["score_breakdown"]["components"] if c["label"] == "PySpark"]
    assert len(pyspark_entries) == 1


# --- Negative keyword scoring ---

def test_negative_keyword_in_title_penalized(cfg):
    result = score_job(_job(title="Senior Data Engineer Support", location_normalized=None, description=""), cfg)
    support = [c for c in result["score_breakdown"]["components"] if c["label"] == "Support"]
    assert len(support) == 1
    assert support[0]["points"] == -12


def test_negative_keyword_in_description_penalized(cfg):
    result = score_job(_job(description="This is a Presales role.", location_normalized=None), cfg)
    presales = [c for c in result["score_breakdown"]["components"] if c["label"] == "Presales"]
    assert len(presales) == 1
    assert presales[0]["points"] == -15


def test_negative_keyword_dedup_title_and_description(cfg):
    # "Presales" in both title and description — counted once
    result = score_job(
        _job(title="Senior Data Engineer Presales", description="Presales engagement.", location_normalized=None),
        cfg,
    )
    presales_entries = [c for c in result["score_breakdown"]["components"] if c["label"] == "Presales"]
    assert len(presales_entries) == 1


def test_no_negative_component_when_no_keyword_matched(cfg):
    result = score_job(_job(title="Senior Data Engineer", description="Clean pipelines.", location_normalized=None), cfg)
    labels = [c["label"] for c in result["score_breakdown"]["components"]]
    assert "Presales" not in labels
    assert "Support" not in labels


# --- Location bonus ---

def test_remote_location_bonus_applied(cfg):
    result = score_job(_job(location_normalized="Remote"), cfg)
    remote = [c for c in result["score_breakdown"]["components"] if c["label"] == "Remote Bonus"]
    assert len(remote) == 1
    assert remote[0]["points"] == 5


def test_india_remote_location_bonus_applied(cfg):
    result = score_job(_job(location_normalized="India Remote"), cfg)
    remote = [c for c in result["score_breakdown"]["components"] if c["label"] == "Remote Bonus"]
    assert len(remote) == 1


def test_non_remote_accepted_location_no_bonus(cfg):
    result = score_job(_job(location_normalized="Gurugram"), cfg)
    remote = [c for c in result["score_breakdown"]["components"] if c["label"] == "Remote Bonus"]
    assert len(remote) == 0


def test_none_location_normalized_no_bonus(cfg):
    result = score_job(_job(location_normalized=None), cfg)
    remote = [c for c in result["score_breakdown"]["components"] if c["label"] == "Remote Bonus"]
    assert len(remote) == 0


# --- Company bonus ---

def test_tier1_company_bonus_applied(cfg):
    result = score_job(_job(company="Atlassian", location_normalized=None), cfg)
    tier1 = [c for c in result["score_breakdown"]["components"] if c["label"] == "Tier 1 Company"]
    assert len(tier1) == 1
    assert tier1[0]["points"] == 8


def test_tier2_company_bonus_applied(cfg):
    result = score_job(_job(company="Tiger Analytics", location_normalized=None), cfg)
    tier2 = [c for c in result["score_breakdown"]["components"] if c["label"] == "Tier 2 Company"]
    assert len(tier2) == 1
    assert tier2[0]["points"] == 5


def test_unknown_company_no_bonus(cfg):
    result = score_job(_job(company="RandomCorp", location_normalized=None), cfg)
    labels = [c["label"] for c in result["score_breakdown"]["components"]]
    assert "Tier 1 Company" not in labels
    assert "Tier 2 Company" not in labels


def test_tier1_wins_when_company_in_both_tiers(cfg):
    # Add the same company to both tiers; Tier 1 must win
    cfg["company_tier_1"] = ["OverlapCorp"]
    cfg["company_tier_2"] = ["OverlapCorp"]
    result = score_job(_job(company="OverlapCorp", location_normalized=None), cfg)
    tier1 = [c for c in result["score_breakdown"]["components"] if c["label"] == "Tier 1 Company"]
    tier2 = [c for c in result["score_breakdown"]["components"] if c["label"] == "Tier 2 Company"]
    assert len(tier1) == 1
    assert len(tier2) == 0


def test_company_match_is_case_insensitive(cfg):
    result = score_job(_job(company="atlassian", location_normalized=None), cfg)
    tier1 = [c for c in result["score_breakdown"]["components"] if c["label"] == "Tier 1 Company"]
    assert len(tier1) == 1


# --- Score computation and threshold ---

def test_known_full_example_score_41(cfg):
    # PySpark(10) + Databricks(10) + Kafka(8) + Remote(5) + Tier1(8) = 41
    result = score_job(
        {
            "title": "Senior Data Engineer",
            "company": "Atlassian",
            "location_normalized": "Remote",
            "description": "We use PySpark, Databricks, and Kafka for large-scale pipelines.",
        },
        cfg,
    )
    assert result["final_score"] == 41


def test_score_can_be_negative(cfg):
    # Role mismatch(-50) + Presales(-15) + Support(-12) = -77
    result = score_job(
        _job(title="Business Analyst Support", description="Presales work.", location_normalized=None, company="NoTier"),
        cfg,
    )
    assert result["final_score"] == -77
    assert result["passed_threshold"] is False


def test_passed_threshold_true_at_exact_threshold(cfg):
    # Set threshold to 10 and construct a job that scores exactly 10
    cfg["notification_threshold"] = 10
    result = score_job(
        _job(description="PySpark", location_normalized="Gurugram", company="NoTier"),
        cfg,
    )
    assert result["final_score"] == 10
    assert result["passed_threshold"] is True


def test_passed_threshold_false_below_threshold(cfg):
    cfg["notification_threshold"] = 30
    result = score_job(_job(description="", location_normalized=None, company="NoTier"), cfg)
    assert result["final_score"] < 30
    assert result["passed_threshold"] is False


# --- score_breakdown content ---

def test_breakdown_final_score_matches_returned_final_score(cfg):
    result = score_job(_job(), cfg)
    assert result["score_breakdown"]["final_score"] == result["final_score"]


def test_breakdown_threshold_at_ingestion_matches_config(cfg):
    cfg["notification_threshold"] = 35
    result = score_job(_job(), cfg)
    assert result["score_breakdown"]["threshold_at_ingestion"] == 35


def test_matched_keywords_contains_positive_and_negative_hits(cfg):
    result = score_job(
        _job(description="Uses PySpark and has Presales duties.", location_normalized=None),
        cfg,
    )
    mk = result["score_breakdown"]["matched_keywords"]
    assert "PySpark" in mk
    assert "Presales" in mk


def test_matched_keywords_excludes_unmatched_keywords(cfg):
    result = score_job(_job(description="No special keywords here.", location_normalized=None), cfg)
    mk = result["score_breakdown"]["matched_keywords"]
    assert "PySpark" not in mk
    assert "Databricks" not in mk
    assert "Presales" not in mk


# --- Edge cases ---

def test_none_description_does_not_crash(cfg):
    result = score_job(_job(description=None), cfg)
    assert isinstance(result["final_score"], int)


def test_empty_description_does_not_crash(cfg):
    result = score_job(_job(description=""), cfg)
    assert isinstance(result["final_score"], int)


def test_none_location_does_not_crash(cfg):
    result = score_job(_job(location_normalized=None), cfg)
    assert isinstance(result["final_score"], int)


def test_input_dict_not_mutated(cfg):
    job = _job()
    original_keys = set(job.keys())
    score_job(job, cfg)
    assert set(job.keys()) == original_keys
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_scoring_scorer.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.scoring.scorer'`

- [ ] **Step 3: Write `src/scoring/scorer.py`**

```python
import logging

from src.scoring.rules import matches_role

logger = logging.getLogger(__name__)


def score_job(job_dict: dict, config: dict) -> dict:
    """Score a single job dict. Pure function — no I/O, no side effects.

    Returns {"final_score": int, "passed_threshold": bool, "score_breakdown": dict}.
    Sets created_at / updated_at: never — caller (ingest.py) owns timestamps.
    Does not mutate job_dict.
    """
    title = job_dict.get("title") or ""
    company = job_dict.get("company") or ""
    location = job_dict.get("location_normalized") or ""
    description = job_dict.get("description") or ""

    positive_keywords: dict = config.get("positive_keywords", {})
    negative_keywords: dict = config.get("negative_keywords", {})
    accepted_role_keywords: list = config.get("accepted_role_keywords", [])
    notification_threshold: int = config.get("notification_threshold", 20)

    components: list[dict] = []
    matched_keywords: list[str] = []

    # Stage 1: Role match gate.
    # If title doesn't match any accepted role keyword, apply the mismatch penalty.
    role_match = matches_role(title, accepted_role_keywords)
    if not role_match:
        components.append({
            "label": "Role Mismatch",
            "points": config.get("role_mismatch_penalty", -50),
        })

    # Stage 2: Positive keyword scan — title first, then description.
    # Each keyword counted at most once across both passes (DECISIONS.md).
    seen_positive: set[str] = set()
    for text in (title, description):
        text_lower = text.lower()
        for kw, weight in positive_keywords.items():
            kw_lower = kw.lower()
            if kw_lower in seen_positive:
                continue
            if kw_lower in text_lower:
                components.append({"label": kw, "points": weight})
                matched_keywords.append(kw)
                seen_positive.add(kw_lower)

    # Stage 3: Negative keyword scan — title first, then description.
    # Same deduplication rule as positive scan.
    seen_negative: set[str] = set()
    for text in (title, description):
        text_lower = text.lower()
        for kw, weight in negative_keywords.items():
            kw_lower = kw.lower()
            if kw_lower in seen_negative:
                continue
            if kw_lower in text_lower:
                components.append({"label": kw, "points": weight})
                matched_keywords.append(kw)
                seen_negative.add(kw_lower)

    # Stage 4: Location bonus.
    # Only Remote and India Remote receive a bonus (SCORING.md §5).
    # Substring match on "remote" covers both "Remote" and "India Remote".
    if "remote" in location.lower():
        components.append({
            "label": "Remote Bonus",
            "points": config.get("remote_location_bonus", 5),
        })

    # Stage 5: Company bonus.
    # Case-insensitive exact match. Tier 1 wins if company appears in both tiers (SCORING.md §6).
    company_lower = company.lower()
    tier1: list = config.get("company_tier_1", [])
    tier2: list = config.get("company_tier_2", [])
    if any(c.lower() == company_lower for c in tier1):
        components.append({"label": "Tier 1 Company", "points": config.get("company_tier_1_bonus", 8)})
    elif any(c.lower() == company_lower for c in tier2):
        components.append({"label": "Tier 2 Company", "points": config.get("company_tier_2_bonus", 5)})

    # Stage 6: Sum and assemble.
    final_score = sum(c["points"] for c in components)

    return {
        "final_score": final_score,
        "passed_threshold": final_score >= notification_threshold,
        "score_breakdown": {
            "role_match": role_match,
            "matched_keywords": matched_keywords,
            "components": components,
            "final_score": final_score,
            "threshold_at_ingestion": notification_threshold,
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_scoring_scorer.py -v
```

Expected: 32 passed.

- [ ] **Step 5: Commit**

```bash
git add src/scoring/scorer.py tests/test_scoring_scorer.py
git commit -m "feat: add scoring/scorer.py — full pipeline, breakdown, matched_keywords, 32 tests"
```

---

## Task 3: scoring/__init__.py + full test run

**Files:**
- Modify: `src/scoring/__init__.py`

- [ ] **Step 1: Update `src/scoring/__init__.py`**

```python
from src.scoring.scorer import score_job
from src.scoring.rules import matches_role

__all__ = ["score_job", "matches_role"]
```

- [ ] **Step 2: Run the full scoring test suite**

```bash
python -m pytest tests/test_scoring_rules.py tests/test_scoring_scorer.py -v
```

Expected: 39 passed (7 rules + 32 scorer).

- [ ] **Step 3: Run the complete project test suite to verify no regressions**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass (Phase 2 DB tests + Phase 3 scoring tests).

- [ ] **Step 4: Commit**

```bash
git add src/scoring/__init__.py
git commit -m "feat: export score_job and matches_role from scoring package"
```

---

## Acceptance Criteria

All items must be true before Phase 3 is considered complete:

- [ ] `python -m pytest tests/test_scoring_rules.py tests/test_scoring_scorer.py -v` passes with zero failures.
- [ ] `matches_role` performs case-insensitive substring match (verified by test).
- [ ] `score_job` applies the role mismatch penalty only when `matches_role` returns False.
- [ ] Positive and negative keyword deduplication verified: keyword in both title and description produces exactly one component entry.
- [ ] Location bonus applied for "Remote" and "India Remote" locations only.
- [ ] Tier 1 company bonus wins over Tier 2 when company appears in both (verified by test).
- [ ] `score_breakdown.matched_keywords` contains matched keywords (positive + negative) in original case.
- [ ] `score_breakdown.final_score` equals the returned top-level `final_score`.
- [ ] `score_breakdown.threshold_at_ingestion` equals `config["notification_threshold"]` at call time.
- [ ] Known example: PySpark(10) + Databricks(10) + Kafka(8) + Remote(5) + Tier1(8) = 41.
- [ ] `None` description and `None` location_normalized do not raise exceptions.
- [ ] Input `job_dict` is not mutated.
- [ ] `scoring/scorer.py` imports only `src.scoring.rules` — zero I/O imports (`sqlite3`, `requests`, `db.*` all absent).
- [ ] `scoring/rules.py` imports nothing beyond Python builtins.
- [ ] No test touches `data/jobs.db` or makes any HTTP call.

---

## Self-Review Notes

**Spec coverage check:**

| Requirement | Covered by |
|---|---|
| Case-insensitive substring role match (SCORING.md §2) | `test_match_is_case_insensitive`, `test_partial_substring_match_returns_true` |
| Role mismatch penalty applied (SCORING.md §2) | `test_role_mismatch_penalty_in_components_when_no_match` |
| Positive keyword scan, each counted once (SCORING.md §3) | `test_positive_keyword_dedup_title_and_description`, `test_positive_keyword_repeated_in_description_counted_once` |
| Negative keyword scan, each counted once (SCORING.md §4) | `test_negative_keyword_dedup_title_and_description` |
| Title scanned before description (approved requirement) | `test_positive_keyword_dedup_title_and_description` — PySpark in title is caught in pass 1 |
| Remote location bonus only (SCORING.md §5) | `test_non_remote_accepted_location_no_bonus` |
| India Remote also earns bonus (SCORING.md §5) | `test_india_remote_location_bonus_applied` |
| Tier 1 wins over Tier 2 (SCORING.md §6) | `test_tier1_wins_when_company_in_both_tiers` |
| Case-insensitive company match (SCORING.md §6) | `test_company_match_is_case_insensitive` |
| Score is raw integer sum, can be negative (SCORING.md §8) | `test_score_can_be_negative` |
| passed_threshold True at exact threshold (SCORING.md §7) | `test_passed_threshold_true_at_exact_threshold` |
| matched_keywords in breakdown (approved addition) | `test_matched_keywords_contains_positive_and_negative_hits` |
| threshold_at_ingestion is a snapshot (DECISIONS.md) | `test_breakdown_threshold_at_ingestion_matches_config` |
| Zero I/O (ARCHITECTURE.md §4, MODULES.md) | No imports of sqlite3/requests/db.* in either scoring file |
| Input dict not mutated | `test_input_dict_not_mutated` |

**No placeholders found.**

**Type consistency:** `score_job` signature and return shape are consistent across all test calls. `matches_role` signature is consistent between `rules.py` definition and `scorer.py` call site.
