"""Data engineering registries, contracts, lineage, and quality checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from math import log
from statistics import fmean
from typing import Iterable, Mapping, Sequence


class DataType(StrEnum):
    """Primitive data types supported by platform data contracts."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"


@dataclass(frozen=True)
class DataField:
    """Schema field and validation constraints for governed data assets."""

    name: str
    data_type: DataType
    required: bool = True
    minimum: float | None = None
    maximum: float | None = None

    def validate(self, value: object) -> str | None:
        """Return a validation error message, or None when valid."""

        if value is None:
            return f"{self.name} is required" if self.required else None
        if self.data_type == DataType.STRING and not isinstance(value, str):
            return f"{self.name} must be a string"
        if self.data_type == DataType.INTEGER and not isinstance(value, int):
            return f"{self.name} must be an integer"
        if self.data_type == DataType.FLOAT and not isinstance(value, int | float):
            return f"{self.name} must be numeric"
        if self.data_type == DataType.BOOLEAN and not isinstance(value, bool):
            return f"{self.name} must be a boolean"
        if self.data_type == DataType.DATETIME and not isinstance(value, datetime):
            return f"{self.name} must be a datetime"
        if isinstance(value, int | float):
            if self.minimum is not None and value < self.minimum:
                return f"{self.name} must be >= {self.minimum}"
            if self.maximum is not None and value > self.maximum:
                return f"{self.name} must be <= {self.maximum}"
        return None


@dataclass(frozen=True)
class DataContract:
    """Versioned schema contract for a dataset, stream, or feature view."""

    name: str
    version: str
    fields: tuple[DataField, ...]
    owner: str
    description: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip() or not self.owner.strip():
            raise ValueError("name, version, and owner are required")
        if not self.fields:
            raise ValueError("at least one field is required")
        field_names = [field.name for field in self.fields]
        if len(field_names) != len(set(field_names)):
            raise ValueError("field names must be unique")

    @property
    def contract_id(self) -> str:
        """Stable identifier for this contract version."""

        return f"{self.name}:{self.version}"

    def validate_row(self, row: Mapping[str, object]) -> tuple[str, ...]:
        """Validate a row and return all contract violations."""

        errors = []
        for field_def in self.fields:
            error = field_def.validate(row.get(field_def.name))
            if error:
                errors.append(error)
        allowed = {field_def.name for field_def in self.fields}
        for field_name in row:
            if field_name not in allowed:
                errors.append(f"{field_name} is not declared in contract")
        return tuple(errors)


@dataclass(frozen=True)
class DataQualityReport:
    """Result of validating a batch against a data contract."""

    contract_id: str
    checked_rows: int
    failed_rows: int
    errors: tuple[str, ...]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def passed(self) -> bool:
        """Whether every row satisfied the contract."""

        return self.failed_rows == 0

    @property
    def pass_rate(self) -> float:
        """Fraction of rows passing validation."""

        if self.checked_rows == 0:
            return 1.0
        return (self.checked_rows - self.failed_rows) / self.checked_rows


@dataclass(frozen=True)
class DatasetRecord:
    """Governed dataset registry entry."""

    name: str
    contract_id: str
    storage_uri: str
    owner: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.storage_uri.strip() or not self.owner.strip():
            raise ValueError("dataset name, storage_uri, and owner are required")


@dataclass(frozen=True)
class FeatureRecord:
    """Feature registry entry with lineage to source datasets."""

    name: str
    version: str
    entity: str
    expression: str
    owner: str
    source_datasets: tuple[str, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not all((self.name.strip(), self.version.strip(), self.entity.strip(), self.expression.strip(), self.owner.strip())):
            raise ValueError("feature name, version, entity, expression, and owner are required")
        if not self.source_datasets:
            raise ValueError("feature must declare at least one source dataset")

    @property
    def feature_id(self) -> str:
        """Stable identifier for this feature version."""

        return f"{self.name}:{self.version}"


class MetadataCatalog:
    """In-memory metadata catalog suitable for deterministic local services and tests."""

    def __init__(self) -> None:
        self._contracts: dict[str, DataContract] = {}
        self._datasets: dict[str, DatasetRecord] = {}
        self._features: dict[str, FeatureRecord] = {}

    def register_contract(self, contract: DataContract) -> None:
        """Register or replace a contract version."""

        self._contracts[contract.contract_id] = contract

    def register_dataset(self, dataset: DatasetRecord) -> None:
        """Register a dataset after verifying its contract exists."""

        if dataset.contract_id not in self._contracts:
            raise ValueError(f"unknown contract: {dataset.contract_id}")
        self._datasets[dataset.name] = dataset

    def register_feature(self, feature: FeatureRecord) -> None:
        """Register a feature after verifying source datasets exist."""

        missing = [dataset for dataset in feature.source_datasets if dataset not in self._datasets]
        if missing:
            raise ValueError(f"unknown source datasets: {', '.join(missing)}")
        self._features[feature.feature_id] = feature

    def contract(self, contract_id: str) -> DataContract:
        """Return a registered data contract."""

        return self._contracts[contract_id]

    def dataset(self, name: str) -> DatasetRecord:
        """Return a registered dataset."""

        return self._datasets[name]

    def feature(self, feature_id: str) -> FeatureRecord:
        """Return a registered feature."""

        return self._features[feature_id]

    def lineage_for_feature(self, feature_id: str) -> tuple[DatasetRecord, ...]:
        """Return dataset lineage for a feature."""

        feature = self.feature(feature_id)
        return tuple(self.dataset(dataset) for dataset in feature.source_datasets)

    def quality_report(self, contract_id: str, rows: Iterable[Mapping[str, object]]) -> DataQualityReport:
        """Validate rows against a contract and summarize data quality."""

        contract = self.contract(contract_id)
        checked = 0
        failed = 0
        errors: list[str] = []
        for row_number, row in enumerate(rows, start=1):
            checked += 1
            row_errors = contract.validate_row(row)
            if row_errors:
                failed += 1
                errors.extend(f"row {row_number}: {error}" for error in row_errors)
        return DataQualityReport(contract_id=contract_id, checked_rows=checked, failed_rows=failed, errors=tuple(errors))


def population_stability_index(expected: Sequence[float], actual: Sequence[float], buckets: int = 10) -> float:
    """Compute PSI for drift monitoring without third-party dependencies."""

    if not expected or not actual:
        raise ValueError("expected and actual samples are required")
    if buckets < 2:
        raise ValueError("buckets must be at least 2")
    minimum = min(min(expected), min(actual))
    maximum = max(max(expected), max(actual))
    if minimum == maximum:
        return 0.0
    width = (maximum - minimum) / buckets
    expected_counts = _bucket_counts(expected, minimum, width, buckets)
    actual_counts = _bucket_counts(actual, minimum, width, buckets)
    expected_total = len(expected)
    actual_total = len(actual)
    epsilon = 1e-6
    psi = 0.0
    for expected_count, actual_count in zip(expected_counts, actual_counts, strict=True):
        expected_pct = max(expected_count / expected_total, epsilon)
        actual_pct = max(actual_count / actual_total, epsilon)
        psi += (actual_pct - expected_pct) * log(actual_pct / expected_pct)
    return round(psi, 6)


def feature_mean(features: Sequence[float]) -> float:
    """Validated mean helper used by feature monitoring pipelines."""

    if not features:
        raise ValueError("features cannot be empty")
    return fmean(features)


def _bucket_counts(values: Sequence[float], minimum: float, width: float, buckets: int) -> list[int]:
    counts = [0 for _ in range(buckets)]
    for value in values:
        index = int((value - minimum) / width)
        counts[min(index, buckets - 1)] += 1
    return counts
