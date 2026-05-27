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
        "Load and follow the `autonomous-execution` and `roadmap-execution` "
        "skills. Do not stop to ask questions; decide-and-log instead.\n\n"
        f"REPO = {repo}\n"
        f"ROADMAP_ISSUE = {roadmap_issue}\n"
        f"DECISIONS_TARGET = {decisions}\n\n"
        "Perform exactly one roadmap iteration as described in the "
        "`roadmap-execution` skill: pick the next todo task, mark it doing, "
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
        "Load and follow the `autonomous-execution` and `cross-repo-triage` "
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
    cwd: Optional[Path],
    on_session=None,
) -> dict:
    """Generic outer loop: spawn → check → repeat until done or escalate.

    ``is_done`` returns True when there is no more work. ``build_prompt``
    returns the headless prompt for one iteration. ``on_session`` is an
    optional callback for telemetry.
    """
    iteration = 0
    retries_used = 0
    while iteration < max_sessions:
        if is_done():
            return {"status": "completed", "iterations": iteration}
        iteration += 1
        prompt = build_prompt()
        result = _spawn_claude(prompt, mode=mode, cwd=cwd)
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
        cwd: working directory for the spawned ``claude`` (typically the
            target repo's local checkout).
        on_session: optional callable invoked with each :class:`SessionResult`.
    """
    check_requirements()
    roadmap = RoadmapStore(repo, roadmap_issue)
    decisions = DecisionLog(
        repo, decisions_target if decisions_target is not None else roadmap_issue
    )
    cwd_path = Path(cwd) if cwd else None
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
        cwd=cwd_path,
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
    on_session=None,
) -> dict:
    """Drive a cross-repo triage backlog.

    ``phase='analyze'`` runs Phase A (classify + order); a single
    iteration is normally enough. ``phase='execute'`` runs Phase B
    (one fix-and-PR per iteration); the loop terminates when no
    unactioned ``fixable`` entries remain.

    The triage backlog lives in ``tracking_repo#tracking_issue`` (see
    :class:`ge.memory.TriageBacklog`).
    """
    if phase not in ("analyze", "execute"):
        raise ValueError(f"phase must be 'analyze' or 'execute', got {phase!r}")
    check_requirements()
    backlog = TriageBacklog(tracking_repo, tracking_issue)
    decisions = DecisionLog(tracking_repo, tracking_issue)
    cwd_path = Path(cwd) if cwd else None

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
            cwd=cwd_path,
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
        cwd=cwd_path,
        on_session=on_session,
    )


# ---------------------------------------------------------------------------
# CLI dispatch entry points (wired in ge.__main__)
# ---------------------------------------------------------------------------


def cli_run_roadmap(
    repo: str,
    roadmap_issue: int,
    *,
    mode: str = "auto",
    decisions_target: Optional[int] = None,
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    cwd: Optional[str] = None,
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
        on_session=_print_session,
    )
    return json.dumps(res, indent=2)


__all__ = [
    "SessionResult",
    "run_roadmap",
    "run_triage",
]
