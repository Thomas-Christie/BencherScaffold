"""Tier 2: BencherClient.evaluate_point against a recording stub."""

import grpc
import pytest

from bencherscaffold.protoclasses.bencher_pb2 import (
    BenchmarkType,
    Constraint,
    ConstraintType,
    EvaluationResult,
    ObjectiveValue,
    Value,
    ValueType,
)



def _point(*types):
    return [Value(type=t, value=float(i)) for i, t in enumerate(types)]


class TestBenchmarkTypeInference:
    @pytest.mark.parametrize(
        "value_type,expected",
        [
            (ValueType.CONTINUOUS, BenchmarkType.PURELY_CONTINUOUS),
            (ValueType.BINARY, BenchmarkType.PURELY_BINARY),
            (ValueType.INTEGER, BenchmarkType.PURELY_ORDINAL_INT),
            (ValueType.CATEGORICAL, BenchmarkType.PURELY_CATEGORICAL),
        ],
    )
    def test_homogeneous_points(self, make_client, value_type, expected):
        client = make_client()
        client.evaluate_point("bench", _point(value_type, value_type))
        assert client.stub.requests[0].benchmark.type == expected

    @pytest.mark.parametrize(
        "types",
        [
            (ValueType.CONTINUOUS, ValueType.BINARY),
            (ValueType.INTEGER, ValueType.CATEGORICAL),
            (ValueType.CONTINUOUS, ValueType.CONTINUOUS, ValueType.INTEGER),
        ],
    )
    def test_mixed_points(self, make_client, types):
        client = make_client()
        client.evaluate_point("bench", _point(*types))
        assert client.stub.requests[0].benchmark.type == BenchmarkType.MIXED

    def test_single_value_point(self, make_client):
        client = make_client()
        client.evaluate_point("bench", _point(ValueType.BINARY))
        assert client.stub.requests[0].benchmark.type == BenchmarkType.PURELY_BINARY

    def test_empty_point_does_not_raise(self, make_client):
        """Characterization: an empty point is accepted, not rejected.

        `all(...)` over an empty sequence is True, so the first branch wins and
        the request goes out as PURELY_CONTINUOUS. Note PURELY_CONTINUOUS == 0
        is also the proto3 default, so the type assertion alone cannot prove the
        branch was taken -- hence the explicit emptiness assertion alongside it.
        """
        client = make_client()
        client.evaluate_point("bench", [])
        request = client.stub.requests[0]
        assert len(request.point.values) == 0
        assert request.benchmark.type == BenchmarkType.PURELY_CONTINUOUS

    def test_purely_ordinal_real_is_unreachable(self):
        """There is no ValueType that maps to PURELY_ORDINAL_REAL.

        The enum member exists in the proto but evaluate_point can never select
        it; this documents that gap rather than leaving a reader hunting for it.
        """
        assert BenchmarkType.PURELY_ORDINAL_REAL not in (
            BenchmarkType.PURELY_CONTINUOUS,
            BenchmarkType.PURELY_BINARY,
            BenchmarkType.PURELY_ORDINAL_INT,
            BenchmarkType.PURELY_CATEGORICAL,
            BenchmarkType.MIXED,
        )


class TestRequestContents:
    def test_name_and_values_are_passed_through(self, make_client):
        client = make_client()
        point = _point(ValueType.CONTINUOUS, ValueType.CONTINUOUS)
        client.evaluate_point("my-benchmark", point)

        request = client.stub.requests[0]
        assert request.benchmark.name == "my-benchmark"
        assert list(request.point.values) == list(point)

    def test_returns_the_whole_evaluation_result(self, make_client, make_result):
        """evaluate_point hands back the message, not a scalar."""
        client = make_client(script=[make_result(1.25)])
        result = client.evaluate_point("bench", _point(ValueType.CONTINUOUS))
        assert isinstance(result, EvaluationResult)
        assert result.objectives[0].value == 1.25

    def test_multiple_objectives_are_preserved(self, make_client):
        """The point of the flat EvaluationResult: MOBO results survive intact."""
        client = make_client(script=[
            EvaluationResult(objectives=[
                ObjectiveValue(name="f1", value=0.3),
                ObjectiveValue(name="f2", value=1.7),
            ])
        ])
        result = client.evaluate_point("bench", _point(ValueType.CONTINUOUS))
        assert [(o.name, o.value) for o in result.objectives] == [("f1", 0.3), ("f2", 1.7)]

    def test_constraints_are_preserved(self, make_client):
        client = make_client(script=[
            EvaluationResult(
                objectives=[ObjectiveValue(name="f1", value=0.5)],
                constraints=[
                    Constraint(name="c1", type=ConstraintType.INEQUALITY, value=-0.2),
                    Constraint(name="c2", type=ConstraintType.EQUALITY, value=0.0),
                ],
            )
        ])
        result = client.evaluate_point("bench", _point(ValueType.CONTINUOUS))
        assert [(c.name, c.type, c.value) for c in result.constraints] == [
            ("c1", ConstraintType.INEQUALITY, -0.2),
            ("c2", ConstraintType.EQUALITY, 0.0),
        ]

    def test_result_without_objectives_is_passed_through(self, make_client):
        """A benchmark reporting nothing is the caller's problem, not the client's."""
        client = make_client(script=[EvaluationResult()])
        result = client.evaluate_point("bench", _point(ValueType.CONTINUOUS))
        assert list(result.objectives) == []
        assert list(result.constraints) == []


class TestRetryLoop:
    def test_success_on_first_try_does_not_sleep(self, make_client, sleeps, make_result):
        client = make_client(script=[make_result(3.0)], max_retries=5)
        result = client.evaluate_point("bench", _point(ValueType.CONTINUOUS))
        assert result.objectives[0].value == 3.0
        assert client.stub.calls == 1
        assert sleeps == []

    def test_retries_until_success(self, make_client, sleeps, make_result):
        client = make_client(
            script=[grpc.RpcError(), grpc.RpcError(), make_result(7.0)],
            max_retries=5,
            wait_time=2,
        )
        result = client.evaluate_point("bench", _point(ValueType.CONTINUOUS))
        assert result.objectives[0].value == 7.0
        assert client.stub.calls == 3
        assert sleeps == [2, 2]

    def test_reraises_after_exhausting_retries(self, make_client, sleeps):
        """For max_retries=N the loop runs N times and sleeps N-1 times."""
        client = make_client(script=[grpc.RpcError()], max_retries=3)
        with pytest.raises(grpc.RpcError):
            client.evaluate_point("bench", _point(ValueType.CONTINUOUS))
        assert client.stub.calls == 3
        assert len(sleeps) == 2

    def test_non_rpc_error_propagates_immediately(self, make_client, sleeps):
        client = make_client(script=[ValueError("boom")], max_retries=5)
        with pytest.raises(ValueError, match="boom"):
            client.evaluate_point("bench", _point(ValueType.CONTINUOUS))
        assert client.stub.calls == 1
        assert sleeps == []

    def test_max_retries_zero_returns_none(self, make_client):
        """Known bug, pinned deliberately: max_retries=0 never calls the server.

        The loop body never executes, so evaluate_point falls off the end and
        returns None despite its `-> float` annotation. This is asserted rather
        than xfailed so that fixing it produces one clear, intentional failure
        here instead of an XPASS that is easy to ignore.
        """
        client = make_client(max_retries=0)
        assert client.evaluate_point("bench", _point(ValueType.CONTINUOUS)) is None
        assert client.stub.calls == 0
