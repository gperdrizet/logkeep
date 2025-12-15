"""Custom application exceptions."""


class LogKeepError(Exception):
    """Base exception for all LogKeep errors."""
    pass


class ValidationError(LogKeepError):
    """Raised when input validation fails."""
    pass


class AuthenticationError(LogKeepError):
    """Raised when authentication fails."""
    pass


class AuthorizationError(LogKeepError):
    """Raised when user lacks required permissions."""
    pass


class NotFoundError(LogKeepError):
    """Raised when requested resource is not found."""
    pass


class DuplicateError(LogKeepError):
    """Raised when attempting to create duplicate resource."""
    pass


class LinkProcessingError(LogKeepError):
    """Raised when link processing fails."""
    pass


class GitHubError(LogKeepError):
    """Raised when GitHub operations fail."""
    pass


class EncryptionError(LogKeepError):
    """Raised when encryption/decryption fails."""
    pass


class ConfigurationError(LogKeepError):
    """Raised when configuration is invalid or missing."""
    pass
