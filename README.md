# pybmwcardata

Async Python client library for the [BMW CarData API](https://bmw-cardata.bmwgroup.com).

## Features

- OAuth 2.0 Device Authorization Grant (RFC 8628) with PKCE
- Full CarData REST API coverage (vehicles, containers, telematics, charging history, tyre diagnosis)
- Async-first design using `aiohttp` (Home Assistant compatible)
- Abstract authentication class for easy integration with token managers
- Typed data models

## Installation

```bash
pip install pybmwcardata
```

## Quick Start

```python
import asyncio
from aiohttp import ClientSession
from pybmwcardata import CarDataApiClient, DeviceAuth

async def main():
    async with ClientSession() as session:
        # Step 1: Initiate Device Code Flow
        device_auth = DeviceAuth(session)
        code_response = await device_auth.request_device_code("your-client-id")

        print(f"Go to: {code_response.verification_uri}")
        print(f"Enter code: {code_response.user_code}")

        # Step 2: Poll for tokens (user must authorize in browser)
        tokens = await device_auth.poll_for_tokens(
            client_id="your-client-id",
            device_code=code_response.device_code,
            code_verifier=code_response.code_verifier,
            interval=code_response.interval,
        )

        # Step 3: Use the API
        api = CarDataApiClient(session, tokens.access_token)

        # Get vehicle mappings
        mappings = await api.get_vehicle_mappings()
        for mapping in mappings:
            print(f"VIN: {mapping.vin}, Type: {mapping.mapping_type}")

        # Get basic vehicle data
        vehicle = await api.get_basic_data(mappings[0].vin)
        print(f"Model: {vehicle.model_name}, Brand: {vehicle.brand}")

asyncio.run(main())
```

## Usage with Home Assistant

This library follows the [Home Assistant API library guide](https://developers.home-assistant.io/docs/api_lib_index).
The `AbstractAuth` class allows Home Assistant to manage token refresh:

```python
from pybmwcardata.auth import AbstractAuth

class HACarDataAuth(AbstractAuth):
    def __init__(self, session, config_entry):
        super().__init__(session)
        self._config_entry = config_entry

    async def async_get_access_token(self) -> str:
        # Return valid token managed by HA
        return self._config_entry.data["access_token"]
```

## API Endpoints Covered

| Endpoint           | Method                                                                             |
| ------------------ | ---------------------------------------------------------------------------------- |
| Vehicle Mappings   | `get_vehicle_mappings()`                                                           |
| Basic Vehicle Data | `get_basic_data(vin)`                                                              |
| Containers CRUD    | `create_container()`, `list_containers()`, `get_container()`, `delete_container()` |
| Telematics Data    | `get_telematic_data(vin, container_id)`                                            |
| Charging History   | `get_charging_history(vin, from_dt, to_dt)`                                        |
| Tyre Diagnosis     | `get_tyre_diagnosis(vin)`                                                          |
| Vehicle Image      | `get_vehicle_image(vin)`                                                           |

## License

Apache License 2.0

