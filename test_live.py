"""Live functional test for python-bmw-cardata against real BMW CarData API.

Usage:
    python test_live.py --client-id YOUR_CLIENT_ID
    python test_live.py --client-id YOUR_CLIENT_ID --vin WBAXXXXXXXX

Tokens are cached in .tokens.json so you only need to authenticate once.
On subsequent runs, the refresh token is used automatically.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import webbrowser
from pathlib import Path

import aiohttp

from bmw_cardata.api import CarDataApiClient
from bmw_cardata.auth import AbstractAuth, DeviceAuth
from bmw_cardata.models import TokenResponse
from bmw_cardata.mqtt import CarDataMqttClient, MqttMessage

TOKEN_CACHE_FILE = Path(__file__).parent / ".tokens.json"


# ── Token persistence ────────────────────────────────────────────────

def _save_tokens(client_id: str, tokens: TokenResponse) -> None:
    """Save tokens to cache file."""
    data = {
        "client_id": client_id,
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "id_token": tokens.id_token,
        "gcid": tokens.gcid,
        "scope": tokens.scope,
        "expires_at": time.time() + tokens.expires_in,
    }
    TOKEN_CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"  💾 Tokens gespeichert in {TOKEN_CACHE_FILE.name}")


def _load_tokens() -> dict | None:
    """Load tokens from cache file if it exists."""
    if not TOKEN_CACHE_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_CACHE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ── Simple concrete Auth using a static token ────────────────────────

class LiveAuth(AbstractAuth):
    """Auth implementation that holds a token obtained from the device flow."""

    def __init__(self, websession: aiohttp.ClientSession, token: str) -> None:
        super().__init__(websession)
        self._token = token

    async def async_get_access_token(self) -> str:
        return self._token


# ── Helpers ──────────────────────────────────────────────────────────

def _separator(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


async def _authenticate(
    session: aiohttp.ClientSession, client_id: str
) -> TokenResponse:
    """Run the device-code flow interactively."""
    _separator("1 · Device Code Flow – Authentifizierung")

    device_auth = DeviceAuth(session)
    dc = await device_auth.request_device_code(client_id)

    print(f"\n  Verification URL : {dc.verification_uri}")
    print(f"  User Code        : {dc.user_code}")
    print(f"  Expires in       : {dc.expires_in}s")

    # Try to open the browser automatically
    try:
        webbrowser.open(dc.verification_uri)
        print("\n  ➜ Browser wurde geöffnet. Gib dort den User-Code ein.")
    except Exception:
        print("\n  ➜ Öffne die URL manuell im Browser und gib den Code ein.")

    print("  Warte auf Autorisierung …\n")

    tokens = await device_auth.poll_for_tokens(
        client_id=client_id,
        device_code=dc.device_code,
        code_verifier=dc.code_verifier,
        interval=dc.interval,
        timeout=dc.expires_in,
    )

    print("  ✔ Tokens erhalten!")
    print(f"    access_token : {tokens.access_token[:20]}…")
    print(f"    refresh_token: {tokens.refresh_token[:20]}…")
    print(f"    gcid         : {tokens.gcid}")
    print(f"    expires_in   : {tokens.expires_in}s")
    _save_tokens(client_id, tokens)
    return tokens


async def _get_or_refresh_tokens(
    session: aiohttp.ClientSession, client_id: str
) -> TokenResponse:
    """Try cached tokens first, refresh if expired, fall back to device flow."""
    cached = _load_tokens()

    if cached and cached.get("client_id") == client_id:
        # Check if access token is still valid (with 60s margin)
        if cached.get("expires_at", 0) > time.time() + 60:
            _separator("1 · Auth – Gespeicherte Tokens verwenden")
            print(f"  ✔ Access Token gültig (noch {int(cached['expires_at'] - time.time())}s)")
            return TokenResponse(
                access_token=cached["access_token"],
                token_type="Bearer",
                expires_in=int(cached["expires_at"] - time.time()),
                refresh_token=cached["refresh_token"],
                scope=cached.get("scope", ""),
                id_token=cached.get("id_token", ""),
                gcid=cached.get("gcid", ""),
            )

        # Access token expired – try refresh
        if cached.get("refresh_token"):
            _separator("1 · Auth – Token Refresh")
            print("  Access Token abgelaufen, versuche Refresh …")
            try:
                device_auth = DeviceAuth(session)
                tokens = await device_auth.refresh_tokens(client_id, cached["refresh_token"])
                print("  ✔ Tokens per Refresh erneuert!")
                print(f"    access_token : {tokens.access_token[:20]}…")
                print(f"    expires_in   : {tokens.expires_in}s")
                _save_tokens(client_id, tokens)
                return tokens
            except Exception as exc:
                print(f"  ⚠ Refresh fehlgeschlagen: {exc}")
                print("  → Starte neuen Device Code Flow …")

    # No cached tokens or refresh failed → full device code flow
    return await _authenticate(session, client_id)


async def _test_vehicle_mappings(api: CarDataApiClient) -> list[str]:
    """Fetch and display vehicle mappings, return list of VINs."""
    _separator("2 · Vehicle Mappings")
    mappings = await api.get_vehicle_mappings()
    if not mappings:
        print("  Keine Fahrzeuge gefunden.")
        return []
    for m in mappings:
        print(f"  VIN: {m.vin}  |  Typ: {m.mapping_type}  |  Seit: {m.mapped_since}")
    return [m.vin for m in mappings]


async def _test_basic_data(api: CarDataApiClient, vin: str) -> None:
    _separator(f"3 · Basic Data – {vin}")
    vehicle = await api.get_basic_data(vin)
    fields = [
        ("Brand", vehicle.brand),
        ("Model", f"{vehicle.model_name} ({vehicle.model_range})"),
        ("Series", vehicle.series),
        ("Body", vehicle.body_type),
        ("Drive", vehicle.drive_train),
        ("Propulsion", vehicle.propulsion_type),
        ("Head Unit", vehicle.head_unit),
        ("Telematics", vehicle.is_telematics_capable),
        ("Doors", vehicle.number_of_doors),
        ("Engine", vehicle.engine),
        ("Built", vehicle.construction_date),
        ("Country", vehicle.country_code_iso),
    ]
    for label, value in fields:
        print(f"  {label:14s}: {value}")


async def _test_containers(api: CarDataApiClient) -> str | None:
    """List containers, ensure one exists, return container_id."""
    _separator("4 · Container")

    containers = await api.list_containers()
    active_containers = [c for c in containers if c.state == "ACTIVE"]

    if containers:
        print("  Vorhandene Container:")
        for c in containers:
            print(f"    {c.container_id}  |  {c.name}  |  {c.state}")

    # Try to create a new container, fall back to existing one
    try:
        print("\n  Versuche Container zu erstellen …")
        container = await api.ensure_container(
            name="LiveTest",
            purpose="Functional testing of python-bmw-cardata",
        )
        print(f"  ✔ Container: {container.container_id}  ({container.name})")
        print(f"    Descriptors: {len(container.technical_descriptors)} Einträge")
        return container.container_id
    except Exception as exc:
        print(f"  ⚠ Erstellung fehlgeschlagen: {exc}")
        if active_containers:
            fallback = active_containers[0]
            print(f"  → Verwende existierenden Container: {fallback.container_id} ({fallback.name})")
            return fallback.container_id
        print("  ✘ Kein aktiver Container verfügbar.")
        return None


async def _test_telematic_data(
    api: CarDataApiClient, vin: str, container_id: str
) -> None:
    _separator(f"5 · Telematic Data – {vin}")
    entries = await api.get_telematic_data(vin, container_id)
    if not entries:
        print("  Keine Telematikdaten verfügbar (Container evtl. gerade erst erstellt).")
        return
    for e in entries:
        print(f"  {e.name:55s}  =  {e.value} {e.unit}  ({e.timestamp})")


async def _test_vehicle_image(api: CarDataApiClient, vin: str) -> None:
    _separator(f"6 · Vehicle Image – {vin}")
    try:
        image_bytes = await api.get_vehicle_image(vin)
        print(f"  ✔ Bild erhalten: {len(image_bytes)} Bytes")
    except Exception as exc:
        print(f"  ✘ Bild nicht verfügbar: {exc}")


MQTT_HOST = "customer.streaming-cardata.bmwgroup.com"
MQTT_PORT = 9000
MQTT_LISTEN_SECONDS = 30


async def _test_mqtt(tokens: TokenResponse, vin: str) -> None:
    _separator(f"7 · MQTT Streaming – {vin}")

    message_count = 0

    async def on_message(msg: MqttMessage) -> None:
        nonlocal message_count
        message_count += 1
        print(f"\n  📨 Nachricht #{message_count} (VIN: {msg.vin})")
        for e in msg.entries:
            print(f"    {e.name:55s}  =  {e.value} {e.unit}")
        if not msg.entries:
            print(f"    Raw: {json.dumps(msg.raw_payload, indent=2)[:500]}")

    async def get_id_token() -> str:
        return tokens.id_token

    client = CarDataMqttClient(
        host=MQTT_HOST,
        gcid=tokens.gcid,
        id_token_provider=get_id_token,
        port=MQTT_PORT,
    )
    client.set_callback(on_message)

    print(f"  Host  : {MQTT_HOST}:{MQTT_PORT}")
    print(f"  GCID  : {tokens.gcid}")
    print(f"  Topic : {tokens.gcid}/{vin}")
    print(f"  Warte {MQTT_LISTEN_SECONDS}s auf Nachrichten …\n")

    await client.connect(vins=[vin])

    await asyncio.sleep(MQTT_LISTEN_SECONDS)

    await client.disconnect()

    if message_count == 0:
        print(f"\n  ⚠ Keine Nachrichten in {MQTT_LISTEN_SECONDS}s empfangen.")
        print("    (Normal wenn Fahrzeug geparkt/aus – Daten kommen nur bei Zustandsänderung)")
    else:
        print(f"\n  ✔ {message_count} Nachricht(en) empfangen.")


# ── Main ─────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Live-Test der BMW CarData Library")
    parser.add_argument("--client-id", default=None, help="BMW CarData Client ID (optional, wird von .tokens.json verwendet wenn vorhanden)")
    parser.add_argument("--vin", default=None, help="Optional: bestimmte VIN testen")
    args = parser.parse_args()

    # Try to get client_id from cache if not provided
    client_id = args.client_id
    if not client_id:
        cached = _load_tokens()
        if cached and cached.get("client_id"):
            client_id = cached["client_id"]
            print(f"  ℹ Client ID aus .tokens.json geladen: {client_id}")
        else:
            print("  ✘ Fehler: --client-id erforderlich (kein cached token vorhanden)")
            sys.exit(1)

    async with aiohttp.ClientSession() as session:
        # 1) Authenticate (uses cache / refresh if available)
        tokens = await _get_or_refresh_tokens(session, client_id)

        # Build API client
        auth = LiveAuth(session, tokens.access_token)
        api = CarDataApiClient(auth)

        # 2) Vehicle Mappings
        try:
            vins = await _test_vehicle_mappings(api)
        except Exception as exc:
            print(f"  ✘ Fehler: {exc}")
            vins = []

        # Pick VIN to test
        vin = args.vin or (vins[0] if vins else None)
        if not vin:
            print("\n  Keine VIN verfügbar. Beende Test.")
            return

        print(f"\n  → Teste mit VIN: {vin}")

        # 3) Basic Data
        try:
            await _test_basic_data(api, vin)
        except Exception as exc:
            print(f"  ✘ Fehler: {exc}")

        # 4) Containers
        container_id = None
        try:
            container_id = await _test_containers(api)
        except Exception as exc:
            print(f"  ✘ Fehler: {exc}")

        # 5) Telematic Data
        if container_id:
            try:
                await _test_telematic_data(api, vin, container_id)
            except Exception as exc:
                print(f"  ✘ Fehler: {exc}")

        # 6) Vehicle Image
        try:
            await _test_vehicle_image(api, vin)
        except Exception as exc:
            print(f"  ✘ Fehler: {exc}")

        # 7) MQTT Streaming
        try:
            await _test_mqtt(tokens, vin)
        except Exception as exc:
            print(f"  ✘ MQTT Fehler: {exc}")

        _separator("Fertig!")
        print("  Alle Tests abgeschlossen.\n")


if __name__ == "__main__":
    asyncio.run(main())
