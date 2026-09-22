from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class BenchmarkType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PURELY_CONTINUOUS: _ClassVar[BenchmarkType]
    PURELY_BINARY: _ClassVar[BenchmarkType]
    PURELY_CATEGORICAL: _ClassVar[BenchmarkType]
    PURELY_ORDINAL_REAL: _ClassVar[BenchmarkType]
    PURELY_ORDINAL_INT: _ClassVar[BenchmarkType]
    MIXED: _ClassVar[BenchmarkType]

class ValueType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    CONTINUOUS: _ClassVar[ValueType]
    BINARY: _ClassVar[ValueType]
    INTEGER: _ClassVar[ValueType]
    CATEGORICAL: _ClassVar[ValueType]

class ConstraintType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    INEQUALITY: _ClassVar[ConstraintType]
    EQUALITY: _ClassVar[ConstraintType]
PURELY_CONTINUOUS: BenchmarkType
PURELY_BINARY: BenchmarkType
PURELY_CATEGORICAL: BenchmarkType
PURELY_ORDINAL_REAL: BenchmarkType
PURELY_ORDINAL_INT: BenchmarkType
MIXED: BenchmarkType
CONTINUOUS: ValueType
BINARY: ValueType
INTEGER: ValueType
CATEGORICAL: ValueType
INEQUALITY: ConstraintType
EQUALITY: ConstraintType

class Value(_message.Message):
    __slots__ = ("type", "value")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    type: ValueType
    value: float
    def __init__(self, type: _Optional[_Union[ValueType, str]] = ..., value: _Optional[float] = ...) -> None: ...

class Benchmark(_message.Message):
    __slots__ = ("name", "type", "description")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    name: str
    type: BenchmarkType
    description: str
    def __init__(self, name: _Optional[str] = ..., type: _Optional[_Union[BenchmarkType, str]] = ..., description: _Optional[str] = ...) -> None: ...

class BenchmarkRequest(_message.Message):
    __slots__ = ("benchmark", "point", "random_seed")
    BENCHMARK_FIELD_NUMBER: _ClassVar[int]
    POINT_FIELD_NUMBER: _ClassVar[int]
    RANDOM_SEED_FIELD_NUMBER: _ClassVar[int]
    benchmark: Benchmark
    point: Point
    random_seed: int
    def __init__(self, benchmark: _Optional[_Union[Benchmark, _Mapping]] = ..., point: _Optional[_Union[Point, _Mapping]] = ..., random_seed: _Optional[int] = ...) -> None: ...

class Point(_message.Message):
    __slots__ = ("values",)
    VALUES_FIELD_NUMBER: _ClassVar[int]
    values: _containers.RepeatedCompositeFieldContainer[Value]
    def __init__(self, values: _Optional[_Iterable[_Union[Value, _Mapping]]] = ...) -> None: ...

class Constraint(_message.Message):
    __slots__ = ("name", "type", "value")
    NAME_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    name: str
    type: ConstraintType
    value: float
    def __init__(self, name: _Optional[str] = ..., type: _Optional[_Union[ConstraintType, str]] = ..., value: _Optional[float] = ...) -> None: ...

class ObjectiveValue(_message.Message):
    __slots__ = ("name", "value")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    name: str
    value: float
    def __init__(self, name: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...

class EvaluationResult(_message.Message):
    __slots__ = ("objectives", "constraints")
    OBJECTIVES_FIELD_NUMBER: _ClassVar[int]
    CONSTRAINTS_FIELD_NUMBER: _ClassVar[int]
    objectives: _containers.RepeatedCompositeFieldContainer[ObjectiveValue]
    constraints: _containers.RepeatedCompositeFieldContainer[Constraint]
    def __init__(self, objectives: _Optional[_Iterable[_Union[ObjectiveValue, _Mapping]]] = ..., constraints: _Optional[_Iterable[_Union[Constraint, _Mapping]]] = ...) -> None: ...
