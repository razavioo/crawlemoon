"""Tests for stealth HTTP client with TLS fingerprint impersonation."""

import pytest
from unittest.mock import MagicMock, patch
import sys

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
    
    # Should fallback to chrome120
    assert client.browser_profile == "chrome120"


def test_stealth_client_with_timeout():
    """Test initialization with custom timeout."""
    client = StealthHTTPClient(timeout=60)
    
    assert client.timeout == 60


def test_stealth_client_with_proxies():
    """Test initialization with proxy configuration."""
    proxies = {"http": "http://proxy:8080", "https": "http://proxy:8080"}
    client = StealthHTTPClient(proxies=proxies)
    
    assert client.proxies == proxies


def test_stealth_client_verify_disabled():
    """Test initialization with SSL verification disabled."""
    client = StealthHTTPClient(verify=False)
    
    assert client.verify is False


def test_browser_profiles_exist():
    """Test that browser profiles are defined."""
    assert "chrome" in BROWSER_PROFILES
    assert "firefox" in BROWSER_PROFILES
    assert "safari" in BROWSER_PROFILES
    assert "edge" in BROWSER_PROFILES


@patch("src.core.http.stealth_client.requests")
def test_get_request(mock_requests):
    """Test GET request with stealth headers."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "Success"
    mock_requests.get.return_value = mock_response
    
    client = StealthHTTPClient()
    response = client.get("https://example.com")
    
    assert response.status_code == 200
    mock_requests.get.assert_called_once()
    
    # Check stealth headers were set
    call_kwargs = mock_requests.get.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert "User-Agent" in headers
    assert "Accept" in headers
    assert "Accept-Language" in headers


@patch("src.core.http.stealth_client.requests")
def test_get_request_custom_headers(mock_requests):
    """Test GET with custom headers."""
    mock_response = MagicMock()
    mock_requests.get.return_value = mock_response
    
    client = StealthHTTPClient()
    custom_headers = {"X-Custom-Header": "test"}
    client.get("https://example.com", headers=custom_headers)
    
    call_kwargs = mock_requests.get.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert headers["X-Custom-Header"] == "test"


@patch("src.core.http.stealth_client.requests")
def test_post_request(mock_requests):
    """Test POST request with stealth headers."""
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_requests.post.return_value = mock_response
    
    client = StealthHTTPClient()
    response = client.post("https://example.com/api", json={"key": "value"})
    
    assert response.status_code == 201
    mock_requests.post.assert_called_once()


@patch("src.core.http.stealth_client.requests")
def test_post_request_form_data(mock_requests):
    """Test POST with form data."""
    mock_response = MagicMock()
    mock_requests.post.return_value = mock_response
    
    client = StealthHTTPClient()
    client.post("https://example.com/form", data={"field": "value"})
    
    call_kwargs = mock_requests.post.call_args[1]
    assert call_kwargs.get("data") == {"field": "value"}


@patch("src.core.http.stealth_client.requests")
def test_custom_request_put(mock_requests):
    """Test custom PUT request."""
    mock_response = MagicMock()
    mock_requests.request.return_value = mock_response
    
    client = StealthHTTPClient()
    response = client.request("PUT", "https://example.com/api", json={"key": "value"})
    
    mock_requests.request.assert_called_once()
    call_args = mock_requests.request.call_args
    assert call_args[0][0] == "PUT"


@patch("src.core.http.stealth_client.requests")
def test_custom_request_delete(mock_requests):
    """Test custom DELETE request."""
    mock_response = MagicMock()
    mock_requests.request.return_value = mock_response
    
    client = StealthHTTPClient()
    response = client.request("DELETE", "https://example.com/api/1")
    
    mock_requests.request.assert_called_once()


def test_create_stealth_client_chrome():
    """Test creating client with chrome profile."""
    client = create_stealth_client(browser="chrome")
    
    assert client.browser_profile == "chrome120"


def test_create_stealth_client_chrome_version():
    """Test creating client with specific chrome version."""
    client = create_stealth_client(browser="chrome", version="110")
    
    assert client.browser_profile == "chrome110"


def test_create_stealth_client_firefox():
    """Test creating client with firefox profile."""
    client = create_stealth_client(browser="firefox")
    
    assert client.browser_profile == "ff120"


def test_create_stealth_client_safari():
    """Test creating client with safari profile."""
    client = create_stealth_client(browser="safari")
    
    assert client.browser_profile == "safari17_0"


def test_create_stealth_client_edge():
    """Test creating client with edge profile."""
    client = create_stealth_client(browser="edge")
    
    assert client.browser_profile == "edge120"


def test_create_stealth_client_with_proxies():
    """Test creating client with proxies."""
    proxies = {"http": "http://proxy:8080"}
    client = create_stealth_client(proxies=proxies)
    
    assert client.proxies == proxies


def test_create_stealth_client_unknown_browser():
    """Test creating client with unknown browser type."""
    client = create_stealth_client(browser="unknown")
    
    # Should fallback to chrome120
    assert client.browser_profile == "chrome120"


def test_create_stealth_client_invalid_version():
    """Test creating client with invalid version."""
    client = create_stealth_client(browser="chrome", version="999")
    
    # Should fallback to chrome120
    assert client.browser_profile == "chrome120"


@patch("src.core.http.stealth_client.requests")
def test_impersonate_parameter_passed(mock_requests):
    """Test that impersonate parameter is passed to requests."""
    mock_response = MagicMock()
    mock_requests.get.return_value = mock_response
    
    client = StealthHTTPClient(browser_profile="edge120")
    client.get("https://example.com")
    
    call_kwargs = mock_requests.get.call_args[1]
    assert call_kwargs.get("impersonate") == "edge120"


@patch("src.core.http.stealth_client.requests")
def test_timeout_passed(mock_requests):
    """Test that timeout is passed to requests."""
    mock_response = MagicMock()
    mock_requests.get.return_value = mock_response
    
    client = StealthHTTPClient(timeout=45)
    client.get("https://example.com")
    
    call_kwargs = mock_requests.get.call_args[1]
    assert call_kwargs.get("timeout") == 45


@patch("src.core.http.stealth_client.requests")
def test_verify_passed(mock_requests):
    """Test that verify is passed to requests."""
    mock_response = MagicMock()
    mock_requests.get.return_value = mock_response
    
    client = StealthHTTPClient(verify=False)
    client.get("https://example.com")
    
    call_kwargs = mock_requests.get.call_args[1]
    assert call_kwargs.get("verify") is False


@patch("src.core.http.stealth_client.requests")
def test_post_sets_origin_header(mock_requests):
    """Test that POST sets Origin header."""
    mock_response = MagicMock()
    mock_requests.post.return_value = mock_response
    
    client = StealthHTTPClient()
    client.post("https://example.com/api")
    
    call_kwargs = mock_requests.post.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert "Origin" in headers


@patch("src.core.http.stealth_client.requests")
def test_post_sets_referer_header(mock_requests):
    """Test that POST sets Referer header."""
    mock_response = MagicMock()
    mock_requests.post.return_value = mock_response
    
    client = StealthHTTPClient()
    client.post("https://example.com/api")
    
    call_kwargs = mock_requests.post.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert "Referer" in headers


@patch("src.core.http.stealth_client.requests")
def test_get_sets_sec_fetch_headers(mock_requests):
    """Test that GET sets Sec-Fetch headers."""
    mock_response = MagicMock()
    mock_requests.get.return_value = mock_response
    
    client = StealthHTTPClient()
    client.get("https://example.com")
    
    call_kwargs = mock_requests.get.call_args[1]
    headers = call_kwargs.get("headers", {})
    assert "Sec-Fetch-Dest" in headers
    assert "Sec-Fetch-Mode" in headers
    assert "Sec-Fetch-Site" in headers

