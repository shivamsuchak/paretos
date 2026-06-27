"""Custom exception hierarchy for Paretos."""


class ParetosError(Exception):
    """Base exception for all Paretos errors."""


class DataLoadError(ParetosError):
    """Raised when data files cannot be loaded or parsed."""


class DataValidationError(ParetosError):
    """Raised when loaded data fails validation checks."""


class CostModelError(ParetosError):
    """Raised when cost computation encounters invalid inputs."""


class ConfigError(ParetosError):
    """Raised when configuration is invalid or missing."""


class PipelineError(ParetosError):
    """Raised when the execution pipeline encounters an error."""


class AgentError(ParetosError):
    """Raised when an agent fails during execution."""
