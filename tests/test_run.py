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
        patchers = _patch_env(states, claude_results=results)
        for ctx in patchers:
            ctx.start()
        try:
            res = run_roadmap("owner/repo", 1, max_sessions=10)
            assert res["status"] == "completed"
            assert res["iterations"] == 2
        finally:
            for ctx in patchers:  # the started ones: fresh patchers would leak these
                ctx.stop()

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


# ---------------------------------------------------------------------------
# Session scope (#9): the argv and cwd a spawn would use. Nothing is spawned.
# ---------------------------------------------------------------------------

import subprocess as _subprocess
from pathlib import Path as _Path

from ge.run import SessionScope, package_root


def _git_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    _subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


class TestSessionScope:
    def test_cwd_defaults_to_the_current_directory(self, tmp_path, monkeypatch):
        """A subdirectory keeps its own .claude/ (and still loads the package's)."""
        pkg = _git_repo(tmp_path / "proj" / "t" / "pkg")
        sub = pkg / "apps" / "one"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        scope = SessionScope.build()
        assert scope.cwd == sub.resolve() and scope.warnings == ()
        assert package_root(sub) == pkg.resolve()

    def test_a_cwd_outside_every_checkout_is_kept_with_a_warning(self, tmp_path):
        assert package_root(tmp_path) is None
        scope = SessionScope.build(cwd=tmp_path)
        assert scope.cwd == tmp_path.resolve()
        assert "not inside a git checkout" in scope.warnings[0]

    def test_directories_must_exist(self, tmp_path):
        with pytest.raises(ValueError, match="not a directory"):
            SessionScope.build(cwd=tmp_path, add_dirs=[tmp_path / "absent"])

    def test_an_add_dirs_claude_md_becomes_a_first_read(self, tmp_path):
        pkg, lib, data = tmp_path / "pkg", tmp_path / "lib", tmp_path / "data"
        for d in (pkg, lib, data):
            d.mkdir()
        (lib / "CLAUDE.md").write_text("routing")
        scope = SessionScope.build(
            cwd=pkg,
            add_dirs=[lib, data, pkg],  # the cwd itself is not an add-dir
            read_first=["docs/overview.md"],
            skills=["pkg-dev", "pkg-dev"],
        )
        assert scope.add_dirs == (lib.resolve(), data.resolve())
        assert scope.read_first == (
            str(lib.resolve() / "CLAUDE.md"),
            str(pkg.resolve() / "docs" / "overview.md"),  # relative to the scope's cwd
        )
        assert scope.skills == ("pkg-dev",)
        preamble = scope.prompt_preamble()
        assert preamble.startswith("Before anything else, Read: ")
        assert "`pkg-dev`" in preamble

    def test_an_empty_scope_adds_no_flags_and_no_preamble(self, tmp_path):
        scope = SessionScope.build(cwd=tmp_path)
        assert scope.cli_args() == () and scope.prompt_preamble() == ""

    def test_effort_is_checked(self, tmp_path):
        with pytest.raises(ValueError, match="effort"):
            SessionScope.build(cwd=tmp_path, effort="huge")

    def test_the_spawn_argv_and_cwd(self, tmp_path):
        """What run_roadmap would exec, captured at subprocess.run: never spawned."""
        lib = tmp_path / "lib"
        lib.mkdir()
        (lib / "CLAUDE.md").write_text("routing")
        calls = []

        def fake_run(cmd, **kw):
            if cmd[0] == "git":  # package_root's probe: answer "not a checkout"
                return _subprocess.CompletedProcess(cmd, 128, "", "not a git repository")
            calls.append((cmd, kw.get("cwd")))
            return _subprocess.CompletedProcess(cmd, 0, "", "")

        todo = iter([_DummyTask("a")])
        with patch("ge.run.check_requirements", return_value={"ok": True}), \
             patch("ge.run.RoadmapStore.next_todo", lambda self: next(todo, None)), \
             patch("ge.run.DecisionLog.append", lambda self, *a, **k: None), \
             patch("ge.run._claude_binary", return_value="/fake/claude"), \
             patch("ge.run.subprocess.run", side_effect=fake_run):
            res = run_roadmap(
                "owner/repo", 1, cwd=tmp_path, add_dirs=[lib],
                skills=["pkg-dev"], model="sonnet", effort="high", max_sessions=3,
            )
        assert res["status"] == "completed" and len(calls) == 1
        (cmd, cwd), = calls
        assert cwd == str(tmp_path.resolve())
        assert cmd[:2] == ["/fake/claude", "-p"]
        prompt = cmd[2]
        assert prompt.startswith(f"Before anything else, Read: `{lib.resolve() / 'CLAUDE.md'}`.")
        assert "`pkg-dev`" in prompt and "ge-roadmap-execution" in prompt
        assert cmd[3:] == [
            "--permission-mode", "auto",
            "--add-dir", str(lib.resolve()),
            "--model", "sonnet",
            "--effort", "high",
        ]
        assert res["scope"] == {
            "cwd": str(tmp_path.resolve()),
            "add_dirs": [str(lib.resolve())],
            "read_first": [str(lib.resolve() / "CLAUDE.md")],
            "skills": ["pkg-dev"],
            "model": "sonnet",
            "effort": "high",
            "warnings": [res["scope"]["warnings"][0]],  # tmp_path is no checkout
        }


def test_decision_comments_never_carry_the_scope(tmp_path):
    """They may land on a public repo, and the scope holds local paths."""
    logged = []
    with patch("ge.run.check_requirements", return_value={"ok": True}), \
         patch("ge.run.RoadmapStore.next_todo", lambda self: _DummyTask("a")), \
         patch("ge.run.DecisionLog.append", lambda self, *a, **k: logged.append(k)), \
         patch("ge.run._spawn_claude", return_value=SessionResult(0, 1, "", "boom", 0.1)):
        res = run_roadmap("owner/repo", 1, cwd=tmp_path, max_sessions=2)
    assert res["status"] == "escalated_error" and logged
    assert all("scope" not in (k.get("metadata") or {}) for k in logged)
    assert str(tmp_path) not in repr(logged)
