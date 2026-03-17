"""Tests for BMW CarData models."""

from __future__ import annotations

from pybmwcardata.models import (
    ChargingSession,
    Container,
    ContainerDetails,
    TelematicDataEntry,
    TyreDiagnosis,
    Vehicle,
    VehicleMapping,
)

from .conftest import (
    SAMPLE_BASIC_DATA,
    SAMPLE_CHARGING_HISTORY,
    SAMPLE_CONTAINER_DETAILS,
    SAMPLE_CONTAINERS,
    SAMPLE_TELEMATIC_DATA,
    SAMPLE_TYRE_DIAGNOSIS,
)


class TestVehicleMapping:
    """Tests for VehicleMapping dataclass."""

    def test_basic_mapping(self) -> None:
        """Test creating a basic vehicle mapping."""
        mapping = VehicleMapping(
            vin="WBA12345678901234",
            mapped_since="2024-01-15T10:00:00Z",
            mapping_type="PRIMARY",
        )
        assert mapping.vin == "WBA12345678901234"
        assert mapping.mapping_type == "PRIMARY"
        assert mapping.mapped_since == "2024-01-15T10:00:00Z"


class TestVehicle:
    """Tests for Vehicle dataclass."""

    def test_from_api_response(self) -> None:
        """Test creating Vehicle from API response."""
        vehicle = Vehicle.from_api_response(SAMPLE_BASIC_DATA)
        assert vehicle.vin == "WBA12345678901234"
        assert vehicle.brand == "BMW"
        assert vehicle.model_name == "330e"
        assert vehicle.model_range == "3er"
        assert vehicle.series == "3"
        assert vehicle.body_type == "G20"
        assert vehicle.drive_train == "PHEV_OTTO"
        assert vehicle.propulsion_type == "PHEV"
        assert vehicle.head_unit == "MGU"
        assert vehicle.is_telematics_capable is True
        assert vehicle.number_of_doors == 4
        assert vehicle.has_navi is True
        assert vehicle.has_sun_roof is False
        assert vehicle.steering == "LEFT"
        assert vehicle.engine == "B48"
        assert vehicle.colour_code == "475"
        assert vehicle.construction_date == "2023-06-15"
        assert vehicle.country_code_iso == "DE"
        assert vehicle.pu_step == "0723"
        assert vehicle.model_key == "3X31"
        assert vehicle.charging_modes == ["AC", "DC"]
        assert vehicle.hvs_max_energy_absolute == "12.0"
        assert vehicle.sim_status == "ACTIVE"

    def test_from_api_response_minimal(self) -> None:
        """Test creating Vehicle from minimal API response."""
        vehicle = Vehicle.from_api_response({"vin": "WBA000"})
        assert vehicle.vin == "WBA000"
        assert vehicle.brand == ""
        assert vehicle.model_name == ""
        assert vehicle.is_telematics_capable is False
        assert vehicle.charging_modes == []
        assert vehicle.hvs_max_energy_absolute is None


class TestContainer:
    """Tests for Container dataclass."""

    def test_from_api_response(self) -> None:
        """Test creating Container from API response."""
        data = SAMPLE_CONTAINERS["containers"][0]
        container = Container.from_api_response(data)
        assert container.container_id == "container-123"
        assert container.name == "HomeAssistant"
        assert container.state == "ACTIVE"

    def test_container_details_from_api_response(self) -> None:
        """Test creating ContainerDetails from API response."""
        details = ContainerDetails.from_api_response(SAMPLE_CONTAINER_DETAILS)
        assert details.container_id == "container-123"
        assert len(details.technical_descriptors) == 2
        assert "vehicle.chassis.mileage" in details.technical_descriptors


class TestTelematicDataEntry:
    """Tests for TelematicDataEntry dataclass."""

    def test_from_api_response(self) -> None:
        """Test creating TelematicDataEntry from API response."""
        data = SAMPLE_TELEMATIC_DATA["telematicData"]["vehicle.chassis.mileage"]
        entry = TelematicDataEntry.from_api_response("vehicle.chassis.mileage", data)
        assert entry.name == "vehicle.chassis.mileage"
        assert entry.value == "45230"
        assert entry.unit == "km"
        assert entry.timestamp == "2025-03-12T14:30:00Z"

    def test_from_api_response_empty(self) -> None:
        """Test creating TelematicDataEntry from empty data."""
        entry = TelematicDataEntry.from_api_response("test.key", {})
        assert entry.name == "test.key"
        assert entry.value == ""
        assert entry.unit == ""
        assert entry.timestamp == ""


class TestChargingSession:
    """Tests for ChargingSession dataclass."""

    def test_from_api_response(self) -> None:
        """Test creating ChargingSession from API response."""
        data = SAMPLE_CHARGING_HISTORY["data"][0]
        session = ChargingSession.from_api_response(data)
        assert session.start_time == 1710200000
        assert session.end_time == 1710210000
        assert session.displayed_soc == 80
        assert session.displayed_start_soc == 20
        assert session.total_charging_duration_sec == 10000
        assert session.energy_consumed_kwh == 7.5
        assert session.mileage == 45000

        # Charging cost
        assert session.charging_cost is not None
        assert session.charging_cost.currency == "EUR"
        assert session.charging_cost.calculated_charging_cost == 2.50
        assert session.charging_cost.calculated_savings == 4.00

        # Charging location
        assert session.charging_location is not None
        assert session.charging_location.municipality == "Munich"
        assert session.charging_location.map_matched_latitude == 48.137

        # Charging blocks
        assert len(session.charging_blocks) == 2
        assert session.charging_blocks[0].average_power_grid_kw == 3.6

    def test_from_api_response_minimal(self) -> None:
        """Test creating ChargingSession from minimal data."""
        session = ChargingSession.from_api_response({})
        assert session.start_time == 0
        assert session.charging_cost is None
        assert session.charging_location is None
        assert session.charging_blocks == []


class TestTyreDiagnosis:
    """Tests for TyreDiagnosis dataclass."""

    def test_from_api_response(self) -> None:
        """Test creating TyreDiagnosis from API response."""
        diagnosis = TyreDiagnosis.from_api_response(SAMPLE_TYRE_DIAGNOSIS)
        assert diagnosis.front_left is not None
        assert diagnosis.front_left.label == "FL"
        assert diagnosis.front_left.quality_status == "GOOD"
        assert diagnosis.front_left.season == "SUMMER"
        assert diagnosis.front_left.manufacturer == "Bridgestone"
        assert diagnosis.front_left.run_flat is True
        assert diagnosis.front_left.dimension == "225/45R18"
        assert diagnosis.front_left.wear_due_mileage == 30000
        assert diagnosis.front_left.tread_design == "T005"
        assert diagnosis.front_left.defect_status == "NONE"
        assert diagnosis.front_left.production_date == "2023-W20"

        assert diagnosis.front_right is not None
        assert diagnosis.front_right.label == "FR"

        assert diagnosis.aggregated_quality_status == "GOOD"

    def test_from_api_response_empty(self) -> None:
        """Test creating TyreDiagnosis from empty data."""
        diagnosis = TyreDiagnosis.from_api_response({})
        assert diagnosis.front_left is None
        assert diagnosis.front_right is None
        assert diagnosis.rear_left is None
        assert diagnosis.rear_right is None

