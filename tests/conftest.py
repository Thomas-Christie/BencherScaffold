import contextlib
import os
import shutil
import socket
import tempfile
from concurrent.futures import ThreadPoolExecutor

import grpc
import pytest

import bencherscaffold.client
from bencherscaffold.client import BencherClient
from bencherscaffold.protoclasses import bencher_pb2_grpc
from bencherscaffold.protoclasses.bencher_pb2 import EvaluationResult

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RecordingStub:
    """Stand-in for ``BencherStub`` that records requests and replays a script.

    Each entry of ``script`` is either an ``EvaluationResult`` to return or an
    exception to raise. The last entry repeats once the script is exhausted, so
    an always-failing stub is just ``[grpc.RpcError()]``.
    """

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.calls = 0

    def evaluate_point(self, request, **kwargs):
        self.requests.append(request)
        self.calls += 1
        item = self.script[min(self.calls - 1, len(self.script) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def make_client():
    """Builds real BencherClients (real channel, real grpc_target) with a fake stub."""
    created = []

    def _make(script=(EvaluationResult(value=0.0),), **kwargs):
        kwargs.setdefault("wait_time", 0)
        client = BencherClient(**kwargs)
        client.stub = RecordingStub(script)
        created.append(client)
        return client

    yield _make
    for client in created:
        client.channel.close()


@pytest.fixture
def sleeps(monkeypatch):
    """Records what the retry loop passes to time.sleep, without sleeping."""
    recorded = []
    monkeypatch.setattr(
        bencherscaffold.client.time, "sleep", lambda seconds: recorded.append(seconds)
    )
    return recorded


class EchoBencher(bencher_pb2_grpc.BencherServicer):
    """Real servicer: records requests, optionally fails the first N calls."""

    def __init__(self, value=42.0, fail_times=0):
        self.requests = []
        self.value = value
        self.fail_times = fail_times

    def evaluate_point(self, request, context):
        self.requests.append(request)
        if len(self.requests) <= self.fail_times:
            context.abort(grpc.StatusCode.UNAVAILABLE, "not ready yet")
        return EvaluationResult(value=self.value + len(request.point.values))


@contextlib.contextmanager
def running_server(servicer, bind_target):
    """Starts a real gRPC server on ``bind_target`` and tears it down promptly."""
    server = grpc.server(ThreadPoolExecutor(max_workers=2))
    bencher_pb2_grpc.add_BencherServicer_to_server(servicer, server)
    bound = server.add_insecure_port(bind_target)
    if bound == 0:
        server.stop(None).wait(timeout=5)
        raise AssertionError("could not bind {}".format(bind_target))
    server.start()
    try:
        yield bound
    finally:
        # stop(None) cancels in-flight RPCs immediately; a grace period here is
        # the usual cause of slow, occasionally hanging teardown.
        server.stop(None).wait(timeout=10)


@pytest.fixture
def tcp_server():
    """Yields (servicer, port); the port is the one the OS actually assigned."""

    @contextlib.contextmanager
    def _serve(**kwargs):
        servicer = EchoBencher(**kwargs)
        with running_server(servicer, "127.0.0.1:0") as port:
            yield servicer, port

    return _serve


@pytest.fixture
def unix_server(short_socket_path):
    """Yields (servicer, target) for a server bound to a unix socket."""

    @contextlib.contextmanager
    def _serve(**kwargs):
        servicer = EchoBencher(**kwargs)
        target = "unix:" + short_socket_path
        with running_server(servicer, target) as bound:
            # add_insecure_port returns 1 for a unix socket, not a port number.
            assert bound != 0
            yield servicer, target

    return _serve


@pytest.fixture
def short_socket_path():
    """A unix socket path short enough for sun_path (104 bytes on macOS, 108 on Linux).

    pytest's tmp_path embeds the test name and can run long, so this uses a
    dedicated short directory instead.
    """
    if not hasattr(socket, "AF_UNIX"):
        pytest.skip("platform has no AF_UNIX")
    directory = tempfile.mkdtemp(prefix="bs", dir=os.environ.get("RUNNER_TEMP") or "/tmp")
    path = os.path.join(directory, "s")
    if len(path.encode()) >= 100:
        shutil.rmtree(directory, ignore_errors=True)
        pytest.skip("unix socket path too long: {}".format(path))
    try:
        yield path
    finally:
        # gRPC does not reliably unlink the socket on stop; a leftover file
        # makes a later add_insecure_port return 0.
        with contextlib.suppress(FileNotFoundError):
            os.unlink(path)
        shutil.rmtree(directory, ignore_errors=True)
