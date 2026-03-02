"""CLI interface for Issue Sentinel."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from issue_sentinel.classifier import ClassificationResult
from issue_sentinel.config import SentinelConfig
from issue_sentinel.sentinel import IssueSentinel
from issue_sentinel.github_client import GitHubClient


@click.group()
@click.version_option(version="0.1.0", prog_name="issue-sentinel")
def main() -> None:
    """Issue Sentinel — AI-powered GitHub issue triage."""
    pass


@main.command()
@click.option("--title", "-t", required=True, help="Issue title")
@click.option("--body", "-b", default="", help="Issue body")
@click.option("--config", "-c", default="issue-sentinel.yaml", help="Config file path")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def classify(title: str, body: str, config: str, json_output: bool) -> None:
    """Classify a single issue from text input."""
    cfg = _load_config(config)
    sentinel = IssueSentinel(cfg)
    result = sentinel.classify(title, body)

    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        _print_result(result, title)


@main.command()
@click.option("--repo", "-r", required=True, help="Repository (owner/repo)")
@click.option("--issue", "-i", required=True, type=int, help="Issue number")
@click.option("--config", "-c", default="issue-sentinel.yaml", help="Config file path")
@click.option("--apply-labels", is_flag=True, help="Apply suggested labels")
@click.option("--comment", is_flag=True, help="Post triage comment")
@click.option("--dry-run", is_flag=True, help="Classify without modifying")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def triage_one(
    repo: str,
    issue: int,
    config: str,
    apply_labels: bool,
    comment: bool,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Triage a single GitHub issue by number."""
    cfg = _load_config(config)
    sentinel = IssueSentinel(cfg)
    client = _get_github_client(repo)

    gh_issue = client.get_issue(issue)
    result = sentinel.triage_issue(
        client, gh_issue,
        apply_labels=apply_labels,
        post_comment=comment,
        dry_run=dry_run,
    )

    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        _print_result(result, gh_issue.title, gh_issue.number)


@main.command()
@click.option("--repo", "-r", required=True, help="Repository (owner/repo)")
@click.option("--config", "-c", default="issue-sentinel.yaml", help="Config file path")
@click.option("--state", default="open", help="Issue state filter")
@click.option("--limit", "-n", default=20, type=int, help="Max issues to triage")
@click.option("--apply-labels", is_flag=True, help="Apply suggested labels")
@click.option("--dry-run", is_flag=True, help="Classify without modifying")
@click.option("--json-output", "-j", is_flag=True, help="Output as JSON")
def triage(
    repo: str,
    config: str,
    state: str,
    limit: int,
    apply_labels: bool,
    dry_run: bool,
    json_output: bool,
) -> None:
    """Bulk triage open issues in a repository."""
    cfg = _load_config(config)
    sentinel = IssueSentinel(cfg)
    client = _get_github_client(repo)

    click.echo(f"Fetching up to {limit} {state} issues from {repo}...")
    issues = client.list_issues(state=state, limit=limit)
    click.echo(f"Found {len(issues)} issues. Triaging...\n")

    results = sentinel.triage_batch(
        client, issues, apply_labels=apply_labels, dry_run=dry_run
    )

    if json_output:
        output = [
            {"issue": i.number, "title": i.title, **r.to_dict()}
            for i, r in results
        ]
        click.echo(json.dumps(output, indent=2))
    else:
        # Summary table
        click.echo(f"{'#':<6} {'Type':<18} {'Area':<15} {'Urg':>5} {'Sentiment':<14} Title")
        click.echo("─" * 90)
        for issue, result in results:
            urg = f"{result.urgency:.0%}"
            click.echo(
                f"#{issue.number:<5} {result.category:<18} {result.area:<15} "
                f"{urg:>5} {result.sentiment:<14} {issue.title[:30]}"
            )

        click.echo(f"\n{'─' * 90}")
        click.echo(f"Triaged {len(results)} issues.")
        if dry_run:
            click.echo("(DRY RUN — no changes applied)")


# ── Helpers ─────────────────────────────────────────────────────────────


def _load_config(path: str) -> SentinelConfig:
    """Load config, falling back to defaults if file doesn't exist."""
    config_path = Path(path)
    if config_path.exists():
        return SentinelConfig.from_yaml(config_path)
    else:
        click.echo(f"Config '{path}' not found — using defaults.", err=True)
        return SentinelConfig()


def _get_github_client(repo: str) -> GitHubClient:
    """Create GitHub client from environment token."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        click.echo(
            "Error: GITHUB_TOKEN environment variable required for GitHub operations.",
            err=True,
        )
        sys.exit(1)
    return GitHubClient(token=token, repo=repo)


def _print_result(
    result: ClassificationResult,
    title: str,
    number: int | None = None,
) -> None:
    """Pretty-print a classification result."""
    header = f"Issue #{number}" if number else "Issue"
    urgency_bar = "█" * int(result.urgency * 10) + "░" * (10 - int(result.urgency * 10))

    click.echo(f"\n🛡️  {header}: {title}")
    click.echo(f"   Category:   {result.category}")
    click.echo(f"   Area:       {result.area}")
    click.echo(f"   Urgency:    [{urgency_bar}] {result.urgency:.0%}")
    click.echo(f"   Sentiment:  {result.sentiment}")
    click.echo(f"   Confidence: {result.confidence:.0%}")
    click.echo(f"   Method:     {result.method}")
    if result.suggested_labels:
        click.echo(f"   Labels:     {', '.join(result.suggested_labels)}")
    if result.reasoning:
        click.echo(f"   Reasoning:  {result.reasoning}")
    click.echo()


if __name__ == "__main__":
    main()
