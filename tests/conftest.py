"""Shared test fixtures for python-bmw-cardata tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientResponse, ClientSession

from bmw_cardata.auth import AbstractAuth


class MockAuth(AbstractAuth):
    """Mock auth implementation for tests."""

    def __init__(self, websession: ClientSession | None = None) -> None:
        """Initialize mock auth."""
        super().__init__(websession or AsyncMock())
        self.token = "test-access-token"

    async def async_get_access_token(self) -> str:
        """Return a test access token."""
        return self.token


def make_mock_response(
    status: int = 200,
    json_data: dict[str, Any] | list[Any] | None = None,
    content: bytes | None = None,
) -> AsyncMock:
    """Create a mock aiohttp response."""
    resp = AsyncMock(spec=ClientResponse)
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.read = AsyncMock(return_value=content or b"")
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock aiohttp session."""
    return AsyncMock()


@pytest.fixture
def mock_auth(mock_session: AsyncMock) -> MockAuth:
    """Create a mock auth instance."""
    return MockAuth(mock_session)


# ── Sample API response data ────────────────────────────────────────

SAMPLE_VEHICLE_MAPPINGS = [
    {
        "vin": "WBA12345678901234",
        "mappedSince": "2024-01-15T10:00:00Z",
        "mappingType": "PRIMARY",
    },
    {
        "vin": "WBA98765432109876",
        "mappedSince": "2024-06-01T08:30:00Z",
        "mappingType": "SECONDARY",
    },
]

SAMPLE_BASIC_DATA = {
    "vin": "WBA12345678901234",
    "brand": "BMW",
    "modelName": "330e",
    "modelRange": "3er",
    "series": "3",
    "bodyType": "G20",
    "driveTrain": "PHEV_OTTO",
    "propulsionType": "PHEV",
    "headUnit": "MGU",
    "isTelematicsCapable": True,
    "numberOfDoors": 4,
    "hasNavi": True,
    "hasSunRoof": False,
    "steering": "LEFT",
    "engine": "B48",
    "colourCode": "475",
    "constructionDate": "2023-06-15",
    "countryCodeISO": "DE",
    "puStep": "0723",
    "modelKey": "3X31",
    "chargingModes": ["AC", "DC"],
    "hvsMaxEnergyAbsolute": "12.0",
    "simStatus": "ACTIVE",
}

SAMPLE_CONTAINERS = {
    "containers": [
        {
            "containerId": "container-123",
            "name": "HomeAssistant",
            "purpose": "HA Integration",
            "state": "ACTIVE",
            "created": "2024-01-20T12:00:00Z",
        }
    ]
}

SAMPLE_CONTAINER_DETAILS = {
    "containerId": "container-123",
    "name": "HomeAssistant",
    "purpose": "HA Integration",
    "state": "ACTIVE",
    "created": "2024-01-20T12:00:00Z",
    "technicalDescriptors": [
        "vehicle.chassis.mileage",
        "vehicle.powertrain.electric.battery.stateOfCharge",
    ],
}

SAMPLE_TELEMATIC_DATA = {
    "telematicData": {
        "vehicle.chassis.mileage": {
            "value": "45230",
            "unit": "km",
            "timestamp": "2025-03-12T14:30:00Z",
        },
        "vehicle.powertrain.electric.battery.stateOfCharge": {
            "value": "72",
            "unit": "%",
            "timestamp": "2025-03-12T14:30:00Z",
        },
        "vehicle.cabin.door.row1.driver.isOpen": {
            "value": "false",
            "unit": "",
            "timestamp": "2025-03-12T14:30:00Z",
        },
    }
}

SAMPLE_CHARGING_HISTORY = {
    "data": [
        {
            "startTime": 1710200000,
            "endTime": 1710210000,
            "displayedSoc": 80,
            "displayedStartSoc": 20,
            "totalChargingDurationSec": 10000,
            "energyConsumedFromPowerGridKwh": 7.5,
            "isPreconditioningActivated": False,
            "mileage": 45000,
            "mileageUnits": "km",
            "timeZone": "Europe/Berlin",
            "chargingCostInformation": {
                "currency": "EUR",
                "calculatedChargingCost": 2.50,
                "calculatedSavings": 4.00,
            },
            "chargingLocation": {
                "municipality": "Munich",
                "formattedAddress": "Munich, Germany",
                "streetAddress": "Hauptstraße 1",
                "mapMatchedLatitude": 48.137,
                "mapMatchedLongitude": 11.576,
            },
            "chargingBlocks": [
                {
                    "startTime": 1710200000,
                    "endTime": 1710205000,
                    "averagePowerGridKw": 3.6,
                },
                {
                    "startTime": 1710205000,
                    "endTime": 1710210000,
                    "averagePowerGridKw": 3.4,
                },
            ],
        }
    ]
}

SAMPLE_TYRE_DIAGNOSIS = {
    "passengerCar": {
        "mountedTyres": {
            "frontLeft": {
                "label": "FL",
                "qualityStatus": {"qualityStatus": "GOOD"},
                "season": {"season": "SUMMER"},
                "tread": {"manufacturer": "Bridgestone", "treadDesign": "T005"},
                "tyreWear": {"status": "OK", "dueMileage": 30000},
                "tyreDefect": {"status": "NONE"},
                "tyreProductionDate": {"value": "2023-W20"},
                "runFlat": {"runFlat": True},
                "dimension": {"value": "225/45R18"},
            },
            "frontRight": {
                "label": "FR",
                "qualityStatus": {"qualityStatus": "GOOD"},
            },
            "rearLeft": {
                "label": "RL",
                "qualityStatus": {"qualityStatus": "GOOD"},
            },
            "rearRight": {
                "label": "RR",
                "qualityStatus": {"qualityStatus": "GOOD"},
            },
            "aggregatedQualityStatus": {"qualityStatus": "GOOD"},
        }
    }
}

SAMPLE_DEVICE_CODE_RESPONSE = {
    "user_code": "AB12-CD34",
    "device_code": "dev-code-xyz",
    "verification_uri": "https://customer.bmwgroup.com/verify",
    "interval": 5,
    "expires_in": 600,
}

SAMPLE_TOKEN_RESPONSE = {
    "access_token": "eyJ-access-token",
    "token_type": "Bearer",
    "expires_in": 3600,
    "refresh_token": "refresh-token-abc",
    "scope": "authenticate_user openid cardata:api:read cardata:streaming:read",
    "id_token": "eyJ-id-token",
    "gcid": "gcid-12345-abcde",
}
