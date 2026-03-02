"""IssueSentinel — the main facade that ties everything together."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from issue_sentinel.classifier import IssueClassifier, ClassificationResult
from issue_sentinel.config import SentinelConfig
from issue_sentinel.llm_classifier import LLMClassifier
from issue_sentinel.sentiment import SentimentAnalyzer
from issue_sentinel.urgency import UrgencyScorer
from issue_sentinel.github_client import GitHubClient, GitHubIssue

logger = logging.getLogger(__name__)


class IssueSentinel:
    """Main entry point for Issue Sentinel.

    Combines rule-based classification, LLM classification,
    sentiment analysis, and urgency scoring into a single triage pipeline.
    """

    def __init__(self, config: SentinelConfig) -> None:
        self.config = config
        self.rule_classifier = IssueClassifier(config)
        self.sentiment_analyzer = SentimentAnalyzer()
        self.urgency_scorer = UrgencyScorer(config.urgency)
        self.llm_classifier: Optional[LLMClassifier] = None

        # Initialize LLM classifier if configured
        if config.classification.provider not in ("rule-based", ""):
            area_names = [a.name for a in config.areas]
            self.llm_classifier = LLMClassifier(config.classification, area_names)

    @classmethod
    def from_config(cls, path: str | Path) -> IssueSentinel:
        """Create IssueSentinel from a YAML config file."""
        config = SentinelConfig.from_yaml(path)
        return cls(config)

    def classify(
        self,
        title: str,
        body: str = "",
        existing_labels: Optional[list[str]] = None,
    ) -> ClassificationResult:
        """Classify a single issue through the full triage pipeline.

        Pipeline:
        1. Rule-based classification (fast, zero-cost)
        2. If low confidence + LLM configured → LLM classification
        3. Sentiment analysis
        4. Urgency scoring
        5. Merge results

        Args:
            title: Issue title
            body: Issue body/description
            existing_labels: Labels already on the issue

        Returns:
            Unified ClassificationResult
        """
        existing_labels = existing_labels or []

        # Step 1: Rule-based classification
        result = self.rule_classifier.classify(title, body, existing_labels)

        # Step 2: LLM fallback for low-confidence or unknown results
        if (
            self.llm_classifier
            and (result.confidence < 0.5 or result.category == "unknown")
        ):
            llm_result = self.llm_classifier.classify(title, body)
            if llm_result:
                # Prefer LLM result but keep rule-based urgency signals
                result = llm_result

        # Step 3: Sentiment analysis
        sentiment_result = self.sentiment_analyzer.analyze(title, body)
        result.sentiment = sentiment_result.label

        # Step 4: Urgency scoring
        urgency_result = self.urgency_scorer.score(title, body)
        result.urgency = urgency_result.score

        # Step 5: Update suggested labels
        if self.config.labels.include_urgency and urgency_result.priority != "p3":
            if urgency_result.priority not in result.suggested_labels:
                result.suggested_labels.append(urgency_result.priority)

        if self.config.labels.include_sentiment and sentiment_result.label != "neutral":
            sentiment_label = f"sentiment:{sentiment_result.label}"
            if sentiment_label not in result.suggested_labels:
                result.suggested_labels.append(sentiment_label)

        return result

    def triage_issue(
        self,
        github_client: GitHubClient,
        issue: GitHubIssue,
        apply_labels: bool = True,
        post_comment: bool = False,
        dry_run: bool = False,
    ) -> ClassificationResult:
        """Triage a GitHub issue: classify + optionally apply labels and comment.

        Args:
            github_client: Authenticated GitHub client
            issue: The issue to triage
            apply_labels: Whether to apply suggested labels
            post_comment: Whether to post a triage comment
            dry_run: If True, classify but don't modify the issue

        Returns:
            ClassificationResult
        """
        result = self.classify(issue.title, issue.body, issue.labels)

        if dry_run:
            logger.info(
                f"[DRY RUN] Issue #{issue.number}: {result.category} | "
                f"{result.area} | urgency={result.urgency:.2f} | {result.sentiment}"
            )
            return result

        # Apply labels
        if apply_labels and result.suggested_labels:
            new_labels = [l for l in result.suggested_labels if l not in issue.labels]
            if new_labels:
                try:
                    github_client.add_labels(issue.number, new_labels)
                except Exception as e:
                    logger.warning(f"Failed to add labels to #{issue.number}: {e}")

        # Post triage comment
        if post_comment:
            comment = self._build_triage_comment(result)
            try:
                github_client.add_comment(issue.number, comment)
            except Exception as e:
                logger.warning(f"Failed to comment on #{issue.number}: {e}")

        return result

    def triage_batch(
        self,
        github_client: GitHubClient,
        issues: list[GitHubIssue],
        apply_labels: bool = True,
        dry_run: bool = False,
    ) -> list[tuple[GitHubIssue, ClassificationResult]]:
        """Triage multiple issues.

        Returns:
            List of (issue, classification_result) tuples
        """
        results = []
        for issue in issues:
            result = self.triage_issue(
                github_client, issue, apply_labels=apply_labels, dry_run=dry_run
            )
            results.append((issue, result))
        return results

    def log_decision(
        self,
        issue_number: int,
        result: ClassificationResult,
        log_path: str | Path = "triage_log.jsonl",
    ) -> None:
        """Append a classification decision to a JSONL log file."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "issue_number": issue_number,
            **result.to_dict(),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _build_triage_comment(self, result: ClassificationResult) -> str:
        """Build a Markdown triage comment."""
        urgency_emoji = {"p0": "🔴", "p1": "🟠", "p2": "🟡", "p3": "🟢"}.get(
            result.suggested_labels[-1] if result.suggested_labels else "p3", "⚪"
        )

        lines = [
            "### 🛡️ Issue Sentinel — Auto Triage",
            "",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| **Type** | `{result.category}` |",
            f"| **Area** | `{result.area}` |",
            f"| **Urgency** | {urgency_emoji} {result.urgency:.0%} |",
            f"| **Sentiment** | {result.sentiment} |",
            f"| **Confidence** | {result.confidence:.0%} |",
            f"| **Method** | {result.method} |",
            "",
            f"*{result.reasoning}*",
            "",
            "---",
            "*Classified by [Issue Sentinel](https://github.com/kustonaut/issue-sentinel)*",
        ]
        return "\n".join(lines)
