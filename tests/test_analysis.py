"""Tests for ge.analysis module."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from ge.analysis import _extract_file_refs, _days_ago, analyze_issue, analyze_pr


# ---------------------------------------------------------------------------
# Helpers for building mock data
# ---------------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    """Format a datetime as ISO 8601 with Z suffix."""
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# _extract_file_refs
# ---------------------------------------------------------------------------


class TestExtractFileRefs:
    def test_backtick_path(self):
        refs = _extract_file_refs('The bug is in `src/main.py` line 42')
        assert 'src/main.py' in refs

    def test_bare_path(self):
        refs = _extract_file_refs('Look at some/path/file.py for details')
        assert 'some/path/file.py' in refs

    def test_multiple_paths(self):
        md = '`src/foo.js` and `lib/bar.ts` are both affected. Also see pkg/baz.go .'
        refs = _extract_file_refs(md)
        assert 'src/foo.js' in refs
        assert 'lib/bar.ts' in refs
        assert 'pkg/baz.go' in refs

    def test_backtick_with_extension_only(self):
        # A dotted name inside backticks (no slash) should still be captured
        refs = _extract_file_refs('Check `config.yaml` please')
        assert 'config.yaml' in refs

    def test_no_paths(self):
        refs = _extract_file_refs('Nothing to see here, just plain text')
        assert refs == []

    def test_various_extensions(self):
        md = '`app/views.html`, `app/style.css`, `data/records.json`'
        refs = _extract_file_refs(md)
        assert 'app/views.html' in refs
        assert 'app/style.css' in refs
        assert 'data/records.json' in refs


# ---------------------------------------------------------------------------
# _days_ago
# ---------------------------------------------------------------------------


class TestDaysAgo:
    def test_known_date(self):
        ten_days_ago = _now() - timedelta(days=10)
        result = _days_ago(_iso(ten_days_ago))
        assert result == 10

    def test_today(self):
        result = _days_ago(_iso(_now()))
        assert result == 0

    def test_none_input(self):
        assert _days_ago(None) is None

    def test_empty_string(self):
        assert _days_ago('') is None


# ---------------------------------------------------------------------------
# analyze_issue
# ---------------------------------------------------------------------------


def _make_issue(*, state='open', created_days_ago=30, updated_days_ago=5,
                closed_days_ago=None, labels=None, body=''):
    created = _iso(_now() - timedelta(days=created_days_ago))
    updated = _iso(_now() - timedelta(days=updated_days_ago))
    issue = {
        'state': state,
        'created_at': created,
        'updated_at': updated,
        'labels': [{'name': l} for l in (labels or [])],
        'body': body,
        'user': {'login': 'alice'},
    }
    if closed_days_ago is not None:
        issue['closed_at'] = _iso(_now() - timedelta(days=closed_days_ago))
    return issue


def _make_comment(body='looks good', created_days_ago=5, login='bob'):
    return {
        'body': body,
        'created_at': _iso(_now() - timedelta(days=created_days_ago)),
        'user': {'login': login},
    }


def _make_pr_item(number, state='open'):
    return {'number': number, 'state': state, 'title': f'PR #{number}'}


_ANALYSIS_PATCHES = [
    'ge.analysis.get_issue',
    'ge.analysis.get_comments',
    'ge.analysis.find_related_prs',
    'ge.analysis.find_related_commits',
]


class TestAnalyzeIssue:
    def _run(self, issue, *, comments=None, related_prs=None, related_commits=None):
        comments = comments if comments is not None else []
        related_prs = related_prs if related_prs is not None else []
        related_commits = related_commits if related_commits is not None else []
        with patch('ge.analysis.get_issue', return_value=issue), \
             patch('ge.analysis.get_comments', return_value=comments), \
             patch('ge.analysis.find_related_prs', return_value=related_prs), \
             patch('ge.analysis.find_related_commits', return_value=related_commits):
            return analyze_issue('owner/repo', 42)

    def test_closed_issue(self):
        issue = _make_issue(state='closed', closed_days_ago=3)
        result = self._run(issue)
        assert result['state'] == 'closed'
        assert result['recommendation'] == 'likely_resolved'

    def test_open_with_merged_related_prs(self):
        issue = _make_issue(state='open')
        prs = [_make_pr_item(10, state='closed')]
        result = self._run(issue, related_prs=prs)
        assert result['recommendation'] == 'investigate'

    def test_open_with_status_labels_wontfix(self):
        issue = _make_issue(state='open', labels=['wontfix'])
        result = self._run(issue)
        assert result['recommendation'] == 'investigate'

    def test_open_with_status_labels_duplicate(self):
        issue = _make_issue(state='open', labels=['duplicate'])
        result = self._run(issue)
        assert result['recommendation'] == 'investigate'

    def test_open_no_concerning_signals(self):
        issue = _make_issue(state='open', created_days_ago=10, updated_days_ago=2)
        result = self._run(issue)
        assert result['recommendation'] == 'proceed'

    def test_very_old_no_activity(self):
        issue = _make_issue(
            state='open', created_days_ago=500, updated_days_ago=400,
        )
        result = self._run(issue)
        assert result['recommendation'] == 'investigate'
        assert any('stale' in s.lower() or 'activity' in s.lower()
                    for s in result['signals'])

    def test_referenced_files_extracted(self):
        issue = _make_issue(body='Check `src/app.py` for the root cause')
        result = self._run(issue)
        assert 'src/app.py' in result['referenced_files']

    def test_labels_returned(self):
        issue = _make_issue(labels=['bug', 'high-priority'])
        result = self._run(issue)
        assert 'bug' in result['labels']
        assert 'high-priority' in result['labels']

    def test_related_commits_signal(self):
        issue = _make_issue()
        commits = [{'sha': 'abc123', 'commit': {'message': 'fix #42'}}]
        result = self._run(issue, related_commits=commits)
        assert any('commit' in s.lower() for s in result['signals'])


# ---------------------------------------------------------------------------
# analyze_pr
# ---------------------------------------------------------------------------


def _make_pr(*, state='open', merged=False, mergeable=True,
             mergeable_state='clean', draft=False,
             created_days_ago=10, updated_days_ago=2, body=''):
    return {
        'state': state,
        'merged': merged,
        'mergeable': mergeable,
        'mergeable_state': mergeable_state,
        'draft': draft,
        'created_at': _iso(_now() - timedelta(days=created_days_ago)),
        'updated_at': _iso(_now() - timedelta(days=updated_days_ago)),
        'body': body,
        'user': {'login': 'alice'},
    }


def _make_review(login, state='APPROVED'):
    return {'user': {'login': login}, 'state': state}


def _make_file(filename, additions=10, deletions=2):
    return {'filename': filename, 'additions': additions, 'deletions': deletions}


class TestAnalyzePr:
    def _run(self, pr, *, comments=None, reviews=None, files=None):
        comments = comments if comments is not None else []
        reviews = reviews if reviews is not None else []
        files = files if files is not None else [_make_file('README.md')]
        with patch('ge.analysis.get_pr', return_value=pr), \
             patch('ge.analysis.get_comments', return_value=comments), \
             patch('ge.github.get_reviews', return_value=reviews), \
             patch('ge.github.get_pr_files', return_value=files):
            return analyze_pr('owner/repo', 7)

    def test_merged_pr(self):
        pr = _make_pr(state='closed', merged=True)
        result = self._run(pr)
        assert result['recommendation'] == 'already_merged'
        assert result['merged'] is True

    def test_closed_unmerged(self):
        pr = _make_pr(state='closed', merged=False)
        result = self._run(pr)
        assert result['recommendation'] == 'closed_unmerged'

    def test_changes_requested(self):
        pr = _make_pr()
        reviews = [_make_review('reviewer1', 'CHANGES_REQUESTED')]
        result = self._run(pr, reviews=reviews)
        assert result['recommendation'] == 'needs_changes'

    def test_not_mergeable(self):
        pr = _make_pr(mergeable=False)
        result = self._run(pr)
        assert result['recommendation'] == 'resolve_conflicts'

    def test_draft(self):
        pr = _make_pr(draft=True)
        result = self._run(pr)
        assert result['recommendation'] == 'draft_wip'

    def test_normal_open_pr(self):
        pr = _make_pr()
        reviews = [_make_review('reviewer1', 'APPROVED')]
        result = self._run(pr, reviews=reviews)
        assert result['recommendation'] == 'proceed'
        assert 'reviewer1' in result['review_states']

    def test_files_changed(self):
        pr = _make_pr()
        files = [_make_file('a.py', 5, 3), _make_file('b.py', 10, 0)]
        result = self._run(pr, files=files)
        assert result['files_changed'] == ['a.py', 'b.py']
        assert result['n_additions'] == 15
        assert result['n_deletions'] == 3

    def test_linked_issues(self):
        pr = _make_pr(body='Fixes #42 and closes #99')
        result = self._run(pr)
        assert 42 in result['linked_issues']
        assert 99 in result['linked_issues']

    def test_priority_merged_over_changes_requested(self):
        """Merged takes precedence even if reviews requested changes."""
        pr = _make_pr(state='closed', merged=True)
        reviews = [_make_review('r1', 'CHANGES_REQUESTED')]
        result = self._run(pr, reviews=reviews)
        assert result['recommendation'] == 'already_merged'

    def test_priority_closed_over_draft(self):
        """Closed-unmerged takes precedence over draft."""
        pr = _make_pr(state='closed', merged=False, draft=True)
        result = self._run(pr)
        assert result['recommendation'] == 'closed_unmerged'
