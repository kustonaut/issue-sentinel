"""GitHub API client for Issue Sentinel."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"


@dataclass
class GitHubIssue:
    """Simplified GitHub issue representation."""

    number: int
    title: str
    body: str
    labels: list[str]
    state: str
    url: str
    author: str
    created_at: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> GitHubIssue:
        """Create from GitHub API response."""
        return cls(
            number=data["number"],
            title=data["title"],
            body=data.get("body") or "",
            labels=[lbl["name"] for lbl in data.get("labels", [])],
            state=data["state"],
            url=data["html_url"],
            author=data.get("user", {}).get("login", "unknown"),
            created_at=data.get("created_at", ""),
        )


class GitHubClient:
    """Minimal GitHub API client for issue operations."""

    def __init__(self, token: str, repo: str) -> None:
        """
        Args:
            token: GitHub personal access token
            repo: Repository in 'owner/repo' format
        """
        self.token = token
        self.repo = repo
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def get_issue(self, number: int) -> GitHubIssue:
        """Fetch a single issue by number."""
        url = f"{BASE_URL}/repos/{self.repo}/issues/{number}"
        resp = self.session.get(url)
        resp.raise_for_status()
        return GitHubIssue.from_api(resp.json())

    def list_issues(
        self,
        state: str = "open",
        limit: int = 30,
        labels: list[str] | None = None,
    ) -> list[GitHubIssue]:
        """List issues from the repository.

        Args:
            state: Issue state filter ('open', 'closed', 'all')
            limit: Maximum number of issues to return
            labels: Filter by label names

        Returns:
            List of GitHubIssue objects
        """
        issues: list[GitHubIssue] = []
        page = 1
        per_page = min(limit, 100)

        while len(issues) < limit:
            params: dict[str, Any] = {
                "state": state,
                "per_page": per_page,
                "page": page,
                "sort": "created",
                "direction": "desc",
            }
            if labels:
                params["labels"] = ",".join(labels)

            url = f"{BASE_URL}/repos/{self.repo}/issues"
            resp = self.session.get(url, params=params)
            resp.raise_for_status()

            data = resp.json()
            if not data:
                break

            for item in data:
                # Skip pull requests (GitHub API returns them in /issues)
                if "pull_request" in item:
                    continue
                issues.append(GitHubIssue.from_api(item))
                if len(issues) >= limit:
                    break

            page += 1

        return issues

    def add_labels(self, number: int, labels: list[str]) -> None:
        """Add labels to an issue.

        Args:
            number: Issue number
            labels: Label names to add
        """
        url = f"{BASE_URL}/repos/{self.repo}/issues/{number}/labels"
        resp = self.session.post(url, json={"labels": labels})
        resp.raise_for_status()
        logger.info(f"Added labels {labels} to issue #{number}")

    def add_comment(self, number: int, body: str) -> None:
        """Add a comment to an issue.

        Args:
            number: Issue number
            body: Comment text (Markdown supported)
        """
        url = f"{BASE_URL}/repos/{self.repo}/issues/{number}/comments"
        resp = self.session.post(url, json={"body": body})
        resp.raise_for_status()
        logger.info(f"Added comment to issue #{number}")

    def create_label(
        self, name: str, color: str = "ededed", description: str = ""
    ) -> None:
        """Create a label in the repository (idempotent — ignores 422 if exists)."""
        url = f"{BASE_URL}/repos/{self.repo}/labels"
        try:
            resp = self.session.post(
                url,
                json={"name": name, "color": color, "description": description},
            )
            if resp.status_code == 422:
                logger.debug(f"Label '{name}' already exists")
            else:
                resp.raise_for_status()
                logger.info(f"Created label '{name}'")
        except requests.RequestException as e:
            logger.warning(f"Failed to create label '{name}': {e}")
