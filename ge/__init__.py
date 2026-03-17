"""ge: GitHub Engineering tools for AI agents.

Reduces boilerplate when working on GitHub issues and PRs with AI coding agents.
Fetches context, downloads media, checks freshness, and assembles everything
into a structured document the agent can consume.

Usage::

    import ge

    # Prepare full context for an issue
    ctx = ge.prepare_issue('owner/repo', 42)

    # Prepare full context for a PR
    ctx = ge.prepare_pr('owner/repo', 7)

    # Or from a full URL
    ctx = ge.prepare('https://github.com/owner/repo/issues/42')
"""

from ge.context import prepare_issue, prepare_pr, prepare_discussion
from ge.analysis import analyze_issue, analyze_pr
from ge.github import (
    get_issue,
    get_pr,
    get_comments,
    get_pr_diff,
    get_discussion,
    find_related_prs,
    find_related_commits,
)
from ge.media import process_all_media, extract_video_frames
from ge.util import parse_github_url


def prepare(url_or_spec, number=None, *, output_dir='.ge', **kwargs):
    """Prepare context from a GitHub URL or repo+number.

    Automatically detects whether it's an issue, PR, or discussion.

    >>> # ctx = ge.prepare('https://github.com/owner/repo/issues/42')
    >>> # ctx = ge.prepare('owner/repo', 42)
    >>> # ctx = ge.prepare('https://github.com/owner/repo/discussions/5')
    """
    if number is None:
        # Parse from URL
        owner, repo, number, kind = parse_github_url(url_or_spec)
        repo_spec = f'{owner}/{repo}'
    else:
        repo_spec = url_or_spec
        # Probe whether it's a PR or issue
        try:
            data = get_pr(repo_spec, number)
            kind = 'pr'
        except Exception:
            kind = 'issue'

    if kind == 'pr':
        return prepare_pr(repo_spec, number, output_dir=output_dir, **kwargs)
    elif kind == 'discussion':
        return prepare_discussion(repo_spec, number, output_dir=output_dir, **kwargs)
    else:
        return prepare_issue(repo_spec, number, output_dir=output_dir, **kwargs)


__all__ = [
    'prepare',
    'prepare_issue',
    'prepare_pr',
    'prepare_discussion',
    'analyze_issue',
    'analyze_pr',
    'get_issue',
    'get_pr',
    'get_comments',
    'get_pr_diff',
    'get_discussion',
    'find_related_prs',
    'find_related_commits',
    'process_all_media',
    'extract_video_frames',
]
