"""Configuration models for Issue Sentinel."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class AreaConfig:
    """Configuration for a product/feature area."""

    name: str
    keywords: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    description: str = ""

    def matches(self, text: str) -> float:
        """Return match score (0-1) for the given text against this area's keywords."""
        text_lower = text.lower()
        if not self.keywords:
            return 0.0
        hits = sum(1 for kw in self.keywords if kw.lower() in text_lower)
        return min(hits / max(len(self.keywords) * 0.3, 1), 1.0)


@dataclass
class UrgencyConfig:
    """Configuration for urgency scoring."""

    high_signals: list[str] = field(
        default_factory=lambda: [
            "regression",
            "crash",
            "data loss",
            "security",
            "breaking change",
            "critical",
            "blocker",
            "production down",
        ]
    )
    escalation_threshold: float = 0.8


@dataclass
class ClassificationConfig:
    """Configuration for the classification engine."""

    provider: str = "rule-based"  # rule-based | openai | anthropic
    model: str = "gpt-4o-mini"
    fallback: str = "rule-based"
    temperature: float = 0.1
    api_key: str = ""


@dataclass
class LabelConfig:
    """Configuration for label application."""

    apply: bool = True
    prefix: str = ""
    include_urgency: bool = True
    include_sentiment: bool = False


@dataclass
class SentinelConfig:
    """Top-level configuration for Issue Sentinel."""

    areas: list[AreaConfig] = field(default_factory=list)
    urgency: UrgencyConfig = field(default_factory=UrgencyConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    labels: LabelConfig = field(default_factory=LabelConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> SentinelConfig:
        """Load configuration from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SentinelConfig:
        """Create configuration from a dictionary."""
        areas = [AreaConfig(**a) for a in data.get("areas", [])]
        urgency = UrgencyConfig(**data.get("urgency", {}))
        classification = ClassificationConfig(**data.get("classification", {}))
        labels = LabelConfig(**data.get("labels", {}))
        return cls(
            areas=areas,
            urgency=urgency,
            classification=classification,
            labels=labels,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a dictionary."""
        return dataclasses.asdict(self)
