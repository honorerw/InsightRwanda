"""Non-sensitive exceptions used by the data layer."""


class DataLoaderError(Exception):
    """Base class for expected data access and parsing errors."""


class DataPathError(DataLoaderError):
    """Raised when a requested path is outside the approved data directory."""


class OptionalDependencyError(DataLoaderError):
    """Raised when a file format needs an optional reader that is unavailable."""


class UnsupportedFormatError(DataLoaderError):
    """Raised when no safe loader is registered for a file extension."""


class SchemaValidationError(DataLoaderError):
    """Raised when a loaded object does not satisfy a required schema."""


class DataPreparationError(DataLoaderError):
    """Raised when an explicit preparation request cannot be performed safely."""


class IndicatorError(DataLoaderError):
    """Base class for indicator catalogue and calculation errors."""


class IndicatorBlockedError(IndicatorError):
    """Raised when an indicator lacks verified evidence for calculation."""


class IndicatorDefinitionError(IndicatorError):
    """Raised when an indicator definition or calculation input is invalid."""

