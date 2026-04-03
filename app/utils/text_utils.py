import re

STOPWORDS = {
    "a", "an", "the", "i", "me", "my", "mine", "you", "your", "yours",
    "he", "him", "his", "she", "her", "hers", "it", "its", "we", "us", "our", "ours",
    "they", "them", "their", "theirs",
    "is", "am", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "done",
    "have", "has", "had",
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "and", "or", "but", "if", "then", "so", "than",
    "of", "to", "in", "on", "at", "for", "with", "as", "by", "from", "about",
    "this", "that", "these", "those",
    "yes", "no", "not",
}

TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")


def normalize_query(query: str) -> str:
    return " ".join(query.strip().split())


def tokenize_query(query: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(query)]


def is_high_frequency_query(query: str) -> bool:
    tokens = tokenize_query(query)
    if not tokens:
        return False

    if len(tokens) == 1 and tokens[0] in STOPWORDS:
        return True

    if len(tokens) == 1 and len(tokens[0]) <= 2:
        return True

    return False