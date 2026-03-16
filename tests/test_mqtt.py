"""Tests for BMW CarData MQTT streaming client."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bmw_cardata.exceptions import MqttConnectionError
from bmw_cardata.models import TelematicDataEntry
from bmw_cardata.mqtt import (
    CarDataMqttClient,
    MqttMessage,
    _parse_streaming_payload,
)


class TestParseStreamingPayload:
    """Tests for the _parse_streaming_payload function."""

    def test_format1_telematic_data_dict(self) -> None:
        """Parse format 1: nested telematicData dict."""
        data = {
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
            }
        }
        entries = _parse_streaming_payload(data)
        assert len(entries) == 2
        by_name = {e.name: e for e in entries}
        assert by_name["vehicle.chassis.mileage"].value == "45230"
        assert by_name["vehicle.powertrain.electric.battery.stateOfCharge"].value == "72"

    def test_format2_single_entry(self) -> None:
        """Parse format 2: single entry with 'name' key."""
        data = {
            "name": "vehicle.chassis.mileage",
            "value": "45500",
            "unit": "km",
            "timestamp": "2025-03-12T15:00:00Z",
        }
        entries = _parse_streaming_payload(data)
        assert len(entries) == 1
        assert entries[0].name == "vehicle.chassis.mileage"
        assert entries[0].value == "45500"

    def test_format3_list_of_entries(self) -> None:
        """Parse format 3: list of entries."""
        data = [
            {
                "name": "vehicle.chassis.mileage",
                "value": "45500",
                "unit": "km",
                "timestamp": "2025-03-12T15:00:00Z",
            },
            {
                "name": "vehicle.body.isMoving",
                "value": "true",
                "unit": "",
                "timestamp": "2025-03-12T15:00:00Z",
            },
        ]
        entries = _parse_streaming_payload(data)
        assert len(entries) == 2

    def test_fallback_top_level_keys(self) -> None:
        """Parse fallback: top-level keys as descriptor names."""
        data = {
            "vehicle.chassis.mileage": {
                "value": "45500",
                "unit": "km",
                "timestamp": "2025-03-12T15:00:00Z",
            }
        }
        entries = _parse_streaming_payload(data)
        assert len(entries) == 1
        assert entries[0].name == "vehicle.chassis.mileage"

    def test_empty_dict(self) -> None:
        """Empty dict returns empty list."""
        assert _parse_streaming_payload({}) == []

    def test_empty_list(self) -> None:
        """Empty list returns empty list."""
        assert _parse_streaming_payload([]) == []

    def test_non_dict_non_list(self) -> None:
        """Non-dict non-list returns empty list."""
        assert _parse_streaming_payload("not a dict") == []

    def test_format3_skips_invalid_items(self) -> None:
        """Format 3 skips items without 'name' key."""
        data = [
            {"name": "vehicle.chassis.mileage", "value": "100"},
            {"no_name_key": True},
            "invalid_string",
        ]
        entries = _parse_streaming_payload(data)
        assert len(entries) == 1


class TestCarDataMqttClient:
    """Tests for CarDataMqttClient."""

    def test_init(self) -> None:
        """Test client initialization."""
        provider = AsyncMock(return_value="id-token")
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="test-gcid",
            id_token_provider=provider,
            port=8883,
        )
        assert client._host == "mqtt.test.com"
        assert client._gcid == "test-gcid"
        assert client._port == 8883
        assert client.connected is False

    def test_build_topics_with_vins(self) -> None:
        """Test topic building with specific VINs."""
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        topics = client._build_topics(["VIN1", "VIN2"])
        assert topics == ["my-gcid/VIN1", "my-gcid/VIN2"]

    def test_build_topics_wildcard(self) -> None:
        """Test topic building with wildcard (no VINs)."""
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        topics = client._build_topics(None)
        assert topics == ["my-gcid/+"]

    def test_build_topics_empty_list(self) -> None:
        """Test topic building with empty VIN list uses wildcard."""
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        topics = client._build_topics([])
        assert topics == ["my-gcid/+"]

    def test_set_callback(self) -> None:
        """Test setting callback."""
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        callback = AsyncMock()
        client.set_callback(callback)
        assert client._callback is callback

    @pytest.mark.asyncio
    async def test_connect_without_aiomqtt_raises(self) -> None:
        """Test connect raises MqttConnectionError when paho-mqtt not installed."""
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        with patch.dict("sys.modules", {"paho.mqtt.client": None}):
            with patch("builtins.__import__", side_effect=ImportError("No paho-mqtt")):
                # The import check happens inside connect()
                with pytest.raises(MqttConnectionError, match="paho-mqtt is required"):
                    await client.connect()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        """Test disconnect when not connected is safe."""
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        # Should not raise
        await client.disconnect()
        assert client.connected is False

    @pytest.mark.asyncio
    async def test_handle_message_calls_callback(self) -> None:
        """Test _handle_message parses and calls callback."""
        callback = AsyncMock()
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        client.set_callback(callback)

        # Create a mock MQTT message
        mock_msg = MagicMock()
        mock_msg.topic = "my-gcid/WBA12345678901234"
        mock_msg.payload = json.dumps({
            "telematicData": {
                "vehicle.chassis.mileage": {
                    "value": "50000",
                    "unit": "km",
                    "timestamp": "2025-03-12T16:00:00Z",
                }
            }
        }).encode()

        await client._handle_message(mock_msg)

        callback.assert_called_once()
        mqtt_msg = callback.call_args[0][0]
        assert isinstance(mqtt_msg, MqttMessage)
        assert mqtt_msg.vin == "WBA12345678901234"
        assert len(mqtt_msg.entries) == 1
        assert mqtt_msg.entries[0].name == "vehicle.chassis.mileage"
        assert mqtt_msg.entries[0].value == "50000"

    @pytest.mark.asyncio
    async def test_handle_message_no_callback(self) -> None:
        """Test _handle_message does nothing without callback."""
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        # No callback set — should not raise
        mock_msg = MagicMock()
        mock_msg.topic = "my-gcid/VIN123"
        mock_msg.payload = b'{"telematicData": {}}'
        await client._handle_message(mock_msg)

    @pytest.mark.asyncio
    async def test_handle_message_invalid_json(self) -> None:
        """Test _handle_message handles invalid JSON gracefully."""
        callback = AsyncMock()
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        client.set_callback(callback)

        mock_msg = MagicMock()
        mock_msg.topic = "my-gcid/VIN123"
        mock_msg.payload = b"not valid json"

        # Should not raise
        await client._handle_message(mock_msg)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_string_payload(self) -> None:
        """Test _handle_message handles string payload."""
        callback = AsyncMock()
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="my-gcid",
            id_token_provider=AsyncMock(),
        )
        client.set_callback(callback)

        mock_msg = MagicMock()
        mock_msg.topic = "my-gcid/VIN123"
        mock_msg.payload = '{"name": "vehicle.chassis.mileage", "value": "100"}'

        await client._handle_message(mock_msg)
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_extracts_vin_from_topic(self) -> None:
        """Test VIN is correctly extracted from MQTT topic."""
        callback = AsyncMock()
        client = CarDataMqttClient(
            host="mqtt.test.com",
            gcid="gcid-abc",
            id_token_provider=AsyncMock(),
        )
        client.set_callback(callback)

        mock_msg = MagicMock()
        mock_msg.topic = "gcid-abc/WBA99887766554433"
        mock_msg.payload = b'{"name": "test", "value": "1"}'

        await client._handle_message(mock_msg)
        mqtt_msg = callback.call_args[0][0]
        assert mqtt_msg.vin == "WBA99887766554433"
