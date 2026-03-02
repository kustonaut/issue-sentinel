"""Core issue classifier — rule-based and LLM-powered classification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from issue_sentinel.config import SentinelConfig


class IssueType(str, Enum):
    """Standard issue categories."""

    BUG = "bug"
    FEATURE = "feature-request"
    QUESTION = "question"
    DOCS = "documentation"
    ENHANCEMENT = "enhancement"
    REGRESSION = "regression"
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """Result of classifying a GitHub issue."""

    category: str = "unknown"
    area: str = "unassigned"
    urgency: float = 0.0
    sentiment: str = "neutral"
    confidence: float = 0.0
    suggested_labels: list[str] = field(default_factory=list)
    reasoning: str = ""
    method: str = "rule-based"  # rule-based | llm

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "category": self.category,
            "area": self.area,
            "urgency": self.urgency,
            "sentiment": self.sentiment,
            "confidence": self.confidence,
            "suggested_labels": self.suggested_labels,
            "reasoning": self.reasoning,
            "method": self.method,
        }


# ── Type Detection Patterns ─────────────────────────────────────────────

_BUG_PATTERNS = [
    r"\bbug\b",
    r"\berror\b",
    r"\bcrash(es|ed|ing)?\b",
    r"\bfail(s|ed|ing|ure)?\b",
    r"\bbroken\b",
    r"\bnot\s+work(ing|s)?\b",
    r"\bdoesn'?t\s+work\b",
    r"\bunexpected(ly)?\b",
    r"\bthrow(s|n|ing)?\b",
    r"\bexception\b",
    r"\bstack\s*trace\b",
    r"\breproduc(e|ible|tion)\b",
]

_FEATURE_PATTERNS = [
    r"\bfeature\s+request\b",
    r"\bplease\s+add\b",
    r"\bwould\s+be\s+(nice|great|helpful)\b",
    r"\bcan\s+you\s+add\b",
    r"\bpropos(al|e)\b",
    r"\benhance(ment)?\b",
    r"\bnew\s+api\b",
    r"\bsupport\s+for\b",
    r"\bability\s+to\b",
]

_QUESTION_PATTERNS = [
    r"\bhow\s+(do|can|to|does)\b",
    r"\bis\s+(it|there)\s+(possible|a\s+way)\b",
    r"\bquestion\b",
    r"\bhelp\s+(me|needed|wanted)\b",
    r"\bconfused\b",
    r"\bdocumentation\b",
    r"\bexample\b",
    r"\btutorial\b",
]

_REGRESSION_PATTERNS = [
    r"\bregression\b",
    r"\bused\s+to\s+work\b",
    r"\bworked\s+(before|previously|in\s+v?\d)\b",
    r"\bafter\s+(updat|upgrad|migrat)\w*\b",
    r"\bsince\s+(updat|upgrad|version)\w*\b",
    r"\bbreaking\s+change\b",
]


class IssueClassifier:
    """Classifies GitHub issues using configurable rule-based matching."""

    def __init__(self, config: SentinelConfig) -> None:
        self.config = config
        self._bug_re = [re.compile(p, re.IGNORECASE) for p in _BUG_PATTERNS]
        self._feature_re = [re.compile(p, re.IGNORECASE) for p in _FEATURE_PATTERNS]
        self._question_re = [re.compile(p, re.IGNORECASE) for p in _QUESTION_PATTERNS]
        self._regression_re = [re.compile(p, re.IGNORECASE) for p in _REGRESSION_PATTERNS]

    def classify(
        self,
        title: str,
        body: str = "",
        existing_labels: list[str] | None = None,
    ) -> ClassificationResult:
        """Classify an issue by type and product area.

        Args:
            title: Issue title
            body: Issue body/description
            existing_labels: Any labels already applied

        Returns:
            ClassificationResult with category, area, and suggested labels
        """
        text = f"{title}\n{body}"
        existing_labels = existing_labels or []

        # 1. Detect issue type
        category = self._detect_type(text)

        # 2. Match product area
        area, area_confidence = self._match_area(text)

        # 3. Build suggested labels
        labels = self._build_labels(category, area, existing_labels)

        # 4. Calculate overall confidence
        type_confidence = self._type_confidence(text, category)
        confidence = (type_confidence + area_confidence) / 2

        return ClassificationResult(
            category=category.value,
            area=area,
            confidence=round(confidence, 2),
            suggested_labels=labels,
            reasoning=self._build_reasoning(category, area, type_confidence, area_confidence),
            method="rule-based",
        )

    def _detect_type(self, text: str) -> IssueType:
        """Detect the issue type from text patterns."""
        scores = {
            IssueType.REGRESSION: self._pattern_score(text, self._regression_re),
            IssueType.BUG: self._pattern_score(text, self._bug_re),
            IssueType.FEATURE: self._pattern_score(text, self._feature_re),
            IssueType.QUESTION: self._pattern_score(text, self._question_re),
        }

        # Regression takes priority if it matches
        if scores[IssueType.REGRESSION] > 0:
            return IssueType.REGRESSION

        best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best_type] > 0:
            return best_type

        return IssueType.UNKNOWN

    def _match_area(self, text: str) -> tuple[str, float]:
        """Match text against configured product areas. Returns (area_name, confidence)."""
        if not self.config.areas:
            return "unassigned", 0.0

        best_area = "unassigned"
        best_score = 0.0

        for area_cfg in self.config.areas:
            score = area_cfg.matches(text)
            if score > best_score:
                best_score = score
                best_area = area_cfg.name

        return best_area, round(best_score, 2)

    def _pattern_score(self, text: str, patterns: list[re.Pattern]) -> float:  # type: ignore[type-arg]
        """Count what fraction of patterns match the text."""
        if not patterns:
            return 0.0
        hits = sum(1 for p in patterns if p.search(text))
        return hits / len(patterns)

    def _type_confidence(self, text: str, issue_type: IssueType) -> float:
        """Calculate confidence in the type classification."""
        pattern_map = {
            IssueType.BUG: self._bug_re,
            IssueType.FEATURE: self._feature_re,
            IssueType.QUESTION: self._question_re,
            IssueType.REGRESSION: self._regression_re,
        }
        patterns = pattern_map.get(issue_type, [])
        if not patterns:
            return 0.1  # Unknown type = low confidence
        score = self._pattern_score(text, patterns)
        return min(score * 3, 1.0)  # Scale up, cap at 1.0

    def _build_labels(
        self, category: IssueType, area: str, existing: list[str]
    ) -> list[str]:
        """Build suggested label list."""
        labels: list[str] = []
        prefix = self.config.labels.prefix

        # Category label
        cat_label = f"{prefix}{category.value}" if prefix else category.value
        if cat_label not in existing:
            labels.append(cat_label)

        # Area label
        if area != "unassigned":
            area_label = f"{prefix}{area}" if prefix else area
            if area_label not in existing:
                labels.append(area_label)

        return labels

    def _build_reasoning(
        self,
        category: IssueType,
        area: str,
        type_conf: float,
        area_conf: float,
    ) -> str:
        """Build human-readable reasoning string."""
        parts = [
            f"Type: {category.value} (confidence: {type_conf:.0%})",
            f"Area: {area} (confidence: {area_conf:.0%})",
        ]
        return " | ".join(parts)
