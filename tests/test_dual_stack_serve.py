"""Tier 3b: DualStackGRCPService binding logic, with grpc.server faked.

serve() blocks forever on wait_for_termination and binds fixed ports, so it is
driven here through a fake server. That keeps the binding rules (which hosts,
which targets, what happens when a bind fails) deterministic and fast.
"""

import pytest

import bencherscaffold.dual_stack_service as dss
from bencherscaffold.dual_stack_service import DualStackGRCPService


class FakeServer:
    def __init__(self, port_results):
        self.port_results = list(port_results)
        self.targets = []
        self.handlers = []
        self.started = 0
        self.waited = 0

    def add_insecure_port(self, target):
        self.targets.append(target)
        return self.port_results.pop(0)

    def add_generic_rpc_handlers(self, handlers):
        self.handlers.extend(handlers)

    def start(self):
        self.started += 1

    def wait_for_termination(self, timeout=None):
        self.waited += 1


@pytest.fixture
def fake_grpc_server(monkeypatch):
    """Replaces grpc.server; returns a callable yielding the FakeServer built."""
    created = {}
    executors = []

    def _install(port_results):
        def factory(executor, *args, **kwargs):
            executors.append(executor)
            server = FakeServer(port_results)
            created["server"] = server
            return server

        monkeypatch.setattr(dss.grpc, "server", factory)
        return created

    yield _install
    # serve() builds a real ThreadPoolExecutor even with a fake server.
    for executor in executors:
        executor.shutdown(wait=False)


def test_binds_every_host_then_starts(fake_grpc_server):
    created = fake_grpc_server([50000, 50000])
    service = DualStackGRCPService(listen_hosts=["0.0.0.0", "[::]"], port=50000)

    service.serve()

    server = created["server"]
    assert server.targets == ["0.0.0.0:50000", "[::]:50000"]
    assert server.started == 1
    assert server.waited == 1
    assert server.handlers, "the SecondLevelBencher servicer was never registered"


def test_unix_targets_pass_through_unchanged(fake_grpc_server):
    created = fake_grpc_server([1, 50000])
    service = DualStackGRCPService(listen_hosts=["unix:/tmp/x.sock", "127.0.0.1"], port=50000)

    service.serve()

    assert created["server"].targets == ["unix:/tmp/x.sock", "127.0.0.1:50000"]


def test_raises_when_no_host_binds(fake_grpc_server):
    created = fake_grpc_server([0, 0])
    service = DualStackGRCPService(listen_hosts=["0.0.0.0", "[::]"], port=50000)

    with pytest.raises(RuntimeError, match="Could not bind"):
        service.serve()

    assert created["server"].started == 0


def test_serve_raises_when_no_hosts_configured(fake_grpc_server):
    """Zero hosts means the bind loop never runs, so bound stays 0.

    This is the downstream consequence of an empty BENCHER_LISTEN env var --
    see test_listen_helpers.py::TestResolveListenEntries::
    test_empty_env_shadows_default.
    """
    created = fake_grpc_server([])
    service = DualStackGRCPService(listen_hosts=[], port=50000)

    with pytest.raises(RuntimeError, match="Could not bind"):
        service.serve()

    assert created["server"].targets == []


def test_partial_bind_is_treated_as_success(fake_grpc_server):
    """Characterization: one successful bind out of two is enough to start.

    serve() sums the add_insecure_port return values, so a failed [::] bind on
    an IPv6-less host silently degrades to IPv4-only rather than erroring. That
    may well be the intent; this test pins it so the choice stays deliberate.
    """
    created = fake_grpc_server([0, 50000])
    service = DualStackGRCPService(listen_hosts=["[::]", "0.0.0.0"], port=50000)

    service.serve()

    assert created["server"].started == 1


class TestConstruction:
    def test_listen_hosts_are_normalized(self):
        service = DualStackGRCPService(listen_hosts=["  a  ", "a", "", "b"])
        assert service.listen_hosts == ("a", "b")

    def test_defaults_to_dual_stack(self):
        assert DualStackGRCPService().listen_hosts == ("0.0.0.0", "[::]")

    def test_kwargs_reach_the_base_class(self):
        service = DualStackGRCPService(listen_hosts=["a"], host="1.2.3.4", port=1234, n_cores=3)
        assert (service.host, service.port, service.n_cores) == ("1.2.3.4", 1234, 3)
