"""BMW CarData API client library."""

__version__ = "0.1.0"

from .api import CarDataApiClient
from .auth import AbstractAuth, DeviceAuth
from .exceptions import (
    ApiError,
    AuthenticationError,
    BMWCarDataError,
    ContainerError,
    InvalidVinError,
    MqttConnectionError,
    MqttStreamError,
    RateLimitError,
)
from .models import (
    ChargingSession,
    Container,
    ContainerDetails,
    DeviceCodeResponse,
    LocationBasedChargingSetting,
    TelematicDataEntry,
    TokenResponse,
    TyreDiagnosis,
    Vehicle,
    VehicleMapping,
)
from .mqtt import CarDataMqttClient, MqttMessage

__all__ = [
    "ApiError",
    "AbstractAuth",
    "AuthenticationError",
    "BMWCarDataError",
    "CarDataApiClient",
    "CarDataMqttClient",
    "ChargingSession",
    "Container",
    "ContainerDetails",
    "ContainerError",
    "DeviceAuth",
    "DeviceCodeResponse",
    "InvalidVinError",
    "LocationBasedChargingSetting",
    "MqttConnectionError",
    "MqttMessage",
    "MqttStreamError",
    "RateLimitError",
    "TelematicDataEntry",
    "TokenResponse",
    "TyreDiagnosis",
    "Vehicle",
    "VehicleMapping",
]
