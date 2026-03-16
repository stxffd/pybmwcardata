"""Data models for BMW CarData API responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class DeviceCodeResponse:
    """Response from the device code request."""

    user_code: str
    device_code: str
    verification_uri: str
    interval: int
    expires_in: int
    code_verifier: str  # stored for later token exchange


@dataclass
class TokenResponse:
    """Response from the token exchange or refresh."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str
    id_token: str
    gcid: str


@dataclass
class VehicleMapping:
    """A vehicle mapping (VIN to account)."""

    vin: str
    mapped_since: str
    mapping_type: str  # PRIMARY or SECONDARY


@dataclass
class Vehicle:
    """Basic vehicle data."""

    vin: str
    brand: str
    model_name: str
    model_range: str
    series: str
    body_type: str
    drive_train: str
    propulsion_type: str
    head_unit: str
    is_telematics_capable: bool
    number_of_doors: int
    has_navi: bool
    has_sun_roof: bool
    steering: str
    engine: str
    colour_code: str
    construction_date: str
    country_code_iso: str
    pu_step: str
    model_key: str
    charging_modes: list[str] = field(default_factory=list)
    hvs_max_energy_absolute: str | None = None
    sim_status: str | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> Vehicle:
        """Create Vehicle from API response."""
        return cls(
            vin=data.get("vin", ""),
            brand=data.get("brand", ""),
            model_name=data.get("modelName", ""),
            model_range=data.get("modelRange", ""),
            series=data.get("series", ""),
            body_type=data.get("bodyType", ""),
            drive_train=data.get("driveTrain", ""),
            propulsion_type=data.get("propulsionType", ""),
            head_unit=data.get("headUnit", ""),
            is_telematics_capable=data.get("isTelematicsCapable", False),
            number_of_doors=data.get("numberOfDoors", 0),
            has_navi=data.get("hasNavi", False),
            has_sun_roof=data.get("hasSunRoof", False),
            steering=data.get("steering", ""),
            engine=data.get("engine", ""),
            colour_code=data.get("colourCode", ""),
            construction_date=data.get("constructionDate", ""),
            country_code_iso=data.get("countryCodeISO", ""),
            pu_step=data.get("puStep", ""),
            model_key=data.get("modelKey", ""),
            charging_modes=data.get("chargingModes", []),
            hvs_max_energy_absolute=data.get("hvsMaxEnergyAbsolute"),
            sim_status=data.get("simStatus"),
        )


@dataclass
class Container:
    """Summary info about a telematics container."""

    container_id: str
    name: str
    purpose: str
    state: str  # ACTIVE or DELETED
    created: str

    @classmethod
    def from_api_response(cls, data: dict) -> Container:
        """Create Container from API response."""
        return cls(
            container_id=data.get("containerId", ""),
            name=data.get("name", ""),
            purpose=data.get("purpose", ""),
            state=data.get("state", ""),
            created=data.get("created", ""),
        )


@dataclass
class ContainerDetails(Container):
    """Detailed container info including descriptors."""

    technical_descriptors: list[str] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict) -> ContainerDetails:
        """Create ContainerDetails from API response."""
        return cls(
            container_id=data.get("containerId", ""),
            name=data.get("name", ""),
            purpose=data.get("purpose", ""),
            state=data.get("state", ""),
            created=data.get("created", ""),
            technical_descriptors=data.get("technicalDescriptors", []),
        )


@dataclass
class TelematicDataEntry:
    """A single telematics data entry (key-value with timestamp)."""

    name: str
    value: str
    unit: str
    timestamp: str

    @classmethod
    def from_api_response(cls, name: str, data: dict) -> TelematicDataEntry:
        """Create TelematicDataEntry from API response."""
        return cls(
            name=name,
            value=data.get("value", ""),
            unit=data.get("unit", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class ChargingCostInformation:
    """Charging cost information."""

    currency: str
    calculated_charging_cost: float
    calculated_savings: float


@dataclass
class ChargingLocation:
    """Charging session location."""

    municipality: str
    formatted_address: str
    street_address: str
    map_matched_latitude: float | None = None
    map_matched_longitude: float | None = None


@dataclass
class ChargingBlock:
    """A block within a charging session."""

    start_time: int
    end_time: int
    average_power_grid_kw: float | None = None


@dataclass
class ChargingSession:
    """A charging history session."""

    start_time: int
    end_time: int
    displayed_soc: int
    displayed_start_soc: int
    total_charging_duration_sec: int
    energy_consumed_kwh: float | None = None
    is_preconditioning_activated: bool = False
    mileage: int = 0
    mileage_units: str = ""
    time_zone: str = ""
    charging_cost: ChargingCostInformation | None = None
    charging_location: ChargingLocation | None = None
    charging_blocks: list[ChargingBlock] = field(default_factory=list)

    @classmethod
    def from_api_response(cls, data: dict) -> ChargingSession:
        """Create ChargingSession from API response."""
        cost_data = data.get("chargingCostInformation")
        cost = None
        if cost_data:
            cost = ChargingCostInformation(
                currency=cost_data.get("currency", ""),
                calculated_charging_cost=cost_data.get("calculatedChargingCost", 0.0),
                calculated_savings=cost_data.get("calculatedSavings", 0.0),
            )

        loc_data = data.get("chargingLocation")
        location = None
        if loc_data:
            location = ChargingLocation(
                municipality=loc_data.get("municipality", ""),
                formatted_address=loc_data.get("formattedAddress", ""),
                street_address=loc_data.get("streetAddress", ""),
                map_matched_latitude=loc_data.get("mapMatchedLatitude"),
                map_matched_longitude=loc_data.get("mapMatchedLongitude"),
            )

        blocks = [
            ChargingBlock(
                start_time=b.get("startTime", 0),
                end_time=b.get("endTime", 0),
                average_power_grid_kw=b.get("averagePowerGridKw"),
            )
            for b in data.get("chargingBlocks", [])
        ]

        return cls(
            start_time=data.get("startTime", 0),
            end_time=data.get("endTime", 0),
            displayed_soc=data.get("displayedSoc", 0),
            displayed_start_soc=data.get("displayedStartSoc", 0),
            total_charging_duration_sec=data.get("totalChargingDurationSec", 0),
            energy_consumed_kwh=data.get("energyConsumedFromPowerGridKwh"),
            is_preconditioning_activated=data.get("isPreconditioningActivated", False),
            mileage=data.get("mileage", 0),
            mileage_units=data.get("mileageUnits", ""),
            time_zone=data.get("timeZone", ""),
            charging_cost=cost,
            charging_location=location,
            charging_blocks=blocks,
        )


@dataclass
class TyreData:
    """Data about a single tyre."""

    label: str
    quality_status: str | None = None
    season: str | None = None
    manufacturer: str | None = None
    tread_design: str | None = None
    wear_status: str | None = None
    wear_due_mileage: int | None = None
    defect_status: str | None = None
    production_date: str | None = None
    run_flat: bool | None = None
    dimension: str | None = None


@dataclass
class TyreDiagnosis:
    """Tyre diagnosis for a vehicle."""

    front_left: TyreData | None = None
    front_right: TyreData | None = None
    rear_left: TyreData | None = None
    rear_right: TyreData | None = None
    aggregated_quality_status: str | None = None

    @classmethod
    def from_api_response(cls, data: dict) -> TyreDiagnosis:
        """Create TyreDiagnosis from API response."""
        passenger_car = data.get("passengerCar", {})
        mounted = passenger_car.get("mountedTyres", {})

        def _parse_tyre(tyre_data: dict | None) -> TyreData | None:
            if not tyre_data:
                return None
            return TyreData(
                label=tyre_data.get("label", ""),
                quality_status=_safe_nested(tyre_data, "qualityStatus", "qualityStatus"),
                season=_safe_nested(tyre_data, "season", "season"),
                manufacturer=_safe_nested(tyre_data, "tread", "manufacturer"),
                tread_design=_safe_nested(tyre_data, "tread", "treadDesign"),
                wear_status=_safe_nested(tyre_data, "tyreWear", "status"),
                wear_due_mileage=tyre_data.get("tyreWear", {}).get("dueMileage"),
                defect_status=_safe_nested(tyre_data, "tyreDefect", "status"),
                production_date=_safe_nested(tyre_data, "tyreProductionDate", "value"),
                run_flat=tyre_data.get("runFlat", {}).get("runFlat"),
                dimension=_safe_nested(tyre_data, "dimension", "value"),
            )

        agg = mounted.get("aggregatedQualityStatus", {})

        return cls(
            front_left=_parse_tyre(mounted.get("frontLeft")),
            front_right=_parse_tyre(mounted.get("frontRight")),
            rear_left=_parse_tyre(mounted.get("rearLeft")),
            rear_right=_parse_tyre(mounted.get("rearRight")),
            aggregated_quality_status=agg.get("qualityStatus") if agg else None,
        )


@dataclass
class ChargingTimeWindow:
    """A charging time window within location-based charging settings."""

    start_hour: int
    start_minute: int
    stop_hour: int
    stop_minute: int


@dataclass
class LocationBasedChargingSetting:
    """Location-based charging setting for a vehicle."""

    id: str
    last_updated: str
    cluster_location_id: str
    latitude: float | None = None
    longitude: float | None = None
    last_visit: str = ""
    visits: int = 0
    charging_mode: str = ""
    optimized_charging_preference: str = ""
    start_charging_time_period_hour: int = 0
    start_charging_time_period_minute: int = 0
    stop_charging_time_period_hour: int = 0
    stop_charging_time_period_minute: int = 0
    vehicle_id_with_gcid: str = ""
    charging_time_windows: list[ChargingTimeWindow] = field(default_factory=list)
    ac_current_limit_flag: str = ""
    ac_current_limit: float | None = None
    acoustic_limit: str = ""
    flap_lock: str = ""
    charging_plug: str = ""

    @classmethod
    def from_api_response(cls, data: dict) -> LocationBasedChargingSetting:
        """Create LocationBasedChargingSetting from API response."""
        windows = [
            ChargingTimeWindow(
                start_hour=w.get("startChargingTimePeriodHour", 0),
                start_minute=w.get("startChargingTimePeriodMinute", 0),
                stop_hour=w.get("stopChargingTimePeriodHour", 0),
                stop_minute=w.get("stopChargingTimePeriodMinute", 0),
            )
            for w in data.get("chargingTimeWindows", [])
        ]
        return cls(
            id=data.get("id", ""),
            last_updated=data.get("lastUpdated", ""),
            cluster_location_id=data.get("clusterLocationId", ""),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            last_visit=data.get("lastVisit", ""),
            visits=data.get("visits", 0),
            charging_mode=data.get("chargingMode", ""),
            optimized_charging_preference=data.get("optimizedChargingPreference", ""),
            start_charging_time_period_hour=data.get("startChargingTimePeriodHour", 0),
            start_charging_time_period_minute=data.get("startChargingTimePeriodMinute", 0),
            stop_charging_time_period_hour=data.get("stopChargingTimePeriodHour", 0),
            stop_charging_time_period_minute=data.get("stopChargingTimePeriodMinute", 0),
            vehicle_id_with_gcid=data.get("vehicleIdWithGcid", ""),
            charging_time_windows=windows,
            ac_current_limit_flag=data.get("acCurrentLimitFlag", ""),
            ac_current_limit=data.get("acCurrentLimit"),
            acoustic_limit=data.get("acousticLimit", ""),
            flap_lock=data.get("flapLock", ""),
            charging_plug=data.get("chargingPlug", ""),
        )


def _safe_nested(data: dict, key1: str, key2: str) -> str | None:
    """Safely get a nested value."""
    nested = data.get(key1)
    if isinstance(nested, dict):
        return nested.get(key2)
    return None
