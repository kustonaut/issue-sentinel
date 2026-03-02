"""Example: Classify issues from the command line."""

from issue_sentinel import IssueSentinel
from issue_sentinel.config import SentinelConfig, AreaConfig

# Quick in-code config (no YAML needed)
config = SentinelConfig(
    areas=[
        AreaConfig(name="backend", keywords=["api", "server", "database", "auth"]),
        AreaConfig(name="frontend", keywords=["ui", "button", "css", "layout", "react"]),
        AreaConfig(name="docs", keywords=["documentation", "readme", "tutorial", "example"]),
    ]
)

sentinel = IssueSentinel(config)

# Classify some sample issues
samples = [
    ("API returns 500 on login endpoint", "After upgrading to v3, the /auth/login crashes."),
    ("Please add dark mode support", "It would be great to have a dark theme for the UI."),
    ("How do I configure the database connection?", "Looking for documentation on setup."),
    ("CRITICAL: data loss when saving", "Users are losing data! This is a regression from v2.8."),
    ("Minor typo in README", "Line 42 says 'teh' instead of 'the'."),
]

print("Issue Sentinel — Demo\n")
print(f"{'Type':<18} {'Area':<12} {'Urg':>5} {'Sentiment':<14} Title")
print("─" * 80)

for title, body in samples:
    result = sentinel.classify(title, body)
    urg = f"{result.urgency:.0%}"
    print(f"{result.category:<18} {result.area:<12} {urg:>5} {result.sentiment:<14} {title[:35]}")
