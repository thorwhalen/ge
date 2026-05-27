"""Tests for ge.run — outer loop, permission-mode handling, kill detection.

All ``claude``-subprocess calls and GitHub I/O are mocked.
"""

from unittest.mock import MagicMock, patch

import pytest

from ge.run import (
    PERMISSION_MODES,
    SessionResult,
    _permission_flags,
    run_roadmap,
    run_triage,
)


class TestPermissionFlags:
    def test_auto(self):
        flags = _permission_flags("auto")
        assert "--permission-mode" in flags and "auto" in flags

    def test_bypass(self):
        flags = _permission_flags("bypass")
        assert "--dangerously-skip-permissions" in flags

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            _permission_flags("nope")


class TestKillDetection:
    def test_clean_exit_not_killed(self):
        r = SessionResult(1, 0, "ok", "", 1.0)
        assert not r.killed_by_denial_cap

    def test_denial_pattern(self):
        r = SessionResult(1, 1, "", "hit consecutive denials cap", 1.0)
        assert r.killed_by_denial_cap

    def test_other_failure_not_denial(self):
        r = SessionResult(1, 2, "", "syntax error", 1.0)
        assert not r.killed_by_denial_cap


# ---------------------------------------------------------------------------
# Outer loop behaviour
# ---------------------------------------------------------------------------


def _patch_env(roadmap_states, *, claude_results):
    """Build the patch stack for testing run_roadmap.

    ``roadmap_states`` is a list of (next_todo_return_value) per call.
    ``claude_results`` is a list of (returncode, stderr) tuples per
    spawned session.
    """
    next_todo_iter = iter(roadmap_states)
    spawn_iter = iter(claude_results)

    def fake_next_todo(self):
        try:
            return next(next_todo_iter)
        except StopIteration:
            return None

    def fake_spawn(prompt, *, mode="auto", cwd=None, extra_args=(), timeout=0):
        rc, stderr = next(spawn_iter)
        return SessionResult(0, rc, "", stderr, 0.1)

    return [
        patch("ge.run.check_requirements", return_value={"ok": True}),
        patch("ge.run.RoadmapStore.next_todo", fake_next_todo),
        patch("ge.run.DecisionLog.append", lambda self, *a, **k: None),
        patch("ge.run._spawn_claude", side_effect=fake_spawn),
    ]


class _DummyTask:
    def __init__(self, tid):
        self.id = tid


class TestRunRoadmap:
    def test_completes_when_no_todo(self):
        with patch("ge.run.check_requirements", return_value={"ok": True}), \
             patch("ge.run.RoadmapStore.next_todo", lambda self: None), \
             patch("ge.run._spawn_claude") as spawn:
            res = run_roadmap("owner/repo", 1, max_sessions=5)
        assert res["status"] == "completed"
        assert res["iterations"] == 0
        spawn.assert_not_called()

    def test_runs_iterations_until_empty(self):
        states = [_DummyTask("a"), _DummyTask("b")]
        # next_todo will be called once per iteration check; provide enough
        results = [(0, ""), (0, "")]
        for ctx in _patch_env(states, claude_results=results):
            ctx.start()
        try:
            res = run_roadmap("owner/repo", 1, max_sessions=10)
            assert res["status"] == "completed"
            assert res["iterations"] == 2
        finally:
            for ctx in _patch_env(states, claude_results=results):
                ctx.stop()  # best-effort cleanup; mock.patch is local-scoped

    def test_denial_cap_retry_then_escalate(self):
        # Iter 1: kill. Iter 2 (retry): kill again. Escalate.
        states = [_DummyTask("a"), _DummyTask("a"), _DummyTask("a")]
        results = [(1, "consecutive denials"), (1, "consecutive denials")]
        with patch("ge.run.check_requirements", return_value={"ok": True}), \
             patch("ge.run.RoadmapStore.next_todo", side_effect=states), \
             patch("ge.run.DecisionLog.append", lambda self, *a, **k: None), \
             patch(
                 "ge.run._spawn_claude",
                 side_effect=[
                     SessionResult(0, 1, "", "consecutive denials", 0.1),
                     SessionResult(0, 1, "", "consecutive denials", 0.1),
                 ],
             ):
            res = run_roadmap("owner/repo", 1, max_sessions=10)
        assert res["status"] == "escalated_denial_cap"

    def test_non_denial_error_escalates_immediately(self):
        with patch("ge.run.check_requirements", return_value={"ok": True}), \
             patch("ge.run.RoadmapStore.next_todo", side_effect=[_DummyTask("a")]), \
             patch("ge.run.DecisionLog.append", lambda self, *a, **k: None), \
             patch(
                 "ge.run._spawn_claude",
                 return_value=SessionResult(0, 2, "", "boom", 0.1),
             ):
            res = run_roadmap("owner/repo", 1, max_sessions=10)
        assert res["status"] == "escalated_error"
        assert res["returncode"] == 2


class TestRunTriage:
    def test_phase_analyze_one_iteration(self):
        with patch("ge.run.check_requirements", return_value={"ok": True}), \
             patch("ge.run.DecisionLog.append", lambda self, *a, **k: None), \
             patch("ge.run.TriageBacklog.__iter__", return_value=iter([])), \
             patch(
                 "ge.run._spawn_claude",
                 return_value=SessionResult(0, 0, "", "", 0.1),
             ) as spawn:
            res = run_triage(
                ["a/b", "c/d"],
                tracking_repo="owner/track",
                tracking_issue=1,
                phase="analyze",
                max_sessions=5,
            )
        assert res["status"] == "completed"
        assert spawn.call_count == 1

    def test_invalid_phase(self):
        with pytest.raises(ValueError):
            run_triage(
                ["a/b"],
                tracking_repo="owner/track",
                tracking_issue=1,
                phase="nope",
            )
