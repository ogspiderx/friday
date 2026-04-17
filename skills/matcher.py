"""
skills/matcher.py — Match user queries to the best available skill.

Uses keyword/trigger matching with optional LLM-assisted semantic matching.
Skills always take priority over shell execution.
"""

from skills.loader import Skill, load_skills


def match_skill(user_query: str, skills: list[Skill] | None = None) -> Skill | None:
    """
    Find the best matching skill for a user query.
    
    Matching strategy (in order):
        1. Exact trigger match — query contains a trigger keyword
        2. Name match — query mentions the skill's name
        3. Description overlap — word overlap with skill description
    
    Args:
        user_query: The user's input text.
        skills: Optional pre-loaded skill list. Loads fresh if None.
    
    Returns:
        Best matching Skill, or None if no match.
    """
    if skills is None:
        skills = load_skills()

    if not skills:
        return None

    query_lower = user_query.lower()
    query_words = set(query_lower.split())

    best_match: Skill | None = None
    best_score: float = 0.0

    for skill in skills:
        score = 0.0

        # 1. Trigger match (highest weight)
        for trigger in skill.triggers:
            if trigger in query_lower:
                score += 3.0
                # Bonus for exact word match
                if trigger in query_words:
                    score += 1.0

        # 2. Name match
        if skill.name.lower() in query_lower:
            score += 2.0

        # 3. Description word overlap
        if skill.description:
            desc_words = set(skill.description.lower().split())
            overlap = query_words & desc_words
            # Filter out common stop words
            stop_words = {"a", "an", "the", "is", "are", "to", "for", "of", "in", "on", "and", "or", "it", "this", "that"}
            meaningful_overlap = overlap - stop_words
            score += len(meaningful_overlap) * 0.5

        # 4. Hybrid Ranking (Metrics Boost)
        # Skills that are frequently used and highly successful get a multiplier
        if score > 0:
            success_multiplier = 1.0 + (skill.success_rate * 0.5) # Up to 50% boost for 100% success
            usage_boost = min(skill.usage_count * 0.05, 1.0)      # Up to 1.0 flat boost for 20+ uses
            score = (score * success_multiplier) + usage_boost

        if score > best_score:
            best_score = score
            best_match = skill

    # Require minimum threshold to avoid false matches
    if best_score < 1.0:
        return None

    return best_match
