"""Tests for internal HTTP proxy client propagation."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.browser.proxy_pool import ProxyPool, Proxy, ProxyType
from src.core.http.proxy import (
    set_http_proxy_pool,
    get_http_proxy_pool,
    httpx_proxy_kwargs,
    select_proxy_for_url,
)
from src.intelligence.network.sitemap import SitemapAnalyzer
from src.intelligence.network.graphql import GraphQLClient
from src.intelligence.network.api_discovery import APIDiscoveryEngine


@pytest.mark.asyncio
async def test_proxy_helpers_registration():
    """Test global registration of HTTP proxy pool and key helpers."""
    original_pool = get_http_proxy_pool()
    try:
        set_http_proxy_pool(None)
        assert get_http_proxy_pool() is None

        # Check default empty args
        args = await httpx_proxy_kwargs("https://example.com")
        assert args == {}

        # Set mock pool
        mock_pool = ProxyPool(proxies=["http://user:pass@1.2.3.4:5678"])
        set_http_proxy_pool(mock_pool)
        assert get_http_proxy_pool() == mock_pool

        # Check proxy selection
        proxy = await select_proxy_for_url("https://example.com")
        assert proxy is not None
        assert proxy.url == "http://1.2.3.4:5678"
        assert proxy.username == "user"
        assert proxy.password == "pass"

        # Check proxy kwargs generation
        args = await httpx_proxy_kwargs("https://example.com")
        assert "proxies" in args
        assert args["proxies"]["http://"] == "http://user:pass@1.2.3.4:5678"
        assert args["proxies"]["https://"] == "http://user:pass@1.2.3.4:5678"

    finally:
        set_http_proxy_pool(original_pool)


@pytest.mark.asyncio
async def test_sitemap_analyzer_uses_proxy():
    """Test SitemapAnalyzer propagates proxy kwargs to httpx.AsyncClient."""
    original_pool = get_http_proxy_pool()
    try:
        mock_pool = ProxyPool(proxies=["http://user:pass@1.2.3.4:5678"])
        set_http_proxy_pool(mock_pool)

        analyzer = SitemapAnalyzer()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<?xml version='1.0' encoding='UTF-8'?><urlset></urlset>"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get.return_value = mock_response

        # Mock httpx.AsyncClient to capture options passed to it
        with patch("httpx.AsyncClient", return_value=mock_client) as mock_async_client:
            await analyzer.analyze_sitemap("https://example.com/sitemap.xml")

            assert mock_async_client.called
            called_kwargs = mock_async_client.call_args[1]
            assert "proxies" in called_kwargs
            assert called_kwargs["proxies"]["http://"] == "http://user:pass@1.2.3.4:5678"

        # Test robots analyzer
        mock_robots_response = MagicMock()
        mock_robots_response.status_code = 200
        mock_robots_response.text = "User-agent: *\nDisallow: /"
        mock_client.get.return_value = mock_robots_response

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_async_client:
            await analyzer.analyze_robots("https://example.com")

            assert mock_async_client.called
            called_kwargs = mock_async_client.call_args[1]
            assert "proxies" in called_kwargs
            assert called_kwargs["proxies"]["http://"] == "http://user:pass@1.2.3.4:5678"

    finally:
        set_http_proxy_pool(original_pool)


@pytest.mark.asyncio
async def test_graphql_client_uses_proxy():
    """Test GraphQLClient query propagates proxy kwargs to httpx.AsyncClient."""
    original_pool = get_http_proxy_pool()
    try:
        mock_pool = ProxyPool(proxies=["http://user:pass@1.2.3.4:5678"])
        set_http_proxy_pool(mock_pool)

        client = GraphQLClient("https://example.com/graphql")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {}}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_async_client:
            await client.query("{ query }")

            assert mock_async_client.called
            called_kwargs = mock_async_client.call_args[1]
            assert "proxies" in called_kwargs
            assert called_kwargs["proxies"]["http://"] == "http://user:pass@1.2.3.4:5678"

    finally:
        set_http_proxy_pool(original_pool)


@pytest.mark.asyncio
async def test_api_discovery_uses_proxy():
    """Test APIDiscoveryEngine run_introspection propagates proxy kwargs to httpx.AsyncClient."""
    original_pool = get_http_proxy_pool()
    try:
        mock_pool = ProxyPool(proxies=["http://user:pass@1.2.3.4:5678"])
        set_http_proxy_pool(mock_pool)

        engine = APIDiscoveryEngine()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"__schema": {}}}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_async_client:
            await engine.run_introspection("https://example.com/graphql")

            assert mock_async_client.called
            called_kwargs = mock_async_client.call_args[1]
            assert "proxies" in called_kwargs
            assert called_kwargs["proxies"]["http://"] == "http://user:pass@1.2.3.4:5678"

    finally:
        set_http_proxy_pool(original_pool)
