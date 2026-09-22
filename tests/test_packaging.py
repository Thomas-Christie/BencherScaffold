"""Tier 4c: what actually ends up in the published wheel.

poetry-core globs every file under the package directory, then subtracts
whatever git ignores. That second half is the risk: once a .gitignore exists, a
pattern that incidentally matches package content (*.pyi, protos/, ...) would
silently drop files from the published wheel with no build error. These
assertions are the only guard against that, so they pin the full expected file
set rather than spot-checking a couple of paths.
"""

import glob
import os
import pathlib
import shutil
import subprocess
import sys
import zipfile

import pytest

pytestmark = pytest.mark.tooling

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

EXPECTED_PACKAGE_FILES = {
    "bencherscaffold/__init__.py",
    "bencherscaffold/client.py",
    "bencherscaffold/dual_stack_service.py",
    "bencherscaffold/protoclasses/__init__.py",
    "bencherscaffold/protoclasses/bencher_pb2.py",
    "bencherscaffold/protoclasses/bencher_pb2.pyi",
    "bencherscaffold/protoclasses/bencher_pb2_grpc.py",
    "bencherscaffold/protoclasses/grcp_service.py",
    "bencherscaffold/protoclasses/second_level_services_pb2.py",
    "bencherscaffold/protoclasses/second_level_services_pb2.pyi",
    "bencherscaffold/protoclasses/second_level_services_pb2_grpc.py",
    "bencherscaffold/protos/bencher.proto",
    "bencherscaffold/protos/second_level_services.proto",
}


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    poetry = shutil.which("poetry")
    if poetry is None:
        pytest.skip("poetry is not installed")
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [poetry, "build", "--format", "wheel", "--output", str(out)],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        timeout=300,
    )
    built = glob.glob(os.path.join(str(out), "*.whl"))
    assert len(built) == 1, "expected exactly one wheel, got {}".format(built)
    return zipfile.ZipFile(built[0])


def test_wheel_ships_exactly_the_expected_package_files(wheel):
    shipped = {n for n in wheel.namelist() if n.startswith("bencherscaffold/")}
    assert shipped == EXPECTED_PACKAGE_FILES


def test_wheel_ships_the_proto_sources_and_type_stubs(wheel):
    """Downstream regenerates against these, so their absence would be silent breakage."""
    names = set(wheel.namelist())
    assert "bencherscaffold/protos/bencher.proto" in names
    assert "bencherscaffold/protoclasses/bencher_pb2.pyi" in names


def test_metadata_preserves_the_marker_split_pins(wheel):
    """End-to-end proof that the per-Python constraints survive into the artifact."""
    metadata_name = next(n for n in wheel.namelist() if n.endswith(".dist-info/METADATA"))
    metadata = wheel.read(metadata_name).decode("utf-8")

    for package in ("grpcio", "protobuf"):
        requirements = [
            line
            for line in metadata.splitlines()
            if line.startswith("Requires-Dist: {} ".format(package))
        ]
        assert len(requirements) == 2, "expected two marker-split pins for {}".format(package)
        assert any('python_version < "3.14"' in line for line in requirements)
        assert any('python_version >= "3.14"' in line for line in requirements)


@pytest.mark.parametrize(
    "module",
    ["bencherscaffold.client", "bencherscaffold.dual_stack_service",
     "bencherscaffold.protoclasses.grcp_service"],
)
def test_modules_import_in_a_clean_interpreter(module):
    """Cheap guard against import-time breakage (e.g. a 3.9+-only annotation).

    The version matrix catches these as collection errors, but only on the
    interpreter that breaks; this fails loudly everywhere.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import {}".format(module)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8")
