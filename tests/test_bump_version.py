"""Tier 4b: the release scripts that rewrite pyproject.toml on every master push.

bump_version.py does a full toml.load/toml.dump round trip of pyproject.toml,
so the risk it carries is not the arithmetic -- it is silently flattening the
marker-split dependency tables that give this package its per-Python pins.
"""

import pathlib
import shutil

import pytest
import toml

import bump_version
import get_version

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"

MINIMAL = """\
[tool.poetry]
name = "demo"
version = "0.9.9"

[[tool.poetry.dependencies.grpcio]]
version = "~1.70.0"
markers = "python_version < '3.14'"
"""


@pytest.fixture
def in_copy_of_pyproject(tmp_path, monkeypatch):
    shutil.copy(PYPROJECT, tmp_path / "pyproject.toml")
    monkeypatch.chdir(tmp_path)
    return tmp_path / "pyproject.toml"


def _bump(version):
    major, minor, patch = map(int, version.split("."))
    return "{}.{}.{}".format(major, minor, patch + 1)


def test_patch_version_is_incremented(in_copy_of_pyproject):
    before = toml.load(str(in_copy_of_pyproject))
    bump_version.bump_version()
    after = toml.load(str(in_copy_of_pyproject))

    assert after["tool"]["poetry"]["version"] == _bump(before["tool"]["poetry"]["version"])


def test_nothing_but_the_version_changes(in_copy_of_pyproject):
    """One assertion covering every table, not just the ones we thought of."""
    before = toml.load(str(in_copy_of_pyproject))
    bump_version.bump_version()
    after = toml.load(str(in_copy_of_pyproject))

    before["tool"]["poetry"].pop("version")
    after["tool"]["poetry"].pop("version")
    assert before == after


def test_marker_split_dependencies_survive_the_round_trip(in_copy_of_pyproject):
    """The per-Python pins are arrays of tables -- exactly what a lossy round
    trip would flatten, and what a wrong pin would silently break at install."""
    bump_version.bump_version()
    after = toml.load(str(in_copy_of_pyproject))

    assert after["tool"]["poetry"]["dependencies"]["grpcio"] == [
        {"version": "~1.70.0", "markers": "python_version < '3.14'"},
        {"version": "~1.76.0", "markers": "python_version >= '3.14'"},
    ]
    assert after["tool"]["poetry"]["group"]["dev"]["dependencies"]["grpcio-tools"] == [
        {"version": "~1.62.0", "markers": "python_version < '3.14'"},
        {"version": "~1.76.0", "markers": "python_version >= '3.14'"},
    ]
    assert after["build-system"]["build-backend"] == "poetry.core.masonry.api"
    assert after["tool"]["poetry"]["packages"] == [{"include": "bencherscaffold", "from": "."}]


def test_marker_quoting_survives_as_text(in_copy_of_pyproject):
    """The markers contain single quotes inside a double-quoted string; a bad
    round trip mangles the quoting without changing the parsed structure."""
    bump_version.bump_version()
    text = in_copy_of_pyproject.read_text(encoding="utf-8")
    assert "python_version < '3.14'" in text
    assert "python_version >= '3.14'" in text


def test_patch_rolls_past_nine_without_touching_minor(tmp_path, monkeypatch):
    target = tmp_path / "pyproject.toml"
    target.write_text(MINIMAL, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    bump_version.bump_version()

    after = toml.load(str(target))
    assert after["tool"]["poetry"]["version"] == "0.9.10"
    assert after["tool"]["poetry"]["dependencies"]["grpcio"] == [
        {"version": "~1.70.0", "markers": "python_version < '3.14'"}
    ]


def test_get_version_reads_the_current_version(in_copy_of_pyproject):
    expected = toml.load(str(in_copy_of_pyproject))["tool"]["poetry"]["version"]
    assert get_version.get_version() == expected
