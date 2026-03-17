"""Authentication for BMW CarData API.

Implements OAuth 2.0 Device Authorization Grant (RFC 8628) with PKCE (S256)
and an AbstractAuth class following the Home Assistant API library pattern.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
from abc import ABC, abstractmethod
from typing import Any

from aiohttp import ClientResponse, ClientSession

from .const import (
    AUTH_BASE_URL,
    DEFAULT_SCOPES,
    DEVICE_CODE_ENDPOINT,
    GRANT_TYPE_DEVICE_CODE,
    GRANT_TYPE_REFRESH_TOKEN,
    TOKEN_ENDPOINT,
)
from .exceptions import (
    AuthenticationError,
    AuthorizationPendingError,
    DeviceCodeExpiredError,
    TokenExpiredError,
)
from .models import DeviceCodeResponse, TokenResponse


def _generate_code_verifier() -> str:
    """Generate a cryptographically random code verifier (43-128 chars, RFC 7636)."""
    return secrets.token_urlsafe(64)[:128]


def _generate_code_challenge(code_verifier: str) -> str:
    """Generate S256 code challenge from verifier (RFC 7636 Section 4.2)."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class AbstractAuth(ABC):
    """Abstract authentication class for BMW CarData API.

    Home Assistant integrations should subclass this and implement
    `async_get_access_token` to provide token management.
    """

    def __init__(self, websession: ClientSession, host: str = "") -> None:
        """Initialize the auth."""
        self.websession = websession
        self.host = host

    @abstractmethod
    async def async_get_access_token(self) -> str:
        """Return a valid access token."""

    async def request(
        self, method: str, url: str, **kwargs: Any
    ) -> ClientResponse:
        """Make an authenticated request to the CarData API."""
        headers: dict[str, str] = dict(kwargs.pop("headers", {}) or {})

        access_token = await self.async_get_access_token()
        headers["Authorization"] = f"Bearer {access_token}"
        headers["Accept"] = "application/json"

        return await self.websession.request(
            method, f"{self.host}{url}", **kwargs, headers=headers
        )


class DeviceAuth:
    """Handle the OAuth 2.0 Device Authorization Grant flow for BMW CarData."""

    def __init__(
        self,
        websession: ClientSession,
        auth_base_url: str = AUTH_BASE_URL,
    ) -> None:
        """Initialize device auth."""
        self._session = websession
        self._auth_base_url = auth_base_url

    async def request_device_code(
        self,
        client_id: str,
        scopes: str = DEFAULT_SCOPES,
    ) -> DeviceCodeResponse:
        """Initiate the device code flow (Step 1).

        Returns user_code & verification_uri for the user to authorize,
        plus the device_code and code_verifier needed for token exchange.
        """
        code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(code_verifier)

        resp = await self._session.post(
            f"{self._auth_base_url}{DEVICE_CODE_ENDPOINT}",
            data={
                "client_id": client_id,
                "response_type": "device_code",
                "scope": scopes,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            },
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        resp.raise_for_status()
        data = await resp.json()

        return DeviceCodeResponse(
            user_code=data["user_code"],
            device_code=data["device_code"],
            verification_uri=data["verification_uri"],
            interval=data.get("interval", 5),
            expires_in=data.get("expires_in", 600),
            code_verifier=code_verifier,
        )

    async def poll_for_tokens(
        self,
        client_id: str,
        device_code: str,
        code_verifier: str,
        interval: int = 5,
        timeout: int = 600,
    ) -> TokenResponse:
        """Poll for tokens after user has authorized (Step 2).

        Blocks until the user completes authorization or the timeout is reached.
        """
        elapsed = 0
        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval

            try:
                return await self.exchange_device_code(
                    client_id=client_id,
                    device_code=device_code,
                    code_verifier=code_verifier,
                )
            except AuthorizationPendingError:
                continue

        raise DeviceCodeExpiredError("Device code expired before user authorized")

    async def exchange_device_code(
        self,
        client_id: str,
        device_code: str,
        code_verifier: str,
    ) -> TokenResponse:
        """Exchange device code for tokens (single attempt).

        Raises AuthorizationPendingError if user hasn't authorized yet.
        """
        resp = await self._session.post(
            f"{self._auth_base_url}{TOKEN_ENDPOINT}",
            data={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": GRANT_TYPE_DEVICE_CODE,
                "code_verifier": code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        # BMW GCDM may return 403 while user hasn't authorized yet
        if resp.status == 403:
            raise AuthorizationPendingError("User has not yet authorized (403)")

        data = await resp.json()

        if resp.status == 400:
            error = data.get("error", "")
            if error == "authorization_pending":
                raise AuthorizationPendingError("User has not yet authorized")
            if error == "slow_down":
                raise AuthorizationPendingError("Slow down polling")
            if error == "expired_token":
                raise DeviceCodeExpiredError("Device code has expired")
            raise AuthenticationError(
                f"Token exchange failed: {data.get('error_description', error)}"
            )

        if resp.status != 200:
            resp.raise_for_status()

        return _parse_token_response(data)

    async def refresh_tokens(
        self, client_id: str, refresh_token: str
    ) -> TokenResponse:
        """Refresh the access token using a refresh token."""
        resp = await self._session.post(
            f"{self._auth_base_url}{TOKEN_ENDPOINT}",
            data={
                "client_id": client_id,
                "grant_type": GRANT_TYPE_REFRESH_TOKEN,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if resp.status == 401:
            raise TokenExpiredError("Refresh token is expired or revoked")

        resp.raise_for_status()
        data = await resp.json()
        return _parse_token_response(data)


def _parse_token_response(data: dict) -> TokenResponse:
    """Parse a token response from the API."""
    return TokenResponse(
        access_token=data["access_token"],
        token_type=data.get("token_type", "Bearer"),
        expires_in=data.get("expires_in", 3600),
        refresh_token=data["refresh_token"],
        scope=data.get("scope", ""),
        id_token=data.get("id_token", ""),
        gcid=data.get("gcid", ""),
    )
