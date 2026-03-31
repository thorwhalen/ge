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

    Returns list of dicts with keys: url, alt, kind ('image', 'video', or 'unknown').

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

    # Bare GitHub user-attachment URLs (no extension — could be image or video,
    # resolved after download via content-type detection)
    for m in re.finditer(
        r"https://github\.com/user-attachments/assets/[\w-]+", markdown
    ):
        url = m.group(0)
        if url not in seen:
            seen.add(url)
            results.append({"url": url, "alt": "", "kind": "unknown"})

    return results


def rewrite_media_refs(markdown, url_to_local):
    """Replace media URLs in markdown with local file paths.

    >>> md = '![bug](https://example.com/bug.png)'
    >>> rewrite_media_refs(md, {'https://example.com/bug.png': 'media/bug.png'})
    '![bug](media/bug.png)'
    """
    for url, local in url_to_local.items():
        markdown = markdown.replace(url, local)
    return markdown


def ensure_dir(path):
    """Create directory if it doesn't exist, return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_output_dir(repo, number, kind="issue"):
    """Compute the default output directory under the user's cache.

    Returns ``~/.cache/ge/<owner>/<repo>/<kind>_<number>``, e.g.
    ``~/.cache/ge/thorwhalen/dol/issue_42``.

    >>> import os; home = os.path.expanduser('~')
    >>> p = default_output_dir('thorwhalen/dol', 42, 'issue')
    >>> str(p) == os.path.join(home, '.cache', 'ge', 'thorwhalen', 'dol', 'issue_42')
    True
    """
    owner, name = parse_repo_spec(repo)
    return Path.home() / ".cache" / "ge" / owner / name / f"{kind}_{number}"


def resolve_target(user_input, *, current_repo=None):
    """Resolve flexible user input into a structured target for ge workflows.

    Accepts any of these forms:
      - A GitHub URL: ``https://github.com/owner/repo/issues/42``
      - A folder path to pre-prepared context: ``~/.cache/ge/owner/repo/issue_42``
      - A bare number: ``42`` or ``#42`` (uses *current_repo*)
      - ``owner/repo#42`` or ``owner/repo/42``
      - ``owner/repo 42``

    Returns a dict with:
      - ``repo``: ``"owner/repo"`` (or None if only a folder was given)
      - ``number``: int
      - ``kind``: ``"issue"`` | ``"pr"`` | ``"discussion"`` | None
      - ``context_dir``: path to pre-prepared context (str or None)
      - ``context_md``: path to the context markdown file (str or None)
      - ``has_prepared_context``: bool — whether context files already exist
      - ``source``: how the input was resolved (``"url"``, ``"folder"``,
        ``"number"``, ``"repo_number"``)

    >>> r = resolve_target('https://github.com/owner/repo/issues/42')
    >>> r['repo'], r['number'], r['kind'], r['source']
    ('owner/repo', 42, 'issue', 'url')

    >>> r = resolve_target('#42', current_repo='owner/repo')
    >>> r['repo'], r['number'], r['source']
    ('owner/repo', 42, 'number')

    >>> r = resolve_target('owner/repo#42')
    >>> r['repo'], r['number'], r['source']
    ('owner/repo', 42, 'repo_number')
    """
    user_input = str(user_input).strip()

    repo = None
    number = None
    kind = None
    context_dir = None
    source = None

    # --- 1. Folder path ---
    expanded = Path(user_input).expanduser()
    if expanded.is_dir():
        context_dir = str(expanded)
        # Try to infer repo/number/kind from folder name convention:
        # ~/.cache/ge/<owner>/<repo>/<kind>_<number>
        m = re.search(r"(issue|pr|discussion)_(\d+)$", expanded.name)
        if m:
            kind = m.group(1)
            number = int(m.group(2))
            # Try to get owner/repo from parent dirs
            parts = expanded.parts
            # Look for the pattern: .../<owner>/<repo>/<kind>_<number>
            if len(parts) >= 3:
                repo = f"{parts[-3]}/{parts[-2]}"
        source = "folder"

    # --- 2. GitHub URL ---
    elif re.match(r"https?://github\.com/", user_input):
        owner, name, number, kind = parse_github_url(user_input)
        repo = f"{owner}/{name}"
        source = "url"

    # --- 3. owner/repo#number or owner/repo/number ---
    elif re.match(r"[^/]+/[^/#]+[#/]\d+$", user_input):
        m = re.match(r"([^/]+/[^/#]+)[#/](\d+)$", user_input)
        repo = m.group(1)
        number = int(m.group(2))
        source = "repo_number"

    # --- 4. "owner/repo 42" (space-separated) ---
    elif re.match(r"[^/]+/[^/\s]+\s+#?\d+$", user_input):
        m = re.match(r"([^/]+/[^/\s]+)\s+#?(\d+)$", user_input)
        repo = m.group(1)
        number = int(m.group(2))
        source = "repo_number"

    # --- 5. Bare number: "42" or "#42" ---
    elif re.match(r"#?\d+$", user_input):
        number = int(user_input.lstrip("#"))
        repo = current_repo
        source = "number"

    else:
        raise ValueError(
            f"Cannot resolve target: {user_input!r}. Expected a GitHub URL, "
            f"folder path, owner/repo#number, or a bare issue number."
        )

    # --- Check for pre-prepared context ---
    if context_dir is None and repo and number and kind:
        candidate = default_output_dir(repo, number, kind)
        if candidate.is_dir():
            context_dir = str(candidate)

    # Even without kind, try all three
    if context_dir is None and repo and number:
        for k in ("issue", "pr", "discussion"):
            candidate = default_output_dir(repo, number, k)
            if candidate.is_dir():
                context_dir = str(candidate)
                if kind is None:
                    kind = k
                break

    # Find the context markdown file
    context_md = None
    has_prepared_context = False
    if context_dir:
        ctx_dir = Path(context_dir)
        # Look for *_context.md
        md_files = list(ctx_dir.glob("*_context.md"))
        if md_files:
            context_md = str(md_files[0])
            has_prepared_context = True

    return {
        "repo": repo,
        "number": number,
        "kind": kind,
        "context_dir": context_dir,
        "context_md": context_md,
        "has_prepared_context": has_prepared_context,
        "source": source,
    }


def check_ffmpeg():
    """Check if ffmpeg is available."""
    if not shutil.which("ffmpeg"):
        raise EnvironmentError(
            "ffmpeg not found (needed for video frame extraction). Install it:\n"
            "  brew install ffmpeg       # macOS\n"
            "  sudo apt install ffmpeg   # Debian/Ubuntu\n"
            "  https://ffmpeg.org        # other platforms"
        )
