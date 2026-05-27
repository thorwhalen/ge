"""Tests for ge.memory — roadmap, decision log, and triage backlog stores.

All GitHub I/O is mocked: tests verify the markdown parsing, the
MutableMapping semantics, and the cache round-trips. End-to-end against
real GitHub is covered by the self-host check, not here.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ge.memory import (
    DECISION_TAG,
    ROADMAP_BEGIN,
    ROADMAP_END,
    TRIAGE_BEGIN,
    TRIAGE_END,
    Decision,
    DecisionLog,
    RoadmapStore,
    TaskRecord,
    TaskState,
    TriageBacklog,
    TriageEntry,
    TriageVerdict,
    _parse_decision_body,
    _parse_task_block,
    _render_task_block,
    _slugify,
    _splice_block,
    github_memory,
)


# ---------------------------------------------------------------------------
# Pure helpers (no I/O)
# ---------------------------------------------------------------------------


class TestParseRender:
    def test_parse_basic(self):
        block = "- [ ] Foo\n- [x] Bar\n- [ ] Baz <!-- ge:doing -->"
        tasks = _parse_task_block(block)
        assert [(t.title, t.state.value) for t in tasks] == [
            ("Foo", "todo"),
            ("Bar", "done"),
            ("Baz", "doing"),
        ]

    def test_unique_ids_on_collision(self):
        tasks = _parse_task_block("- [ ] Same title\n- [ ] Same title")
        ids = [t.id for t in tasks]
        assert ids[0] != ids[1]
        assert ids[0] == "same-title"

    def test_render_roundtrip(self):
        original = "- [ ] A\n- [x] B\n- [ ] C <!-- ge:doing -->"
        rendered = _render_task_block(_parse_task_block(original))
        assert rendered == original

    def test_slugify(self):
        assert _slugify("Hello World!") == "hello-world"
        assert _slugify("") == "task"


class TestSpliceBlock:
    def test_replace_existing(self):
        body = "intro\n<!--B-->\nold\n<!--E-->\noutro"
        out = _splice_block(body, "<!--B-->", "<!--E-->", "new")
        assert "new" in out
        assert "old" not in out
        assert out.startswith("intro")
        assert out.rstrip().endswith("outro")

    def test_append_when_missing(self):
        body = "existing body"
        out = _splice_block(body, "<!--B-->", "<!--E-->", "fresh", header="## H")
        assert "## H" in out
        assert "fresh" in out
        assert out.startswith("existing body")

    def test_empty_body(self):
        out = _splice_block("", "<!--B-->", "<!--E-->", "x")
        assert "<!--B-->" in out and "<!--E-->" in out and "x" in out


class TestDecisionBodyParse:
    def test_basic(self):
        body = f"{DECISION_TAG}\n### Decision: Try Plan A\n\nbecause shorter"
        s, r, m = _parse_decision_body(body)
        assert s == "Try Plan A"
        assert r == "because shorter"
        assert m == {}

    def test_with_metadata(self):
        body = (
            f"{DECISION_TAG}\n### Decision: X\n\nwhy Y\n\n"
            "```json\n"
            '{"k": 1}\n'
            "```\n"
        )
        s, r, m = _parse_decision_body(body)
        assert s == "X"
        assert "why Y" in r
        assert m == {"k": 1}


# ---------------------------------------------------------------------------
# RoadmapStore — with mocked GitHub I/O
# ---------------------------------------------------------------------------


@pytest.fixture
def roadmap_body():
    return (
        "intro text\n"
        f"{ROADMAP_BEGIN}\n"
        "- [ ] Add tests\n"
        "- [x] Write docs\n"
        "- [ ] Ship it <!-- ge:doing -->\n"
        f"{ROADMAP_END}\n"
        "outro"
    )


def _make_store(tmp_path, body):
    """Build a RoadmapStore whose I/O is patched against ``body``."""
    state = {"body": body}

    def fake_get(repo, number):
        return {"body": state["body"], "title": "Roadmap", "html_url": "u"}

    def fake_patch(repo, number, new_body):
        state["body"] = new_body
        return {}

    store = RoadmapStore("owner/repo", 1, cache_dir=tmp_path)
    get_patch = patch("ge.memory._get_issue_body", side_effect=fake_get)
    patch_patch = patch("ge.memory._patch_issue_body", side_effect=fake_patch)
    return store, get_patch, patch_patch, state


class TestRoadmapStore:
    def test_iter_and_len(self, tmp_path, roadmap_body):
        store, g, p, _ = _make_store(tmp_path, roadmap_body)
        with g, p:
            assert len(store) == 3
            assert list(store) == ["add-tests", "write-docs", "ship-it"]

    def test_getitem(self, tmp_path, roadmap_body):
        store, g, p, _ = _make_store(tmp_path, roadmap_body)
        with g, p:
            t = store["write-docs"]
            assert t.state == TaskState.done
            assert t.title == "Write docs"

    def test_next_todo(self, tmp_path, roadmap_body):
        store, g, p, _ = _make_store(tmp_path, roadmap_body)
        with g, p:
            nxt = store.next_todo()
            assert nxt.id == "add-tests"

    def test_setitem_changes_state(self, tmp_path, roadmap_body):
        store, g, p, state = _make_store(tmp_path, roadmap_body)
        with g, p:
            rec = store["add-tests"]
            rec.state = TaskState.done
            store["add-tests"] = rec
        assert "- [x] Add tests" in state["body"]

    def test_append_new_task(self, tmp_path, roadmap_body):
        store, g, p, state = _make_store(tmp_path, roadmap_body)
        with g, p:
            rec = store.append("New thing")
        assert rec.id == "new-thing"
        assert "New thing" in state["body"]

    def test_delitem(self, tmp_path, roadmap_body):
        store, g, p, state = _make_store(tmp_path, roadmap_body)
        with g, p:
            del store["write-docs"]
        assert "Write docs" not in state["body"]

    def test_missing_block_yields_empty(self, tmp_path):
        store, g, p, _ = _make_store(tmp_path, "no markers here")
        with g, p:
            assert len(store) == 0
            assert store.next_todo() is None

    def test_cache_written_on_fetch(self, tmp_path, roadmap_body):
        store, g, p, _ = _make_store(tmp_path, roadmap_body)
        with g, p:
            store.hydrate()
        cache_files = list(tmp_path.glob("roadmap_*.json"))
        assert cache_files, "expected a cache snapshot file"
        data = json.loads(cache_files[0].read_text())
        assert {t["title"] for t in data["tasks"]} == {
            "Add tests",
            "Write docs",
            "Ship it",
        }


# ---------------------------------------------------------------------------
# DecisionLog
# ---------------------------------------------------------------------------


class TestDecisionLog:
    def test_append_posts_tagged_comment(self, tmp_path):
        log = DecisionLog("owner/repo", 1, cache_dir=tmp_path)
        captured = {}

        def fake_post(repo, number, body):
            captured["body"] = body
            return {
                "html_url": "https://github.com/owner/repo/issues/1#c-1",
                "created_at": "2026-05-27T12:00:00Z",
            }

        with patch("ge.memory._post_issue_comment", side_effect=fake_post):
            dec = log.append("Picked plan A", rationale="cheaper", metadata={"k": 1})
        assert DECISION_TAG in captured["body"]
        assert "Picked plan A" in captured["body"]
        assert dec.url is not None

    def test_iter_filters_by_tag(self, tmp_path):
        log = DecisionLog("owner/repo", 1, cache_dir=tmp_path)
        comments = [
            {"body": "unrelated chat", "created_at": "t1", "html_url": "u1"},
            {
                "body": (
                    f"{DECISION_TAG}\n### Decision: Use SQLite\n\n"
                    "because lighter"
                ),
                "created_at": "t2",
                "html_url": "u2",
            },
        ]
        with patch("ge.memory.gh_api", return_value=comments):
            decisions = list(log)
        assert len(decisions) == 1
        assert decisions[0].summary == "Use SQLite"


# ---------------------------------------------------------------------------
# TriageBacklog
# ---------------------------------------------------------------------------


def _make_triage(tmp_path, body):
    state = {"body": body}

    def fake_get(repo, number):
        return {"body": state["body"], "title": "Triage", "html_url": "u"}

    def fake_patch(repo, number, new_body):
        state["body"] = new_body
        return {}

    backlog = TriageBacklog("owner/repo", 9, cache_dir=tmp_path)
    return (
        backlog,
        patch("ge.memory._get_issue_body", side_effect=fake_get),
        patch("ge.memory._patch_issue_body", side_effect=fake_patch),
        state,
    )


class TestTriageBacklog:
    def test_empty_when_no_block(self, tmp_path):
        b, g, p, _ = _make_triage(tmp_path, "no block")
        with g, p:
            assert len(b) == 0

    def test_add_and_retrieve(self, tmp_path):
        b, g, p, state = _make_triage(tmp_path, "")
        with g, p:
            b["owner/repo#42"] = TriageEntry(
                ref="owner/repo#42",
                verdict=TriageVerdict.fixable,
                order=1,
                rationale="quick win",
            )
            assert "owner/repo#42" in b
            entry = b["owner/repo#42"]
            assert entry.verdict == TriageVerdict.fixable

    def test_rejects_bad_key(self, tmp_path):
        b, g, p, _ = _make_triage(tmp_path, "")
        with g, p, pytest.raises(ValueError):
            b["not a ref"] = TriageVerdict.fixable

    def test_iteration_order_by_order_field(self, tmp_path):
        body = (
            f"{TRIAGE_BEGIN}\n"
            + json.dumps(
                [
                    {"ref": "o/r#3", "verdict": "fixable", "order": 2},
                    {"ref": "o/r#1", "verdict": "stale", "order": 1},
                    {"ref": "o/r#2", "verdict": "blocked", "order": 3},
                ]
            )
            + f"\n{TRIAGE_END}"
        )
        b, g, p, _ = _make_triage(tmp_path, body)
        with g, p:
            assert list(b) == ["o/r#1", "o/r#3", "o/r#2"]

    def test_delitem(self, tmp_path):
        body = (
            f"{TRIAGE_BEGIN}\n"
            + json.dumps([{"ref": "o/r#1", "verdict": "fixable", "order": 1}])
            + f"\n{TRIAGE_END}"
        )
        b, g, p, _ = _make_triage(tmp_path, body)
        with g, p:
            del b["o/r#1"]
            assert "o/r#1" not in b


# ---------------------------------------------------------------------------
# Mall factory
# ---------------------------------------------------------------------------


class TestGithubMemory:
    def test_includes_only_requested_stores(self, tmp_path):
        mall = github_memory(
            "owner/repo", roadmap_issue=1, cache_dir=tmp_path
        )
        assert set(mall) == {"roadmap"}
        mall_full = github_memory(
            "owner/repo",
            roadmap_issue=1,
            decisions_target=1,
            triage_issue=2,
            cache_dir=tmp_path,
        )
        assert set(mall_full) == {"roadmap", "decisions", "triage"}
        assert isinstance(mall_full["roadmap"], RoadmapStore)
        assert isinstance(mall_full["decisions"], DecisionLog)
        assert isinstance(mall_full["triage"], TriageBacklog)
