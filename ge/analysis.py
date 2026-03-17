"""Issue and PR analysis: staleness, relevance, and state assessment.

Examines an issue or PR to determine if it's still relevant, already fixed,
or needs further investigation before work begins.
"""

import re
from datetime import datetime, timezone

from ge.github import (
    get_issue,
    get_pr,
    get_comments,
    get_timeline,
    find_related_prs,
    find_related_commits,
    get_default_branch,
    get_file_at_ref,
)


def _parse_iso(datestr):
    """Parse ISO 8601 date string to datetime."""
    if not datestr:
        return None
    return datetime.fromisoformat(datestr.replace('Z', '+00:00'))


def _days_ago(datestr):
    """How many days ago was this ISO date?"""
    dt = _parse_iso(datestr)
    if not dt:
        return None
    delta = datetime.now(timezone.utc) - dt
    return delta.days


def _extract_file_refs(markdown):
    """Extract file paths mentioned in markdown (code blocks, backticks, paths).

    >>> refs = _extract_file_refs('The bug is in `src/main.py` line 42')
    >>> 'src/main.py' in refs
    True
    """
    paths = set()
    # Backtick-wrapped paths
    for m in re.finditer(r'`([^`]+\.\w{1,10})`', markdown):
        candidate = m.group(1).strip()
        # Heuristic: looks like a file path (has extension, no spaces usually)
        if '/' in candidate or '.' in candidate:
            paths.add(candidate)
    # Bare paths in text (conservative)
    for m in re.finditer(r'(?:^|\s)((?:[\w.-]+/)+[\w.-]+\.\w{1,10})', markdown, re.M):
        paths.add(m.group(1))
    return list(paths)


def analyze_issue(repo, number):
    """Analyze an issue for staleness and current relevance.

    Returns a dict with:
      - state: open/closed
      - age_days: days since creation
      - last_activity_days: days since last comment/event
      - labels: list of label names
      - related_prs: PRs that reference this issue
      - related_commits: commits mentioning this issue
      - referenced_files: files mentioned in the issue body
      - signals: list of human-readable observations about freshness
      - recommendation: 'proceed', 'investigate', or 'likely_resolved'

    >>> # analysis = analyze_issue('owner/repo', 42)
    """
    issue = get_issue(repo, number)
    comments = get_comments(repo, number)
    related_prs = find_related_prs(repo, number)
    related_commits = find_related_commits(repo, number)

    signals = []

    # Basic state
    state = issue.get('state', 'unknown')
    age_days = _days_ago(issue.get('created_at'))
    labels = [l['name'] for l in issue.get('labels', [])]

    # Last activity
    activity_dates = [issue.get('created_at')]
    for c in comments:
        activity_dates.append(c.get('created_at'))
    if issue.get('updated_at'):
        activity_dates.append(issue['updated_at'])
    last_activity = max((d for d in activity_dates if d), default=None)
    last_activity_days = _days_ago(last_activity)

    # Closed?
    if state == 'closed':
        signals.append(
            f"Issue is CLOSED (closed {_days_ago(issue.get('closed_at', '')) or '?'} days ago)"
        )

    # Stale?
    if last_activity_days and last_activity_days > 180:
        signals.append(f"No activity for {last_activity_days} days — may be stale")
    elif last_activity_days and last_activity_days > 60:
        signals.append(f"Last activity was {last_activity_days} days ago")

    # Related PRs that may have fixed it
    merged_prs = [p for p in related_prs if p.get('state') == 'closed']
    open_prs = [p for p in related_prs if p.get('state') == 'open']
    if merged_prs:
        titles = ', '.join(f"#{p['number']}" for p in merged_prs)
        signals.append(f"Related merged/closed PRs: {titles} — may already be fixed")
    if open_prs:
        titles = ', '.join(f"#{p['number']}" for p in open_prs)
        signals.append(f"Related open PRs: {titles} — someone may be working on this")

    # Related commits
    if related_commits:
        signals.append(
            f"{len(related_commits)} commit(s) reference this issue"
        )

    # Labels hinting at status
    status_labels = {'wontfix', 'duplicate', 'invalid', 'stale', 'resolved'}
    found_status = [l for l in labels if l.lower() in status_labels]
    if found_status:
        signals.append(f"Status labels: {', '.join(found_status)}")

    # Labels that inform priority and type
    priority_labels = {
        'good first issue': 'Good first issue — likely well-scoped and approachable',
        'help wanted': 'Help wanted — maintainers welcome contributions',
        'priority:high': 'High priority',
        'priority:critical': 'Critical priority',
        'bug': 'Labeled as bug',
        'enhancement': 'Labeled as enhancement/feature request',
        'documentation': 'Labeled as documentation',
    }
    for label in labels:
        desc = priority_labels.get(label.lower())
        if desc:
            signals.append(desc)

    # Check for closing keywords in comments
    closing_phrases = ['fixed in', 'resolved by', 'this has been', 'closing as',
                       'no longer', 'already been']
    for c in comments:
        body = (c.get('body') or '').lower()
        for phrase in closing_phrases:
            if phrase in body:
                signals.append(
                    f"Comment by @{c.get('author', {}).get('login', c.get('user', {}).get('login', '?'))} "
                    f"contains '{phrase}' — may indicate resolution"
                )
                break

    # Referenced files
    body = issue.get('body') or ''
    all_text = body + '\n'.join(c.get('body', '') for c in comments)
    referenced_files = _extract_file_refs(all_text)

    # Recommendation
    if state == 'closed':
        recommendation = 'likely_resolved'
    elif merged_prs or found_status:
        recommendation = 'investigate'
    elif last_activity_days and last_activity_days > 365:
        recommendation = 'investigate'
    else:
        recommendation = 'proceed'

    return {
        'state': state,
        'age_days': age_days,
        'last_activity_days': last_activity_days,
        'labels': labels,
        'related_prs': related_prs,
        'related_commits': related_commits,
        'referenced_files': referenced_files,
        'signals': signals,
        'recommendation': recommendation,
    }


def analyze_pr(repo, number):
    """Analyze a PR for review context and merge readiness.

    Returns a dict with state, review status, CI signals, conflicts, etc.

    >>> # analysis = analyze_pr('owner/repo', 7)
    """
    from ge.github import get_reviews, get_pr_files, get_commit_status

    pr = get_pr(repo, number)
    comments = get_comments(repo, number)
    reviews = get_reviews(repo, number)
    files = get_pr_files(repo, number)

    signals = []

    state = pr.get('state', 'unknown')
    merged = pr.get('merged', False)
    mergeable = pr.get('mergeable')
    mergeable_state = pr.get('mergeable_state', 'unknown')
    draft = pr.get('draft', False)

    if merged:
        signals.append("PR is already MERGED")
    elif state == 'closed':
        signals.append("PR is CLOSED without merge")
    if draft:
        signals.append("PR is a DRAFT")

    # Review states
    review_states = {}
    for r in reviews:
        user = r.get('user', {}).get('login', '?')
        rstate = r.get('state', '?')
        review_states[user] = rstate
    approved = [u for u, s in review_states.items() if s == 'APPROVED']
    changes_requested = [u for u, s in review_states.items() if s == 'CHANGES_REQUESTED']
    if approved:
        signals.append(f"Approved by: {', '.join(approved)}")
    if changes_requested:
        signals.append(f"Changes requested by: {', '.join(changes_requested)}")

    # Merge conflicts
    if mergeable is False:
        signals.append("PR has MERGE CONFLICTS")
    elif mergeable_state == 'dirty':
        signals.append("PR may have merge conflicts (mergeable_state=dirty)")

    # Files changed
    n_files = len(files)
    n_additions = sum(f.get('additions', 0) for f in files)
    n_deletions = sum(f.get('deletions', 0) for f in files)
    signals.append(f"Changes: {n_files} files, +{n_additions}/-{n_deletions}")

    # CI status
    ci_state = None
    head_sha = pr.get('head', {}).get('sha')
    if head_sha:
        try:
            status = get_commit_status(repo, head_sha)
            ci_state = status.get('state')  # success, failure, pending, error
            total = status.get('total_count', 0)
            if ci_state == 'success':
                signals.append(f"CI checks PASSED ({total} check(s))")
            elif ci_state == 'failure':
                signals.append(f"CI checks FAILED ({total} check(s))")
            elif ci_state == 'pending':
                signals.append(f"CI checks PENDING ({total} check(s))")
            elif ci_state == 'error':
                signals.append(f"CI checks ERROR ({total} check(s))")
        except Exception:
            pass  # CI status not available

    # Referenced issues (from PR body)
    body = pr.get('body') or ''
    issue_refs = re.findall(
        r'(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)', body, re.I
    )
    linked_issues = list(set(int(n) for n in issue_refs))

    age_days = _days_ago(pr.get('created_at'))
    last_activity_days = _days_ago(pr.get('updated_at'))

    # Recommendation
    if merged:
        recommendation = 'already_merged'
    elif state == 'closed':
        recommendation = 'closed_unmerged'
    elif changes_requested:
        recommendation = 'needs_changes'
    elif mergeable is False:
        recommendation = 'resolve_conflicts'
    elif draft:
        recommendation = 'draft_wip'
    else:
        recommendation = 'proceed'

    return {
        'state': state,
        'merged': merged,
        'draft': draft,
        'mergeable': mergeable,
        'ci_state': ci_state,
        'age_days': age_days,
        'last_activity_days': last_activity_days,
        'review_states': review_states,
        'linked_issues': linked_issues,
        'files_changed': [f.get('filename') for f in files],
        'n_additions': n_additions,
        'n_deletions': n_deletions,
        'signals': signals,
        'recommendation': recommendation,
    }


def check_referenced_files(repo, file_paths, *, ref=None):
    """Check if files mentioned in an issue still exist on the default branch.

    Returns dict mapping path -> {'exists': bool, 'snippet': str | None}.

    >>> # status = check_referenced_files('owner/repo', ['src/main.py'])
    """
    if ref is None:
        ref = get_default_branch(repo)
    result = {}
    for path in file_paths:
        try:
            content = get_file_at_ref(repo, path, ref=ref)
            # Return first 30 lines as snippet
            lines = content.split('\n')[:30]
            result[path] = {'exists': True, 'snippet': '\n'.join(lines)}
        except Exception:
            result[path] = {'exists': False, 'snippet': None}
    return result
