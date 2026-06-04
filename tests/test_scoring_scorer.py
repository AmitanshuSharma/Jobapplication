"""Tests for src/scoring/scorer.py — full scoring pipeline. Zero I/O, no DB."""
import pytest

from src.scoring.scorer import score_job


@pytest.fixture
def cfg():
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
    assert "matched_positive_keywords" in bd
    assert "matched_negative_keywords" in bd
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
    result = score_job(_job(title="Senior Data Engineer - Python", location_normalized=None, description=""), cfg)
    python_entries = [c for c in result["score_breakdown"]["components"] if c["label"] == "Python"]
    assert len(python_entries) == 1
    assert python_entries[0]["points"] == 4


def test_positive_keyword_dedup_title_and_description(cfg):
    result = score_job(
        _job(title="Senior Data Engineer PySpark", description="PySpark and Databricks.", location_normalized=None),
        cfg,
    )
    pyspark_entries = [c for c in result["score_breakdown"]["components"] if c["label"] == "PySpark"]
    assert len(pyspark_entries) == 1


def test_positive_keyword_repeated_in_description_counted_once(cfg):
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


def test_matched_positive_keywords_contains_positive_hits(cfg):
    result = score_job(
        _job(description="Uses PySpark and Databricks.", location_normalized=None),
        cfg,
    )
    mk = result["score_breakdown"]["matched_positive_keywords"]
    assert "PySpark" in mk
    assert "Databricks" in mk


def test_matched_negative_keywords_contains_negative_hits(cfg):
    result = score_job(
        _job(description="Presales work with Support duties.", location_normalized=None),
        cfg,
    )
    mk = result["score_breakdown"]["matched_negative_keywords"]
    assert "Presales" in mk
    assert "Support" in mk


def test_matched_positive_keywords_excludes_unmatched(cfg):
    result = score_job(_job(description="No special keywords.", location_normalized=None), cfg)
    mk = result["score_breakdown"]["matched_positive_keywords"]
    assert "PySpark" not in mk
    assert "Databricks" not in mk


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
    original = dict(job)
    score_job(job, cfg)
    assert job == original
