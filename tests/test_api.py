"""Tests for BMW CarData API client."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from pybmwcardata.api import CarDataApiClient
from pybmwcardata.exceptions import (
    ApiError,
    AuthenticationError,
    ContainerError,
    ContainerLimitReachedError,
    InvalidVinError,
    RateLimitError,
)

from .conftest import (
    SAMPLE_BASIC_DATA,
    SAMPLE_CHARGING_HISTORY,
    SAMPLE_CONTAINERS,
    SAMPLE_CONTAINER_DETAILS,
    SAMPLE_TELEMATIC_DATA,
    SAMPLE_TYRE_DIAGNOSIS,
    SAMPLE_VEHICLE_MAPPINGS,
    MockAuth,
    make_mock_response,
)


@pytest.fixture
def api_client() -> CarDataApiClient:
    """Create an API client with mock auth."""
    auth = MockAuth()
    return CarDataApiClient(auth, api_base_url="https://api-test.example.com")


class TestGetVehicleMappings:
    """Tests for get_vehicle_mappings."""

    @pytest.mark.asyncio
    async def test_returns_list(self, api_client: CarDataApiClient) -> None:
        """Test getting vehicle mappings as a list."""
        resp = make_mock_response(200, SAMPLE_VEHICLE_MAPPINGS)
        api_client._auth.request = AsyncMock(return_value=resp)

        mappings = await api_client.get_vehicle_mappings()
        assert len(mappings) == 2
        assert mappings[0].vin == "WBA12345678901234"
        assert mappings[0].mapping_type == "PRIMARY"
        assert mappings[1].vin == "WBA98765432109876"
        assert mappings[1].mapping_type == "SECONDARY"

    @pytest.mark.asyncio
    async def test_returns_dict_with_mappings_key(self, api_client: CarDataApiClient) -> None:
        """Test getting vehicle mappings wrapped in dict."""
        resp = make_mock_response(200, {"mappings": SAMPLE_VEHICLE_MAPPINGS})
        api_client._auth.request = AsyncMock(return_value=resp)

        mappings = await api_client.get_vehicle_mappings()
        assert len(mappings) == 2

    @pytest.mark.asyncio
    async def test_returns_single_mapping(self, api_client: CarDataApiClient) -> None:
        """Test getting a single vehicle mapping as dict."""
        resp = make_mock_response(200, SAMPLE_VEHICLE_MAPPINGS[0])
        api_client._auth.request = AsyncMock(return_value=resp)

        mappings = await api_client.get_vehicle_mappings()
        assert len(mappings) == 1
        assert mappings[0].vin == "WBA12345678901234"

    @pytest.mark.asyncio
    async def test_auth_error_401(self, api_client: CarDataApiClient) -> None:
        """Test 401 raises AuthenticationError."""
        resp = make_mock_response(
            401, {"exveErrorId": "", "exveErrorMsg": "Unauthorized"}
        )
        api_client._auth.request = AsyncMock(return_value=resp)

        with pytest.raises(AuthenticationError, match="Authentication failed"):
            await api_client.get_vehicle_mappings()

    @pytest.mark.asyncio
    async def test_auth_error_403(self, api_client: CarDataApiClient) -> None:
        """Test 403 raises AuthenticationError."""
        resp = make_mock_response(
            403, {"exveErrorId": "", "exveErrorMsg": "Forbidden"}
        )
        api_client._auth.request = AsyncMock(return_value=resp)

        with pytest.raises(AuthenticationError, match="Access forbidden"):
            await api_client.get_vehicle_mappings()


class TestGetBasicData:
    """Tests for get_basic_data."""

    @pytest.mark.asyncio
    async def test_returns_vehicle(self, api_client: CarDataApiClient) -> None:
        """Test getting basic vehicle data."""
        resp = make_mock_response(200, SAMPLE_BASIC_DATA)
        api_client._auth.request = AsyncMock(return_value=resp)

        vehicle = await api_client.get_basic_data("WBA12345678901234")
        assert vehicle.vin == "WBA12345678901234"
        assert vehicle.model_name == "330e"
        assert vehicle.brand == "BMW"


class TestContainerManagement:
    """Tests for container CRUD operations."""

    @pytest.mark.asyncio
    async def test_list_containers(self, api_client: CarDataApiClient) -> None:
        """Test listing containers."""
        resp = make_mock_response(200, SAMPLE_CONTAINERS)
        api_client._auth.request = AsyncMock(return_value=resp)

        containers = await api_client.list_containers()
        assert len(containers) == 1
        assert containers[0].container_id == "container-123"
        assert containers[0].name == "HomeAssistant"
        assert containers[0].state == "ACTIVE"

    @pytest.mark.asyncio
    async def test_get_container(self, api_client: CarDataApiClient) -> None:
        """Test getting container details."""
        resp = make_mock_response(200, SAMPLE_CONTAINER_DETAILS)
        api_client._auth.request = AsyncMock(return_value=resp)

        details = await api_client.get_container("container-123")
        assert details.container_id == "container-123"
        assert len(details.technical_descriptors) == 2

    @pytest.mark.asyncio
    async def test_create_container(self, api_client: CarDataApiClient) -> None:
        """Test creating a container."""
        resp = make_mock_response(201, SAMPLE_CONTAINER_DETAILS)
        api_client._auth.request = AsyncMock(return_value=resp)

        details = await api_client.create_container(
            name="TestContainer",
            purpose="Testing",
            technical_descriptors=["vehicle.chassis.mileage"],
        )
        assert details.container_id == "container-123"

    @pytest.mark.asyncio
    async def test_delete_container_204(self, api_client: CarDataApiClient) -> None:
        """Test deleting a container (204 response)."""
        resp = make_mock_response(204)
        api_client._auth.request = AsyncMock(return_value=resp)

        # Should not raise
        await api_client.delete_container("container-123")

    @pytest.mark.asyncio
    async def test_container_limit_error(self, api_client: CarDataApiClient) -> None:
        """Test CU-124 raises ContainerLimitReachedError."""
        resp = make_mock_response(
            400, {"exveErrorId": "CU-124", "exveErrorMsg": "Max containers reached"}
        )
        api_client._auth.request = AsyncMock(return_value=resp)

        with pytest.raises(ContainerLimitReachedError):
            await api_client.create_container("name", "purpose", [])

    @pytest.mark.asyncio
    async def test_ensure_container_existing(self, api_client: CarDataApiClient) -> None:
        """Test ensure_container returns existing active container."""
        list_resp = make_mock_response(200, SAMPLE_CONTAINERS)
        details_resp = make_mock_response(200, SAMPLE_CONTAINER_DETAILS)
        api_client._auth.request = AsyncMock(side_effect=[list_resp, details_resp])

        container = await api_client.ensure_container(name="HomeAssistant")
        assert container.container_id == "container-123"
        assert api_client._auth.request.call_count == 2  # list + get_details

    @pytest.mark.asyncio
    async def test_ensure_container_creates_new(self, api_client: CarDataApiClient) -> None:
        """Test ensure_container creates when none exists."""
        list_resp = make_mock_response(200, {"containers": []})
        create_resp = make_mock_response(201, SAMPLE_CONTAINER_DETAILS)
        api_client._auth.request = AsyncMock(side_effect=[list_resp, create_resp])

        container = await api_client.ensure_container(name="NewContainer")
        assert container.container_id == "container-123"
        assert api_client._auth.request.call_count == 2  # list + create


class TestTelematicData:
    """Tests for get_telematic_data."""

    @pytest.mark.asyncio
    async def test_parses_telematic_data(self, api_client: CarDataApiClient) -> None:
        """Test parsing telematic data entries."""
        resp = make_mock_response(200, SAMPLE_TELEMATIC_DATA)
        api_client._auth.request = AsyncMock(return_value=resp)

        entries = await api_client.get_telematic_data("WBA123", "container-123")
        assert len(entries) == 3

        by_name = {e.name: e for e in entries}
        assert by_name["vehicle.chassis.mileage"].value == "45230"
        assert by_name["vehicle.chassis.mileage"].unit == "km"
        assert by_name["vehicle.powertrain.electric.battery.stateOfCharge"].value == "72"

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, api_client: CarDataApiClient) -> None:
        """Test 429 raises RateLimitError."""
        resp = make_mock_response(429, {"exveErrorId": "CU-429"})
        api_client._auth.request = AsyncMock(return_value=resp)

        with pytest.raises(RateLimitError):
            await api_client.get_telematic_data("WBA123", "container-123")

    @pytest.mark.asyncio
    async def test_invalid_vin_error(self, api_client: CarDataApiClient) -> None:
        """Test CU-120 raises InvalidVinError."""
        resp = make_mock_response(
            400, {"exveErrorId": "CU-120", "exveErrorMsg": "Invalid VIN"}
        )
        api_client._auth.request = AsyncMock(return_value=resp)

        with pytest.raises(InvalidVinError):
            await api_client.get_telematic_data("INVALID", "container-123")


class TestChargingHistory:
    """Tests for get_charging_history."""

    @pytest.mark.asyncio
    async def test_returns_sessions(self, api_client: CarDataApiClient) -> None:
        """Test parsing charging history."""
        resp = make_mock_response(200, SAMPLE_CHARGING_HISTORY)
        api_client._auth.request = AsyncMock(return_value=resp)

        sessions = await api_client.get_charging_history(
            "WBA123",
            from_dt=datetime(2024, 1, 1),
            to_dt=datetime(2024, 12, 31),
        )
        assert len(sessions) == 1
        assert sessions[0].displayed_soc == 80
        assert sessions[0].energy_consumed_kwh == 7.5


class TestVehicleImage:
    """Tests for get_vehicle_image."""

    @pytest.mark.asyncio
    async def test_returns_bytes(self, api_client: CarDataApiClient) -> None:
        """Test getting vehicle image as bytes."""
        image_data = b"\x89PNG\r\n\x1a\n..."
        resp = make_mock_response(200, content=image_data)
        api_client._auth.request = AsyncMock(return_value=resp)

        result = await api_client.get_vehicle_image("WBA123")
        assert result == image_data


class TestErrorHandling:
    """Tests for API error response handling."""

    @pytest.mark.asyncio
    async def test_generic_api_error(self, api_client: CarDataApiClient) -> None:
        """Test unknown error raises ApiError."""
        resp = make_mock_response(
            500, {"exveErrorId": "SRV-500", "exveErrorMsg": "Internal server error"}
        )
        api_client._auth.request = AsyncMock(return_value=resp)

        with pytest.raises(ApiError) as exc_info:
            await api_client.get_vehicle_mappings()

        assert exc_info.value.error_id == "SRV-500"
        assert exc_info.value.status == 500

    @pytest.mark.asyncio
    async def test_container_error_105(self, api_client: CarDataApiClient) -> None:
        """Test CU-105 raises ContainerError."""
        resp = make_mock_response(
            400, {"exveErrorId": "CU-105", "exveErrorMsg": "Container not found"}
        )
        api_client._auth.request = AsyncMock(return_value=resp)

        with pytest.raises(ContainerError):
            await api_client.get_container("invalid-id")

