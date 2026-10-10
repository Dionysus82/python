"""Explicit error types. User-facing messages are safe to display."""


class AccessDeniedError(Exception):
    """The caller is not entitled to the requested record."""


class AuthorisationError(Exception):
    """A query was attempted without an authorisation scope."""


class IngestionError(Exception):
    """A document failed validation or parsing and was not indexed."""


class StorageError(Exception):
    """The trusted document store rejected a key or object."""


class GroundingError(Exception):
    """A claim failed post-generation validation."""


class ConfigurationError(Exception):
    """The process cannot start safely with the current configuration."""


class SeparationOfDutiesError(Exception):
    """The same user cannot both generate and review a draft."""


class LLMDisabledError(Exception):
    """An external model was requested while the provider is disabled."""
