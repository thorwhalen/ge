"""GitHub-backed durable memory for autonomous agent execution.

Three stores exposed as ``collections.abc`` facades. GitHub is the single
source of truth; a thin per-store local snapshot under ``.ge/cache/`` is a
hydrate-only cache (disposable, never authoritative).

- :class:`RoadmapStore` — ``MutableMapping[task_id, TaskRecord]`` over a
  *roadmap issue* whose body holds a markdown task list between
  ``<!-- ge:roadmap:begin -->`` / ``<!-- ge:roadmap:end -->`` markers.
- :class:`DecisionLog` — append-only ``Iterable[Decision]`` backed by
  decision-tagged comments on an issue or PR.
- :class:`TriageBacklog` — ``MutableMapping[issue_ref, TriageVerdict]``
  spanning multiple repos. Backed by a tracking issue containing a fenced
  JSON block (``<!-- ge:triage:begin -->`` / ``end``). Cross-repo refs use
  ``"owner/repo#N"``.

The :func:`github_memory` factory bundles these into a mall.

Design notes
------------
- Writes go to GitHub *first*; the local cache is updated as a side-effect on
  successful round-trip. A failed write does **not** poison the cache.
- ``check_requirements`` verifies ``gh`` is installed, authenticated, and
  carries the ``project`` scope (needed if the user later switches the
  triage backend to a GitHub Project).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterable, Iterator, Mapping, MutableMapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ge.util import _check_gh, gh_api, parse_repo_spec


# ---------------------------------------------------------------------------
# Constants / markers
# ---------------------------------------------------------------------------

ROADMAP_BEGIN = "<!-- ge:roadmap:begin -->"
ROADMAP_END = "<!-- ge:roadmap:end -->"
DOING_MARKER = "<!-- ge:doing -->"
TRIAGE_BEGIN = "<!-- ge:triage:begin -->"
TRIAGE_END = "<!-- ge:triage:end -->"
DECISION_TAG = "<!-- ge:decision -->"

_TASK_LINE_RE = re.compile(
    r"^- \[( |x|X)\] (.*?)\s*(<!-- ge:doing -->)?\s*$",
)
_ISSUE_REF_RE = re.compile(r"^([^/\s]+)/([^/\s#]+)#(\d+)$")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class TaskState(str, Enum):
    """Roadmap task lifecycle state."""

    todo = "todo"
    doing = "doing"
    done = "done"


@dataclass
class TaskRecord:
    """A single roadmap task.

    ``id`` is a stable slug derived from the title. ``metadata`` holds any
    extra agent-attached fields (e.g. links to PRs).
    """

    id: str
    title: str
    state: TaskState = TaskState.todo
    metadata: dict = field(default_factory=dict)


class TriageVerdict(str, Enum):
    """Triage classification for an issue."""

    stale = "stale"
    closeable = "closeable"
    fixable = "fixable"
    blocked = "blocked"


@dataclass
class TriageEntry:
    """A cross-repo triage backlog entry."""

    ref: str  # "owner/repo#N"
    verdict: TriageVerdict
    order: int = 0
    rationale: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class Decision:
    """A logged decision (rendered as a tagged comment on an issue/PR)."""

    summary: str
    rationale: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: Optional[str] = None
    url: Optional[str] = None


# ---------------------------------------------------------------------------
# Local cache (plain JSON, disposable)
# ---------------------------------------------------------------------------


def _cache_root(repo_root: Optional[Path] = None) -> Path:
    """Return the local cache root, ``<repo_root>/.ge/cache``.

    >>> p = _cache_root(Path('/tmp'))
    >>> str(p).endswith('.ge/cache')
    True
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    return root / ".ge" / "cache"


def _cache_write(path: Path, payload: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def _cache_read(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Slugify helper (stable task ids)
# ---------------------------------------------------------------------------


def _slugify(title: str, *, max_len: int = 60) -> str:
    """Convert a task title to a stable slug suitable as a dict key.

    >>> _slugify('Fix #42: the thing!')
    'fix-42-the-thing'
    >>> _slugify('  Hello   World  ')
    'hello-world'
    """
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len] or "task"


# ---------------------------------------------------------------------------
# Markdown task-list parsing / rendering
# ---------------------------------------------------------------------------


def _parse_task_block(block: str) -> list[TaskRecord]:
    """Parse the contents of a roadmap block into TaskRecords.

    >>> tasks = _parse_task_block('- [ ] Foo\\n- [x] Bar\\n- [ ] Baz <!-- ge:doing -->')
    >>> [(t.title, t.state.value) for t in tasks]
    [('Foo', 'todo'), ('Bar', 'done'), ('Baz', 'doing')]
    """
    out = []
    seen_ids = set()
    for line in block.splitlines():
        m = _TASK_LINE_RE.match(line.rstrip())
        if not m:
            continue
        check = m.group(1).lower()
        title = m.group(2).strip()
        doing = bool(m.group(3))
        if check == "x":
            state = TaskState.done
        elif doing:
            state = TaskState.doing
        else:
            state = TaskState.todo
        base = _slugify(title)
        tid = base
        n = 2
        while tid in seen_ids:
            tid = f"{base}-{n}"
            n += 1
        seen_ids.add(tid)
        out.append(TaskRecord(id=tid, title=title, state=state))
    return out


def _render_task_block(tasks: Iterable[TaskRecord]) -> str:
    """Render TaskRecords as a markdown task list.

    >>> _render_task_block([TaskRecord('x', 'Foo', TaskState.done)])
    '- [x] Foo'
    """
    lines = []
    for t in tasks:
        check = "x" if t.state == TaskState.done else " "
        suffix = f" {DOING_MARKER}" if t.state == TaskState.doing else ""
        lines.append(f"- [{check}] {t.title}{suffix}")
    return "\n".join(lines)


def _splice_block(
    body: str, begin: str, end: str, inner: str, *, header: str = ""
) -> str:
    """Replace the content between ``begin`` and ``end`` markers in ``body``.

    If the markers do not exist, append a new block (optionally preceded by
    ``header``) at the end of ``body``.

    >>> _splice_block('x', '<!--B-->', '<!--E-->', 'inside')
    'x\\n\\n<!--B-->\\ninside\\n<!--E-->'
    >>> _splice_block('pre <!--B-->\\nold\\n<!--E--> post', '<!--B-->', '<!--E-->', 'new')
    'pre <!--B-->\\nnew\\n<!--E--> post'
    """
    pattern = re.compile(
        re.escape(begin) + r".*?" + re.escape(end), re.DOTALL
    )
    replacement = f"{begin}\n{inner}\n{end}"
    if pattern.search(body):
        return pattern.sub(replacement, body)
    sep = "\n\n" if body and not body.endswith("\n\n") else ""
    extras = (header + "\n") if header else ""
    return f"{body}{sep}{extras}{replacement}"


def _extract_block(body: str, begin: str, end: str) -> Optional[str]:
    """Return the text between begin/end markers, or None if not found.

    >>> _extract_block('x <!--B-->\\nhi\\n<!--E--> y', '<!--B-->', '<!--E-->')
    'hi'
    >>> _extract_block('nope', '<!--B-->', '<!--E-->') is None
    True
    """
    m = re.search(
        re.escape(begin) + r"\s*\n?(.*?)\n?\s*" + re.escape(end),
        body,
        re.DOTALL,
    )
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Issue body read / write helpers
# ---------------------------------------------------------------------------


def _get_issue_body(repo: str, number: int) -> dict:
    """Fetch issue dict (title, body, html_url, ...)."""
    owner, name = parse_repo_spec(repo)
    return gh_api(f"repos/{owner}/{name}/issues/{number}")


def _patch_issue_body(repo: str, number: int, body: str) -> dict:
    """PATCH an issue body via gh api."""
    _check_gh()
    owner, name = parse_repo_spec(repo)
    cmd = [
        "gh",
        "api",
        "-X",
        "PATCH",
        f"repos/{owner}/{name}/issues/{number}",
        "-f",
        f"body={body}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to PATCH issue {repo}#{number}: {result.stderr.strip()}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def _post_issue_comment(repo: str, number: int, body: str) -> dict:
    """POST a comment on an issue/PR via gh api."""
    _check_gh()
    owner, name = parse_repo_spec(repo)
    cmd = [
        "gh",
        "api",
        "-X",
        "POST",
        f"repos/{owner}/{name}/issues/{number}/comments",
        "-f",
        f"body={body}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to comment on {repo}#{number}: {result.stderr.strip()}"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# RoadmapStore
# ---------------------------------------------------------------------------


class RoadmapStore(MutableMapping):
    """A ``MutableMapping[task_id, TaskRecord]`` over a roadmap issue.

    Iteration yields task ids in roadmap order. Mutations rewrite the
    roadmap issue body in place; the local cache is updated on success.

    Initialise via :func:`github_memory` or directly with ``(repo, issue)``.
    The roadmap issue body should contain (or will be augmented with) a
    block::

        <!-- ge:roadmap:begin -->
        - [ ] Task one
        - [x] Task two
        <!-- ge:roadmap:end -->

    Tasks outside the block are ignored.
    """

    def __init__(
        self,
        repo: str,
        issue_number: int,
        *,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.repo = repo
        self.issue_number = int(issue_number)
        self._cache_dir = Path(cache_dir) if cache_dir else _cache_root()
        self._cache_path = self._cache_dir / (
            f"roadmap_{repo.replace('/', '_')}_{self.issue_number}.json"
        )

    # ----- backing store I/O ----- #

    def _fetch_tasks(self) -> list[TaskRecord]:
        issue = _get_issue_body(self.repo, self.issue_number)
        body = issue.get("body") or ""
        block = _extract_block(body, ROADMAP_BEGIN, ROADMAP_END)
        tasks = _parse_task_block(block) if block is not None else []
        self._snapshot(issue, tasks)
        return tasks

    def _snapshot(self, issue: Mapping, tasks: list[TaskRecord]) -> None:
        _cache_write(
            self._cache_path,
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "repo": self.repo,
                "issue_number": self.issue_number,
                "issue_url": issue.get("html_url"),
                "title": issue.get("title"),
                "tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "state": t.state.value,
                        "metadata": t.metadata,
                    }
                    for t in tasks
                ],
            },
        )

    def _write_tasks(self, tasks: list[TaskRecord]) -> None:
        issue = _get_issue_body(self.repo, self.issue_number)
        body = issue.get("body") or ""
        new_inner = _render_task_block(tasks)
        new_body = _splice_block(
            body, ROADMAP_BEGIN, ROADMAP_END, new_inner, header="## Roadmap"
        )
        _patch_issue_body(self.repo, self.issue_number, new_body)
        # refetch to keep cache in sync with server state
        self._snapshot({"html_url": issue.get("html_url"), "title": issue.get("title")}, tasks)

    # ----- public roadmap helpers ----- #

    def hydrate(self) -> list[TaskRecord]:
        """Refresh the local cache from GitHub and return the current task list."""
        return self._fetch_tasks()

    def next_todo(self) -> Optional[TaskRecord]:
        """Return the first ``todo`` task in roadmap order, or None."""
        for t in self._fetch_tasks():
            if t.state == TaskState.todo:
                return t
        return None

    def append(self, title: str, *, state: TaskState = TaskState.todo) -> TaskRecord:
        """Add a new task to the end of the roadmap."""
        tasks = self._fetch_tasks()
        slug = _slugify(title)
        existing_ids = {t.id for t in tasks}
        tid = slug
        n = 2
        while tid in existing_ids:
            tid = f"{slug}-{n}"
            n += 1
        rec = TaskRecord(id=tid, title=title, state=state)
        tasks.append(rec)
        self._write_tasks(tasks)
        return rec

    # ----- MutableMapping interface ----- #

    def __getitem__(self, key: str) -> TaskRecord:
        for t in self._fetch_tasks():
            if t.id == key:
                return t
        raise KeyError(key)

    def __setitem__(self, key: str, value: TaskRecord | TaskState | str) -> None:
        tasks = self._fetch_tasks()
        new = self._coerce(key, value)
        for i, t in enumerate(tasks):
            if t.id == key:
                tasks[i] = new
                self._write_tasks(tasks)
                return
        tasks.append(new)
        self._write_tasks(tasks)

    def __delitem__(self, key: str) -> None:
        tasks = self._fetch_tasks()
        kept = [t for t in tasks if t.id != key]
        if len(kept) == len(tasks):
            raise KeyError(key)
        self._write_tasks(kept)

    def __iter__(self) -> Iterator[str]:
        return iter(t.id for t in self._fetch_tasks())

    def __len__(self) -> int:
        return len(self._fetch_tasks())

    def __contains__(self, key: object) -> bool:
        return any(t.id == key for t in self._fetch_tasks())

    @staticmethod
    def _coerce(key: str, value) -> TaskRecord:
        if isinstance(value, TaskRecord):
            return value
        if isinstance(value, TaskState):
            return TaskRecord(id=key, title=key, state=value)
        if isinstance(value, str):
            return TaskRecord(id=key, title=key, state=TaskState(value))
        raise TypeError(
            f"RoadmapStore values must be TaskRecord/TaskState/str, got {type(value)}"
        )


# ---------------------------------------------------------------------------
# DecisionLog
# ---------------------------------------------------------------------------


class DecisionLog(Iterable):
    """Append-only iterable of :class:`Decision` records.

    Backed by issue/PR comments tagged with ``<!-- ge:decision -->`` on a
    single target (issue or PR). Iteration fetches all comments from
    GitHub, filters by tag, and yields parsed decisions in chronological
    order.

    Significant choices and course-corrections should be appended here so
    they survive into future sessions. Micro-decisions belong in local
    scratch and should be summarised at handover.
    """

    def __init__(
        self,
        repo: str,
        target_number: int,
        *,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.repo = repo
        self.target_number = int(target_number)
        self._cache_dir = Path(cache_dir) if cache_dir else _cache_root()
        self._cache_path = self._cache_dir / (
            f"decisions_{repo.replace('/', '_')}_{self.target_number}.json"
        )

    def append(
        self,
        summary: str,
        *,
        rationale: str = "",
        metadata: Optional[Mapping] = None,
    ) -> Decision:
        """Post a tagged comment recording this decision.

        Returns the :class:`Decision` (with ``url`` and ``created_at``
        populated from the GitHub response on success).
        """
        meta = dict(metadata or {})
        body_parts = [DECISION_TAG, f"### Decision: {summary}"]
        if rationale:
            body_parts.append("")
            body_parts.append(rationale)
        if meta:
            body_parts.append("")
            body_parts.append("```json")
            body_parts.append(json.dumps(meta, indent=2, default=str))
            body_parts.append("```")
        body = "\n".join(body_parts)
        resp = _post_issue_comment(self.repo, self.target_number, body)
        dec = Decision(
            summary=summary,
            rationale=rationale,
            metadata=meta,
            created_at=resp.get("created_at"),
            url=resp.get("html_url"),
        )
        self._append_cache(dec)
        return dec

    def _append_cache(self, dec: Decision) -> None:
        existing = _cache_read(self._cache_path) or {"decisions": []}
        existing["decisions"].append(asdict(dec))
        _cache_write(self._cache_path, existing)

    def __iter__(self) -> Iterator[Decision]:
        owner, name = parse_repo_spec(self.repo)
        comments = gh_api(
            f"repos/{owner}/{name}/issues/{self.target_number}/comments",
            paginate=True,
        )
        out = []
        for c in comments or []:
            body = c.get("body") or ""
            if DECISION_TAG not in body:
                continue
            summary, rationale, meta = _parse_decision_body(body)
            out.append(
                Decision(
                    summary=summary,
                    rationale=rationale,
                    metadata=meta,
                    created_at=c.get("created_at"),
                    url=c.get("html_url"),
                )
            )
        _cache_write(
            self._cache_path,
            {"decisions": [asdict(d) for d in out]},
        )
        return iter(out)


def _parse_decision_body(body: str) -> tuple[str, str, dict]:
    """Parse a decision-tagged comment body.

    >>> s, r, m = _parse_decision_body('<!-- ge:decision -->\\n### Decision: Try X\\n\\nbecause Y')
    >>> s, r, m
    ('Try X', 'because Y', {})
    """
    summary = ""
    rationale = ""
    meta: dict = {}
    text = body.replace(DECISION_TAG, "").strip()
    m = re.match(r"###\s*Decision:\s*(.+)", text)
    if m:
        summary = m.group(1).strip()
        text = text[m.end():].strip()
    code = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if code:
        try:
            meta = json.loads(code.group(1))
        except json.JSONDecodeError:
            meta = {}
        text = (text[: code.start()] + text[code.end():]).strip()
    rationale = text.strip()
    return summary, rationale, meta


# ---------------------------------------------------------------------------
# TriageBacklog
# ---------------------------------------------------------------------------


class TriageBacklog(MutableMapping):
    """Cross-repo triage backlog.

    Keys are issue refs of the form ``"owner/repo#N"``; values are
    :class:`TriageEntry`. Iteration order is the agent-chosen resolution
    order (the ``order`` field).

    Backed by a *tracking issue* whose body holds a JSON block between
    ``<!-- ge:triage:begin -->`` / ``end``. This keeps the implementation
    free of GraphQL/Project dependencies while preserving full cross-repo
    semantics — fully-qualified refs do the heavy lifting.

    Switching to a GitHub Project backend later is a swap of this class's
    I/O methods; the public interface stays the same.
    """

    def __init__(
        self,
        repo: str,
        tracking_issue: int,
        *,
        cache_dir: Optional[Path] = None,
    ) -> None:
        self.repo = repo
        self.tracking_issue = int(tracking_issue)
        self._cache_dir = Path(cache_dir) if cache_dir else _cache_root()
        self._cache_path = self._cache_dir / (
            f"triage_{repo.replace('/', '_')}_{self.tracking_issue}.json"
        )

    # ----- backing I/O ----- #

    def _fetch(self) -> dict[str, TriageEntry]:
        issue = _get_issue_body(self.repo, self.tracking_issue)
        body = issue.get("body") or ""
        block = _extract_block(body, TRIAGE_BEGIN, TRIAGE_END) or "[]"
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            data = []
        entries: dict[str, TriageEntry] = {}
        for d in data:
            ref = d.get("ref")
            if not ref or not _ISSUE_REF_RE.match(ref):
                continue
            entries[ref] = TriageEntry(
                ref=ref,
                verdict=TriageVerdict(d.get("verdict", "fixable")),
                order=int(d.get("order", 0)),
                rationale=d.get("rationale", ""),
                metadata=d.get("metadata", {}),
            )
        _cache_write(
            self._cache_path,
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "tracking_issue": self.tracking_issue,
                "entries": [
                    {
                        "ref": e.ref,
                        "verdict": e.verdict.value,
                        "order": e.order,
                        "rationale": e.rationale,
                        "metadata": e.metadata,
                    }
                    for e in entries.values()
                ],
            },
        )
        return entries

    def _write(self, entries: dict[str, TriageEntry]) -> None:
        ordered = sorted(entries.values(), key=lambda e: (e.order, e.ref))
        payload = [
            {
                "ref": e.ref,
                "verdict": e.verdict.value,
                "order": e.order,
                "rationale": e.rationale,
                "metadata": e.metadata,
            }
            for e in ordered
        ]
        block = json.dumps(payload, indent=2, default=str)
        issue = _get_issue_body(self.repo, self.tracking_issue)
        body = issue.get("body") or ""
        new_body = _splice_block(
            body, TRIAGE_BEGIN, TRIAGE_END, block, header="## Triage backlog"
        )
        _patch_issue_body(self.repo, self.tracking_issue, new_body)

    # ----- MutableMapping ----- #

    def __getitem__(self, key: str) -> TriageEntry:
        entries = self._fetch()
        if key not in entries:
            raise KeyError(key)
        return entries[key]

    def __setitem__(self, key: str, value: TriageEntry | Mapping | TriageVerdict) -> None:
        if not _ISSUE_REF_RE.match(key):
            raise ValueError(
                f"Triage key must be 'owner/repo#N', got {key!r}"
            )
        entries = self._fetch()
        entries[key] = self._coerce(key, value, existing=entries.get(key))
        self._write(entries)

    def __delitem__(self, key: str) -> None:
        entries = self._fetch()
        if key not in entries:
            raise KeyError(key)
        del entries[key]
        self._write(entries)

    def __iter__(self) -> Iterator[str]:
        entries = self._fetch()
        return iter(
            e.ref for e in sorted(entries.values(), key=lambda e: (e.order, e.ref))
        )

    def __len__(self) -> int:
        return len(self._fetch())

    def __contains__(self, key: object) -> bool:
        return key in self._fetch()

    @staticmethod
    def _coerce(
        key: str, value, *, existing: Optional[TriageEntry] = None
    ) -> TriageEntry:
        if isinstance(value, TriageEntry):
            return value
        if isinstance(value, TriageVerdict):
            base = existing or TriageEntry(ref=key, verdict=value)
            base.verdict = value
            return base
        if isinstance(value, Mapping):
            return TriageEntry(
                ref=key,
                verdict=TriageVerdict(value.get("verdict", "fixable")),
                order=int(value.get("order", existing.order if existing else 0)),
                rationale=value.get("rationale", existing.rationale if existing else ""),
                metadata=dict(value.get("metadata", existing.metadata if existing else {})),
            )
        raise TypeError(
            f"TriageBacklog values must be TriageEntry/TriageVerdict/Mapping, "
            f"got {type(value)}"
        )


# ---------------------------------------------------------------------------
# Mall factory
# ---------------------------------------------------------------------------


def github_memory(
    repo: str,
    *,
    roadmap_issue: Optional[int] = None,
    decisions_target: Optional[int] = None,
    triage_issue: Optional[int] = None,
    cache_dir: Optional[Path] = None,
) -> dict[str, object]:
    """Bundle the three stores into a "mall" dict keyed by name.

    Each store is only constructed if its target was provided. ``roadmap``
    requires ``roadmap_issue``; ``decisions`` requires ``decisions_target``
    (the issue or PR number where decisions are logged); ``triage``
    requires ``triage_issue`` (the tracking issue holding the JSON block).

    >>> # mall = github_memory('owner/repo', roadmap_issue=1, decisions_target=1)
    """
    mall: dict[str, object] = {}
    if roadmap_issue is not None:
        mall["roadmap"] = RoadmapStore(repo, roadmap_issue, cache_dir=cache_dir)
    if decisions_target is not None:
        mall["decisions"] = DecisionLog(repo, decisions_target, cache_dir=cache_dir)
    if triage_issue is not None:
        mall["triage"] = TriageBacklog(repo, triage_issue, cache_dir=cache_dir)
    return mall


# ---------------------------------------------------------------------------
# check_requirements
# ---------------------------------------------------------------------------


def check_requirements(*, require_project_scope: bool = False) -> dict:
    """Verify external prerequisites for the memory layer.

    Returns a dict ``{"ok": bool, "gh": ..., "auth": ..., "scopes": [...],
    "missing": [...]}``. Raises ``EnvironmentError`` with actionable
    install instructions if a hard requirement is missing.

    Set ``require_project_scope=True`` if you plan to swap the triage
    backend to a GitHub Project.
    """
    _check_gh()  # raises with install instructions if gh missing/not authed
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
    )
    text = result.stdout + result.stderr
    scopes_match = re.search(r"Token scopes:\s*(.+)", text)
    scopes_raw = scopes_match.group(1) if scopes_match else ""
    scopes = [s.strip().strip("'\"") for s in scopes_raw.split(",") if s.strip()]
    missing: list[str] = []
    if require_project_scope and not any(
        s == "project" or s == "read:project" or s.endswith(":project")
        for s in scopes
    ):
        missing.append("project")
    return {
        "ok": not missing,
        "gh": True,
        "auth": True,
        "scopes": scopes,
        "missing": missing,
        "hint": (
            "Run `gh auth refresh -s project` to grant the project scope."
            if missing
            else ""
        ),
    }


# ---------------------------------------------------------------------------
# CLI dispatch functions (used by ge.__main__)
# ---------------------------------------------------------------------------


def cli_roadmap_show(repo: str, issue: int) -> str:
    """Show the parsed roadmap tasks (JSON)."""
    store = RoadmapStore(repo, issue)
    tasks = store.hydrate()
    return json.dumps(
        [
            {"id": t.id, "title": t.title, "state": t.state.value}
            for t in tasks
        ],
        indent=2,
    )


def cli_roadmap_next(repo: str, issue: int) -> str:
    """Print the next todo task id (or empty string)."""
    store = RoadmapStore(repo, issue)
    nxt = store.next_todo()
    return nxt.id if nxt else ""


def cli_roadmap_set(repo: str, issue: int, task_id: str, state: str) -> str:
    """Set a roadmap task's state (todo|doing|done)."""
    store = RoadmapStore(repo, issue)
    rec = store[task_id]
    rec.state = TaskState(state)
    store[task_id] = rec
    return f"{task_id} -> {state}"


def cli_roadmap_append(repo: str, issue: int, title: str) -> str:
    """Append a new todo task to the roadmap."""
    store = RoadmapStore(repo, issue)
    rec = store.append(title)
    return rec.id


def cli_decision_log(
    repo: str, target: int, summary: str, *, rationale: str = ""
) -> str:
    """Append a decision to the decision log."""
    log = DecisionLog(repo, target)
    dec = log.append(summary, rationale=rationale)
    return dec.url or summary


def cli_decisions_show(repo: str, target: int) -> str:
    """Show recorded decisions (JSON)."""
    log = DecisionLog(repo, target)
    return json.dumps([asdict(d) for d in log], indent=2)


def cli_triage_show(repo: str, issue: int) -> str:
    """Show the triage backlog (JSON, in resolution order)."""
    backlog = TriageBacklog(repo, issue)
    return json.dumps(
        [
            {
                "ref": backlog[k].ref,
                "verdict": backlog[k].verdict.value,
                "order": backlog[k].order,
                "rationale": backlog[k].rationale,
            }
            for k in backlog
        ],
        indent=2,
    )


def cli_triage_set(
    repo: str,
    issue: int,
    ref: str,
    verdict: str,
    *,
    order: int = 0,
    rationale: str = "",
) -> str:
    """Add or update a triage entry."""
    backlog = TriageBacklog(repo, issue)
    backlog[ref] = TriageEntry(
        ref=ref,
        verdict=TriageVerdict(verdict),
        order=int(order),
        rationale=rationale,
    )
    return f"{ref} -> {verdict} (order={order})"


def cli_check_requirements(*, project_scope: bool = False) -> str:
    """Check that gh is installed, authed, and (optionally) has project scope."""
    return json.dumps(
        check_requirements(require_project_scope=project_scope), indent=2
    )


__all__ = [
    "TaskState",
    "TaskRecord",
    "TriageVerdict",
    "TriageEntry",
    "Decision",
    "RoadmapStore",
    "DecisionLog",
    "TriageBacklog",
    "github_memory",
    "check_requirements",
]
