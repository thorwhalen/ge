"""Internal utilities: gh CLI wrapper, subprocess helpers, URL parsing."""

import json
import subprocess
import re
import shutil
from pathlib import Path

_gh_checked = False


def _check_gh():
    """Verify gh CLI is installed and authenticated (cached after first call)."""
    global _gh_checked
    if _gh_checked:
        return
    if not shutil.which("gh"):
        raise EnvironmentError(
            "gh CLI not found. Install it:\n"
            "  brew install gh          # macOS\n"
            "  sudo apt install gh      # Debian/Ubuntu\n"
            "  https://cli.github.com   # other platforms\n"
            "Then run: gh auth login"
        )
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise EnvironmentError("gh CLI not authenticated. Run:\n  gh auth login")
    _gh_checked = True


def gh_api(endpoint, *, method="GET", params=None, paginate=False, raw=False):
    """Call the GitHub REST API via gh CLI.

    >>> # gh_api('repos/octocat/Hello-World/issues/1')
    """
    _check_gh()
    cmd = ["gh", "api", endpoint]
    if method != "GET":
        cmd.extend(["-X", method])
    if paginate:
        cmd.append("--paginate")
    for k, v in (params or {}).items():
        cmd.extend(["-f", f"{k}={v}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gh api {endpoint} failed: {result.stderr.strip()}")
    if raw:
        return result.stdout
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # gh may return HTML on rate limiting or auth errors
        preview = result.stdout[:200]
        raise RuntimeError(
            f"gh api {endpoint} returned non-JSON response "
            f"(possible rate limit or auth issue): {preview!r}"
        )


def gh_auth_token():
    """Get the current gh auth token for authenticated downloads.

    >>> # token = gh_auth_token()
    """
    _check_gh()
    result = subprocess.run(
        ["gh", "auth", "token"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to get gh auth token: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_repo_spec(repo_spec):
    """Parse 'owner/repo' or full GitHub URL into (owner, repo).

    >>> parse_repo_spec('thorwhalen/dol')
    ('thorwhalen', 'dol')
    >>> parse_repo_spec('https://github.com/thorwhalen/dol')
    ('thorwhalen', 'dol')
    >>> parse_repo_spec('https://github.com/thorwhalen/dol/issues/42')
    ('thorwhalen', 'dol')
    """
    repo_spec = repo_spec.strip().rstrip("/")
    # Full URL
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)", repo_spec)
    if m:
        return m.group(1), m.group(2)
    # owner/repo
    parts = repo_spec.split("/")
    if len(parts) == 2:
        return parts[0], parts[1]
    raise ValueError(
        f"Cannot parse repo spec: {repo_spec!r}. Expected 'owner/repo' or a GitHub URL."
    )


def parse_github_url(url):
    """Parse a full GitHub issue/PR/discussion URL into (owner, repo, number, kind).

    >>> parse_github_url('https://github.com/thorwhalen/dol/issues/42')
    ('thorwhalen', 'dol', 42, 'issue')
    >>> parse_github_url('https://github.com/thorwhalen/dol/pull/7')
    ('thorwhalen', 'dol', 7, 'pr')
    >>> parse_github_url('https://github.com/thorwhalen/dol/discussions/5')
    ('thorwhalen', 'dol', 5, 'discussion')
    """
    m = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/(issues|pull|discussions)/(\d+)", url
    )
    if not m:
        raise ValueError(f"Cannot parse GitHub URL: {url!r}")
    kind_map = {"issues": "issue", "pull": "pr", "discussions": "discussion"}
    kind = kind_map[m.group(3)]
    return m.group(1), m.group(2), int(m.group(4)), kind


# Backward compatibility alias
parse_issue_url = parse_github_url


def extract_media_urls(markdown):
    """Extract image and video URLs from GitHub-flavored markdown.

    Returns list of dicts with keys: url, alt, kind ('image' or 'video').

    >>> urls = extract_media_urls('![screenshot](https://example.com/img.png)')
    >>> urls[0]['kind']
    'image'
    """
    results = []
    seen = set()

    # Markdown images: ![alt](url)
    for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", markdown):
        url = m.group(2)
        if url not in seen:
            seen.add(url)
            results.append({"url": url, "alt": m.group(1), "kind": "image"})

    # HTML img tags: <img src="url" ...>
    for m in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', markdown, re.I):
        url = m.group(1)
        if url not in seen:
            seen.add(url)
            results.append({"url": url, "alt": "", "kind": "image"})

    # HTML video tags and GitHub video attachments
    for m in re.finditer(r'<video[^>]+src=["\']([^"\']+)["\']', markdown, re.I):
        url = m.group(1)
        if url not in seen:
            seen.add(url)
            results.append({"url": url, "alt": "", "kind": "video"})

    # GitHub user-attached videos often appear as plain URLs ending in .mp4/.mov/.webm
    for m in re.finditer(r"https?://[^\s)<]+\.(?:mp4|mov|webm|avi)", markdown, re.I):
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            results.append({"url": url, "alt": "", "kind": "video"})

    return results


def rewrite_media_refs(markdown, url_to_local):
    """Replace media URLs in markdown with local file paths.

    >>> md = '![bug](https://example.com/bug.png)'
    >>> rewrite_media_refs(md, {'https://example.com/bug.png': '.ge/media/bug.png'})
    '![bug](.ge/media/bug.png)'
    """
    for url, local in url_to_local.items():
        markdown = markdown.replace(url, local)
    return markdown


def ensure_dir(path):
    """Create directory if it doesn't exist, return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def check_ffmpeg():
    """Check if ffmpeg is available."""
    if not shutil.which("ffmpeg"):
        raise EnvironmentError(
            "ffmpeg not found (needed for video frame extraction). Install it:\n"
            "  brew install ffmpeg       # macOS\n"
            "  sudo apt install ffmpeg   # Debian/Ubuntu\n"
            "  https://ffmpeg.org        # other platforms"
        )
