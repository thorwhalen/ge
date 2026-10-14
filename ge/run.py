"""Autonomous-execution runner — Layer 3.

Launches ``claude`` in headless mode in a loop, one invocation per work
unit. State persists between iterations *only* through GitHub-backed
memory (:mod:`ge.memory`); each session starts with a fresh context
window and rehydrates from the roadmap / triage backlog.

Two entry points:

- :func:`run_roadmap` — drive a roadmap issue end to end.
- :func:`run_triage`  — drive a cross-repo triage backlog (Phase A or B).

The permission-mode choice (``auto`` vs ``bypass``) lives here because
SKILL.md files cannot set ``--permission-mode`` — that is a launch-time
flag on ``claude``.

What a spawned session can see is decided here too (:class:`SessionScope`):
the cwd picks which ``CLAUDE.md`` files load (the cwd's and its ancestors'), an
``--add-dir`` contributes its skills but never its ``CLAUDE.md``, and each one
widens the skill listing toward the budget past which descriptions are dropped
silently. So the runner warns when the cwd is outside every package checkout,
adds directories only when asked, puts any add-dir's ``CLAUDE.md`` and the requested routing
documents into the prompt as the first Read, names the skills to load, and
returns the scope with the run so a later diagnosis can see it.

Token / context exhaustion is *not* a failure: it ends the current
session; the loop's next iteration just rehydrates and continues. A
session terminated by the permission-denial cap *is* a failure: the
runner retries once and then escalates.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from ge.memory import (
    DecisionLog,
    RoadmapStore,
    TaskState,
    TriageBacklog,
    check_requirements,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


PERMISSION_MODES = {
    "auto": ("--permission-mode", "auto"),
    "bypass": ("--dangerously-skip-permissions",),
}

DEFAULT_MAX_SESSIONS = 50
DEFAULT_SESSION_TIMEOUT_SEC = 60 * 60 * 2  # 2h hard ceiling per session

#: The instruction files a cwd loads; an add-dir's are listed for the first Read.
INSTRUCTION_FILES = ("CLAUDE.md", ".claude/CLAUDE.md")

#: ``claude --effort`` levels.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def _git_root(path: Path) -> Optional[Path]:
    """The top of the git checkout holding *path*, or ``None``."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    top = proc.stdout.strip()
    return Path(top) if proc.returncode == 0 and top else None


def package_root(path: str | Path | None = None) -> Optional[Path]:
    """The git checkout holding *path* (default: the current directory), or ``None``.

    A session's ``CLAUDE.md`` comes from its cwd and the cwd's ancestors, so any
    directory inside a package checkout loads the package's instructions (and a
    subdirectory adds its own). A directory outside every checkout, such as a
    projects root or a scratch folder, loads none of the work's.
    """
    here = Path(path if path is not None else os.getcwd()).expanduser().resolve()
    return _git_root(here)


#: Why a scope's cwd may not load the work's instructions.
OUTSIDE_A_CHECKOUT = (
    "the session's cwd {cwd} is not inside a git checkout, so no package's CLAUDE.md "
    "loads (a projects root or a scratch folder loads none of the work's): pass the "
    "package root as cwd"
)


@dataclass(frozen=True)
class SessionScope:
    """What one spawned ``claude`` session can see, decided by the runner.

    - ``cwd``: where the session starts, so whose ``CLAUDE.md`` loads.
    - ``add_dirs``: further directories the run must *edit*, passed as
      ``--add-dir``. Each one adds its skills to the listing; none adds its
      ``CLAUDE.md``, which is why those become first Reads.
    - ``read_first``: routing documents the prompt tells the session to Read
      before anything else (absolute paths).
    - ``skills``: skills to load by name, beyond the runner's own. A skill named
      in the prompt is invocable even when the listing shows it name-only.
    - ``model`` / ``effort``: ``claude --model`` / ``--effort``, when set.
    - ``warnings``: why this scope may not load the work's instructions.

    >>> scope = SessionScope(cwd=Path("/w/pkg"), add_dirs=(Path("/w/lib"),), model="opus")
    >>> scope.cli_args()
    ('--add-dir', '/w/lib', '--model', 'opus')
    """

    cwd: Path
    add_dirs: tuple[Path, ...] = ()
    read_first: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    model: Optional[str] = None
    effort: Optional[str] = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self):
        if self.effort is not None and self.effort not in EFFORT_LEVELS:
            raise ValueError(f"effort must be one of {EFFORT_LEVELS}, not {self.effort!r}")

    @classmethod
    def build(
        cls,
        *,
        cwd: str | Path | None = None,
        add_dirs: Iterable[str | Path] = (),
        read_first: Iterable[str] = (),
        skills: Iterable[str] = (),
        model: Optional[str] = None,
        effort: Optional[str] = None,
    ) -> "SessionScope":
        """A scope from loose arguments, checked before anything is spawned.

        ``cwd`` defaults to the current directory. Directories must exist; relative
        add-dirs resolve against the current directory, relative ``read_first``
        paths against the scope's cwd (both become absolute). Every add-dir's
        instruction file is added to ``read_first``. A cwd outside every git
        checkout is kept, with a warning (:data:`OUTSIDE_A_CHECKOUT`).
        """
        root = Path(cwd if cwd is not None else os.getcwd()).expanduser().resolve()
        dirs = tuple(dict.fromkeys(Path(d).expanduser().resolve() for d in add_dirs))
        dirs = tuple(d for d in dirs if d != root)
        missing = [str(d) for d in (root, *dirs) if not d.is_dir()]
        if missing:
            raise ValueError(f"not a directory: {', '.join(missing)}")
        unloaded = [
            str(d / name) for d in dirs for name in INSTRUCTION_FILES if (d / name).is_file()
        ]
        given = [str((root / Path(r).expanduser()).resolve()) for r in read_first if r]
        warnings = () if package_root(root) else (OUTSIDE_A_CHECKOUT.format(cwd=root),)
        return cls(
            cwd=root,
            add_dirs=dirs,
            read_first=tuple(dict.fromkeys([*unloaded, *given])),
            skills=tuple(dict.fromkeys(s for s in skills if s)),
            model=model or None,
            effort=effort or None,
            warnings=warnings,
        )

    def cli_args(self) -> tuple[str, ...]:
        """The ``claude`` flags this scope adds (after ``-p`` and the permission flags)."""
        args: list[str] = []
        for d in self.add_dirs:
            args += ["--add-dir", str(d)]
        if self.model:
            args += ["--model", self.model]
        if self.effort:
            args += ["--effort", self.effort]
        return tuple(args)

    def prompt_preamble(self) -> str:
        """The lines that open the prompt: the first Reads, then the skills to load."""
        lines = []
        if self.read_first:
            lines.append(
                "Before anything else, Read: " + ", ".join(f"`{r}`" for r in self.read_first) + "."
            )
        if self.skills:
            lines.append(
                "Also load these skills by name: " + ", ".join(f"`{k}`" for k in self.skills) + "."
            )
        return "\n".join(lines) + ("\n\n" if lines else "")

    def as_dict(self) -> dict:
        """JSON-ready, for the run's result and its decision log."""
        return {
            "cwd": str(self.cwd),
            "add_dirs": [str(d) for d in self.add_dirs],
            "read_first": list(self.read_first),
            "skills": list(self.skills),
            "model": self.model,
            "effort": self.effort,
            "warnings": list(self.warnings),
        }


@dataclass
class SessionResult:
    """Outcome of a single ``claude`` invocation."""

    iteration: int
    returncode: int
    stdout: str
    stderr: str
    duration_sec: float

    @property
    def killed_by_denial_cap(self) -> bool:
        """Heuristic: did Claude Code terminate due to the denial cap?"""
        markers = (
            "consecutive denials",
            "permission denied limit",
            "denial cap",
            "tool_use was denied",
        )
        text = (self.stderr + self.stdout).lower()
        return self.returncode != 0 and any(m in text for m in markers)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _claude_binary() -> str:
    """Return the path to the ``claude`` CLI, or raise EnvironmentError."""
    path = shutil.which("claude")
    if not path:
        raise EnvironmentError(
            "claude CLI not found on PATH. Install Claude Code:\n"
            "  https://docs.claude.com/claude-code"
        )
    return path


def _permission_flags(mode: str) -> tuple[str, ...]:
    if mode not in PERMISSION_MODES:
        raise ValueError(
            f"Unknown permission mode {mode!r}. Use one of: {sorted(PERMISSION_MODES)}"
        )
    return PERMISSION_MODES[mode]


def _spawn_claude(
    prompt: str,
    *,
    mode: str = "auto",
    cwd: Optional[Path] = None,
    extra_args: Iterable[str] = (),
    timeout: int = DEFAULT_SESSION_TIMEOUT_SEC,
) -> SessionResult:
    """Run a single headless ``claude -p`` invocation and capture its output."""
    cmd = [
        _claude_binary(),
        "-p",
        prompt,
        *_permission_flags(mode),
        *extra_args,
    ]
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
        )
        return SessionResult(
            iteration=0,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_sec=time.monotonic() - start,
        )
    except subprocess.TimeoutExpired as exc:
        return SessionResult(
            iteration=0,
            returncode=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "")
            + f"\n[runner] session exceeded {timeout}s timeout",
            duration_sec=time.monotonic() - start,
        )


def _build_roadmap_prompt(
    *,
    repo: str,
    roadmap_issue: int,
    decisions_target: Optional[int],
) -> str:
    decisions = decisions_target if decisions_target is not None else roadmap_issue
    return (
        "You are running unattended via the ge autonomous runner. "
        "Load and follow the `ge-autonomous-execution` and `ge-roadmap-execution` "
        "skills. Do not stop to ask questions; decide-and-log instead.\n\n"
        f"REPO = {repo}\n"
        f"ROADMAP_ISSUE = {roadmap_issue}\n"
        f"DECISIONS_TARGET = {decisions}\n\n"
        "Perform exactly one roadmap iteration as described in the "
        "`ge-roadmap-execution` skill: pick the next todo task, mark it doing, "
        "complete it (with verification), mark it done, and exit. If there "
        "are no todo tasks left, exit immediately. Token/context exhaustion "
        "is not a failure — the outer runner relaunches with a fresh "
        "context for the next iteration."
    )


def _build_triage_prompt(
    *,
    repos: list[str],
    tracking_repo: str,
    tracking_issue: int,
    phase: str,
) -> str:
    return (
        "You are running unattended via the ge autonomous runner. "
        "Load and follow the `ge-autonomous-execution` and `ge-cross-repo-triage` "
        "skills. Do not stop to ask questions; decide-and-log instead.\n\n"
        f"REPOS = {json.dumps(repos)}\n"
        f"TRACKING_REPO = {tracking_repo}\n"
        f"TRACKING_ISSUE = {tracking_issue}\n"
        f"PHASE = {phase}\n\n"
        "Phase A: classify and order open issues across REPOS into the "
        "TriageBacklog at TRACKING_REPO#TRACKING_ISSUE, then exit.\n"
        "Phase B: take the next unactioned backlog entry in order. For a "
        "fixable entry, write a failing test, confirm it fails, fix the "
        "bug, confirm it passes, open a draft PR (referencing the issue), "
        "and exit. Stop at PR — do not merge."
    )


# ---------------------------------------------------------------------------
# Outer loops
# ---------------------------------------------------------------------------


def _has_todo(roadmap: RoadmapStore) -> bool:
    return roadmap.next_todo() is not None


def _run_loop(
    *,
    repo: str,
    decisions: DecisionLog,
    is_done,
    build_prompt,
    mode: str,
    max_sessions: int,
    scope: SessionScope,
    on_session=None,
) -> dict:
    """Generic outer loop: spawn → check → repeat until done or escalate.

    ``is_done`` returns True when there is no more work. ``build_prompt``
    returns the headless prompt for one iteration; ``scope``'s preamble opens
    it and its flags and cwd start the session. ``on_session`` is an optional
    callback for telemetry. Every result carries ``scope``.
    """
    for warning in scope.warnings:
        sys.stderr.write(f"[ge] warning: {warning}\n")
    result_dict = _loop(
        decisions=decisions,
        is_done=is_done,
        build_prompt=lambda: scope.prompt_preamble() + build_prompt(),
        mode=mode,
        max_sessions=max_sessions,
        scope=scope,
        on_session=on_session,
    )
    return {**result_dict, "scope": scope.as_dict()}


def _loop(
    *,
    decisions: DecisionLog,
    is_done,
    build_prompt,
    mode: str,
    max_sessions: int,
    scope: SessionScope,
    on_session=None,
) -> dict:
    iteration = 0
    retries_used = 0
    while iteration < max_sessions:
        if is_done():
            return {"status": "completed", "iterations": iteration}
        iteration += 1
        prompt = build_prompt()
        result = _spawn_claude(
            prompt, mode=mode, cwd=scope.cwd, extra_args=scope.cli_args()
        )
        result.iteration = iteration
        if on_session is not None:
            on_session(result)

        if result.returncode == 0:
            retries_used = 0
            continue

        if result.killed_by_denial_cap:
            if retries_used == 0:
                retries_used = 1
                try:
                    decisions.append(
                        "Session killed by permission-denial cap; retrying once",
                        rationale=(
                            "The headless agent hit Claude Code's denial "
                            "cap on iteration "
                            f"{iteration}. Retrying with a fresh context."
                        ),
                        metadata={
                            "iteration": iteration,
                            "returncode": result.returncode,
                        },
                    )
                except Exception:
                    pass  # decision logging is best-effort
                continue
            try:
                decisions.append(
                    "Stopping: denial cap hit twice in a row",
                    rationale="Two consecutive headless sessions terminated by "
                    "the permission-denial cap. Escalating to user.",
                    metadata={"iteration": iteration},
                )
            except Exception:
                pass
            return {
                "status": "escalated_denial_cap",
                "iterations": iteration,
                "last_stderr": result.stderr[-2000:],
            }

        # Non-zero exit for some other reason — escalate.
        try:
            decisions.append(
                f"Stopping: claude exited with code {result.returncode}",
                rationale="Non-clean exit from headless claude session "
                "outside the denial-cap pattern. Escalating.",
                metadata={
                    "iteration": iteration,
                    "returncode": result.returncode,
                    "stderr_tail": result.stderr[-500:],
                },
            )
        except Exception:
            pass
        return {
            "status": "escalated_error",
            "iterations": iteration,
            "returncode": result.returncode,
            "last_stderr": result.stderr[-2000:],
        }

    return {"status": "max_sessions_reached", "iterations": iteration}


def run_roadmap(
    repo: str,
    roadmap_issue: int,
    *,
    mode: str = "auto",
    decisions_target: Optional[int] = None,
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    cwd: Optional[str | Path] = None,
    add_dirs: Iterable[str | Path] = (),
    read_first: Iterable[str] = (),
    skills: Iterable[str] = (),
    model: Optional[str] = None,
    effort: Optional[str] = None,
    on_session=None,
) -> dict:
    """Drive a roadmap issue to completion.

    Each iteration is one headless ``claude`` invocation that performs
    exactly one roadmap step. The loop terminates when:

    - no todo tasks remain (``status='completed'``),
    - two consecutive sessions hit the denial cap (``status='escalated_denial_cap'``),
    - a session exits non-zero for another reason (``status='escalated_error'``),
    - or ``max_sessions`` is reached.

    Args:
        repo: ``"owner/repo"`` containing the roadmap issue.
        roadmap_issue: the roadmap issue number.
        mode: ``"auto"`` (default) or ``"bypass"``.
        decisions_target: issue/PR number to log decisions on. Defaults
            to ``roadmap_issue``.
        max_sessions: safety ceiling on total iterations.
        cwd: where the spawned ``claude`` starts, so whose ``CLAUDE.md`` it
            loads. Defaults to the current directory. A cwd outside every git
            checkout (a projects root, a scratch folder) loads no package's
            instructions: it is kept, and named in the scope's ``warnings``.
        add_dirs: directories the run must edit besides ``cwd`` (``--add-dir``);
            their ``CLAUDE.md`` files become first Reads, since an add-dir's
            never loads.
        read_first: routing documents the session must Read first.
        skills: skills to load by name, beyond ``ge-autonomous-execution`` and
            ``ge-roadmap-execution``.
        model, effort: ``claude --model`` / ``--effort``.
        on_session: optional callable invoked with each :class:`SessionResult`.

    The result carries ``scope`` (:meth:`SessionScope.as_dict`), so a later
    diagnosis can see what the sessions could see.
    """
    scope = SessionScope.build(
        cwd=cwd,
        add_dirs=add_dirs,
        read_first=read_first,
        skills=skills,
        model=model,
        effort=effort,
    )
    check_requirements()
    roadmap = RoadmapStore(repo, roadmap_issue)
    decisions = DecisionLog(
        repo, decisions_target if decisions_target is not None else roadmap_issue
    )
    return _run_loop(
        repo=repo,
        decisions=decisions,
        is_done=lambda: not _has_todo(roadmap),
        build_prompt=lambda: _build_roadmap_prompt(
            repo=repo,
            roadmap_issue=roadmap_issue,
            decisions_target=decisions_target,
        ),
        mode=mode,
        max_sessions=max_sessions,
        scope=scope,
        on_session=on_session,
    )


def run_triage(
    repos: list[str],
    *,
    tracking_repo: str,
    tracking_issue: int,
    phase: str = "analyze",
    mode: str = "auto",
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    cwd: Optional[str | Path] = None,
    add_dirs: Iterable[str | Path] = (),
    read_first: Iterable[str] = (),
    skills: Iterable[str] = (),
    model: Optional[str] = None,
    effort: Optional[str] = None,
    on_session=None,
) -> dict:
    """Drive a cross-repo triage backlog.

    ``phase='analyze'`` runs Phase A (classify + order); a single
    iteration is normally enough. ``phase='execute'`` runs Phase B
    (one fix-and-PR per iteration); the loop terminates when no
    unactioned ``fixable`` entries remain.

    The triage backlog lives in ``tracking_repo#tracking_issue`` (see
    :class:`ge.memory.TriageBacklog`). ``cwd``, ``add_dirs``, ``read_first``,
    ``skills``, ``model`` and ``effort`` scope each spawned session, as for
    :func:`run_roadmap`; the result carries ``scope``.
    """
    if phase not in ("analyze", "execute"):
        raise ValueError(f"phase must be 'analyze' or 'execute', got {phase!r}")
    scope = SessionScope.build(
        cwd=cwd,
        add_dirs=add_dirs,
        read_first=read_first,
        skills=skills,
        model=model,
        effort=effort,
    )
    check_requirements()
    backlog = TriageBacklog(tracking_repo, tracking_issue)
    decisions = DecisionLog(tracking_repo, tracking_issue)

    if phase == "analyze":
        # Phase A: typically one iteration. We still gate via the same
        # outer loop so denial-cap retry logic applies.
        ran = {"flag": False}

        def is_done():
            if ran["flag"]:
                return True
            return False

        def build():
            ran["flag"] = True
            return _build_triage_prompt(
                repos=list(repos),
                tracking_repo=tracking_repo,
                tracking_issue=tracking_issue,
                phase=phase,
            )

        return _run_loop(
            repo=tracking_repo,
            decisions=decisions,
            is_done=is_done,
            build_prompt=build,
            mode=mode,
            max_sessions=max_sessions,
            scope=scope,
            on_session=on_session,
        )

    # Phase B: one fixable entry per iteration.
    def _next_fixable():
        from ge.memory import TriageVerdict

        for ref in backlog:
            entry = backlog[ref]
            if entry.verdict != TriageVerdict.fixable:
                continue
            # Heuristic: 'pr_url' metadata absent = unactioned.
            if not entry.metadata.get("pr_url"):
                return entry
        return None

    return _run_loop(
        repo=tracking_repo,
        decisions=decisions,
        is_done=lambda: _next_fixable() is None,
        build_prompt=lambda: _build_triage_prompt(
            repos=list(repos),
            tracking_repo=tracking_repo,
            tracking_issue=tracking_issue,
            phase=phase,
        ),
        mode=mode,
        max_sessions=max_sessions,
        scope=scope,
        on_session=on_session,
    )


# ---------------------------------------------------------------------------
# CLI dispatch entry points (wired in ge.__main__)
# ---------------------------------------------------------------------------


def _csv(text: Optional[str]) -> list[str]:
    """A comma-separated CLI value as a list (``None`` or blank: empty)."""
    return [part.strip() for part in (text or "").split(",") if part.strip()]


def cli_run_roadmap(
    repo: str,
    roadmap_issue: int,
    *,
    mode: str = "auto",
    decisions_target: Optional[int] = None,
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    cwd: Optional[str] = None,
    add_dirs: Optional[str] = None,
    read_first: Optional[str] = None,
    skills: Optional[str] = None,
    model: Optional[str] = None,
    effort: Optional[str] = None,
) -> str:
    """Run the roadmap loop (CLI wrapper). Prints a per-iteration summary."""

    def _print_session(r: SessionResult) -> None:
        sys.stderr.write(
            f"[ge] iter={r.iteration} rc={r.returncode} "
            f"duration={r.duration_sec:.1f}s\n"
        )
        sys.stderr.flush()

    res = run_roadmap(
        repo,
        int(roadmap_issue),
        mode=mode,
        decisions_target=decisions_target
        if decisions_target is None
        else int(decisions_target),
        max_sessions=int(max_sessions),
        cwd=cwd,
        add_dirs=_csv(add_dirs),
        read_first=_csv(read_first),
        skills=_csv(skills),
        model=model,
        effort=effort,
        on_session=_print_session,
    )
    return json.dumps(res, indent=2)


def cli_run_triage(
    tracking_repo: str,
    tracking_issue: int,
    repos: str,
    *,
    phase: str = "analyze",
    mode: str = "auto",
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    cwd: Optional[str] = None,
    add_dirs: Optional[str] = None,
    read_first: Optional[str] = None,
    skills: Optional[str] = None,
    model: Optional[str] = None,
    effort: Optional[str] = None,
) -> str:
    """Run the triage loop (CLI wrapper). ``repos`` is comma-separated."""
    repo_list = [r.strip() for r in repos.split(",") if r.strip()]

    def _print_session(r: SessionResult) -> None:
        sys.stderr.write(
            f"[ge] iter={r.iteration} rc={r.returncode} "
            f"duration={r.duration_sec:.1f}s\n"
        )
        sys.stderr.flush()

    res = run_triage(
        repo_list,
        tracking_repo=tracking_repo,
        tracking_issue=int(tracking_issue),
        phase=phase,
        mode=mode,
        max_sessions=int(max_sessions),
        cwd=cwd,
        add_dirs=_csv(add_dirs),
        read_first=_csv(read_first),
        skills=_csv(skills),
        model=model,
        effort=effort,
        on_session=_print_session,
    )
    return json.dumps(res, indent=2)


__all__ = [
    "SessionResult",
    "SessionScope",
    "package_root",
    "run_roadmap",
    "run_triage",
]
