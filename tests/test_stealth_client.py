"""Tests for stealth HTTP client with TLS fingerprint impersonation."""

import pytest
from unittest.mock import MagicMock, patch

# Skip tests if curl_cffi is not available
curl_cffi_available = True
try:
    from src.core.http.stealth_client import (
        StealthHTTPClient,
        create_stealth_client,
        BROWSER_PROFILES,
    )
except ImportError:
    curl_cffi_available = False
    StealthHTTPClient = None
    create_stealth_client = None
    BROWSER_PROFILES = {}

pytestmark = pytest.mark.skipif(
    not curl_cffi_available,
    reason="curl_cffi not installed"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_session(status_code: int = 200, text: str = "ok") -> MagicMock:
    """Return a mock cffi Session with a pre-configured response."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = text
    mock_session.get.return_value = mock_response
    mock_session.post.return_value = mock_response
    mock_session.request.return_value = mock_response
    return mock_session


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def test_stealth_client_initialization():
    """Test stealth HTTP client initialization."""
    client = StealthHTTPClient()
    assert client is not None
    assert client.browser_profile == "chrome120"
    assert client.timeout == 30
    assert client.verify is True
    assert client.proxies is None


def test_stealth_client_custom_profile():
    """Test initialization with custom browser profile."""
    client = StealthHTTPClient(browser_profile="ff120")
    assert client.browser_profile == "ff120"


def test_stealth_client_invalid_profile_fallback():
    """Test fallback when invalid profile specified."""
    client = StealthHTTPClient(browser_profile="invalid_profile")
    assert client.browser_profile == "chrome120"


def test_stealth_client_with_timeout():
    client = StealthHTTPClient(timeout=60)
    assert client.timeout == 60


def test_stealth_client_with_proxies():
    proxies = {"http": "http://proxy:8080", "https": "http://proxy:8080"}
    client = StealthHTTPClient(proxies=proxies)
    assert client.proxies == proxies


def test_stealth_client_verify_disabled():
    client = StealthHTTPClient(verify=False)
    assert client.verify is False


def test_browser_profiles_exist():
    assert "chrome" in BROWSER_PROFILES
    assert "firefox" in BROWSER_PROFILES
    assert "safari" in BROWSER_PROFILES
    assert "edge" in BROWSER_PROFILES


# ---------------------------------------------------------------------------
# GET requests
# ---------------------------------------------------------------------------

def test_get_request():
    """Test GET request with stealth headers."""
    client = StealthHTTPClient()
    client._session = _make_mock_session(200, "Success")

    response = client.get("https://example.com")

    assert response.status_code == 200
    client._session.get.assert_called_once()

    call_kwargs = client._session.get.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert "User-Agent" in headers
    assert "Accept" in headers
    assert "Accept-Language" in headers


def test_get_request_custom_headers():
    """Test GET with custom headers merged into defaults."""
    client = StealthHTTPClient()
    client._session = _make_mock_session()

    client.get("https://example.com", headers={"X-Custom-Header": "test"})

    call_kwargs = client._session.get.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert headers.get("X-Custom-Header") == "test"
    # Default headers should also be present
    assert "User-Agent" in headers


def test_get_sets_sec_fetch_headers():
    """Test that GET sets Sec-Fetch-* headers."""
    client = StealthHTTPClient()
    client._session = _make_mock_session()

    client.get("https://example.com")

    call_kwargs = client._session.get.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert "Sec-Fetch-Dest" in headers
    assert "Sec-Fetch-Mode" in headers
    assert "Sec-Fetch-Site" in headers


def test_timeout_passed_to_get():
    """Test that timeout is forwarded."""
    client = StealthHTTPClient(timeout=45)
    client._session = _make_mock_session()

    client.get("https://example.com")

    call_kwargs = client._session.get.call_args[1]
    assert call_kwargs.get("timeout") == 45


def test_verify_passed_to_get():
    """Test that verify is forwarded."""
    client = StealthHTTPClient(verify=False)
    client._session = _make_mock_session()

    client.get("https://example.com")

    call_kwargs = client._session.get.call_args[1]
    assert call_kwargs.get("verify") is False


# ---------------------------------------------------------------------------
# POST requests
# ---------------------------------------------------------------------------

def test_post_request():
    """Test POST request with stealth headers."""
    client = StealthHTTPClient()
    client._session = _make_mock_session(201)

    response = client.post("https://example.com/api", json={"key": "value"})

    assert response.status_code == 201
    client._session.post.assert_called_once()


def test_post_request_form_data():
    """Test POST with form data forwarded."""
    client = StealthHTTPClient()
    client._session = _make_mock_session()

    client.post("https://example.com/form", data={"field": "value"})

    call_kwargs = client._session.post.call_args[1]
    assert call_kwargs.get("data") == {"field": "value"}


def test_post_sets_content_type_json():
    """Test that POST sets Content-Type: application/json for JSON payloads."""
    client = StealthHTTPClient()
    client._session = _make_mock_session()

    client.post("https://example.com/api", json={"key": "val"})

    call_kwargs = client._session.post.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert headers.get("Content-Type") == "application/json"


def test_post_sets_content_type_form():
    """Test that POST sets form content-type for form data."""
    client = StealthHTTPClient()
    client._session = _make_mock_session()

    client.post("https://example.com/form", data={"k": "v"})

    call_kwargs = client._session.post.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert "application/x-www-form-urlencoded" in headers.get("Content-Type", "")


# ---------------------------------------------------------------------------
# Custom request method
# ---------------------------------------------------------------------------

def test_custom_request_put():
    """Test custom PUT request."""
    client = StealthHTTPClient()
    client._session = _make_mock_session()

    client.request("PUT", "https://example.com/api")

    client._session.request.assert_called_once()
    call_args = client._session.request.call_args[0]
    assert call_args[0] == "PUT"


def test_custom_request_delete():
    """Test custom DELETE request."""
    client = StealthHTTPClient()
    client._session = _make_mock_session()

    client.request("DELETE", "https://example.com/api/1")

    client._session.request.assert_called_once()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def test_create_stealth_client_chrome():
    client = create_stealth_client(browser="chrome")
    assert client.browser_profile == "chrome120"


def test_create_stealth_client_chrome_version():
    client = create_stealth_client(browser="chrome", version="110")
    assert client.browser_profile == "chrome110"


def test_create_stealth_client_firefox():
    client = create_stealth_client(browser="firefox")
    assert client.browser_profile == "ff120"


def test_create_stealth_client_safari():
    client = create_stealth_client(browser="safari")
    assert client.browser_profile == "safari17_0"


def test_create_stealth_client_edge():
    client = create_stealth_client(browser="edge")
    assert client.browser_profile == "edge120"


def test_create_stealth_client_with_proxies():
    proxies = {"http": "http://proxy:8080"}
    client = create_stealth_client(proxies=proxies)
    assert client.proxies == proxies


def test_create_stealth_client_unknown_browser():
    client = create_stealth_client(browser="unknown")
    assert client.browser_profile == "chrome120"


def test_create_stealth_client_invalid_version():
    client = create_stealth_client(browser="chrome", version="999")
    assert client.browser_profile == "chrome120"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

def test_stealth_client_context_manager():
    """Test that close() is called via context manager."""
    with StealthHTTPClient() as client:
        assert client is not None
    # If __exit__ worked without error, we're good


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------

def test_get_raises_http_request_error_on_failure():
    """HTTPRequestError raised when session throws."""
    from src.exceptions import HTTPRequestError

    client = StealthHTTPClient()
    client._session = MagicMock()
    client._session.get.side_effect = RuntimeError("network down")

    with pytest.raises(HTTPRequestError):
        client.get("https://example.com")


def test_post_raises_http_request_error_on_failure():
    from src.exceptions import HTTPRequestError

    client = StealthHTTPClient()
    client._session = MagicMock()
    client._session.post.side_effect = RuntimeError("timeout")

    with pytest.raises(HTTPRequestError):
        client.post("https://example.com")
