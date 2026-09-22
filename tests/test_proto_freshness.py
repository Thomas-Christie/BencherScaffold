"""Tier 4a: the checked-in protoclasses must match the .proto sources.

Catches the "edited the .proto, forgot to run create_protos.sh" mistake.

The comparison is on the *parsed* FileDescriptorProto embedded in each
generated module, extracted with ast without ever importing the regenerated
file. That matters twice over:

  * importing a regenerated _pb2 module alongside the checked-in one registers
    the same proto file twice and blows up the default descriptor pool;
  * a byte-diff would fail on protoc's version header, and --descriptor_set_out
    would fail because it emits json_name on every field while the descriptor
    embedded in gencode omits it.
"""

import ast
import os
import pathlib

import pytest

from bencherscaffold.protoclasses import bencher_pb2, second_level_services_pb2

pytestmark = pytest.mark.tooling

grpc_tools = pytest.importorskip("grpc_tools", reason="grpcio-tools not installed")
from grpc_tools import protoc  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PROTOCLASSES = REPO_ROOT / "bencherscaffold" / "protoclasses"
PROTO_MODULES = {"bencher": bencher_pb2, "second_level_services": second_level_services_pb2}

REGENERATE_HINT = "protos are stale -- run ./create_protos.sh and commit the result"


def _embedded_descriptor(path):
    """Returns the bytes passed to AddSerializedFile, without importing the module."""
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "AddSerializedFile":
            return node.args[0].value
    raise AssertionError("no AddSerializedFile call found in {}".format(path))


def _parsed(serialized):
    from google.protobuf import descriptor_pb2

    descriptor = descriptor_pb2.FileDescriptorProto()
    descriptor.ParseFromString(serialized)
    return descriptor


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory):
    out = tmp_path_factory.mktemp("protogen")
    well_known = os.path.join(os.path.dirname(grpc_tools.__file__), "_proto")
    # -I must be the repo root: the include path is baked into the descriptor's
    # file name, and the checked-in one says bencherscaffold/protos/...
    args = ["protoc", "-I={}".format(REPO_ROOT), "-I={}".format(well_known),
            "--python_out={}".format(out), "--grpc_python_out={}".format(out)]
    args += [str(REPO_ROOT / "bencherscaffold" / "protos" / "{}.proto".format(name))
             for name in PROTO_MODULES]
    assert protoc.main(args) == 0, "protoc failed"
    return out / "bencherscaffold" / "protos"


@pytest.mark.parametrize("name", sorted(PROTO_MODULES))
def test_generated_descriptor_matches_proto_source(regenerated, name):
    fresh = _parsed(_embedded_descriptor(regenerated / "{}_pb2.py".format(name)))
    current = _parsed(PROTO_MODULES[name].DESCRIPTOR.serialized_pb)
    assert current == fresh, REGENERATE_HINT


@pytest.mark.parametrize("name", sorted(PROTO_MODULES))
def test_grpc_stubs_expose_every_rpc(name):
    """Structural check on _pb2_grpc.py, driven off the descriptor.

    The stub files are never text-diffed: grpcio-tools >= 1.63 adds a
    GRPC_GENERATED_VERSION guard block that 1.62 does not, so their text
    legitimately differs by toolchain while the RPC surface must not.
    """
    source = (PROTOCLASSES / "{}_pb2_grpc.py".format(name)).read_text(encoding="utf-8")
    descriptor = _parsed(PROTO_MODULES[name].DESCRIPTOR.serialized_pb)
    for service in descriptor.service:
        for method in service.method:
            assert "'/{}/{}'".format(service.name, method.name) in source, REGENERATE_HINT


@pytest.mark.parametrize("name", sorted(PROTO_MODULES))
def test_imports_are_rewritten_to_protoclasses(name):
    """protoc emits `from bencherscaffold.protos import`; the package ships
    these modules from protoclasses, so create_protos.sh rewrites the import.
    Nothing else guards that step."""
    for suffix in ("_pb2.py", "_pb2_grpc.py", "_pb2.pyi"):
        path = PROTOCLASSES / "{}{}".format(name, suffix)
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        assert "from bencherscaffold.protos import" not in source, REGENERATE_HINT
