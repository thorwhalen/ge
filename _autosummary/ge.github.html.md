# ge.github

GitHub data fetching via gh CLI.

Provides functions to retrieve issues, PRs, comments, timeline events,
related commits, and referenced code – all through the gh CLI so that
private repo access is handled by the user’s existing gh auth.

### Functions

| [`find_related_commits`](#ge.github.find_related_commits)(repo, issue_number, \*)   | Find recent commits that reference this issue number.                   |
|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`find_related_prs`](#ge.github.find_related_prs)(repo, issue_number)           | Find PRs that reference or close this issue.                            |
| [`get_comments`](#ge.github.get_comments)(repo, number)                     | Fetch all comments on an issue or PR.                                   |
| [`get_commit_status`](#ge.github.get_commit_status)(repo, ref)                   | Fetch the combined commit status (CI checks) for a git ref.             |
| [`get_default_branch`](#ge.github.get_default_branch)(repo)                       | Get the default branch name for a repo.                                 |
| [`get_discussion`](#ge.github.get_discussion)(repo, number)                   | Fetch a GitHub Discussion via GraphQL (discussions aren't in REST API). |
| [`get_file_at_ref`](#ge.github.get_file_at_ref)(repo, path, \*[, ref])         | Fetch a file's content at a specific git ref (branch, tag, sha).        |
| [`get_issue`](#ge.github.get_issue)(repo, number)                        | Fetch a GitHub issue with body, labels, assignees, state, etc.          |
| [`get_pr`](#ge.github.get_pr)(repo, number)                           | Fetch a GitHub pull request with body, diff stats, merge state, etc.    |
| [`get_pr_diff`](#ge.github.get_pr_diff)(repo, number)                      | Fetch the raw diff of a PR.                                             |
| [`get_pr_files`](#ge.github.get_pr_files)(repo, number)                     | Fetch the list of files changed in a PR.                                |
| [`get_review_comments`](#ge.github.get_review_comments)(repo, number)              | Fetch inline review comments on a PR (code-level comments).             |
| [`get_reviews`](#ge.github.get_reviews)(repo, number)                      | Fetch PR reviews (approved, changes requested, etc.).                   |
| [`get_timeline`](#ge.github.get_timeline)(repo, number)                     | Fetch the issue/PR timeline (events: referenced, closed, labeled, ...). |

### ge.github.find_related_commits(repo, issue_number, , limit=20)

Find recent commits that reference this issue number.

```pycon
>>> # commits = find_related_commits('owner/repo', 42)
```

### ge.github.find_related_prs(repo, issue_number)

Find PRs that reference or close this issue.

Uses the timeline API to find cross-referenced PRs, and also searches
for PRs mentioning the issue number.

```pycon
>>> # prs = find_related_prs('owner/repo', 42)
```

### ge.github.get_comments(repo, number)

Fetch all comments on an issue or PR.

```pycon
>>> # comments = get_comments('owner/repo', 42)
```

### ge.github.get_commit_status(repo, ref)

Fetch the combined commit status (CI checks) for a git ref.

```pycon
>>> # status = get_commit_status('owner/repo', 'abc123')
```

### ge.github.get_default_branch(repo)

Get the default branch name for a repo.

```pycon
>>> # branch = get_default_branch('owner/repo')
```

### ge.github.get_discussion(repo, number)

Fetch a GitHub Discussion via GraphQL (discussions aren’t in REST API).

```pycon
>>> # disc = get_discussion('owner/repo', 5)
```

### ge.github.get_file_at_ref(repo, path, , ref='HEAD')

Fetch a file’s content at a specific git ref (branch, tag, sha).

```pycon
>>> # content = get_file_at_ref('owner/repo', 'src/main.py', ref='main')
```

### ge.github.get_issue(repo, number)

Fetch a GitHub issue with body, labels, assignees, state, etc.

```pycon
>>> # issue = get_issue('owner/repo', 42)
```

### ge.github.get_pr(repo, number)

Fetch a GitHub pull request with body, diff stats, merge state, etc.

```pycon
>>> # pr = get_pr('owner/repo', 7)
```

### ge.github.get_pr_diff(repo, number)

Fetch the raw diff of a PR.

```pycon
>>> # diff = get_pr_diff('owner/repo', 7)
```

### ge.github.get_pr_files(repo, number)

Fetch the list of files changed in a PR.

```pycon
>>> # files = get_pr_files('owner/repo', 7)
```

### ge.github.get_review_comments(repo, number)

Fetch inline review comments on a PR (code-level comments).

```pycon
>>> # review_comments = get_review_comments('owner/repo', 7)
```

### ge.github.get_reviews(repo, number)

Fetch PR reviews (approved, changes requested, etc.).

```pycon
>>> # reviews = get_reviews('owner/repo', 7)
```

### ge.github.get_timeline(repo, number)

Fetch the issue/PR timeline (events: referenced, closed, labeled, …).

This gives us cross-references, commits that mention the issue, etc.

```pycon
>>> # events = get_timeline('owner/repo', 42)
```
