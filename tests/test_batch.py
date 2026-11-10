"""Offline tests for ge.batch: a fake GitHub API records every call."""

import json

import pytest

from ge import batch


class FakeApi:
    """Stands in for gh_api: numbers issues from 100, ids are number * 10."""

    def __init__(self, *, fail_create_at=None, edge_error=None):
        self.calls, self.bodies, self.next = [], {}, 100
        self.fail_create_at, self.edge_error = fail_create_at, edge_error

    def __call__(self, endpoint, *, method="GET", body=None, **kw):
        self.calls.append((method, endpoint, body))
        if method == "POST" and endpoint.endswith("/issues"):
            if self.next == self.fail_create_at:
                raise RuntimeError("gh api failed: secondary rate limit")
            n, self.next = self.next, self.next + 1
            self.bodies[n] = body["body"]
            return {"number": n, "id": n * 10, "html_url": f"https://x/issues/{n}"}
        if method == "PATCH":
            self.bodies[int(endpoint.rsplit("/", 1)[1])] = body["body"]
            return {}
        if endpoint.endswith("/blocked_by"):
            if self.edge_error:
                raise RuntimeError(self.edge_error)
            return {}
        if method == "GET":  # an existing issue
            return {"id": int(endpoint.rsplit("/", 1)[1]) * 10}
        raise AssertionError((method, endpoint))

    def edges(self):
        return [(e.split("/")[-3], b["issue_id"]) for m, e, b in self.calls if e.endswith("/blocked_by")]


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


def test_files_in_dependency_order_and_resolves_references():
    api, state = _file()
    assert {k: v["number"] for k, v in state["issues"].items()} == {"A": 100, "B": 101, "C": 102}
    # B was created before C existed, then patched once C had a number
    assert api.bodies == {100: "First.", 101: "Needs #100; docs in #102.", 102: "Documents #101."}
    assert sorted(state["bodies_final"]) == ["A", "B", "C"]
    created = [b for m, e, b in api.calls if m == "POST" and e == "repos/o/r/issues"]
    assert created[1]["labels"] == ["enhancement"] and "labels" not in created[0]


def test_creates_blocked_by_edges_with_internal_ids_including_existing_issues():
    api, state = _file()
    # blocked issue number in the URL, blocker's *id* (not number) in the body
    assert api.edges() == [("101", 1000), ("101", 120), ("102", 1010)]
    assert ("GET", "repos/o/r/issues/12", None) in api.calls
    assert state["edges"] == [["B", "A"], ["B", "#12"], ["C", "B"]]


def test_an_interrupted_run_resumes_from_the_map_without_filing_twice(tmp_path):
    map_path = tmp_path / "m.json"
    api = FakeApi(fail_create_at=101)
    with pytest.raises(RuntimeError):
        _file(api=api, map_path=map_path)
    assert list(json.loads(map_path.read_text())["issues"]) == ["A"]

    api2 = FakeApi()
    api2.next = 101
    _, state = _file(api=api2, map_path=map_path)
    creates = [b["title"] for m, e, b in api2.calls if m == "POST" and e == "repos/o/r/issues"]
    assert creates == ["Printer", "Docs"]  # A was not filed again
    assert api2.bodies[101] == "Needs #100; docs in #102."
    assert json.loads(map_path.read_text()) == state

    api3 = FakeApi()
    _file(api=api3, map_path=map_path)  # a third run has nothing left to do
    assert api3.calls == []


def test_failed_edges_are_recorded_retried_and_cleared(tmp_path):
    map_path = tmp_path / "m.json"
    _, state = _file(api=FakeApi(edge_error="HTTP 404 Not Found"), map_path=map_path)
    assert set(state["edge_errors"]) == {"B <- A", "B <- #12", "C <- B"} and state["edges"] == []
    api = FakeApi()
    _, state = _file(api=api, map_path=map_path)
    assert state["edge_errors"] == {} and len(state["edges"]) == 3
    assert not any(m == "POST" and e.endswith("/issues") for m, e, b in api.calls)


def test_an_edge_that_already_exists_counts_as_done():
    _, state = _file(api=FakeApi(edge_error="HTTP 422: Dependency already exists"))
    assert state["edge_errors"] == {} and len(state["edges"]) == 3


def test_a_map_from_another_repo_is_refused(tmp_path):
    map_path = tmp_path / "m.json"
    map_path.write_text(json.dumps({"repo": "other/repo", "issues": {}}))
    with pytest.raises(ValueError, match="other/repo"):
        _file(map_path=map_path)


@pytest.mark.parametrize(
    "records,message",
    [
        ([{"key": "A", "title": "a"}, {"key": "A", "title": "b"}], "duplicate key 'A'"),
        ([{"key": "A"}], "missing 'title'"),
        ([{"title": "a"}], "missing or non-string 'key'"),
        ([{"key": "A", "title": "a", "depends_on": ["Z"]}], "neither a key nor an issue"),
        ([{"key": "A", "title": "a", "body": "see {#Z}"}], "unknown key {#Z}"),
        ([{"key": "A", "title": "a", "depends_on": ["B"]}, {"key": "B", "title": "b", "depends_on": ["A"]}], "cycle"),
    ],
)
def test_an_invalid_batch_files_nothing(records, message):
    api = FakeApi()
    with pytest.raises(ValueError, match=message.replace("{", r"\{").replace("}", r"\}")):
        _file(records, api=api)
    assert api.calls == []


def test_existing_issue_spellings_are_accepted():
    for dep in (12, "#12", "12", "owner/repo#12"):
        assert batch.validate([{"key": "A", "title": "a", "depends_on": [dep]}]) == ["A"]


def test_load_records_json_and_yaml(tmp_path):
    (tmp_path / "r.json").write_text(json.dumps(RECORDS))
    assert batch.load_records(tmp_path / "r.json") == RECORDS
    pytest.importorskip("yaml")
    (tmp_path / "r.yaml").write_text("- key: A\n  title: Parser\n")
    assert batch.load_records(tmp_path / "r.yaml") == [{"key": "A", "title": "Parser"}]
    (tmp_path / "d.json").write_text("{}")
    with pytest.raises(ValueError, match="list of records"):
        batch.load_records(tmp_path / "d.json")


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
    assert seen["cmd"][-2:] == ["--input", "-"] and json.loads(seen["input"]) == {"labels": ["x"], "id": 3}
