"""Tier 3a: a real gRPC server, a real BencherClient, over TCP and a unix socket.

BencherClient talks to /Bencher/evaluate_point, so these tests pair it with a
BencherServicer. GRCPService/DualStackGRCPService serve the *different*
/SecondLevelBencher/evaluate_point service and would answer UNIMPLEMENTED here.
"""

import grpc
import pytest

from bencherscaffold.client import BencherClient
from bencherscaffold.protoclasses.bencher_pb2 import BenchmarkType, Value, ValueType


def _client(address, port):
    client = BencherClient(address=address, port=port, max_retries=3, wait_time=0)
    # Wait for the subchannel so the first RPC cannot race it and silently
    # consume a retry, which would make request counting non-deterministic.
    grpc.channel_ready_future(client.channel).result(timeout=15)
    return client


def _point():
    return [
        Value(type=ValueType.CONTINUOUS, value=1.0),
        Value(type=ValueType.CONTINUOUS, value=2.0),
    ]


def test_roundtrip_over_tcp(tcp_server):
    with tcp_server() as (servicer, port):
        client = _client("127.0.0.1", port)
        try:
            result = client.evaluate_point("live-bench", _point())
        finally:
            client.channel.close()

    assert result == 44.0  # 42.0 + two values
    assert len(servicer.requests) == 1
    request = servicer.requests[0]
    assert request.benchmark.name == "live-bench"
    assert request.benchmark.type == BenchmarkType.PURELY_CONTINUOUS
    assert [v.value for v in request.point.values] == [1.0, 2.0]


def test_mixed_point_reaches_the_server_as_mixed(tcp_server):
    point = [
        Value(type=ValueType.CONTINUOUS, value=1.0),
        Value(type=ValueType.BINARY, value=1.0),
    ]
    with tcp_server() as (servicer, port):
        client = _client("127.0.0.1", port)
        try:
            client.evaluate_point("live-bench", point)
        finally:
            client.channel.close()

    assert servicer.requests[0].benchmark.type == BenchmarkType.MIXED


def test_real_retry_recovers_from_server_errors(tcp_server):
    """Exercises the grpc.RpcError retry path through real serialization."""
    with tcp_server(fail_times=2) as (servicer, port):
        client = _client("127.0.0.1", port)
        try:
            result = client.evaluate_point("live-bench", _point())
        finally:
            client.channel.close()

    assert result == 44.0
    assert len(servicer.requests) == 3


def test_retries_exhausted_against_a_real_server(tcp_server):
    with tcp_server(fail_times=99) as (servicer, port):
        client = _client("127.0.0.1", port)
        try:
            with pytest.raises(grpc.RpcError):
                client.evaluate_point("live-bench", _point())
        finally:
            client.channel.close()

    assert len(servicer.requests) == 3  # max_retries=3


def test_roundtrip_over_unix_socket(unix_server):
    """Covers the grpc_target unix: passthrough branch end to end."""
    with unix_server() as (servicer, target):
        client = _client(target, 0)
        try:
            result = client.evaluate_point("unix-bench", _point())
        finally:
            client.channel.close()

    assert result == 44.0
    assert servicer.requests[0].benchmark.name == "unix-bench"
