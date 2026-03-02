"""Sentiment analysis for GitHub issues."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Sentiment(str, Enum):
    """Issue reporter sentiment levels."""

    FRUSTRATED = "frustrated"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    CONSTRUCTIVE = "constructive"


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""

    sentiment: Sentiment
    score: float  # -1.0 (very frustrated) to 1.0 (very positive)
    signals: list[str]  # which patterns triggered

    @property
    def label(self) -> str:
        return self.sentiment.value


# ── Sentiment Signal Patterns ───────────────────────────────────────────

_FRUSTRATED_SIGNALS = [
    (r"\bfrustra(ted|ting|tion)\b", -0.8),
    (r"\bwaste\s+of\s+time\b", -0.9),
    (r"\bunacceptable\b", -0.7),
    (r"\brigorous\s+bug\b", -0.6),
    (r"\bterrible\b", -0.9),
    (r"\bhorrible\b", -0.9),
    (r"\bawful\b", -0.8),
    (r"\babsurd\b", -0.7),
    (r"\bridiculous\b", -0.7),
    (r"\bdays?\s+debugging\b", -0.6),
    (r"!!+", -0.4),
    (r"\bFIX\s+THIS\b", -0.7),
    (r"\bplease\s+fix\s+(this\s+)?ASAP\b", -0.5),
    (r"\bstill\s+(not\s+)?(fixed|working|resolved)\b", -0.6),
    (r"\bmonths?\s+ago\b.*\b(still|yet)\b", -0.5),
]

_NEGATIVE_SIGNALS = [
    (r"\bunfortunately\b", -0.3),
    (r"\bdisappoint(ed|ing)?\b", -0.4),
    (r"\bannoy(ed|ing)?\b", -0.3),
    (r"\bconfus(ed|ing)\b", -0.2),
    (r"\bmisleading\b", -0.3),
    (r"\bpoorly\b", -0.3),
    (r"\block(ed|ing)?\s+(us|me|our)\b", -0.4),
    (r"\bblock(er|ing)\b", -0.4),
]

_POSITIVE_SIGNALS = [
    (r"\bthank(s| you)\b", 0.3),
    (r"\bgreat\s+(work|job|library|tool)\b", 0.5),
    (r"\blove\s+(this|the|it)\b", 0.5),
    (r"\bawesome\b", 0.4),
    (r"\bexcellent\b", 0.4),
    (r"\bamazing\b", 0.4),
    (r"\bhelpful\b", 0.3),
    (r"\bimpressive\b", 0.4),
]

_CONSTRUCTIVE_SIGNALS = [
    (r"\bsuggestion\b", 0.2),
    (r"\bproposal\b", 0.2),
    (r"\bwould\s+be\s+(nice|great|helpful)\b", 0.2),
    (r"\bhere'?s?\s+(a\s+)?(workaround|fix|patch)\b", 0.3),
    (r"\bpull\s+request\b", 0.3),
    (r"\bPR\s*#?\d+\b", 0.3),
    (r"\bhappy\s+to\s+(help|contribute)\b", 0.4),
    (r"\bminimal\s+repro\b", 0.2),
    (r"\breproduction\s+(repo|step|case)\b", 0.2),
]


class SentimentAnalyzer:
    """Analyzes sentiment of GitHub issue text."""

    def __init__(self) -> None:
        self._frustrated = [(re.compile(p, re.IGNORECASE), s) for p, s in _FRUSTRATED_SIGNALS]
        self._negative = [(re.compile(p, re.IGNORECASE), s) for p, s in _NEGATIVE_SIGNALS]
        self._positive = [(re.compile(p, re.IGNORECASE), s) for p, s in _POSITIVE_SIGNALS]
        self._constructive = [(re.compile(p, re.IGNORECASE), s) for p, s in _CONSTRUCTIVE_SIGNALS]

    def analyze(self, title: str, body: str = "") -> SentimentResult:
        """Analyze sentiment of issue text.

        Args:
            title: Issue title
            body: Issue body

        Returns:
            SentimentResult with sentiment label, score, and triggered signals
        """
        text = f"{title}\n{body}"
        score = 0.0
        signals: list[str] = []

        # Check all signal groups
        for patterns in [self._frustrated, self._negative, self._positive, self._constructive]:
            for pattern, weight in patterns:
                if pattern.search(text):
                    score += weight
                    signals.append(f"{pattern.pattern} ({weight:+.1f})")

        # Clamp to [-1, 1]
        score = max(-1.0, min(1.0, score))

        # Map score to sentiment
        sentiment = self._score_to_sentiment(score, signals)

        return SentimentResult(
            sentiment=sentiment,
            score=round(score, 2),
            signals=signals,
        )

    def _score_to_sentiment(self, score: float, signals: list[str]) -> Sentiment:
        """Map a numeric score to a sentiment category."""
        if score <= -0.5:
            return Sentiment.FRUSTRATED
        elif score <= -0.1:
            return Sentiment.NEGATIVE
        elif score >= 0.3:
            # Check if it's constructive (has PR, workaround, suggestion signals)
            constructive_markers = [
                "suggestion", "proposal", "workaround",
                "fix", "patch", "PR", "pull",
            ]
            if any(m.lower() in " ".join(signals).lower() for m in constructive_markers):
                return Sentiment.CONSTRUCTIVE
            return Sentiment.POSITIVE
        elif score >= 0.1:
            return Sentiment.CONSTRUCTIVE if signals else Sentiment.NEUTRAL
        else:
            return Sentiment.NEUTRAL
