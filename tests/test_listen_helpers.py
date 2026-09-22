"""Tier 1: the pure listen-host helpers in dual_stack_service."""

import argparse

import pytest

from bencherscaffold.dual_stack_service import (
    _DEFAULT_HOSTS,
    _normalize_hosts,
    add_listen_argument,
    grpc_target,
    parse_listen_entries,
    resolve_listen_entries,
)

ENV_VAR = "BENCHERSCAFFOLD_TEST_LISTEN"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ("0.0.0.0", "[::]")),
        ([], ()),
        (["  a  ", "a", "", "b"], ("a", "b")),
        (["b", "a", "b"], ("b", "a")),
        (["   ", "\t"], ()),
    ],
    ids=["none-defaults", "empty", "strip-dedup", "first-wins-order", "all-blank"],
)
def test_normalize_hosts(raw, expected):
    assert _normalize_hosts(raw) == expected


def test_normalize_hosts_default_matches_module_constant():
    assert _normalize_hosts(None) == _DEFAULT_HOSTS


@pytest.mark.parametrize(
    "host,port,expected",
    [
        ("unix:/tmp/b.sock", 50051, "unix:/tmp/b.sock"),
        ("unix:///tmp/b.sock", 1, "unix:///tmp/b.sock"),
        ("127.0.0.1", 50051, "127.0.0.1:50051"),
        ("[::]", 50051, "[::]:50051"),
        ("example.org", 80, "example.org:80"),
    ],
    ids=["unix-passthrough", "unix-abs-passthrough", "ipv4", "ipv6-bracketed", "hostname"],
)
def test_grpc_target(host, port, expected):
    assert grpc_target(host, port) == expected


def test_grpc_target_bare_ipv6_is_malformed():
    """Characterization: a bare (unbracketed) IPv6 address produces a broken target.

    gRPC needs '[::]:1'; grpc_target only string-joins, so '::' yields ':::1'.
    This pins current behaviour — if bracket injection is ever added, this test
    should be updated deliberately rather than silently.
    """
    assert grpc_target("::", 1) == ":::1"


def test_parse_listen_entries_none_versus_empty():
    """None and "" are different answers, and the difference is load-bearing.

    resolve_listen_entries branches on `is not None`, so an empty env var means
    "zero hosts" (which later makes serve() raise), not "fall back to default".
    Both are falsy, so assert identity rather than truthiness.
    """
    assert parse_listen_entries(None) is None
    assert parse_listen_entries("") == ()
    assert parse_listen_entries("a, b ,a") == ("a", "b")


class TestResolveListenEntries:
    def test_cli_wins_over_env_and_default(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "from-env")
        assert resolve_listen_entries(["cli"], ENV_VAR, ["default"]) == ("cli",)

    def test_empty_cli_list_still_shadows_env(self, monkeypatch):
        """An empty list is not None, so it wins — yielding zero hosts."""
        monkeypatch.setenv(ENV_VAR, "from-env")
        assert resolve_listen_entries([], ENV_VAR, ["default"]) == ()

    def test_env_used_when_cli_absent(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "x, y ,x")
        assert resolve_listen_entries(None, ENV_VAR, ["default"]) == ("x", "y")

    def test_empty_env_shadows_default(self, monkeypatch):
        """Set-but-empty env var resolves to no hosts at all.

        See test_dual_stack_serve.py::test_serve_raises_when_no_hosts_configured
        for the consequence: serve() then raises RuntimeError.
        """
        monkeypatch.setenv(ENV_VAR, "")
        assert resolve_listen_entries(None, ENV_VAR, ["default"]) == ()

    def test_default_used_when_env_unset(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        assert resolve_listen_entries(None, ENV_VAR, ["default"]) == ("default",)

    def test_falls_back_to_module_defaults(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        assert resolve_listen_entries(None, ENV_VAR, None) == _DEFAULT_HOSTS
        assert resolve_listen_entries(None, None, None) == _DEFAULT_HOSTS


class TestAddListenArgument:
    def test_default_is_none_and_repeats_accumulate(self):
        """The default must stay None, and must not be mutated by a parse.

        resolve_listen_entries distinguishes None from (), so an argparse
        default of [] would silently change precedence. Parsing with args and
        then without, on the same parser, catches the classic aliasing bug.
        """
        parser = argparse.ArgumentParser()
        add_listen_argument(parser, ENV_VAR)

        assert parser.parse_args(["--listen-host", "a", "--listen-host", "b"]).listen_hosts == [
            "a",
            "b",
        ]
        assert parser.parse_args([]).listen_hosts is None

    def test_custom_option_and_dest(self):
        parser = argparse.ArgumentParser()
        add_listen_argument(parser, ENV_VAR, option="--bind", dest="binds")
        assert parser.parse_args(["--bind", "a"]).binds == ["a"]

    def test_help_mentions_env_var_and_examples(self):
        parser = argparse.ArgumentParser()
        add_listen_argument(parser, ENV_VAR, examples=["1.2.3.4", "unix:/tmp/x.sock"])
        help_text = parser.format_help()
        assert ENV_VAR in help_text
        assert "1.2.3.4" in help_text
        assert "unix:/tmp/x.sock" in help_text
