"""Exceptions for BMW CarData API."""


class BMWCarDataError(Exception):
    """Base exception for BMW CarData."""


class AuthenticationError(BMWCarDataError):
    """Raised when authentication fails."""


class TokenExpiredError(AuthenticationError):
    """Raised when the access token has expired."""


class DeviceCodeExpiredError(AuthenticationError):
    """Raised when the device code has expired during polling."""


class AuthorizationPendingError(AuthenticationError):
    """Raised when the user has not yet authorized the device (polling should continue)."""


class RateLimitError(BMWCarDataError):
    """Raised when the daily API rate limit (50 req/day) has been reached."""


class InvalidVinError(BMWCarDataError):
    """Raised when the VIN format is invalid."""


class ContainerError(BMWCarDataError):
    """Raised when a container operation fails."""


class ContainerLimitReachedError(ContainerError):
    """Raised when the maximum number of containers (10) has been reached."""


class ApiError(BMWCarDataError):
    """Raised when the API returns an unexpected error."""

    def __init__(self, message: str, error_id: str | None = None, status: int | None = None):
        super().__init__(message)
        self.error_id = error_id
        self.status = status


class MqttConnectionError(BMWCarDataError):
    """Raised when the MQTT connection fails."""


class MqttStreamError(BMWCarDataError):
    """Raised when an error occurs during MQTT streaming."""
