"""Tests for BMW CarData auth module."""

from __future__ import annotations

import base64
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientSession

from bmw_cardata.auth import (
    AbstractAuth,
    DeviceAuth,
    _generate_code_challenge,
    _generate_code_verifier,
)
from bmw_cardata.exceptions import (
    AuthenticationError,
    AuthorizationPendingError,
    DeviceCodeExpiredError,
    TokenExpiredError,
)

from .conftest import (
    SAMPLE_DEVICE_CODE_RESPONSE,
    SAMPLE_TOKEN_RESPONSE,
    MockAuth,
    make_mock_response,
)


class TestPKCE:
    """Tests for PKCE helper functions."""

    def test_code_verifier_length(self) -> None:
        """Code verifier should be 43-128 characters."""
        verifier = _generate_code_verifier()
        assert 43 <= len(verifier) <= 128

    def test_code_verifier_randomness(self) -> None:
        """Two verifiers should not be equal."""
        v1 = _generate_code_verifier()
        v2 = _generate_code_verifier()
        assert v1 != v2

    def test_code_verifier_url_safe(self) -> None:
        """Code verifier should only contain URL-safe characters."""
        verifier = _generate_code_verifier()
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed for c in verifier)

    def test_code_challenge_s256(self) -> None:
        """Code challenge should be SHA256 of the verifier (base64url no padding)."""
        verifier = "test-verifier-string"
        expected_digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
        assert _generate_code_challenge(verifier) == expected

    def test_code_challenge_no_padding(self) -> None:
        """Code challenge should have no base64 padding."""
        challenge = _generate_code_challenge("any-string")
        assert "=" not in challenge


class TestAbstractAuth:
    """Tests for AbstractAuth base class."""

    @pytest.mark.asyncio
    async def test_request_adds_auth_header(self) -> None:
        """Request method should add Authorization header."""
        session = AsyncMock()
        mock_resp = make_mock_response(200, {"ok": True})
        session.request.return_value = mock_resp

        auth = MockAuth(session)
        auth.host = "https://api.example.com"

        await auth.request("GET", "/test")

        session.request.assert_called_once()
        call_kwargs = session.request.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["Authorization"] == "Bearer test-access-token"
        assert headers["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_request_prepends_host(self) -> None:
        """Request should prepend host to URL."""
        session = AsyncMock()
        session.request.return_value = make_mock_response(200)

        auth = MockAuth(session)
        auth.host = "https://api.example.com"

        await auth.request("GET", "/test/path")

        args = session.request.call_args[0]
        assert args[1] == "https://api.example.com/test/path"


class TestDeviceAuth:
    """Tests for DeviceAuth class."""

    @pytest.mark.asyncio
    async def test_request_device_code(self) -> None:
        """Test requesting a device code."""
        session = AsyncMock()
        mock_resp = make_mock_response(200, SAMPLE_DEVICE_CODE_RESPONSE)
        session.post.return_value = mock_resp

        device_auth = DeviceAuth(session, auth_base_url="https://auth.test.com")
        result = await device_auth.request_device_code("test-client-id")

        assert result.user_code == "AB12-CD34"
        assert result.device_code == "dev-code-xyz"
        assert result.verification_uri == "https://customer.bmwgroup.com/verify"
        assert result.interval == 5
        assert result.expires_in == 600
        assert result.code_verifier  # Should be set
        assert len(result.code_verifier) > 0

        # Verify the request was made correctly
        session.post.assert_called_once()
        call_args = session.post.call_args
        assert "test-client-id" in str(call_args)

    @pytest.mark.asyncio
    async def test_exchange_device_code_success(self) -> None:
        """Test successful device code exchange."""
        session = AsyncMock()
        mock_resp = make_mock_response(200, SAMPLE_TOKEN_RESPONSE)
        session.post.return_value = mock_resp

        device_auth = DeviceAuth(session)
        result = await device_auth.exchange_device_code(
            client_id="test-client",
            device_code="dev-code",
            code_verifier="verifier",
        )

        assert result.access_token == "eyJ-access-token"
        assert result.refresh_token == "refresh-token-abc"
        assert result.id_token == "eyJ-id-token"
        assert result.gcid == "gcid-12345-abcde"
        assert result.expires_in == 3600

    @pytest.mark.asyncio
    async def test_exchange_device_code_authorization_pending(self) -> None:
        """Test device code exchange when user hasn't authorized yet."""
        session = AsyncMock()
        mock_resp = make_mock_response(400, {"error": "authorization_pending"})
        session.post.return_value = mock_resp

        device_auth = DeviceAuth(session)
        with pytest.raises(AuthorizationPendingError):
            await device_auth.exchange_device_code(
                client_id="test-client",
                device_code="dev-code",
                code_verifier="verifier",
            )

    @pytest.mark.asyncio
    async def test_exchange_device_code_slow_down(self) -> None:
        """Test device code exchange with slow_down response."""
        session = AsyncMock()
        mock_resp = make_mock_response(400, {"error": "slow_down"})
        session.post.return_value = mock_resp

        device_auth = DeviceAuth(session)
        with pytest.raises(AuthorizationPendingError):
            await device_auth.exchange_device_code(
                client_id="test-client",
                device_code="dev-code",
                code_verifier="verifier",
            )

    @pytest.mark.asyncio
    async def test_exchange_device_code_expired(self) -> None:
        """Test device code exchange when code has expired."""
        session = AsyncMock()
        mock_resp = make_mock_response(400, {"error": "expired_token"})
        session.post.return_value = mock_resp

        device_auth = DeviceAuth(session)
        with pytest.raises(DeviceCodeExpiredError):
            await device_auth.exchange_device_code(
                client_id="test-client",
                device_code="dev-code",
                code_verifier="verifier",
            )

    @pytest.mark.asyncio
    async def test_exchange_device_code_generic_error(self) -> None:
        """Test device code exchange with generic error."""
        session = AsyncMock()
        mock_resp = make_mock_response(
            400, {"error": "invalid_grant", "error_description": "Some error"}
        )
        session.post.return_value = mock_resp

        device_auth = DeviceAuth(session)
        with pytest.raises(AuthenticationError, match="Some error"):
            await device_auth.exchange_device_code(
                client_id="test-client",
                device_code="dev-code",
                code_verifier="verifier",
            )

    @pytest.mark.asyncio
    async def test_refresh_tokens_success(self) -> None:
        """Test successful token refresh."""
        session = AsyncMock()
        mock_resp = make_mock_response(200, SAMPLE_TOKEN_RESPONSE)
        session.post.return_value = mock_resp

        device_auth = DeviceAuth(session)
        result = await device_auth.refresh_tokens("client-id", "old-refresh-token")

        assert result.access_token == "eyJ-access-token"
        assert result.refresh_token == "refresh-token-abc"

    @pytest.mark.asyncio
    async def test_refresh_tokens_expired(self) -> None:
        """Test token refresh with expired refresh token."""
        session = AsyncMock()
        mock_resp = make_mock_response(401)
        session.post.return_value = mock_resp

        device_auth = DeviceAuth(session)
        with pytest.raises(TokenExpiredError):
            await device_auth.refresh_tokens("client-id", "expired-refresh-token")

    @pytest.mark.asyncio
    async def test_poll_for_tokens_success(self) -> None:
        """Test polling for tokens completes after user authorizes."""
        session = AsyncMock()

        # First two calls: authorization_pending, third: success
        pending_resp = make_mock_response(400, {"error": "authorization_pending"})
        success_resp = make_mock_response(200, SAMPLE_TOKEN_RESPONSE)
        session.post.side_effect = [pending_resp, pending_resp, success_resp]

        device_auth = DeviceAuth(session)
        result = await device_auth.poll_for_tokens(
            client_id="client",
            device_code="code",
            code_verifier="verifier",
            interval=0,  # No wait in tests
            timeout=10,
        )

        assert result.access_token == "eyJ-access-token"
        assert session.post.call_count == 3

    @pytest.mark.asyncio
    async def test_poll_for_tokens_timeout(self) -> None:
        """Test polling for tokens times out."""
        session = AsyncMock()
        pending_resp = make_mock_response(400, {"error": "authorization_pending"})
        session.post.return_value = pending_resp

        device_auth = DeviceAuth(session)
        with pytest.raises(DeviceCodeExpiredError, match="expired"):
            await device_auth.poll_for_tokens(
                client_id="client",
                device_code="code",
                code_verifier="verifier",
                interval=0,
                timeout=0,  # Immediate timeout
            )
