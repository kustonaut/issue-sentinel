"""LLM-powered issue classification for ambiguous issues."""

from __future__ import annotations

import json
import logging
from typing import Any

from issue_sentinel.classifier import ClassificationResult
from issue_sentinel.config import ClassificationConfig

logger = logging.getLogger(__name__)

# ── Prompt Template ─────────────────────────────────────────────────────

CLASSIFICATION_PROMPT = """You are a GitHub issue classifier. Classify the following issue into:

**Type** (pick one): bug, feature-request, question, documentation, enhancement, regression
**Area** (pick from list): {areas}
**Urgency** (0.0 to 1.0): How urgent is this issue?

Issue Title: {title}
Issue Body:
{body}

Respond in JSON format only:
{{
  "category": "bug|feature-request|question|documentation|enhancement|regression",
  "area": "area-name",
  "urgency": 0.5,
  "reasoning": "one-sentence explanation"
}}"""


class LLMClassifier:
    """Classifies issues using LLM APIs (OpenAI or Anthropic)."""

    def __init__(self, config: ClassificationConfig, area_names: list[str]) -> None:
        self.config = config
        self.area_names = area_names
        self._client: Any = None

    def classify(
        self,
        title: str,
        body: str = "",
    ) -> ClassificationResult | None:
        """Classify an issue using an LLM.

        Returns None if LLM call fails (caller should fallback to rule-based).
        """
        try:
            if self.config.provider == "openai":
                return self._classify_openai(title, body)
            elif self.config.provider == "anthropic":
                return self._classify_anthropic(title, body)
            else:
                logger.warning(f"Unknown LLM provider: {self.config.provider}")
                return None
        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
            return None

    def _build_prompt(self, title: str, body: str) -> str:
        """Build the classification prompt."""
        areas_str = ", ".join(self.area_names) if self.area_names else "general"
        return CLASSIFICATION_PROMPT.format(
            areas=areas_str,
            title=title,
            body=body[:2000],  # Truncate long bodies
        )

    def _parse_response(self, text: str) -> ClassificationResult | None:
        """Parse LLM JSON response into ClassificationResult."""
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_text = text.strip()
            if "```" in json_text:
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
                json_text = json_text.strip()

            data = json.loads(json_text)
            return ClassificationResult(
                category=data.get("category", "unknown"),
                area=data.get("area", "unassigned"),
                urgency=float(data.get("urgency", 0.5)),
                confidence=0.8,  # LLM results get baseline 0.8 confidence
                reasoning=data.get("reasoning", ""),
                method="llm",
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None

    def _classify_openai(self, title: str, body: str) -> ClassificationResult | None:
        """Classify using OpenAI API."""
        try:
            import openai
        except ImportError:
            logger.error("openai package not installed. Run: pip install issue-sentinel[llm]")
            return None

        if not self._client:
            self._client = openai.OpenAI(api_key=self.config.api_key or None)

        prompt = self._build_prompt(title, body)
        response = self._client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.temperature,
            max_tokens=200,
        )

        text = response.choices[0].message.content or ""
        return self._parse_response(text)

    def _classify_anthropic(self, title: str, body: str) -> ClassificationResult | None:
        """Classify using Anthropic API."""
        try:
            import anthropic
        except ImportError:
            logger.error("anthropic package not installed. Run: pip install issue-sentinel[llm]")
            return None

        if not self._client:
            self._client = anthropic.Anthropic(api_key=self.config.api_key or None)

        prompt = self._build_prompt(title, body)
        response = self._client.messages.create(
            model=self.config.model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else ""
        return self._parse_response(text)
