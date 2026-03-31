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

from pathlib import Path as _Path

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
from ge.media import (
    process_all_media,
    extract_video_frames,
    describe_images,
    copy_images_to_clipboard,
)
from ge.util import parse_github_url, resolve_target


def prepare(
    url_or_spec, number=None, *, output_dir=None, describe_media=True, **kwargs
):
    """Prepare context from a GitHub URL or repo+number.

    Automatically detects whether it's an issue, PR, or discussion.

    When ``describe_media`` is True (default) and the ``anthropic`` package
    is available, downloaded images are described via the Claude API so
    the agent gets visual context without manual image pasting.

    >>> # ctx = ge.prepare('https://github.com/owner/repo/issues/42')
    >>> # ctx = ge.prepare('owner/repo', 42)
    >>> # ctx = ge.prepare('https://github.com/owner/repo/discussions/5')
    """
    if number is None:
        # Parse from URL
        owner, repo, number, kind = parse_github_url(url_or_spec)
        repo_spec = f"{owner}/{repo}"
    else:
        repo_spec = url_or_spec
        # Probe whether it's a PR or issue
        try:
            data = get_pr(repo_spec, number)
            kind = "pr"
        except Exception:
            kind = "issue"

    if kind == "pr":
        return prepare_pr(
            repo_spec,
            number,
            output_dir=output_dir,
            describe_media=describe_media,
            **kwargs,
        )
    elif kind == "discussion":
        return prepare_discussion(
            repo_spec,
            number,
            output_dir=output_dir,
            describe_media=describe_media,
            **kwargs,
        )
    else:
        return prepare_issue(
            repo_spec,
            number,
            output_dir=output_dir,
            describe_media=describe_media,
            **kwargs,
        )


_SKILLS_DIR = _Path(__file__).parent / "data" / "skills"


def install_skills(*, target_dir=None):
    """Symlink ge skills into ~/.claude/skills/ for global discovery.

    Creates symlinks from ``target_dir/<skill>`` to the skill folders bundled
    with the ge package.  Existing correct symlinks are left alone; a warning
    is printed if a symlink points elsewhere.

    Args:
        target_dir: Destination directory.  Defaults to ``~/.claude/skills/``.
    """
    if target_dir is None:
        target_dir = _Path.home() / ".claude" / "skills"
    else:
        target_dir = _Path(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)

    for source in sorted(_SKILLS_DIR.iterdir()):
        if not source.is_dir():
            continue
        link = target_dir / source.name
        if link.is_symlink():
            if link.resolve() == source.resolve():
                print(f"  ✓ {source.name} (already installed)")
                continue
            else:
                print(
                    f"  ⚠ {source.name}: symlink exists but points to "
                    f"{link.resolve()}, expected {source.resolve()}. Skipping."
                )
                continue
        elif link.exists():
            print(
                f"  ⚠ {source.name}: {link} already exists and is not a "
                f"symlink. Skipping."
            )
            continue
        link.symlink_to(source.resolve())
        print(f"  ✓ {source.name} -> {source.resolve()}")

    print(f"\nSkills installed to {target_dir}")


def uninstall_skills(*, target_dir=None):
    """Remove ge skill symlinks from ~/.claude/skills/.

    Only removes symlinks that point back into the ge package's skill
    directory.  Non-symlinks and symlinks owned by other packages are
    left untouched.

    Args:
        target_dir: Directory to remove from.  Defaults to ``~/.claude/skills/``.
    """
    if target_dir is None:
        target_dir = _Path.home() / ".claude" / "skills"
    else:
        target_dir = _Path(target_dir)

    if not target_dir.exists():
        print("Nothing to uninstall (target directory does not exist).")
        return

    removed = 0
    for source in sorted(_SKILLS_DIR.iterdir()):
        if not source.is_dir():
            continue
        link = target_dir / source.name
        if link.is_symlink() and link.resolve() == source.resolve():
            link.unlink()
            print(f"  ✓ Removed {source.name}")
            removed += 1
        elif link.is_symlink():
            print(
                f"  · Skipped {source.name} (symlink points to "
                f"{link.resolve()}, not owned by ge)"
            )
        elif link.exists():
            print(f"  · Skipped {source.name} (not a symlink, not owned by ge)")

    if removed:
        print(f"\n{removed} skill(s) uninstalled from {target_dir}")
    else:
        print("\nNo ge skills found to uninstall.")


__all__ = [
    "prepare",
    "prepare_issue",
    "prepare_pr",
    "prepare_discussion",
    "analyze_issue",
    "analyze_pr",
    "get_issue",
    "get_pr",
    "get_comments",
    "get_pr_diff",
    "get_discussion",
    "find_related_prs",
    "find_related_commits",
    "process_all_media",
    "extract_video_frames",
    "describe_images",
    "copy_images_to_clipboard",
    "resolve_target",
    "install_skills",
    "uninstall_skills",
]
