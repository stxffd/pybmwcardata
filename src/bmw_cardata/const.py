"""Constants for BMW CarData API."""

# OAuth / Device Code Flow
AUTH_BASE_URL = "https://customer.bmwgroup.com"
DEVICE_CODE_ENDPOINT = "/gcdm/oauth/device/code"
TOKEN_ENDPOINT = "/gcdm/oauth/token"

# CarData REST API
API_BASE_URL = "https://api-cardata.bmwgroup.com"

# Default scopes
SCOPE_API = "cardata:api:read"
SCOPE_STREAMING = "cardata:streaming:read"
SCOPE_AUTH = "authenticate_user openid"
DEFAULT_SCOPES = f"{SCOPE_AUTH} {SCOPE_API} {SCOPE_STREAMING}"

# Device code flow grant type (RFC 8628)
GRANT_TYPE_DEVICE_CODE = "urn:ietf:params:oauth:grant-type:device_code"
GRANT_TYPE_REFRESH_TOKEN = "refresh_token"

# API version header
API_VERSION_HEADER = "x-version"
API_VERSION = "v1"

# Rate limits
DAILY_API_RATE_LIMIT = 50

# Token validity
ACCESS_TOKEN_VALIDITY_SECONDS = 3600  # 1 hour
REFRESH_TOKEN_VALIDITY_SECONDS = 1_209_600  # 14 days

# MQTT Streaming
MQTT_HOST = "customer.streaming-cardata.bmwgroup.com"
MQTT_PORT = 9000
