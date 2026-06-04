def matches_role(title: str, accepted_role_keywords: list[str]) -> bool:
    """Return True if title contains any accepted role keyword (case-insensitive substring match)."""
    title_lower = title.lower()
    return any(kw.lower() in title_lower for kw in accepted_role_keywords)
