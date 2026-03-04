"""Tests for shared GitHub authentication service."""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import jwt
import pytest

from shared.exceptions import AuthenticationError
from shared.github_auth import GitHubAuthService


@pytest.fixture
def valid_private_key():
    """Valid RSA private key for testing."""
    return """-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAzcRm9FGmkeQCtDc6Rp8d1OfZJu7jcz/njGzkhNH/MbHT1R9J
kY8SlwjDkG+eHdvkSQbox0rS893JiJpRRbVdGdLLIRckYnfyd0zGML533zrgCkLq
IqJeM8cjJ0HQIX53DIvzos85eEm6IVlzl4NvTkSIU3gGnFAHxV7WcNpHUyQTmcXr
BRQ/doJ/I+kJSPA8NqW69UE/dOm8BgyYadG2k4mt1uq1h0g1EFavHrxtkBP225Gk
3NmI8Hv77SOl3SB33NMyP1gTswJecHjLOqAHFjBPDsk/XXcA1MKr8Zz2kxtuulUM
wt/uyGxpnym5zk0DlrXT4bUlHeYvp6AFufMH6QIDAQABAoIBAC+ow33oYY/eA4BR
YGaWGTdEgigB4d3CWfPNDvrylsygVyPAbO5ReKlR5tYP/EwHL+94MbdjTcwdPT4u
HA/sy4UdLV5bOVqzVI4sUqVcoHAsd1L5H7jo6a/Neodvt3DilVlrGwHFRJbnYLyz
ttHLqB61QewvWzyeTsZ4ymt2K1oGkQC+n9t8xBnYx6TSChpSxj/0n8WNGNi7vcZ9
bOcJGzwWZmMwysrtFvkhQM2AsmB8SJ5HipBs9X/Z5hQ3YTm4f9ICcHpGbQ6+X6fM
ixT7PeFdhvw+TYVp9O1j5ml/6w948TKmZFGdX+KMqq/BnlI/cv4tz+jEUBuSvivm
z/zZvJkCgYEA96xSLnPKlHRh95IXg7Z6A8wDilAxR+pkGEuVVKwW5qxOkx8hK7cT
XsYZswk/3mo6sADYR+5Pzlyuq4zdyCh5qj6MBgHClcMIikDrfu0NxjN6KCw4zLfk
3Rnz7JTh0usXOxfvnXv5C91omE+5BCUJ53OWpGjjRaVB2Fr9GvXtp5UCgYEA1K9n
dzemJRl4VADt7pEJ7hBgAAU8hGYxk5oICMhC/cFov9+2NiSiQgcC2CHXDthtjQCv
JULwEOUVeK5dxd+6orScczzrXt6W4mzaMgKio9aaqAGVEHkKIrqVNT2kveMgrv2i
MNoCv0RbB7wHJIzBiIAIl+53G8Gvpzgt+mE7OgUCgYAPzPGNPxvcbrRVS/+uCnUs
Staq+0S5ls1980x6k2P+oV196019cXeN40t+bYeik9pcoiEqLZzvyF/oV9tKSrLA
Vq8uLuyQC1o/H7cmaM8pJt2TNIcHIHA8Xsx9+l2RzCe2QGer/127EQv8M5HVHtvL
5UbmBD8DkXBq8hsVnjzkJQKBgQCgTaR6YuNDSzM6fYjYK1GEsarp2QiH8k6jpZEw
rWBwynodRIydunbhtU8bgEYL1mybvkxElXNECKZqU2IyZjLRt7fD08LDupmXB9xd
nUbgnjvrLWYhCFnvWxpjCpdE2BAmVN0OXQN9DhRefAYWMlEchQP1H7N+pDm0m89r
zCVL0QKBgH7Pxj3uPlij1wI05iQ9wCFE75vsV3/Aij84XRsIV1+BNjDV0hlbSetK
D/nPt/drlmGjI0UicDiYBjl9BpdIDJQjYnWkfAXoCBU1JHhBNuPTv5ROOcvQZX0b
MnrxRgG+Eb8wMMcZMowTNgOeaUZnZKw36JznpI3aQ4suV8jS88gU
-----END RSA PRIVATE KEY-----"""


@pytest.fixture
def mock_http_client():
    """Mock HTTP client."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def auth_service(valid_private_key, mock_http_client):
    """Create auth service instance."""
    return GitHubAuthService(
        app_id="123456",
        private_key=valid_private_key,
        installation_id="789012",
        http_client=mock_http_client,
    )


class TestGitHubAuthService:
    """Test GitHubAuthService class."""

    def test_init(self, auth_service):
        """Test initialization."""
        assert auth_service._app_id == "123456"
        assert auth_service._installation_id == "789012"
        assert auth_service._token is None
        assert auth_service._expires_at == 0

    def test_is_configured_valid(self, auth_service):
        """Test is_configured with valid credentials."""
        assert auth_service.is_configured() is True

    def test_is_configured_missing_credentials(self, mock_http_client):
        """Test is_configured with missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            service = GitHubAuthService(
                app_id="",
                private_key="",
                installation_id="",
                http_client=mock_http_client,
            )
            assert service.is_configured() is False

    def test_is_configured_partial_credentials(self, mock_http_client):
        """Test is_configured with partial credentials."""
        with patch.dict(os.environ, {}, clear=True):
            service = GitHubAuthService(
                app_id="123",
                private_key="",
                installation_id="456",
                http_client=mock_http_client,
            )
            # Missing private key
            assert service.is_configured() is False

    def test_validate_private_key_invalid_empty(self, mock_http_client):
        """Test private key validation with empty key."""
        with patch.dict(os.environ, {}, clear=True):
            service = GitHubAuthService(
                app_id="123",
                private_key="",
                installation_id="456",
                http_client=mock_http_client,
            )
            assert service._validate_private_key() is False

    def test_validate_private_key_invalid_format(self, mock_http_client):
        """Test private key validation with invalid format."""
        with patch.dict(os.environ, {}, clear=True):
            service = GitHubAuthService(
                app_id="123",
                private_key="not a valid key",
                installation_id="456",
                http_client=mock_http_client,
            )
            assert service._validate_private_key() is False

    def test_validate_private_key_missing_markers(self, mock_http_client):
        """Test private key validation with missing BEGIN/END markers."""
        with patch.dict(os.environ, {}, clear=True):
            service = GitHubAuthService(
                app_id="123",
                private_key="RSA PRIVATE KEY without markers",
                installation_id="456",
                http_client=mock_http_client,
            )
            assert service._validate_private_key() is False

    @pytest.mark.asyncio
    async def test_get_token_success(self, auth_service, mock_http_client):
        """Test successful token retrieval."""
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"token": "ghs_test_token"}
        mock_http_client.post = AsyncMock(return_value=mock_response)

        token = await auth_service.get_token()

        assert token == "ghs_test_token"
        assert auth_service._token == "ghs_test_token"
        assert auth_service._expires_at > time.time()
        mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_token_cached(self, auth_service):
        """Test token caching."""
        # Set a valid cached token
        auth_service._token = "cached_token"
        auth_service._expires_at = time.time() + 300  # 5 minutes from now

        token = await auth_service.get_token()

        assert token == "cached_token"
        # HTTP client should not be called for cached token
        auth_service._http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_token_refresh_expired(self, auth_service, mock_http_client):
        """Test token refresh when expired."""
        # Set an expired token
        auth_service._token = "old_token"
        auth_service._expires_at = time.time() - 100  # Expired

        # Mock successful refresh
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"token": "new_token"}
        mock_http_client.post = AsyncMock(return_value=mock_response)

        token = await auth_service.get_token()

        assert token == "new_token"
        assert auth_service._token == "new_token"
        mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_token_invalid_private_key(self, mock_http_client):
        """Test getting token with invalid private key."""
        service = GitHubAuthService(
            app_id="123",
            private_key="invalid",
            installation_id="456",
            http_client=mock_http_client,
        )

        with pytest.raises(AuthenticationError, match="GitHub App credentials"):
            await service.get_token()

    @pytest.mark.asyncio
    async def test_get_token_api_error(self, auth_service, mock_http_client):
        """Test handling of API errors."""
        # Mock API error response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_http_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(Exception):  # noqa: B017 - Will raise GitHubAPIError
            await auth_service.get_token()

    @pytest.mark.asyncio
    async def test_context_manager(self, valid_private_key):
        """Test async context manager."""
        async with GitHubAuthService(
            app_id="123",
            private_key=valid_private_key,
            installation_id="456",
        ) as service:
            assert service._http_client is not None
            assert service._owns_client is True

    def test_jwt_generation(self, auth_service):
        """Test JWT token generation."""
        # This is tested indirectly through _refresh_token
        # Just verify the private key is valid for JWT
        now = int(time.time())
        payload = {"iat": now, "exp": now + 600, "iss": auth_service._app_id}

        # Should not raise an exception
        jwt_token = jwt.encode(payload, auth_service._private_key, algorithm="RS256")
        assert jwt_token is not None
