---
name: ge-analyze
description: "Use when you need to check whether a GitHub issue or PR is still relevant, stale, or already resolved — without preparing full context or downloading media."
---

# ge-analyze: Triage GitHub Issues and PRs

Use this skill for quick triage — checking whether an issue or PR is worth working on, finding related PRs/commits, or assessing staleness. This does NOT download media or prepare full context documents.

## Prerequisites

- `ge` package installed
- `gh` CLI authenticated

## Issue Analysis

```python
import ge

analysis = ge.analyze_issue('owner/repo', 42)
```

Returns a dict with:

| Field | Type | Description |
|-------|------|-------------|
| `state` | str | `"open"` or `"closed"` |
| `age_days` | int | Days since issue was created |
| `last_activity_days` | int | Days since last comment or event |
| `labels` | list[str] | Issue labels |
| `related_prs` | list[dict] | PRs that reference this issue |
| `related_commits` | list[dict] | Commits that reference this issue |
| `referenced_files` | list[dict] | Files mentioned in the issue body, with existence check |
| `signals` | list[str] | Human-readable signal descriptions |
| `recommendation` | str | One of: `proceed`, `investigate`, `likely_resolved` |

### Interpreting issue recommendations

- **`proceed`** — Issue is open, active, and unresolved. Safe to work on.
- **`investigate`** — Mixed signals. There may be related merged PRs, recent activity suggesting partial resolution, or the issue is very old. Ask the user before investing effort.
- **`likely_resolved`** — Issue is closed, or has strong resolution signals (merged fix PRs, closing comments). Confirm with the user that they still want work done.

## PR Analysis

```python
analysis = ge.analyze_pr('owner/repo', 7)
```

Returns a dict with:

| Field | Type | Description |
|-------|------|-------------|
| `state` | str | `"open"`, `"closed"`, or `"merged"` |
| `merged` | bool | Whether the PR has been merged |
| `draft` | bool | Whether it's a draft PR |
| `mergeable` | str | Merge status (`"MERGEABLE"`, `"CONFLICTING"`, etc.) |
| `ci_state` | str | CI/check status |
| `review_states` | dict | Review verdicts by reviewer |
| `linked_issues` | list | Issues linked to this PR |
| `files_changed` | int | Number of files changed |
| `signals` | list[str] | Human-readable signal descriptions |
| `recommendation` | str | One of the values below |

### Interpreting PR recommendations

- **`proceed`** — PR is open and ready for work or review.
- **`needs_changes`** — Reviewers requested changes. Focus on addressing their feedback.
- **`resolve_conflicts`** — Merge conflicts exist. Resolve them first.
- **`draft_wip`** — PR is a draft. It may be incomplete.
- **`already_merged`** — PR was already merged. Confirm with user what they want.
- **`closed_unmerged`** — PR was closed without merging. Confirm with user.

## Checking Referenced Files

Verify whether files mentioned in an issue still exist on the default branch:

```python
from ge.analysis import check_referenced_files

results = check_referenced_files('owner/repo', ['src/auth.py', 'config/settings.yaml'])
# Returns list of dicts with 'path', 'exists', and 'ref' fields
```

## When to Escalate to Full Context

If the analysis says `proceed` and the user wants you to actually work on the issue, switch to the main `ge` skill — it runs `ge.prepare()` which fetches everything (comments, media, full analysis) and writes a structured context document.
