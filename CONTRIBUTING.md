# Contributing to Issue Sentinel

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/kustonaut/issue-sentinel.git
cd issue-sentinel

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=issue_sentinel --cov-report=term-missing

# Type checking
mypy src/issue_sentinel/ --ignore-missing-imports

# Lint
ruff check src/ tests/
ruff format src/ tests/
```

## Code Style

- Python 3.10+ — use modern type hints (`list[str]` not `List[str]`)
- Dataclasses over dicts for structured data
- Docstrings on all public methods (Google style)
- `ruff` for formatting and linting
- `mypy --strict` for type safety

## Project Structure

```
src/issue_sentinel/
├── __init__.py          # Package exports
├── classifier.py        # Rule-based issue classification
├── cli.py               # Click CLI interface
├── config.py            # YAML-driven configuration
├── github_client.py     # GitHub REST API client
├── llm_classifier.py    # LLM-powered classification (OpenAI/Anthropic)
├── sentinel.py          # Main facade — ties everything together
├── sentiment.py         # Sentiment analysis engine
└── urgency.py           # Urgency scoring engine
```

## Adding a New Feature

1. **Open an issue first** — describe what you want to change and why
2. **Fork + branch** — create a feature branch from `main`
3. **Write tests** — add tests in `tests/` before or alongside your code
4. **Keep PRs small** — one feature per PR, well-scoped
5. **Run the full suite** — `pytest && ruff check && mypy` must all pass

## Common Contributions

### Adding new issue type patterns
Edit `classifier.py` — add patterns to the appropriate `_*_PATTERNS` list. Each pattern is a regex string. Add a corresponding test case.

### Adding new urgency signals
Edit `urgency.py` — add a tuple `(regex_pattern, weight, description)` to the appropriate signal list (`_CRITICAL_SIGNALS`, `_HIGH_SIGNALS`, etc.).

### Adding new sentiment signals
Edit `sentiment.py` — add a tuple `(regex_pattern, weight)` to the appropriate signal list.

### Supporting a new LLM provider
Edit `llm_classifier.py` — add a new method `_call_<provider>()` following the pattern of `_call_openai()` and `_call_anthropic()`.

## Commit Messages

Use conventional commits:
- `feat: add support for ...`
- `fix: handle edge case where ...`
- `docs: update README with ...`
- `test: add tests for ...`
- `chore: update dependencies`

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
