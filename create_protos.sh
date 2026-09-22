#!/usr/bin/env bash
# Regenerates bencherscaffold/protoclasses/ from bencherscaffold/protos/*.proto.
#
# protoc emits the modules next to the .proto files, with imports rooted at
# bencherscaffold.protos. The package ships them from bencherscaffold.protoclasses
# instead, so this script moves the generated files and rewrites those imports.
# tests/test_proto_freshness.py fails if the checked-in output drifts from the .proto
# sources, and its failure message points back here.
set -euo pipefail

cd "$(dirname "$0")"

python -m grpc_tools.protoc -I=. --python_out=. --pyi_out=. --grpc_python_out=. \
    bencherscaffold/protos/*.proto

for f in bencherscaffold/protos/*_pb2.py bencherscaffold/protos/*_pb2.pyi bencherscaffold/protos/*_pb2_grpc.py; do
    [ -e "$f" ] || continue
    sed -i.bak 's/^from bencherscaffold\.protos import/from bencherscaffold.protoclasses import/' "$f"
    rm -f "$f.bak"
    mv "$f" bencherscaffold/protoclasses/
done

echo "Regenerated bencherscaffold/protoclasses/"
