"""Characterization tests pinning ge's CLI grammar.

ge is driven constantly by agents, so its command names, flag spellings and
exit codes are a contract. This module pins that contract at the level that
actually broke things during the argh -> cw migration:

* every command in ``_cli_commands`` is reachable under its dashed name;
* ``prepare -d`` DISABLES media description (``bool = True`` becomes a
  ``store_false`` flag) -- the counter-intuitive spelling ge's own docstrings
  document, and the one most likely to be "fixed" into a regression;
* no arguments prints usage to STDOUT and exits 0 (argh's behaviour, which a
  bare argparse parser with a required subparser does NOT reproduce);
* error paths exit 2;
* ``main()`` RETURNS its exit code rather than exiting, so the console script
  and the ``__main__`` guard must both propagate it.
"""

import json
import subprocess
import sys

import pytest

import cw
from ge.__main__ import _cli_commands, main

# The dashed command names argparse exposes, derived from the SSOT list.
COMMAND_NAMES = [f.__name__.replace("_", "-") for f in _cli_commands]


def _run(*argv):
    """Run ``python -m ge`` with argv, returning (rc, stdout, stderr)."""
    p = subprocess.run(
        [sys.executable, "-m", "ge", *argv],
        capture_output=True,
        text=True,
        timeout=180,
    )
    return p.returncode, p.stdout, p.stderr


@pytest.fixture(scope="module")
def parser():
    return cw.mk_parser(_cli_commands)


def test_every_command_in_the_ssot_list_is_reachable(parser):
    """Each function in _cli_commands gets a subcommand under its dashed name."""
    (subparsers,) = [
        a for a in parser._actions if isinstance(a, type(parser._subparsers._group_actions[0]))
    ] or [parser._subparsers._group_actions[0]]
    assert sorted(subparsers.choices) == sorted(COMMAND_NAMES)


def test_the_command_set_is_exactly_what_agents_depend_on():
    """A guard against silently adding/removing/renaming a command."""
    assert COMMAND_NAMES == [
        "prepare",
        "prepare-discussion",
        "analyze-issue",
        "analyze-pr",
        "fetch-issue",
        "fetch-pr",
        "fetch-discussion",
        "media",
        "video-frames",
        "describe-images",
        "copy-images",
        "resolve",
        "install-skills",
        "uninstall-skills",
        "roadmap-show",
        "roadmap-next",
        "roadmap-set",
        "roadmap-append",
        "decision-log",
        "decisions-show",
        "triage-show",
        "triage-set",
        "check-requirements",
        "run-roadmap",
        "run-triage",
    ]


@pytest.mark.parametrize("flag", ["-d", "--describe-media"])
def test_prepare_d_flag_DISABLES_media_description(parser, flag):
    """``-d`` turns descriptions OFF. It is a store_false, not a store_true.

    ``describe_media: bool = True`` makes argh/cw emit a bare flag that flips
    the default to False. ge's docstrings document ``-d`` as "disable image
    descriptions". Reading it as "enable" would invert the behaviour of every
    ``ge prepare`` an agent runs.
    """
    assert parser.parse_args(["prepare", "a/b", flag]).describe_media is False


def test_prepare_describes_media_by_default(parser):
    assert parser.parse_args(["prepare", "a/b"]).describe_media is True


def test_prepare_d_takes_no_value(parser):
    """``-d`` is a bare flag; a value after it is parsed as the next argument."""
    ns = parser.parse_args(["prepare", "a/b", "-d", "-n", "42"])
    assert (ns.describe_media, ns.number) == (False, 42)


def test_no_arguments_prints_usage_to_stdout_and_exits_zero():
    """argh's behaviour, preserved. Bare argparse would exit 2 to stderr."""
    rc, out, err = _run()
    assert rc == 0
    assert out.startswith("usage:")
    assert err == ""


def test_invalid_command_exits_two():
    rc, out, err = _run("no-such-command")
    assert rc == 2
    assert "invalid choice" in err


def test_missing_required_argument_exits_two():
    rc, out, err = _run("prepare")
    assert rc == 2
    assert "url-or-spec" in err


def test_unrecognised_flag_exits_two():
    rc, out, err = _run("prepare", "--no-such-flag")
    assert rc == 2


def test_main_returns_the_exit_code_rather_than_exiting():
    """cw.dispatch RETURNS the code where argh exited by itself.

    The console script (``ge = ge.__main__:main``) and the ``__main__`` guard
    both rely on this being a return value. If ``main()`` grew a bare
    ``cw.dispatch(...)`` with no return, every error path would exit 0 and no
    other test in this repo would notice.
    """
    argv = sys.argv
    try:
        sys.argv = ["ge", "no-such-command"]
        rc = main()
    finally:
        sys.argv = argv
    # cw.dispatch swallows argparse's SystemExit and hands back the code, so
    # main() RETURNS 2 here. It must never return None on a failure path.
    assert rc == 2


def test_module_entry_point_propagates_a_nonzero_exit_code():
    """End-to-end proof that `python -m ge` does not swallow failures."""
    assert _run("prepare")[0] == 2


def test_help_lists_every_command():
    rc, out, err = _run("--help")
    assert rc == 0
    for name in COMMAND_NAMES:
        assert name in out


@pytest.mark.parametrize("name", COMMAND_NAMES)
def test_every_subcommand_has_working_help(name):
    rc, out, err = _run(name, "--help")
    assert rc == 0, err
    assert out.startswith("usage:")


def test_ge_does_not_depend_on_argh():
    """The migration's point: argh (LGPL) is gone from the runtime path."""
    import ge.__main__ as m

    assert "argh" not in open(m.__file__).read()
