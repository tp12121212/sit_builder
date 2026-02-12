from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class CandidateItem:
    candidate_type: str
    element_type_hint: str
    value: str
    pattern_template: str | None
    frequency: int
    confidence: float
    score: float
    evidence: list[dict]
    metadata: dict


REGEX_PATTERNS: list[tuple[str, str, float]] = [
    ("EMAIL", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", 0.9),
    ("CREDIT_CARD", r"\b(?:\d[ -]*?){13,19}\b", 0.8),
    ("SSN", r"\b\d{3}-\d{2}-\d{4}\b", 0.95),
    ("IP_ADDRESS", r"\b(?:\d{1,3}\.){3}\d{1,3}\b", 0.7),
]

WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
STOPWORDS = {
    "the",
    "and",
    "for",
    "that",
    "with",
    "this",
    "from",
    "your",
    "have",
    "will",
    "into",
    "were",
    "which",
    "there",
    "their",
    "about",
    "document",
}


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    length = len(value)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def _context_snippet(text: str, start: int, end: int, window: int = 50) -> str:
    s = max(0, start - window)
    e = min(len(text), end + window)
    return text[s:e]


def discover_candidates(text: str) -> list[CandidateItem]:
    candidates: list[CandidateItem] = []

    for label, pattern, confidence in REGEX_PATTERNS:
        matches = list(re.finditer(pattern, text))
        if not matches:
            continue

        value_counts = Counter(match.group(0) for match in matches)
        for value, freq in value_counts.items():
            first = next(match for match in matches if match.group(0) == value)
            entropy = shannon_entropy(value)
            score = min(100.0, (freq * 8) + (confidence * 40) + (entropy * 5))
            candidates.append(
                CandidateItem(
                    candidate_type="PATTERN",
                    element_type_hint="REGEX",
                    value=value,
                    pattern_template=pattern,
                    frequency=freq,
                    confidence=confidence,
                    score=round(score, 2),
                    evidence=[
                        {
                            "context": _context_snippet(text, first.start(), first.end()),
                            "position": first.start(),
                            "confidence": confidence,
                        }
                    ],
                    metadata={"label": label, "entropy": round(entropy, 3)},
                )
            )

    tokens = [token.lower() for token in WORD_RE.findall(text)]
    token_counts = Counter(token for token in tokens if token not in STOPWORDS)
    for token, freq in token_counts.most_common(40):
        if freq < 2:
            continue

        idx = text.lower().find(token)
        score = min(100.0, (freq * 10) + (shannon_entropy(token) * 8) + 15)
        candidates.append(
            CandidateItem(
                candidate_type="KEYWORD",
                element_type_hint="KEYWORD_LIST",
                value=token,
                pattern_template=None,
                frequency=freq,
                confidence=0.65,
                score=round(score, 2),
                evidence=[{"context": _context_snippet(text, idx, idx + len(token)), "position": idx, "confidence": 0.65}],
                metadata={"source": "frequency"},
            )
        )

    try:
        import spacy  # type: ignore

        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text)
        ner_counts: Counter[str] = Counter(ent.text.strip() for ent in doc.ents if len(ent.text.strip()) > 2)
        for value, freq in ner_counts.most_common(20):
            idx = text.find(value)
            candidates.append(
                CandidateItem(
                    candidate_type="ENTITY",
                    element_type_hint="DICTIONARY",
                    value=value,
                    pattern_template=None,
                    frequency=freq,
                    confidence=0.75,
                    score=min(100.0, round(freq * 12 + 35, 2)),
                    evidence=[{"context": _context_snippet(text, idx, idx + len(value)), "position": idx, "confidence": 0.75}],
                    metadata={"source": "spacy"},
                )
            )
    except Exception:
        pass

    dedup: dict[tuple[str, str], CandidateItem] = {}
    for item in candidates:
        key = (item.candidate_type, item.value.lower())
        current = dedup.get(key)
        if current is None or item.score > current.score:
            dedup[key] = item

    return sorted(dedup.values(), key=lambda item: item.score, reverse=True)
