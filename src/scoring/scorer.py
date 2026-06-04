import logging

from src.scoring.rules import matches_role

logger = logging.getLogger(__name__)


def score_job(job_dict: dict, config: dict) -> dict:
    """Score a single job dict. Pure function — no I/O, no side effects.

    Returns {"final_score": int, "passed_threshold": bool, "score_breakdown": dict}.
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
    matched_positive_keywords: list[str] = []
    matched_negative_keywords: list[str] = []

    # Stage 1: Role match gate.
    role_match = matches_role(title, accepted_role_keywords)
    if not role_match:
        components.append({
            "label": "Role Mismatch",
            "points": config.get("role_mismatch_penalty", -50),
        })

    # Stage 2: Positive keyword scan — title first, then description.
    seen_positive: set[str] = set()
    for text in (title, description):
        text_lower = text.lower()
        for kw, weight in positive_keywords.items():
            kw_lower = kw.lower()
            if kw_lower in seen_positive:
                continue
            if kw_lower in text_lower:
                components.append({"label": kw, "points": weight})
                matched_positive_keywords.append(kw)
                seen_positive.add(kw_lower)

    # Stage 3: Negative keyword scan — title first, then description.
    seen_negative: set[str] = set()
    for text in (title, description):
        text_lower = text.lower()
        for kw, weight in negative_keywords.items():
            kw_lower = kw.lower()
            if kw_lower in seen_negative:
                continue
            if kw_lower in text_lower:
                components.append({"label": kw, "points": weight})
                matched_negative_keywords.append(kw)
                seen_negative.add(kw_lower)

    # Stage 4: Location bonus — derived from accepted_locations config, not hardcoded.
    remote_locations = [
        loc for loc in config.get("accepted_locations", []) if "remote" in loc.lower()
    ]
    if any(location.lower() == loc.lower() for loc in remote_locations):
        components.append({
            "label": "Remote Bonus",
            "points": config.get("remote_location_bonus", 5),
        })

    # Stage 5: Company bonus — Tier 1 wins if company appears in both tiers.
    company_lower = company.lower()
    tier1: list = config.get("company_tier_1", [])
    tier2: list = config.get("company_tier_2", [])
    if any(c.lower() == company_lower for c in tier1):
        components.append({"label": "Tier 1 Company", "points": config.get("company_tier_1_bonus", 8)})
    elif any(c.lower() == company_lower for c in tier2):
        components.append({"label": "Tier 2 Company", "points": config.get("company_tier_2_bonus", 5)})

    # Assemble result.
    final_score = sum(c["points"] for c in components)

    return {
        "final_score": final_score,
        "passed_threshold": final_score >= notification_threshold,
        "score_breakdown": {
            "role_match": role_match,
            "matched_positive_keywords": matched_positive_keywords,
            "matched_negative_keywords": matched_negative_keywords,
            "components": components,
            "final_score": final_score,
            "threshold_at_ingestion": notification_threshold,
        },
    }
