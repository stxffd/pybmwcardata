"""MQTT streaming client for BMW CarData.

Connects to the BMW CarData MQTT broker to receive real-time vehicle
telematic data updates. Uses the id_token for authentication (GCID as
username, id_token as password) over TLS.

Uses paho-mqtt directly with a background thread (loop_start) to avoid
Windows ProactorEventLoop issues with add_reader/add_writer.

Protocol details (from BMW CarData docs):
- MQTT over SSL/TLS (mqtts://) on port 8883 or 9000
- QoS 0 (at most once delivery)
- Topic format: {gcid}/{vin} per vehicle, or {gcid}/+ for all VINs
- One connection per GCID allowed at a time
- id_token expires hourly; reconnect required with fresh token
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
from collections.abc import Callable, Coroutine
from concurrent.futures import Future as ConcurrentFuture
from dataclasses import dataclass
from typing import Any

from .const import MQTT_HOST, MQTT_PORT
from .exceptions import MqttConnectionError, MqttStreamError
from .models import TelematicDataEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class MqttMessage:
    """A parsed MQTT streaming message."""

    vin: str
    entries: list[TelematicDataEntry]
    raw_payload: dict[str, Any]


MqttCallback = Callable[[MqttMessage], Coroutine[Any, Any, None]]


class CarDataMqttClient:
    """MQTT streaming client for BMW CarData real-time data.

    Uses paho-mqtt with a background thread, bridging messages back to
    the asyncio event loop via run_coroutine_threadsafe.

    Usage::

        client = CarDataMqttClient(
            gcid="your-gcid",
            id_token_provider=get_fresh_id_token,
        )
        client.set_callback(on_message)
        await client.connect(vins=["WBA12345678901234"])
        # ... later ...
        await client.disconnect()
    """

    def __init__(
        self,
        gcid: str,
        id_token_provider: Callable[[], Coroutine[Any, Any, str]],
        host: str = MQTT_HOST,
        port: int = MQTT_PORT,
    ) -> None:
        """Initialize the MQTT client.

        Args:
            gcid: The user's GCID (used as MQTT username and client_id).
            id_token_provider: Async callable that returns a valid id_token.
            host: MQTT broker hostname (default: BMW CarData broker).
            port: MQTT broker port (default: 9000).
        """
        self._host = host
        self._port = port
        self._gcid = gcid
        self._id_token_provider = id_token_provider
        self._callback: MqttCallback | None = None
        self._client: Any | None = None  # paho mqtt.Client
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._topics: list[str] = []

    @property
    def connected(self) -> bool:
        """Return True if the MQTT client is currently connected."""
        return self._connected

    def set_callback(self, callback: MqttCallback) -> None:
        """Set the callback for incoming MQTT messages."""
        self._callback = callback

    async def connect(self, vins: list[str] | None = None) -> None:
        """Start the MQTT streaming connection.

        Args:
            vins: List of VINs to subscribe to. If None, subscribes to all
                  VINs via wildcard topic ({gcid}/+).
        """
        try:
            import paho.mqtt.client as mqtt
        except ImportError as err:
            raise MqttConnectionError(
                "paho-mqtt is required for MQTT streaming. "
                "Install with: pip install pybmwcardata[mqtt]"
            ) from err

        if self._client is not None:
            _LOGGER.warning("MQTT client already running, disconnecting first")
            await self.disconnect()

        self._loop = asyncio.get_running_loop()
        self._topics = self._build_topics(vins)

        id_token = await self._id_token_provider()

        client = mqtt.Client(
            client_id=self._gcid,
            clean_session=True,
            userdata={"topics": self._topics},
            protocol=mqtt.MQTTv311,
            transport="tcp",
        )

        client.username_pw_set(username=self._gcid, password=id_token)

        # TLS setup with explicit protocol version for compatibility
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        # Force TLSv1.2 minimum (some servers require this)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        client.tls_set_context(context)
        client.tls_insecure_set(False)

        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect

        client.reconnect_delay_set(min_delay=5, max_delay=60)

        self._client = client

        # Start background network thread, then connect
        client.loop_start()

        connect_event = threading.Event()
        self._connect_event = connect_event
        self._connect_rc: int | None = None

        client.connect_async(self._host, self._port, keepalive=60)

        # Wait for connection with timeout
        connected = await self._loop.run_in_executor(
            None, connect_event.wait, 20.0
        )

        if not connected or self._connect_rc != 0:
            rc = self._connect_rc
            client.loop_stop()
            self._client = None
            raise MqttConnectionError(
                f"MQTT connection failed (rc={rc})"
            )

    async def disconnect(self) -> None:
        """Stop the MQTT streaming connection."""
        client = self._client
        self._client = None
        self._connected = False
        if client is not None:
            client.disconnect()
            try:
                client.loop_stop()
            except Exception as err:
                _LOGGER.warning("Error stopping MQTT loop: %s", err)

    def _build_topics(self, vins: list[str] | None) -> list[str]:
        """Build MQTT topic strings."""
        if not vins:
            return [f"{self._gcid}/+"]
        return [f"{self._gcid}/{vin}" for vin in vins]

    async def _handle_message(self, message: Any) -> None:
        """Handle and process an MQTT message asynchronously.
        
        Args:
            message: The MQTT message object with topic and payload attributes.
        """
        if not self._callback:
            return

        try:
            topic_str = message.topic
            payload = message.payload
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")

            data = json.loads(payload)

            # Extract VIN from topic: {gcid}/{vin}
            parts = topic_str.split("/", 1)
            vin = parts[1] if len(parts) > 1 else ""

            entries = _parse_streaming_payload(data)

            mqtt_message = MqttMessage(
                vin=vin,
                entries=entries,
                raw_payload=data,
            )

            await self._callback(mqtt_message)

        except json.JSONDecodeError:
            _LOGGER.warning(
                "Received non-JSON MQTT payload on topic %s", message.topic
            )
        except Exception:
            _LOGGER.exception("Error handling MQTT message")

    # â”€â”€ paho-mqtt callbacks (run in background thread) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _on_connect(
        self, client: Any, userdata: dict, flags: Any, rc: int, *args: Any
    ) -> None:
        """Handle MQTT connect callback."""
        self._connect_rc = rc
        if hasattr(self, "_connect_event"):
            self._connect_event.set()

        if rc != 0:
            _LOGGER.warning("MQTT connection failed with rc=%s", rc)
            return

        self._connected = True
        _LOGGER.info(
            "Connected to BMW CarData MQTT broker at %s:%s",
            self._host,
            self._port,
        )

        topics = userdata.get("topics", self._topics)
        for topic in topics:
            client.subscribe(topic, qos=0)
            _LOGGER.debug("Subscribed to topic: %s", topic)

    def _on_message(
        self, client: Any, userdata: dict, message: Any
    ) -> None:
        """Handle incoming MQTT message (runs in paho thread)."""
        if not self._callback or not self._loop:
            return

        try:
            topic_str = message.topic
            payload = message.payload
            if isinstance(payload, bytes):
                payload = payload.decode("utf-8")

            data = json.loads(payload)

            # Extract VIN from topic: {gcid}/{vin}
            parts = topic_str.split("/", 1)
            vin = parts[1] if len(parts) > 1 else ""

            entries = _parse_streaming_payload(data)

            mqtt_message = MqttMessage(
                vin=vin,
                entries=entries,
                raw_payload=data,
            )

            # Bridge back to asyncio event loop
            future = asyncio.run_coroutine_threadsafe(
                self._callback(mqtt_message), self._loop
            )
            # Log exceptions from the async callback
            future.add_done_callback(self._log_callback_exception)

        except json.JSONDecodeError:
            _LOGGER.warning(
                "Received non-JSON MQTT payload on topic %s", message.topic
            )
        except Exception:
            _LOGGER.exception("Error handling MQTT message")

    def _on_disconnect(
        self, client: Any, userdata: dict, rc: int, *args: Any
    ) -> None:
        """Handle MQTT disconnect callback."""
        self._connected = False
        if rc == 0:
            _LOGGER.info("MQTT disconnected cleanly")
        else:
            _LOGGER.warning("MQTT unexpected disconnect (rc=%s)", rc)

    @staticmethod
    def _log_callback_exception(future: ConcurrentFuture[Any]) -> None:
        """Log exceptions from async callbacks dispatched to the event loop."""
        try:
            future.result()
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.exception("Exception in MQTT async callback: %s", err)


def _parse_streaming_payload(data: dict[str, Any]) -> list[TelematicDataEntry]:
    """Parse the JSON payload from a streaming message into TelematicDataEntry list.

    BMW CarData streaming messages can come in different formats:

    Format 1 - Telematics data dict (same as REST API):
        {"telematicData": {"vehicle.chassis.mileage": {"value": "123", "unit": "km", "timestamp": "..."}}}

    Format 2 - Single entry:
        {"name": "vehicle.chassis.mileage", "value": "123", "unit": "km", "timestamp": "..."}

    Format 3 - List of entries:
        [{"name": "vehicle.chassis.mileage", "value": "123", ...}, ...]
    """
    entries: list[TelematicDataEntry] = []

    if isinstance(data, list):
        # Format 3: list of entries
        for item in data:
            if isinstance(item, dict) and "name" in item:
                entries.append(TelematicDataEntry.from_api_response(item["name"], item))
        return entries

    if not isinstance(data, dict):
        return entries

    # Format 1: nested telematicData dict
    telematic_data = data.get("telematicData")
    if isinstance(telematic_data, dict):
        for name, entry_data in telematic_data.items():
            if isinstance(entry_data, dict):
                entries.append(TelematicDataEntry.from_api_response(name, entry_data))
        return entries

    # Format 2: single entry with "name" key
    if "name" in data:
        entries.append(TelematicDataEntry.from_api_response(data["name"], data))
        return entries

    # Fallback: treat top-level keys as descriptor names
    for name, value_data in data.items():
        if isinstance(value_data, dict) and "value" in value_data:
            entries.append(TelematicDataEntry.from_api_response(name, value_data))

    return entries

