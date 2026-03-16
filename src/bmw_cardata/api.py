"""BMW CarData REST API client.

Provides async methods for all CarData API endpoints.
Uses AbstractAuth for authentication, allowing Home Assistant
to manage token refresh externally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from aiohttp import ClientSession

from .auth import AbstractAuth
from .const import API_BASE_URL, API_VERSION, API_VERSION_HEADER
from .exceptions import (
    ApiError,
    AuthenticationError,
    ContainerError,
    ContainerLimitReachedError,
    InvalidVinError,
    RateLimitError,
)
from .models import (
    ChargingSession,
    Container,
    ContainerDetails,
    LocationBasedChargingSetting,
    TelematicDataEntry,
    TyreDiagnosis,
    Vehicle,
    VehicleMapping,
)


class CarDataApiClient:
    """Client for the BMW CarData REST API."""

    def __init__(
        self,
        auth: AbstractAuth,
        api_base_url: str = API_BASE_URL,
    ) -> None:
        """Initialize the API client.

        Args:
            auth: An AbstractAuth instance that provides authenticated requests.
            api_base_url: Base URL for the CarData API.
        """
        self._auth = auth
        self._auth.host = api_base_url

    def _default_headers(self) -> dict[str, str]:
        """Return default headers for API requests."""
        return {API_VERSION_HEADER: API_VERSION}

    async def _handle_response(self, resp: Any) -> dict:
        """Handle API response, raising appropriate exceptions."""
        if resp.status == 200 or resp.status == 201:
            return await resp.json()

        # Try to parse error response
        try:
            error_data = await resp.json()
        except Exception:
            error_data = {}

        error_id = error_data.get("exveErrorId", "")
        error_msg = error_data.get("exveErrorMsg", "Unknown error")

        if resp.status == 401:
            raise AuthenticationError(f"Authentication failed: {error_msg}")
        if resp.status == 403:
            raise AuthenticationError(f"Access forbidden: {error_msg}")
        if resp.status == 429 or error_id == "CU-429":
            raise RateLimitError("Daily API rate limit (50 requests) reached")

        # Specific error IDs
        if error_id == "CU-120":
            raise InvalidVinError(f"Invalid VIN format: {error_msg}")
        if error_id == "CU-124":
            raise ContainerLimitReachedError(f"Max containers reached: {error_msg}")
        if error_id in ("CU-105", "CU-121", "CU-122"):
            raise ContainerError(f"Container error [{error_id}]: {error_msg}")

        raise ApiError(
            f"API error [{error_id}]: {error_msg}",
            error_id=error_id,
            status=resp.status,
        )

    # ── Vehicle Mappings ──────────────────────────────────────────────

    async def get_vehicle_mappings(self) -> list[VehicleMapping]:
        """Get all vehicles mapped to the account.

        Returns a list of VehicleMapping with VIN, mapping type (PRIMARY/SECONDARY),
        and mapping date.
        """
        resp = await self._auth.request(
            "GET",
            "/customers/vehicles/mappings",
            headers=self._default_headers(),
        )
        data = await self._handle_response(resp)

        # API may return a single object or list
        if isinstance(data, dict) and "vin" in data:
            data = [data]
        elif isinstance(data, dict):
            data = data.get("mappings", data.get("data", [data]))

        if not isinstance(data, list):
            data = [data]

        return [
            VehicleMapping(
                vin=item.get("vin", ""),
                mapped_since=item.get("mappedSince", ""),
                mapping_type=item.get("mappingType", ""),
            )
            for item in data
            if isinstance(item, dict) and item.get("vin")
        ]

    # ── Basic Vehicle Data ────────────────────────────────────────────

    async def get_basic_data(self, vin: str) -> Vehicle:
        """Get basic vehicle data (model, brand, equipment, etc.)."""
        resp = await self._auth.request(
            "GET",
            f"/customers/vehicles/{vin}/basicData",
            headers=self._default_headers(),
        )
        data = await self._handle_response(resp)
        return Vehicle.from_api_response(data)

    # ── Container Management ──────────────────────────────────────────

    async def list_containers(self) -> list[Container]:
        """List all telematics containers."""
        resp = await self._auth.request(
            "GET",
            "/customers/containers",
            headers=self._default_headers(),
        )
        data = await self._handle_response(resp)
        containers_data = data.get("containers", [])
        return [Container.from_api_response(c) for c in containers_data]

    async def get_container(self, container_id: str) -> ContainerDetails:
        """Get details of a specific container."""
        resp = await self._auth.request(
            "GET",
            f"/customers/containers/{container_id}",
            headers=self._default_headers(),
        )
        data = await self._handle_response(resp)
        return ContainerDetails.from_api_response(data)

    async def create_container(
        self,
        name: str,
        purpose: str,
        technical_descriptors: list[str],
    ) -> ContainerDetails:
        """Create a new telematics container.

        Args:
            name: Human-readable container name.
            purpose: Description of the container's use.
            technical_descriptors: List of telematic data key paths.

        Returns:
            The created container details.
        """
        resp = await self._auth.request(
            "POST",
            "/customers/containers",
            headers={**self._default_headers(), "Content-Type": "application/json"},
            json={
                "name": name,
                "purpose": purpose,
                "technicalDescriptors": technical_descriptors,
            },
        )
        data = await self._handle_response(resp)
        return ContainerDetails.from_api_response(data)

    async def delete_container(self, container_id: str) -> None:
        """Delete (deactivate) a container."""
        resp = await self._auth.request(
            "DELETE",
            f"/customers/containers/{container_id}",
        )
        if resp.status not in (200, 204):
            await self._handle_response(resp)

    # ── Telematics Data ───────────────────────────────────────────────

    async def get_telematic_data(
        self, vin: str, container_id: str
    ) -> list[TelematicDataEntry]:
        """Get telematics data for a vehicle from a container.

        Args:
            vin: Vehicle Identification Number.
            container_id: The container to retrieve data from.

        Returns:
            List of telematic data entries with name, value, unit, timestamp.
        """
        resp = await self._auth.request(
            "GET",
            f"/customers/vehicles/{vin}/telematicData",
            params={"containerId": container_id},
            headers=self._default_headers(),
        )
        data = await self._handle_response(resp)
        telematic_data = data.get("telematicData", {})

        return [
            TelematicDataEntry.from_api_response(name, entry)
            for name, entry in telematic_data.items()
            if isinstance(entry, dict)
        ]

    # ── Charging History ──────────────────────────────────────────────

    async def get_charging_history(
        self,
        vin: str,
        from_dt: datetime,
        to_dt: datetime,
        max_pages: int = 10,
    ) -> list[ChargingSession]:
        """Get charging session history for a vehicle.

        Automatically follows pagination (nextToken) to retrieve all sessions.

        Args:
            vin: Vehicle Identification Number.
            from_dt: Start of the time range.
            to_dt: End of the time range.
            max_pages: Maximum number of pages to fetch (default 10).

        Returns:
            List of charging sessions.
        """
        all_sessions: list[ChargingSession] = []
        next_token: str | None = None

        for _ in range(max_pages):
            params: dict[str, str] = {
                "from": from_dt.isoformat(),
                "to": to_dt.isoformat(),
            }
            if next_token:
                params["nextToken"] = next_token

            resp = await self._auth.request(
                "GET",
                f"/customers/vehicles/{vin}/chargingHistory",
                params=params,
                headers=self._default_headers(),
            )
            data = await self._handle_response(resp)
            sessions_data = data.get("data", [])
            all_sessions.extend(
                ChargingSession.from_api_response(s) for s in sessions_data
            )

            next_token = data.get("next_token") or data.get("nextToken")
            if not next_token:
                break

        return all_sessions

    # ── Tyre Diagnosis ────────────────────────────────────────────────

    async def get_tyre_diagnosis(self, vin: str) -> TyreDiagnosis:
        """Get Smart Maintenance Tyre Diagnosis data."""
        resp = await self._auth.request(
            "GET",
            f"/customers/vehicles/{vin}/smartMaintenanceTyreDiagnosis",
            headers=self._default_headers(),
        )
        data = await self._handle_response(resp)
        return TyreDiagnosis.from_api_response(data)

    # ── Location-Based Charging Settings ──────────────────────────────

    async def get_location_based_charging_settings(
        self,
        vin: str,
        max_pages: int = 10,
    ) -> list[LocationBasedChargingSetting]:
        """Get location-based charging settings for a vehicle.

        Automatically follows pagination (nextToken) to retrieve all settings.

        Args:
            vin: Vehicle Identification Number.
            max_pages: Maximum number of pages to fetch (default 10).

        Returns:
            List of location-based charging settings.
        """
        all_settings: list[LocationBasedChargingSetting] = []
        next_token: str | None = None

        for _ in range(max_pages):
            params: dict[str, str] = {}
            if next_token:
                params["nextToken"] = next_token

            resp = await self._auth.request(
                "GET",
                f"/customers/vehicles/{vin}/locationBasedChargingSettings",
                params=params if params else None,
                headers=self._default_headers(),
            )
            data = await self._handle_response(resp)
            settings_data = data.get("data", [])
            all_settings.extend(
                LocationBasedChargingSetting.from_api_response(s)
                for s in settings_data
            )

            next_token = data.get("next_token") or data.get("nextToken")
            if not next_token:
                break

        return all_settings

    # ── Vehicle Image ─────────────────────────────────────────────────

    async def get_vehicle_image(self, vin: str) -> bytes:
        """Get the vehicle image as bytes."""
        resp = await self._auth.request(
            "GET",
            f"/customers/vehicles/{vin}/image",
            headers=self._default_headers(),
        )
        if resp.status != 200:
            await self._handle_response(resp)
        return await resp.read()

    # ── Convenience: Ensure container exists ──────────────────────────

    async def ensure_container(
        self,
        name: str = "HomeAssistant",
        purpose: str = "Home Assistant Integration",
        technical_descriptors: list[str] | None = None,
    ) -> ContainerDetails:
        """Find an existing container by name or create a new one.

        This is a convenience method for integrations. If a container with
        the given name already exists and is ACTIVE, it is returned.
        Otherwise, a new container is created.
        """
        if technical_descriptors is None:
            technical_descriptors = DEFAULT_DESCRIPTORS

        containers = await self.list_containers()
        for container in containers:
            if container.name == name and container.state == "ACTIVE":
                return await self.get_container(container.container_id)

        return await self.create_container(name, purpose, technical_descriptors)


# Common telematics descriptors useful for home automation
DEFAULT_DESCRIPTORS = [
    # Location
    "vehicle.cabin.infotainment.navigation.currentLocation.longitude",
    "vehicle.cabin.infotainment.navigation.currentLocation.latitude",
    "vehicle.cabin.infotainment.navigation.currentLocation.heading",
    "vehicle.cabin.infotainment.navigation.currentLocation.speed",
    # Mileage & fuel
    "vehicle.chassis.mileage",
    "vehicle.powertrain.combustionEngine.remainingFuelLiters",
    "vehicle.powertrain.combustionEngine.remainingFuelPercent",
    "vehicle.powertrain.combustionEngine.remainingRange",
    "vehicle.powertrain.combustionEngine.combinedFuelConsumption",
    # Electric / charging
    "vehicle.powertrain.electric.battery.stateOfCharge",
    "vehicle.powertrain.electric.battery.remainingRange",
    "vehicle.powertrain.electric.battery.charging.power",
    "vehicle.powertrain.electric.battery.charging.status",
    "vehicle.powertrain.electric.battery.charging.chargingTarget",
    "vehicle.drivetrain.batteryManagement.header",
    "vehicle.drivetrain.batteryManagement.maxEnergy",
    "vehicle.drivetrain.electricEngine.charging.status",
    # Doors
    "vehicle.cabin.door.row1.driver.isOpen",
    "vehicle.cabin.door.row1.passenger.isOpen",
    "vehicle.cabin.door.row2.driver.isOpen",
    "vehicle.cabin.door.row2.passenger.isOpen",
    # Door locks
    "vehicle.cabin.door.row1.driver.isLocked",
    "vehicle.cabin.door.row1.passenger.isLocked",
    "vehicle.cabin.door.row2.driver.isLocked",
    "vehicle.cabin.door.row2.passenger.isLocked",
    # Windows
    "vehicle.cabin.door.row1.driver.window.isOpen",
    "vehicle.cabin.door.row1.passenger.window.isOpen",
    "vehicle.cabin.door.row2.driver.window.isOpen",
    "vehicle.cabin.door.row2.passenger.window.isOpen",
    # Trunk / hood
    "vehicle.body.trunk.isOpen",
    "vehicle.body.hood.isOpen",
    # Climate
    "vehicle.cabin.hvac.ambientAirTemperature",
    # Tyres
    "vehicle.chassis.axle.row1.wheel.left.tire.pressure",
    "vehicle.chassis.axle.row1.wheel.right.tire.pressure",
    "vehicle.chassis.axle.row2.wheel.left.tire.pressure",
    "vehicle.chassis.axle.row2.wheel.right.tire.pressure",
    # Motion / parking
    "vehicle.body.isMoving",
    "vehicle.cabin.parkingBrake.isActive",
]
