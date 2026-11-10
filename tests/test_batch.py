"""Offline tests for ge.batch: a fake GitHub API holds issues and edges and records every call."""

import json

import pytest

from ge import batch


class FakeApi:
    """Stands in for gh_api: numbers issues from 100, ids are number * 10."""

    def __init__(self, *, fail_create_at=None, edge_error=None, existing=None):
        self.calls, self.issues, self.blocked_by, self.next = [], {}, {}, 100
        self.fail_create_at, self.edge_error = fail_create_at, edge_error
        for n, body in (existing or {}).items():  # issues already in the repository
            self.issues[n] = {"number": n, "id": n * 10, "html_url": f"https://x/issues/{n}", "body": body}

    def __call__(self, endpoint, *, method="GET", body=None, **kw):
        self.calls.append((method, endpoint, body))
        path = endpoint.split("?")[0]
        if method == "POST" and path.endswith("/issues"):
            if self.next == self.fail_create_at:
                raise RuntimeError("gh api failed: secondary rate limit")
            n, self.next = self.next, self.next + 1
            self.issues[n] = {"number": n, "id": n * 10, "html_url": f"https://x/issues/{n}", "body": body["body"]}
            return dict(self.issues[n])
        if method == "PATCH":
            n = int(path.rsplit("/", 1)[1])
            self.issues[n]["body"] = body["body"]
            return dict(self.issues[n])
        if path.endswith("/blocked_by"):
            n = int(path.split("/")[-3])
            if method == "POST":
                if self.edge_error:
                    raise RuntimeError(self.edge_error)
                self.blocked_by.setdefault(n, []).append(body["issue_id"])
                return {}
            return [{"id": i} for i in self.blocked_by.get(n, [])]
        if method == "GET" and path.endswith("/issues"):  # recent issues, newest first
            page = int(endpoint.split("page=")[-1]) if "&page=" in endpoint else 1
            ordered = sorted(self.issues.values(), key=lambda i: -i["number"])
            return [dict(i) for i in ordered[(page - 1) * 100 : page * 100]]
        if method == "GET":  # one issue: ours if we hold it, else an existing one
            n = int(path.rsplit("/", 1)[1])
            return dict(self.issues.get(n) or {"number": n, "id": n * 10, "body": ""})
        raise AssertionError((method, endpoint))

    def writes(self, method, suffix=""):
        return [(e, b) for m, e, b in self.calls if m == method and e.split("?")[0].endswith(suffix)]


RECORDS = [
    {"key": "B", "title": "Printer", "body": "Needs {#A}; docs in {#C}.", "depends_on": ["A", "#12"], "labels": ["enhancement"]},
    {"key": "A", "title": "Parser", "body": "First."},
    {"key": "C", "title": "Docs", "body": "Documents {#B}.", "depends_on": ["B"]},
]


def _file(records=RECORDS, **kw):
    kw.setdefault("api", FakeApi())
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("log", lambda s: None)
    return kw["api"], batch.file_issues(records, "o/r", **kw)


def _text(api, n):
    """An issue's body without its hidden marker line."""
    return api.issues[n]["body"].rsplit("\n\n<!-- ge-batch:", 1)[0]


def test_files_in_dependency_order_and_resolves_references():
    api, state = _file()
    assert {k: v["number"] for k, v in state["issues"].items()} == {"A": 100, "B": 101, "C": 102}
    # B was created before C existed, then patched once C had a number
    assert [_text(api, n) for n in (100, 101, 102)] == ["First.", "Needs #100; docs in #102.", "Documents #101."]
    assert [e for e, b in api.writes("PATCH")] == ["repos/o/r/issues/101"]
    created = [b for e, b in api.writes("POST", "/issues")]
    assert created[1]["labels"] == ["enhancement"] and "labels" not in created[0]


def test_creates_blocked_by_edges_with_internal_ids_including_existing_issues():
    api, state = _file()
    # the blocked issue's number in the URL, the blocker's *id* (not number) in the body
    assert api.blocked_by == {101: [1000, 120], 102: [1010]}
    assert state["edges"] == [
        {"blocked": "B", "blocker": "A"},
        {"blocked": "B", "blocker": "#12"},
        {"blocked": "C", "blocker": "B"},
    ]


def test_an_interrupted_run_resumes_from_the_map_without_filing_twice(tmp_path):
    map_path = tmp_path / "m.json"
    api = FakeApi(fail_create_at=101)
    with pytest.raises(RuntimeError):
        _file(api=api, map_path=map_path)
    assert list(json.loads(map_path.read_text())["issues"]) == ["A"]

    api.fail_create_at = None
    _, state = _file(api=api, map_path=map_path)
    # one attempt failed, then each record was filed exactly once
    assert [b["title"] for e, b in api.writes("POST", "/issues")] == ["Parser", "Printer", "Printer", "Docs"]
    assert sorted(api.issues) == [100, 101, 102]
    assert _text(api, 101) == "Needs #100; docs in #102."
    assert json.loads(map_path.read_text()) == state

    n_calls = len(api.calls)
    _file(api=api, map_path=map_path)  # a third run writes nothing
    assert not [c for c in api.calls[n_calls:] if c[0] != "GET"]


def test_an_issue_created_before_a_crash_is_adopted_not_filed_again(tmp_path):
    api = FakeApi()
    _, first = _file(api=api)  # filed, but say the map was never saved
    _, state = _file(api=api, map_path=tmp_path / "m.json")
    assert len(api.writes("POST", "/issues")) == 3  # nothing filed the second time
    assert {k: v["number"] for k, v in state["issues"].items()} == {"A": 100, "B": 101, "C": 102}
    assert len(api.blocked_by[101]) == 2  # edges already there are not added again


def test_an_edited_record_is_sent_again_on_the_next_run(tmp_path):
    map_path = tmp_path / "m.json"
    api, _ = _file(api=FakeApi(), map_path=map_path)
    edited = [dict(r, body="Rewritten, still after {#B}.") if r["key"] == "C" else r for r in RECORDS]
    _file(edited, api=api, map_path=map_path)
    assert _text(api, 102) == "Rewritten, still after #101."


def test_failed_edges_are_recorded_retried_and_cleared(tmp_path):
    map_path = tmp_path / "m.json"
    api = FakeApi(edge_error="gh api failed: HTTP 404 Not Found")
    _, state = _file(api=api, map_path=map_path)
    assert {(e["blocked"], e["blocker"]) for e in state["edge_errors"]} == {("B", "A"), ("B", "#12"), ("C", "B")}
    assert state["edges"] == []
    api.edge_error = None
    _, state = _file(api=api, map_path=map_path)
    assert state["edge_errors"] == [] and len(state["edges"]) == 3
    assert len(api.writes("POST", "/issues")) == 3


def test_an_edge_already_on_github_is_not_posted_again():
    api = FakeApi()
    api.blocked_by[101] = [1000]  # B is already blocked by A
    _, state = _file(api=api)
    assert api.blocked_by[101] == [1000, 120] and len(state["edges"]) == 3


def test_a_map_from_another_repo_is_refused(tmp_path):
    map_path = tmp_path / "m.json"
    map_path.write_text(json.dumps({"repo": "other/repo", "issues": {}}))
    with pytest.raises(ValueError, match="other/repo"):
        _file(map_path=map_path)


def test_repo_given_as_url_or_other_case_matches_the_map(tmp_path):
    map_path = tmp_path / "m.json"
    api, _ = _file(api=FakeApi(), map_path=map_path)
    batch.file_issues(RECORDS, "https://github.com/O/R", api=api, map_path=map_path, sleep=lambda s: None, log=lambda s: None)
    assert len(api.writes("POST", "/issues")) == 3


@pytest.mark.parametrize(
    "records,message",
    [
        ([{"key": "A", "title": "a"}, {"key": "A", "title": "b"}], "duplicate key 'A'"),
        ([{"key": "A"}], "missing or non-string 'title'"),
        ([{"title": "a"}], "missing or non-string 'key'"),
        ([{"key": "12", "title": "a"}], "must not look like an issue number"),
        ([{"key": "A", "title": "a", "depends_on": ["Z"]}], "neither a key nor an issue"),
        ([{"key": "A", "title": "a", "depends_on": "12"}], "'depends_on' must be a list"),
        ([{"key": "A", "title": "a", "depends_on": [True]}], "'depends_on' must be a list"),
        ([{"key": "A", "title": "a", "labels": "bug"}], "'labels' must be a list"),
        ([{"key": "A", "title": "a", "milestone": "v1"}], "'milestone' must be a milestone number"),
        ([{"key": "A", "title": "a", "body": "see {#Z}"}], "unknown key {#Z}"),
        ([{"key": "A", "title": "a", "depends_on": ["B"]}, {"key": "B", "title": "b", "depends_on": ["A"]}], "cycle"),
    ],
)
def test_an_invalid_batch_files_nothing(records, message):
    api = FakeApi()
    with pytest.raises(ValueError) as e:
        _file(records, api=api)
    assert message in str(e.value)
    assert api.calls == []


def test_existing_issue_spellings_are_accepted():
    for dep in (12, "#12", "12", "owner/repo#12"):
        assert batch.validate([{"key": "A", "title": "a", "depends_on": [dep]}]) == ["A"]


def test_escaped_reference_stays_literal():
    api, _ = _file([{"key": "A", "title": "a", "body": "Pandoc anchor {{#intro}}."}])
    assert _text(api, 100) == "Pandoc anchor {#intro}."


def test_load_records_json_and_yaml(tmp_path):
    (tmp_path / "r.json").write_text(json.dumps(RECORDS))
    assert batch.load_records(tmp_path / "r.json") == RECORDS
    pytest.importorskip("yaml")
    (tmp_path / "r.yaml").write_text("- key: A\n  title: Parser\n")
    assert batch.load_records(tmp_path / "r.yaml") == [{"key": "A", "title": "Parser"}]
    (tmp_path / "d.json").write_text("{}")
    with pytest.raises(ValueError, match="list of records"):
        batch.load_records(tmp_path / "d.json")


def test_cli_dry_run_prints_the_order_and_calls_nothing(tmp_path, capsys, monkeypatch):
    from ge.__main__ import file_batch

    monkeypatch.setattr(batch, "file_issues", lambda *a, **kw: pytest.fail("dry run filed"))
    (tmp_path / "r.json").write_text(json.dumps(RECORDS))
    file_batch(str(tmp_path / "r.json"), "o/r", dry_run=True)
    assert [line.split()[0] for line in capsys.readouterr().out.splitlines()] == ["A", "B", "C"]


def test_gh_api_sends_a_json_body_on_stdin(monkeypatch):
    import subprocess

    from ge import util

    seen = {}

    def run(cmd, **kw):
        seen.update(cmd=cmd, input=kw.get("input"))
        return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": 1}', stderr="")

    monkeypatch.setattr(util, "_check_gh", lambda: None)
    monkeypatch.setattr(util.subprocess, "run", run)
    assert util.gh_api("repos/o/r/issues", method="POST", body={"labels": ["x"], "id": 3}) == {"ok": 1}
    assert seen["cmd"][-4:] == ["-X", "POST", "--input", "-"]
    assert json.loads(seen["input"]) == {"labels": ["x"], "id": 3}
    with pytest.raises(ValueError):
        util.gh_api("x", params={"a": 1}, body={"b": 2})


def test_a_body_edited_on_github_is_not_overwritten_unless_forced(tmp_path):
    map_path = tmp_path / "m.json"
    api, _ = _file(api=FakeApi(), map_path=map_path)
    api.issues[102]["body"] = "- [x] ticked by a person"  # edited on GitHub
    edited = [dict(r, body="Typo fixed, after {#B}.") if r["key"] == "C" else r for r in RECORDS]
    _, state = _file(edited, api=api, map_path=map_path)
    assert state["body_conflicts"] == ["C"] and api.issues[102]["body"] == "- [x] ticked by a person"
    _, state = _file(edited, api=api, map_path=map_path, force=True)
    assert state["body_conflicts"] == [] and _text(api, 102) == "Typo fixed, after #101."


def test_adoption_skips_pull_requests_and_pages_through_recent_issues(tmp_path):
    api = FakeApi()
    _file(api=api)
    mark = batch.marker(RECORDS[1])  # A's marker
    for n in range(200, 330):  # 130 newer issues push A (#100) to page 2
        api.issues[n] = {"number": n, "id": n * 10, "html_url": f"https://x/{n}", "body": ""}
    api.issues[400] = {"number": 400, "id": 4000, "html_url": "https://x/pull/400", "body": mark, "pull_request": {}}
    _, state = _file(api=api, map_path=tmp_path / "m.json")
    assert state["issues"]["A"]["number"] == 100  # not the PR, and found on page 2
    assert len(api.writes("POST", "/issues")) == 3


def test_markers_are_scoped_by_batch_name():
    a = {"key": "A", "title": "Parser"}
    assert batch.marker(a, "plan-1") != batch.marker(a, "plan-2")
    assert batch.marker(a, "plan-1") == batch.marker(dict(a, title="Renamed"), "plan-1")


def test_edges_of_a_removed_dependency_leave_the_map(tmp_path):
    map_path = tmp_path / "m.json"
    api = FakeApi(edge_error="gh api failed: HTTP 404")
    _file(api=api, map_path=map_path)
    api.edge_error = None
    trimmed = [dict(r, depends_on=["A"]) if r["key"] == "B" else r for r in RECORDS]
    _, state = _file(trimmed, api=api, map_path=map_path)
    assert state["edge_errors"] == []
    assert {(e["blocked"], e["blocker"]) for e in state["edges"]} == {("B", "A"), ("C", "B")}
