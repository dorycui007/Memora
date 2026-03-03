"""Text utilities for entity extraction from natural language queries."""

from __future__ import annotations

import re

# Common English words that appear capitalized at sentence starts but aren't entities.
_SKIP_WORDS = {
    "What", "How", "Who", "Where", "When", "Why", "Which",
    "Is", "Are", "Was", "Were", "Do", "Does", "Did", "Can",
    "Could", "Should", "Would", "Will", "The", "A", "An",
    "My", "His", "Her", "Their", "Our", "Its", "That", "This",
    "Tell", "Show", "Give", "Get", "Has", "Have", "Had",
}


def extract_entity_candidates(query: str) -> list[str]:
    """Extract likely proper-noun entity names from a natural language query.

    Splits on whitespace, strips punctuation and possessives, then keeps
    capitalized words that aren't common English stop words.
    """
    candidates: list[str] = []
    for word in query.split():
        clean = word.rstrip(".,;:!?'\"")
        if clean.endswith("'s") or clean.endswith("\u2019s"):
            clean = clean[:-2]
        if clean and clean[0].isupper() and clean not in _SKIP_WORDS and len(clean) > 1:
            candidates.append(clean)
    return candidates


# Words stripped when extracting the question focus.
_QUESTION_STOP = {
    "what", "how", "who", "where", "when", "why", "which",
    "is", "are", "was", "were", "do", "does", "did", "can",
    "could", "should", "would", "will", "the", "a", "an",
    "of", "in", "on", "for", "to", "with", "about", "from",
    "my", "his", "her", "their", "our", "its", "that", "this",
    "tell", "show", "give", "get", "has", "have", "had",
    "me", "i", "you", "we", "they", "he", "she", "it",
}


def extract_question_focus(query: str) -> str | None:
    """Extract the attribute/relationship focus from a question.

    Examples:
        "what is the status of Samuel's investigation?" → "investigation status"
        "what commitments does Alice have?" → "commitments"
        "how is the budget progressing?" → "budget progressing"

    Returns None if no meaningful focus can be extracted.
    """
    # Strip question marks and normalize
    text = query.rstrip("?!.").strip().lower()
    # Remove possessives
    text = re.sub(r"['']s\b", "", text)
    # Remove entity candidates (capitalized words) from original to isolate focus
    entity_names = {c.lower() for c in extract_entity_candidates(query)}
    words = [w for w in text.split() if w not in _QUESTION_STOP and w not in entity_names]
    if not words:
        return None
    return " ".join(words)
