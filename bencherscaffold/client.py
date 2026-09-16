import time
from collections.abc import Sequence
from typing import Union

import grpc

from bencherscaffold.dual_stack_service import grpc_target
from bencherscaffold.protoclasses.bencher_pb2 import (
    BenchmarkRequest, BenchmarkType, ConstrainedEvaluationResult,
    EvaluationResult, Point, Benchmark, Value, ValueType,
)
from bencherscaffold.protoclasses.bencher_pb2_grpc import BencherStub


class BencherClient:
    def __init__(
            self,
            address: str = '127.0.0.1',
            port: int = 50051,
            max_retries: int = 10,
            wait_time: int = 5,
    ):
        """
        Initializes the BencherClient with the given parameters.
        Args:
            address: The address of the server. Can be an IP address/hostname
                or a Unix socket path (e.g. "unix:///tmp/bencher.sock").
            port: The port number of the server. Ignored for Unix sockets.
            max_retries: The maximum number of retries for the request.
            wait_time: The time to wait between retries in seconds.
        """
        self.channel = grpc.insecure_channel(grpc_target(address, port))
        self.stub = BencherStub(self.channel)
        self.max_retries = max_retries
        self.wait_time = wait_time

    def evaluate_point(
            self,
            benchmark_name: str,
            point: Sequence[Value]
    ) -> Union[float, ConstrainedEvaluationResult]:
        """
        Evaluates a point in the benchmark space.
        This method sends a request to the server to evaluate a specific point in the benchmark space.
        It retries the request if it fails, up to the maximum number of retries specified.
        If the request fails after the maximum number of retries, it raises the last exception encountered.
        The point must be a sequence of floats, and its length must match the number of dimensions of the benchmark.

        Args:
            benchmark_name: The name of the benchmark to evaluate.
            point:  A sequence of floats representing the point in the benchmark space to evaluate.

        Returns:
            The evaluated value of the point in the benchmark space, or a 
            ConstrainedEvaluationResult (objective plus constraints) for constrained 
            benchmarks.

        """

        if all(p.type == ValueType.CONTINUOUS for p in point):
            benchmark_type = BenchmarkType.PURELY_CONTINUOUS
        elif all(p.type == ValueType.BINARY for p in point):
            benchmark_type = BenchmarkType.PURELY_BINARY
        elif all(p.type == ValueType.INTEGER for p in point):
            benchmark_type = BenchmarkType.PURELY_ORDINAL_INT
        elif all(p.type == ValueType.CATEGORICAL for p in point):
            benchmark_type = BenchmarkType.PURELY_CATEGORICAL
        else:
            benchmark_type = BenchmarkType.MIXED

        benchmark = Benchmark(
            name=benchmark_name,
            type=benchmark_type,
        )

        request = BenchmarkRequest(
            benchmark=benchmark,
            point=Point(
                values=point,
            ),

        )
        for n_retry in range(self.max_retries):
            try:
                response: EvaluationResult = self.stub.evaluate_point(request)
                if response.WhichOneof("result") == "constrained_value":
                    return response.constrained_value
                return response.value
            except grpc.RpcError as e:
                if n_retry < self.max_retries - 1:
                    print(f"Retrying... {n_retry + 1}/{self.max_retries}")
                    time.sleep(self.wait_time)
                else:
                    raise e
