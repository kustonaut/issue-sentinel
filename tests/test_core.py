"""Tests for Issue Sentinel core components."""

import json

import pytest

from issue_sentinel.classifier import ClassificationResult, IssueClassifier
from issue_sentinel.config import (
    AreaConfig,
    LabelConfig,
    SentinelConfig,
    UrgencyConfig,
)
from issue_sentinel.sentiment import Sentiment, SentimentAnalyzer
from issue_sentinel.sentinel import IssueSentinel
from issue_sentinel.urgency import UrgencyScorer

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def config() -> SentinelConfig:
    """Standard test configuration."""
    return SentinelConfig(
        areas=[
            AreaConfig(
                name="backend",
                keywords=["api", "server", "database", "auth", "endpoint"],
            ),
            AreaConfig(
                name="frontend",
                keywords=["ui", "button", "css", "layout", "react"],
            ),
            AreaConfig(
                name="docs",
                keywords=["documentation", "readme", "tutorial", "example"],
            ),
        ],
        urgency=UrgencyConfig(
            high_signals=["regression", "crash", "data loss", "security"],
            escalation_threshold=0.8,
        ),
    )


@pytest.fixture
def sentinel(config: SentinelConfig) -> IssueSentinel:
    return IssueSentinel(config)


@pytest.fixture
def classifier(config: SentinelConfig) -> IssueClassifier:
    return IssueClassifier(config)


@pytest.fixture
def sentiment_analyzer() -> SentimentAnalyzer:
    return SentimentAnalyzer()


@pytest.fixture
def urgency_scorer() -> UrgencyScorer:
    return UrgencyScorer()


# ── Classifier Tests ────────────────────────────────────────────────────


class TestIssueClassifier:
    def test_detects_bug(self, classifier: IssueClassifier):
        result = classifier.classify(
            title="API returns 500 on login endpoint",
            body="When I call the /auth/login endpoint, it crashes the server.",
        )
        assert result.category == "bug"
        assert result.area == "backend"

    def test_detects_feature_request(self, classifier: IssueClassifier):
        result = classifier.classify(
            title="Please add support for dark mode in the UI",
            body="It would be great to have a dark theme for the dashboard.",
        )
        assert result.category == "feature-request"

    def test_detects_question(self, classifier: IssueClassifier):
        result = classifier.classify(
            title="How do I configure the database connection?",
            body="I'm confused about how to use the server API.",
        )
        assert result.category == "question"
        assert result.area == "backend"

    def test_detects_regression(self, classifier: IssueClassifier):
        result = classifier.classify(
            title="API endpoint used to work in v1.4 but broken after upgrade",
            body="This was working before. After updating to v1.5, regression.",
        )
        assert result.category == "regression"

    def test_area_matching_backend(self, classifier: IssueClassifier):
        result = classifier.classify(
            title="Database auth endpoint fails",
            body="Server API returns invalid response",
        )
        assert result.area == "backend"

    def test_area_matching_frontend(self, classifier: IssueClassifier):
        result = classifier.classify(
            title="React button component crashes on click",
            body="UI layout breaks when button is pressed",
        )
        assert result.area == "frontend"

    def test_unknown_area(self, classifier: IssueClassifier):
        result = classifier.classify(
            title="Generic bug report",
            body="Something doesn't work",
        )
        # Should still detect as bug even without clear area
        assert result.category == "bug"

    def test_labels_not_duplicated(self, classifier: IssueClassifier):
        result = classifier.classify(
            title="Server bug",
            body="crash",
            existing_labels=["bug"],
        )
        assert "bug" not in result.suggested_labels

    def test_empty_title(self, classifier: IssueClassifier):
        """Edge case: empty title should not crash."""
        result = classifier.classify(title="", body="")
        assert result is not None
        assert isinstance(result.category, str)

    def test_very_long_body(self, classifier: IssueClassifier):
        """Edge case: very long body should still classify."""
        long_body = "This is a bug report. " * 500
        result = classifier.classify(title="Bug report", body=long_body)
        assert result.category == "bug"

    def test_classification_result_to_dict(self, classifier: IssueClassifier):
        """ClassificationResult.to_dict() returns valid dict."""
        result = classifier.classify(title="Bug in server API", body="crash")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "category" in d
        assert "area" in d
        assert "confidence" in d
        assert "urgency" in d
        assert "sentiment" in d

    def test_enhancement_detection(self, classifier: IssueClassifier):
        """Enhancement keywords trigger enhancement type."""
        result = classifier.classify(
            title="Improvement: better error messages for the API",
            body="Enhance the developer experience by improving error output.",
        )
        assert result.category in ("enhancement", "feature-request")

    def test_docs_detection(self, classifier: IssueClassifier):
        """Documentation-related issues match question patterns."""
        result = classifier.classify(
            title="Documentation is outdated for the auth endpoint",
            body="The docs say to use method X but it was removed.",
        )
        # "documentation" is classified under question patterns in the rule-based engine
        assert result.category in ("question", "bug")

    def test_multiple_area_keywords_picks_strongest(self, classifier: IssueClassifier):
        """When multiple areas match, the strongest match wins."""
        result = classifier.classify(
            title="React button layout css rendering issue",
            body="The button css layout is broken in the ui component.",
        )
        assert result.area == "frontend"

    def test_confidence_range(self, classifier: IssueClassifier):
        """Confidence should always be between 0 and 1."""
        result = classifier.classify(title="Bug", body="crash error")
        assert 0.0 <= result.confidence <= 1.0

    def test_label_prefix(self):
        """Labels respect the configured prefix."""
        cfg = SentinelConfig(
            labels=LabelConfig(prefix="triage/"),
            areas=[AreaConfig(name="core", keywords=["core"])],
        )
        classifier = IssueClassifier(cfg)
        result = classifier.classify(title="Core bug", body="Error in core module")
        for label in result.suggested_labels:
            assert label.startswith("triage/")


# ── Sentiment Tests ─────────────────────────────────────────────────────


class TestSentimentAnalyzer:
    def test_frustrated_sentiment(self, sentiment_analyzer: SentimentAnalyzer):
        result = sentiment_analyzer.analyze(
            title="This is TERRIBLE",
            body="Frustrated! Waste of time debugging this AWFUL bug."
        )
        assert result.sentiment == Sentiment.FRUSTRATED
        assert result.score < -0.3

    def test_neutral_sentiment(self, sentiment_analyzer: SentimentAnalyzer):
        result = sentiment_analyzer.analyze(
            title="API returns incorrect value",
            body="When calling getValue(), the returned value is off by one."
        )
        assert result.sentiment == Sentiment.NEUTRAL

    def test_positive_sentiment(self, sentiment_analyzer: SentimentAnalyzer):
        result = sentiment_analyzer.analyze(
            title="Great library!",
            body="Thanks for this awesome tool. Love the API design."
        )
        assert result.sentiment == Sentiment.POSITIVE
        assert result.score > 0.3

    def test_constructive_sentiment(self, sentiment_analyzer: SentimentAnalyzer):
        result = sentiment_analyzer.analyze(
            title="Suggestion: add batch processing",
            body="Here's a workaround I found. Happy to contribute a PR."
        )
        assert result.sentiment == Sentiment.CONSTRUCTIVE

    def test_empty_text(self, sentiment_analyzer: SentimentAnalyzer):
        """Empty text should return neutral."""
        result = sentiment_analyzer.analyze(title="", body="")
        assert result.sentiment == Sentiment.NEUTRAL
        assert result.score == 0.0

    def test_score_clamped(self, sentiment_analyzer: SentimentAnalyzer):
        """Score should never exceed [-1, 1] even with many signals."""
        result = sentiment_analyzer.analyze(
            title="TERRIBLE HORRIBLE AWFUL RIDICULOUS!!!",
            body="Frustrated! Waste of time! FIX THIS! Unacceptable! Absurd! Still not fixed!"
        )
        assert -1.0 <= result.score <= 1.0

    def test_signals_populated(self, sentiment_analyzer: SentimentAnalyzer):
        """Triggered signals should be listed."""
        result = sentiment_analyzer.analyze(
            title="Thanks for the great work!",
            body="",
        )
        assert len(result.signals) > 0

    def test_sentiment_result_label(self, sentiment_analyzer: SentimentAnalyzer):
        """SentimentResult.label property returns string."""
        result = sentiment_analyzer.analyze(title="Bug", body="")
        assert isinstance(result.label, str)

    def test_negative_sentiment(self, sentiment_analyzer: SentimentAnalyzer):
        """Negative (not frustrated) sentiment detected."""
        result = sentiment_analyzer.analyze(
            title="Disappointing behavior",
            body="Unfortunately this is confusing and misleading.",
        )
        assert result.sentiment in (Sentiment.NEGATIVE, Sentiment.FRUSTRATED)
        assert result.score < 0


# ── Urgency Tests ───────────────────────────────────────────────────────


class TestUrgencyScorer:
    def test_critical_urgency(self, urgency_scorer: UrgencyScorer):
        result = urgency_scorer.score(
            title="Security vulnerability in auth module",
            body="Remote code execution possible via CVE-2026-12345"
        )
        assert result.score >= 0.8
        assert result.priority == "p0"

    def test_high_urgency(self, urgency_scorer: UrgencyScorer):
        result = urgency_scorer.score(
            title="Regression: app crashes on startup",
            body="This is a blocker. Worked in previous version."
        )
        assert result.score >= 0.5
        assert result.priority in ("p0", "p1")

    def test_low_urgency(self, urgency_scorer: UrgencyScorer):
        result = urgency_scorer.score(
            title="Minor typo in docs",
            body="Cosmetic issue, low priority."
        )
        assert result.score < 0.2
        assert result.priority == "p3"

    def test_no_signals(self, urgency_scorer: UrgencyScorer):
        result = urgency_scorer.score(
            title="Feature request",
            body="Would be nice to have dark mode."
        )
        assert result.priority == "p3"

    def test_data_loss_is_critical(self, urgency_scorer: UrgencyScorer):
        """Data loss should trigger critical urgency."""
        result = urgency_scorer.score(
            title="Data loss when saving",
            body="Users are losing data.",
        )
        assert result.score >= 0.8
        assert result.priority == "p0"

    def test_production_outage_is_critical(self, urgency_scorer: UrgencyScorer):
        result = urgency_scorer.score(
            title="Production down",
            body="Complete production outage since 3am.",
        )
        assert result.score >= 0.8
        assert result.priority == "p0"

    def test_custom_high_signals(self):
        """Custom high signals from config are respected."""
        cfg = UrgencyConfig(high_signals=["deploy-blocker"])
        scorer = UrgencyScorer(config=cfg)
        result = scorer.score(
            title="This is a deploy-blocker",
            body="Cannot deploy until this is fixed.",
        )
        assert result.score >= 0.5

    def test_score_clamped(self, urgency_scorer: UrgencyScorer):
        """Score should stay in [0, 1] even with many signals."""
        result = urgency_scorer.score(
            title="CRITICAL security vulnerability CVE-2026-99999",
            body="Production down! Data loss! Remote code execution! ASAP! P0!",
        )
        assert 0.0 <= result.score <= 1.0

    def test_urgency_result_label(self, urgency_scorer: UrgencyScorer):
        """UrgencyResult.label returns priority string."""
        result = urgency_scorer.score(title="Minor issue", body="")
        assert result.label in ("p0", "p1", "p2", "p3")

    def test_signals_list_populated(self, urgency_scorer: UrgencyScorer):
        """Triggered signals should be listed."""
        result = urgency_scorer.score(
            title="Regression crash",
            body="Blocking release.",
        )
        assert len(result.signals) > 0


# ── Config Tests ────────────────────────────────────────────────────────


class TestConfig:
    def test_default_config(self):
        """Default SentinelConfig should be valid."""
        cfg = SentinelConfig()
        assert cfg.areas == []
        assert cfg.urgency.escalation_threshold == 0.8
        assert cfg.classification.provider == "rule-based"
        assert cfg.labels.apply is True

    def test_config_to_dict(self):
        """to_dict() should roundtrip key fields."""
        cfg = SentinelConfig(
            areas=[AreaConfig(name="test", keywords=["a", "b"])],
        )
        d = cfg.to_dict()
        assert isinstance(d, dict)
        assert len(d["areas"]) == 1
        assert d["areas"][0]["name"] == "test"

    def test_area_config_matches(self):
        """AreaConfig.matches() returns score > 0 for matching text."""
        area = AreaConfig(name="backend", keywords=["api", "server", "database"])
        score = area.matches("The server api database connection")
        assert score > 0

    def test_area_config_no_match(self):
        """AreaConfig.matches() returns 0 for non-matching text."""
        area = AreaConfig(name="backend", keywords=["api", "server", "database"])
        score = area.matches("This is about ui buttons")
        assert score == 0.0

    def test_from_dict_empty(self):
        """from_dict({}) should return valid default config."""
        cfg = SentinelConfig.from_dict({})
        assert isinstance(cfg, SentinelConfig)
        assert cfg.areas == []


# ── Integration Tests ───────────────────────────────────────────────────


class TestIssueSentinel:
    def test_full_pipeline(self, sentinel: IssueSentinel):
        result = sentinel.classify(
            title="API endpoint regression — crashes after upgrade!",
            body="This used to work! I'm frustrated. Blocking our release."
        )
        assert result.category == "regression"
        assert result.area == "backend"
        assert result.urgency > 0.3
        assert result.sentiment == "frustrated"
        assert len(result.suggested_labels) > 0

    def test_pipeline_with_neutral_issue(self, sentinel: IssueSentinel):
        result = sentinel.classify(
            title="How to use the server API for database queries",
            body="Looking for an example of reading records from the database."
        )
        assert result.category == "question"
        assert result.area == "backend"
        assert result.urgency < 0.3
        assert result.sentiment == "neutral"

    def test_from_config_default(self):
        """Test that default config works."""
        sentinel = IssueSentinel(SentinelConfig())
        result = sentinel.classify("Test issue", "Test body")
        assert result is not None
        assert isinstance(result, ClassificationResult)

    def test_urgency_label_added(self, sentinel: IssueSentinel):
        """High-urgency issues get urgency labels."""
        result = sentinel.classify(
            title="Security vulnerability in authentication API",
            body="Remote code execution via CVE-2026-99999. Production down.",
        )
        assert any(lbl in result.suggested_labels for lbl in ("p0", "p1"))

    def test_sentiment_label_when_enabled(self):
        """When include_sentiment=True, sentiment labels are added."""
        cfg = SentinelConfig(
            areas=[AreaConfig(name="core", keywords=["core"])],
            labels=LabelConfig(include_sentiment=True),
        )
        sentinel = IssueSentinel(cfg)
        result = sentinel.classify(
            title="This is TERRIBLE! Core bug!",
            body="Frustrated! Waste of time!",
        )
        assert any("sentiment:" in lbl for lbl in result.suggested_labels)

    def test_classify_returns_all_fields(self, sentinel: IssueSentinel):
        """Every field on ClassificationResult is populated after classify()."""
        result = sentinel.classify(
            title="Server bug",
            body="API endpoint crashes",
        )
        assert result.category is not None
        assert result.area is not None
        assert isinstance(result.confidence, float)
        assert isinstance(result.urgency, float)
        assert result.sentiment is not None
        assert result.method is not None
        assert isinstance(result.suggested_labels, list)
        assert isinstance(result.reasoning, str)

    def test_log_decision(self, sentinel: IssueSentinel, tmp_path):
        """log_decision writes valid JSONL."""
        log_file = tmp_path / "test_log.jsonl"
        result = sentinel.classify("Bug", "crash")
        sentinel.log_decision(42, result, log_path=log_file)

        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["issue_number"] == 42
        assert "category" in entry
        assert "timestamp" in entry

    def test_triage_comment_format(self, sentinel: IssueSentinel):
        """_build_triage_comment returns valid markdown."""
        result = sentinel.classify("Bug in auth", "crashes")
        comment = sentinel._build_triage_comment(result)
        assert "Issue Sentinel" in comment
        assert "Type" in comment
        assert "Area" in comment
        assert "Urgency" in comment
