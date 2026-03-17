"""GitHub data fetching via gh CLI.

Provides functions to retrieve issues, PRs, comments, timeline events,
related commits, and referenced code -- all through the gh CLI so that
private repo access is handled by the user's existing gh auth.
"""

from ge.util import gh_api, parse_repo_spec


# ---------------------------------------------------------------------------
# Core fetchers
# ---------------------------------------------------------------------------


def get_issue(repo, number):
    """Fetch a GitHub issue with body, labels, assignees, state, etc.

    >>> # issue = get_issue('owner/repo', 42)
    """
    owner, name = parse_repo_spec(repo)
    return gh_api(f"repos/{owner}/{name}/issues/{number}")


def get_pr(repo, number):
    """Fetch a GitHub pull request with body, diff stats, merge state, etc.

    >>> # pr = get_pr('owner/repo', 7)
    """
    owner, name = parse_repo_spec(repo)
    return gh_api(f"repos/{owner}/{name}/pulls/{number}")


def get_comments(repo, number):
    """Fetch all comments on an issue or PR.

    >>> # comments = get_comments('owner/repo', 42)
    """
    owner, name = parse_repo_spec(repo)
    return gh_api(
        f"repos/{owner}/{name}/issues/{number}/comments",
        paginate=True,
    )


def get_review_comments(repo, number):
    """Fetch inline review comments on a PR (code-level comments).

    >>> # review_comments = get_review_comments('owner/repo', 7)
    """
    owner, name = parse_repo_spec(repo)
    return gh_api(
        f"repos/{owner}/{name}/pulls/{number}/comments",
        paginate=True,
    )


def get_reviews(repo, number):
    """Fetch PR reviews (approved, changes requested, etc.).

    >>> # reviews = get_reviews('owner/repo', 7)
    """
    owner, name = parse_repo_spec(repo)
    return gh_api(
        f"repos/{owner}/{name}/pulls/{number}/reviews",
        paginate=True,
    )


def get_timeline(repo, number):
    """Fetch the issue/PR timeline (events: referenced, closed, labeled, ...).

    This gives us cross-references, commits that mention the issue, etc.

    >>> # events = get_timeline('owner/repo', 42)
    """
    owner, name = parse_repo_spec(repo)
    # Timeline API is in preview; gh handles the accept header for us
    return gh_api(
        f"repos/{owner}/{name}/issues/{number}/timeline",
        paginate=True,
    )


def get_pr_diff(repo, number):
    """Fetch the raw diff of a PR.

    >>> # diff = get_pr_diff('owner/repo', 7)
    """
    owner, name = parse_repo_spec(repo)
    # gh api with accept header for diff format
    import subprocess

    result = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{owner}/{name}/pulls/{number}",
            "-H",
            "Accept: application/vnd.github.diff",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get PR diff: {result.stderr.strip()}")
    return result.stdout


def get_pr_files(repo, number):
    """Fetch the list of files changed in a PR.

    >>> # files = get_pr_files('owner/repo', 7)
    """
    owner, name = parse_repo_spec(repo)
    return gh_api(
        f"repos/{owner}/{name}/pulls/{number}/files",
        paginate=True,
    )


# ---------------------------------------------------------------------------
# Cross-reference & search
# ---------------------------------------------------------------------------


def find_related_prs(repo, issue_number):
    """Find PRs that reference or close this issue.

    Uses the timeline API to find cross-referenced PRs, and also searches
    for PRs mentioning the issue number.

    >>> # prs = find_related_prs('owner/repo', 42)
    """
    owner, name = parse_repo_spec(repo)
    related = []
    seen = set()

    # From timeline events
    try:
        events = get_timeline(repo, issue_number)
        for ev in events:
            if not isinstance(ev, dict):
                continue
            # cross-referenced events link to PRs
            if ev.get("event") == "cross-referenced":
                source = ev.get("source", {}).get("issue", {})
                if source.get("pull_request") and source.get("number") not in seen:
                    seen.add(source["number"])
                    related.append(
                        {
                            "number": source["number"],
                            "title": source.get("title", ""),
                            "state": source.get("state", ""),
                            "url": source.get("html_url", ""),
                        }
                    )
    except Exception:
        pass  # Timeline may fail on some repos; fall through to search

    # Search for PRs mentioning this issue
    try:
        results = gh_api(
            "search/issues",
            params={
                "q": f"repo:{owner}/{name} type:pr {issue_number} in:body,comments",
            },
        )
        for item in results.get("items", []):
            if item["number"] not in seen:
                seen.add(item["number"])
                related.append(
                    {
                        "number": item["number"],
                        "title": item.get("title", ""),
                        "state": item.get("state", ""),
                        "url": item.get("html_url", ""),
                    }
                )
    except Exception:
        pass

    return related


def find_related_commits(repo, issue_number, *, limit=20):
    """Find recent commits that reference this issue number.

    >>> # commits = find_related_commits('owner/repo', 42)
    """
    owner, name = parse_repo_spec(repo)
    try:
        results = gh_api(
            "search/commits",
            params={
                "q": f"repo:{owner}/{name} #{issue_number}",
                "per_page": str(limit),
            },
        )
        return [
            {
                "sha": item["sha"][:10],
                "message": item["commit"]["message"].split("\n")[0],
                "date": item["commit"]["author"]["date"],
                "url": item["html_url"],
            }
            for item in results.get("items", [])
        ]
    except Exception:
        return []


def get_file_at_ref(repo, path, *, ref="HEAD"):
    """Fetch a file's content at a specific git ref (branch, tag, sha).

    >>> # content = get_file_at_ref('owner/repo', 'src/main.py', ref='main')
    """
    owner, name = parse_repo_spec(repo)
    import base64

    data = gh_api(f"repos/{owner}/{name}/contents/{path}", params={"ref": ref})
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return data.get("content", "")


def get_commit_status(repo, ref):
    """Fetch the combined commit status (CI checks) for a git ref.

    >>> # status = get_commit_status('owner/repo', 'abc123')
    """
    owner, name = parse_repo_spec(repo)
    return gh_api(f"repos/{owner}/{name}/commits/{ref}/status")


def get_default_branch(repo):
    """Get the default branch name for a repo.

    >>> # branch = get_default_branch('owner/repo')
    """
    owner, name = parse_repo_spec(repo)
    data = gh_api(f"repos/{owner}/{name}")
    return data.get("default_branch", "main")


def get_discussion(repo, number):
    """Fetch a GitHub Discussion via GraphQL (discussions aren't in REST API).

    >>> # disc = get_discussion('owner/repo', 5)
    """
    owner, name = parse_repo_spec(repo)
    import subprocess

    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        discussion(number: $number) {
          title
          body
          url
          createdAt
          author { login }
          comments(first: 50) {
            nodes {
              body
              createdAt
              author { login }
            }
          }
        }
      }
    }
    """
    result = subprocess.run(
        [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={number}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get discussion: {result.stderr.strip()}")
    import json

    data = json.loads(result.stdout)
    return data.get("data", {}).get("repository", {}).get("discussion")
