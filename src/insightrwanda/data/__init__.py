"""Safe, explicit data access and validation utilities for InsightRwanda."""

from .errors import (
    DataLoaderError,
    DataPathError,
    DataPreparationError,
    OptionalDependencyError,
    SchemaValidationError,
    UnsupportedFormatError,
)
from .loaders import (
    load_csv,
    load_geojson,
    load_source,
    load_stata,
    load_xls,
    load_xlsx,
)
from .prepare import PreparationConfig, prepare_dataset
from .geography import load_geographic_resource_registry, normalize_geographic_resource, summarize_geographic_resources
from .registry import get_dataset, load_dataset_registry, registry_summary, resolve_dataset_path
from .quality import QualityConfig, profile_dataframe, profile_geojson, write_quality_report
from .validation import (
    check_expected_columns,
    duplicate_column_names,
    missingness_summary,
    validate_dataframe,
    validate_geojson_structure,
)

__all__ = [
    "DataLoaderError",
    "DataPathError",
    "DataPreparationError",
    "OptionalDependencyError",
    "SchemaValidationError",
    "UnsupportedFormatError",
    "check_expected_columns",
    "duplicate_column_names",
    "load_csv",
    "load_geojson",
    "load_source",
    "load_stata",
    "load_xls",
    "load_xlsx",
    "missingness_summary",
    "PreparationConfig",
    "prepare_dataset",
    "get_dataset",
    "load_dataset_registry",
    "registry_summary",
    "resolve_dataset_path",
    "QualityConfig",
    "profile_dataframe",
    "profile_geojson",
    "validate_dataframe",
    "validate_geojson_structure",
    "write_quality_report",
    "load_geographic_resource_registry",
    "normalize_geographic_resource",
    "summarize_geographic_resources",
]

