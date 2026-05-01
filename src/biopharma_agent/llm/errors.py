"""LLM-specific errors."""

from __future__ import annotations


class LLMError(RuntimeError):
    """Base class for LLM integration failures."""


class LLMConfigurationError(LLMError):
    """Raised when a provider is missing required configuration."""


class LLMHTTPError(LLMError):
    """Raised when an HTTP provider returns a failed response."""


class LLMResponseError(LLMError):
    """Raised when a provider response cannot be parsed."""

