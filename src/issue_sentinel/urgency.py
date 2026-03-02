"""Urgency scoring for GitHub issues."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from issue_sentinel.config import UrgencyConfig


@dataclass
class UrgencyResult:
    """Result of urgency scoring."""

    score: float  # 0.0 (low) to 1.0 (critical)
    priority: str  # p0, p1, p2, p3
    signals: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.priority


# ── Urgency Signal Patterns ─────────────────────────────────────────────

_CRITICAL_SIGNALS = [
    (r"\bsecurity\s*(vuln|issue|bug|hole|breach)\b", 0.9, "security vulnerability"),
    (r"\bdata\s*loss\b", 0.9, "data loss"),
    (r"\bproduction\s*(down|outage|crash|issue)\b", 0.9, "production impact"),
    (r"\bCVE-\d{4}-\d+\b", 0.9, "CVE reference"),
    (r"\b(remote|arbitrary)\s*code\s*execution\b", 1.0, "RCE"),
]

_HIGH_SIGNALS = [
    (r"\bregression\b", 0.7, "regression"),
    (r"\bbreaking\s*change\b", 0.7, "breaking change"),
    (r"\bcrash(es|ed|ing)?\b", 0.6, "crash"),
    (r"\bblocking\b", 0.6, "blocking"),
    (r"\bblocker\b", 0.7, "blocker"),
    (r"\bcritical\b", 0.6, "marked critical"),
    (r"\burgent(ly)?\b", 0.5, "marked urgent"),
    (r"\bASAP\b", 0.5, "ASAP"),
    (r"\bP0\b", 0.8, "P0"),
    (r"\bP1\b", 0.6, "P1"),
]

_MEDIUM_SIGNALS = [
    (r"\bworkaround\b.*\b(ugly|hacky|bad|terrible)\b", 0.4, "bad workaround"),
    (r"\bno\s*workaround\b", 0.5, "no workaround"),
    (r"\bmultiple\s*(users?|people|customers?|teams?)\b", 0.4, "multiple affected"),
    (r"\bupstream\b", 0.3, "upstream dependency"),
    (r"\brelease\s*(block|deadline)\b", 0.5, "release deadline"),
]

_LOW_SIGNALS = [
    (r"\bnice\s*to\s*have\b", -0.2, "nice to have"),
    (r"\blow\s*priority\b", -0.3, "low priority"),
    (r"\bcosmetic\b", -0.2, "cosmetic"),
    (r"\btypo\b", -0.2, "typo"),
    (r"\bminor\b", -0.1, "minor"),
]


class UrgencyScorer:
    """Scores the urgency of a GitHub issue based on signal patterns."""

    def __init__(self, config: UrgencyConfig | None = None) -> None:
        self.config = config or UrgencyConfig()
        self._critical = [(re.compile(p, re.IGNORECASE), s, d) for p, s, d in _CRITICAL_SIGNALS]
        self._high = [(re.compile(p, re.IGNORECASE), s, d) for p, s, d in _HIGH_SIGNALS]
        self._medium = [(re.compile(p, re.IGNORECASE), s, d) for p, s, d in _MEDIUM_SIGNALS]
        self._low = [(re.compile(p, re.IGNORECASE), s, d) for p, s, d in _LOW_SIGNALS]

        # Compile custom high signals from config
        self._custom_high = [
            (re.compile(rf"\b{re.escape(s)}\b", re.IGNORECASE), 0.6, s)
            for s in self.config.high_signals
            if not any(s.lower() in p for p, _, _ in _CRITICAL_SIGNALS + _HIGH_SIGNALS)
        ]

    def score(self, title: str, body: str = "") -> UrgencyResult:
        """Score the urgency of an issue.

        Args:
            title: Issue title
            body: Issue body

        Returns:
            UrgencyResult with score (0-1), priority (p0-p3), and triggered signals
        """
        text = f"{title}\n{body}"
        total_score = 0.0
        signals: list[str] = []

        # Check all signal groups (highest severity first)
        for patterns in [self._critical, self._high, self._custom_high, self._medium, self._low]:
            for pattern, weight, description in patterns:
                if pattern.search(text):
                    total_score += weight
                    signals.append(f"{description} ({weight:+.1f})")

        # Clamp to [0, 1]
        total_score = max(0.0, min(1.0, total_score))

        # Map to priority
        priority = self._score_to_priority(total_score)

        return UrgencyResult(
            score=round(total_score, 2),
            priority=priority,
            signals=signals,
        )

    def _score_to_priority(self, score: float) -> str:
        """Map urgency score to priority label."""
        if score >= 0.8:
            return "p0"
        elif score >= 0.5:
            return "p1"
        elif score >= 0.2:
            return "p2"
        else:
            return "p3"
