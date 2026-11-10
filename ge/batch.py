"""File a batch of related issues: dependency order, cross-references, ``blocked_by`` edges.

A batch is a list of records, each with a ``key`` local to the batch::

    [
      {"key": "A", "title": "Parser", "body": "First piece."},
      {"key": "B", "title": "Printer", "body": "Uses the parser of {#A}.",
       "labels": ["enhancement"], "depends_on": ["A", "#12"]}
    ]

:func:`file_issues` validates the whole batch before filing anything (field
types, unique keys, known references, no dependency cycle), then:

1. creates the issues in dependency order, replacing each ``{#KEY}`` in a body
   with the ``#number`` that issue became (write ``{{#x}}`` for a literal ``{#x}``);
2. updates every body whose final text differs from what was last sent: the
   ones that referred to a key filed later, and any record edited since. A body
   someone has edited on GitHub since is never overwritten: it is listed in
   ``body_conflicts`` instead (``force=True`` overwrites);
3. creates a GitHub ``blocked_by`` dependency edge for every ``depends_on``
   that the blocked issue does not already have.

``depends_on`` takes batch keys and existing issues (``12``, ``"#12"``,
``"owner/repo#12"``). Progress is written to a map file after every step, so
an interrupted run is resumed by running it again. Each body carries a hidden
marker for its record (its key and the batch name), so an issue created just
before a crash (or after a lost map) is found among the repository's recent
issues and adopted, not filed twice.
The map's shape is stable, for writing the links back into a source document::

    {"repo": "owner/repo",
     "issues": {"A": {"number": 7, "url": "...", "id": 123, "body_sha": "..."}},
     "edges": [{"blocked": "B", "blocker": "A"}],
     "edge_errors": [{"blocked": "B", "blocker": "#12", "error": "..."}],
     "body_conflicts": ["C"]}

The batch knows nothing about any document format: produce the records however you like.
"""

import hashlib
import json
import os
import re
import time
from collections.abc import Callable, Iterable, Mapping
from graphlib import CycleError, TopologicalSorter
from pathlib import Path

#: ``{#KEY}`` in a body becomes ``#number`` once KEY is filed; ``{{#KEY}}`` stays literal.
REF_PATTERN = re.compile(r"(?<!\{)\{#([^{}\s]+)\}(?!\})")
_ESCAPED_REF = re.compile(r"\{(\{#[^{}\s]+\})\}")
#: An existing issue named in ``depends_on``: ``12``, ``#12``, ``owner/repo#12``.
EXISTING_ISSUE = re.compile(r"^(?:(?P<repo>[\w.-]+/[\w.-]+))?#?(?P<number>\d+)$")
#: Seconds after each write to GitHub; it throttles bursts of content creation.
DEFAULT_PAUSE = 1.0
#: Pages of 100 of the repository's most recent issues searched for an unrecorded one.
ADOPT_PAGES = 3
_LIST_FIELDS = ("depends_on", "labels", "assignees")

Api = Callable[..., object]  # gh_api's signature: (endpoint, *, method=..., body=...)


def _refs(text: str) -> set[str]:
    """Keys referred to as ``{#KEY}`` in *text*.

    >>> sorted(_refs("after {#A} and {#B.2}, not {A}, #3 or {{#C}}"))
    ['A', 'B.2']
    """
    return set(REF_PATTERN.findall(text or ""))


def render_body(body: str, numbers: Mapping[str, int]) -> str:
    """Replace ``{#KEY}`` with ``#number`` for every key already filed.

    >>> render_body("after {#A}, before {#B}, literal {{#A}}", {"A": 7})
    'after #7, before {#B}, literal {#A}'
    """
    text = REF_PATTERN.sub(lambda m: f"#{numbers[m[1]]}" if m[1] in numbers else m[0], body or "")
    return _ESCAPED_REF.sub(r"\1", text)


def marker(record: Mapping, batch: str | None = None) -> str:
    """Hidden line identifying the record an issue was filed from.

    It hashes the key and the *batch* name, so two batches using the same keys
    in one repository never adopt each other's issues; without a batch name the
    title stands in for it.
    """
    scope = record["title"] if batch is None else batch
    digest = hashlib.sha1(f"{record['key']}\0{scope}".encode()).hexdigest()[:12]
    return f"<!-- ge-batch:{digest} -->"


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()


def validate(records: Iterable[Mapping]) -> list[str]:
    """Check a batch and return its keys in filing order; raise ValueError on any problem.

    >>> validate([{"key": "B", "title": "b", "depends_on": ["A"]},
    ...           {"key": "A", "title": "a", "body": "see {#B}"}])
    ['A', 'B']
    """
    records = list(records)
    problems, seen = [], set()
    for i, r in enumerate(records):
        k = r.get("key")
        name = k if isinstance(k, str) else f"record {i}"
        if not k or not isinstance(k, str):
            problems.append(f"record {i}: missing or non-string 'key'")
        elif EXISTING_ISSUE.match(k):
            problems.append(f"{k}: a key must not look like an issue number")
        elif k in seen:
            problems.append(f"record {i}: duplicate key {k!r}")
        seen.add(k)
        if not r.get("title") or not isinstance(r["title"], str):
            problems.append(f"{name}: missing or non-string 'title'")
        if not isinstance(r.get("body", ""), str):
            problems.append(f"{name}: 'body' must be a string")
        for field in _LIST_FIELDS:
            v = r.get(field, [])
            if not isinstance(v, list) or any(isinstance(x, bool) or not isinstance(x, (str, int)) for x in v):
                problems.append(f"{name}: {field!r} must be a list of strings or numbers, got {v!r}")
        m = r.get("milestone")
        if m is not None and (isinstance(m, bool) or not isinstance(m, int)):
            problems.append(f"{name}: 'milestone' must be a milestone number, got {m!r}")
    if problems:  # the checks below assume well-typed records
        raise ValueError("invalid batch:\n  " + "\n  ".join(problems))
    for r in records:
        for dep in r.get("depends_on", ()):
            if str(dep) not in seen and not EXISTING_ISSUE.match(str(dep)):
                problems.append(f"{r['key']}: depends_on {dep!r} is neither a key nor an issue")
        for ref in _refs(r.get("body", "")) - seen:
            problems.append(f"{r['key']}: body refers to unknown key {{#{ref}}} (write {{{{#{ref}}}}} for a literal)")
    if problems:
        raise ValueError("invalid batch:\n  " + "\n  ".join(problems))
    graph = {r["key"]: [str(d) for d in r.get("depends_on", ()) if str(d) in seen] for r in records}
    try:
        TopologicalSorter(graph).prepare()
    except CycleError as e:
        raise ValueError(f"invalid batch: dependency cycle {e.args[1]}") from None
    depth: dict[str, int] = {}

    def depth_of(key):  # longest dependency chain under key
        if key not in depth:
            depth[key] = 1 + max((depth_of(d) for d in graph[key]), default=-1)
        return depth[key]

    position = {r["key"]: i for i, r in enumerate(records)}  # input order among peers
    return sorted(graph, key=lambda k: (depth_of(k), position[k]))


def _normalize_repo(repo: str) -> str:
    from ge.util import parse_repo_spec

    return "/".join(parse_repo_spec(repo))


def _load_map(path: Path | None, repo: str) -> dict:
    state = {"repo": repo, "issues": {}, "edges": [], "edge_errors": [], "body_conflicts": []}
    if path and path.exists():
        state.update(json.loads(path.read_text()))
        if state["repo"].lower() != repo.lower():
            raise ValueError(f"{path} records a batch filed in {state['repo']}, not {repo}")
    return state


def _save_map(path: Path | None, state: Mapping) -> None:
    """Write the map atomically: a crash mid-write leaves the previous map intact."""
    if path:
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        with open(tmp, "w") as f:
            f.write(json.dumps(state, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)


def file_issues(
    records: Iterable[Mapping],
    repo: str,
    *,
    map_path: str | Path | None = None,
    batch: str | None = None,
    force: bool = False,
    api: Api | None = None,
    pause: float = DEFAULT_PAUSE,
    adopt_pages: int = ADOPT_PAGES,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> dict:
    """File *records* as issues in *repo* (``owner/name`` or URL); return the map (see module doc).

    *api* defaults to :func:`ge.util.gh_api`; pass a fake to test.
    """
    if api is None:
        from ge.util import gh_api as api
    records = list(records)
    order = validate(records)
    records = {r["key"]: r for r in records}
    repo = _normalize_repo(repo)
    path = Path(map_path) if map_path else None
    state = _load_map(path, repo)
    issues = state["issues"]

    def numbers():
        return {k: v["number"] for k, v in issues.items()}

    def final_body(key):
        return render_body(records[key].get("body", ""), numbers()) + "\n\n" + marker(records[key], batch)

    def write(endpoint, method, body):
        out = api(endpoint, method=method, body=body)
        sleep(pause)
        return out

    def record_issue(key, issue, body_sha):
        issues[key] = {"number": issue["number"], "url": issue["html_url"], "id": issue["id"], "body_sha": body_sha}
        _save_map(path, state)
        log(f"{key}  #{issue['number']}  {issue['html_url']}")

    # 0. adopt issues created by an earlier run that died before saving the map;
    # what was sent is unknown, so body_sha stays None (step 2 handles it)
    missing = {marker(records[k], batch): k for k in order if k not in issues}
    for page in range(1, adopt_pages + 1):
        if not missing:
            break
        recent = api(f"repos/{repo}/issues?state=all&sort=created&direction=desc&per_page=100&page={page}")
        for issue in recent:
            for mark, key in list(missing.items()):
                if mark in (issue.get("body") or "") and "pull_request" not in issue:
                    record_issue(key, issue, None)
                    del missing[mark]
        if len(recent) < 100:
            break

    for key in order:  # 1. create
        if key in issues:
            continue
        r = records[key]
        payload = {"title": r["title"], "body": final_body(key)}
        for field in ("labels", "assignees", "milestone"):
            if r.get(field):
                payload[field] = r[field]
        made = write(f"repos/{repo}/issues", "POST", payload)
        record_issue(key, made, _sha(made.get("body") or payload["body"]))

    conflicts = []
    for key in order:  # 2. bodies with forward references, or records edited since
        body, known = final_body(key), issues[key].get("body_sha")
        if _sha(body) == known:
            continue
        endpoint = f"repos/{repo}/issues/{issues[key]['number']}"
        current = api(endpoint).get("body") or ""
        ours = _sha(current) == known or (known is None and REF_PATTERN.search(current))
        if _sha(current) == _sha(body):
            issues[key]["body_sha"] = _sha(current)
        elif ours or force:
            made = write(endpoint, "PATCH", {"body": body})
            issues[key]["body_sha"] = _sha((made or {}).get("body") or body)
        else:  # someone edited it on GitHub: never overwrite silently
            conflicts.append(key)
            log(f"{key}: #{issues[key]['number']} was edited on GitHub; not updated (force=True overwrites)")
        _save_map(path, state)
    state["body_conflicts"] = conflicts
    _save_map(path, state)

    wanted = {(k, str(d)) for k in order for d in records[k].get("depends_on", ())}
    state["edges"] = [e for e in state["edges"] if (e["blocked"], e["blocker"]) in wanted]
    state["edge_errors"] = [e for e in state["edge_errors"] if (e["blocked"], e["blocker"]) in wanted]
    done = {(e["blocked"], e["blocker"]) for e in state["edges"]}
    for key in order:  # 3. dependency edges
        number = issues[key]["number"]
        endpoint = f"repos/{repo}/issues/{number}/dependencies/blocked_by"
        existing = None
        for dep in map(str, records[key].get("depends_on", ())):
            if (key, dep) in done:
                continue
            state["edge_errors"] = [e for e in state["edge_errors"] if (e["blocked"], e["blocker"]) != (key, dep)]
            try:
                if dep in issues:
                    blocker = issues[dep]["id"]
                else:
                    m = EXISTING_ISSUE.match(dep)
                    blocker = api(f"repos/{m['repo'] or repo}/issues/{m['number']}")["id"]
                if existing is None:
                    existing = {i["id"] for i in api(f"{endpoint}?per_page=100")}
                if blocker not in existing:
                    write(endpoint, "POST", {"issue_id": blocker})
                    existing.add(blocker)
            except RuntimeError as e:
                state["edge_errors"].append({"blocked": key, "blocker": dep, "error": str(e)})
                _save_map(path, state)
                log(f"{key}: blocked_by {dep} failed: {e}")
                continue
            state["edges"].append({"blocked": key, "blocker": dep})
            done.add((key, dep))
            _save_map(path, state)
    return state


def load_records(path: str | Path) -> list[dict]:
    """Records from a ``.json`` file (a list), or ``.yaml`` / ``.yml`` when PyYAML is installed."""
    path = Path(path)
    text = path.read_text()
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise ImportError(f"{path} is YAML: pip install pyyaml, or give a .json file") from None
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{path} must hold a list of records, got {type(data).__name__}")
    return data
