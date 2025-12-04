"""Tests for network interceptor."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.intelligence.network.interceptor import (
    DeepNetworkInterceptor,
    CapturedRequest,
    CapturedResponse,
    WebSocketMessage,
    WebSocketSession,
)


def test_interceptor_initialization():
    """Test network interceptor initialization."""
    interceptor = DeepNetworkInterceptor()
    
    assert len(interceptor.requests) == 0
    assert len(interceptor.responses) == 0
    assert len(interceptor.websockets) == 0
    assert interceptor._enabled is False


@pytest.mark.asyncio
async def test_start_intercepting():
    """Test starting network interception."""
    interceptor = DeepNetworkInterceptor()
    page = AsyncMock()
    page.on = MagicMock()
    page.context = MagicMock()
    page.context.on = MagicMock()
    
    await interceptor.start_intercepting(page)
    
    assert interceptor._enabled is True
    assert page.on.call_count >= 3  # request, response, websocket


@pytest.mark.asyncio
async def test_start_intercepting_no_double_enable():
    """Test starting interception doesn't enable twice."""
    interceptor = DeepNetworkInterceptor()
    page = AsyncMock()
    page.on = MagicMock()
    page.context = MagicMock()
    page.context.on = MagicMock()
    
    await interceptor.start_intercepting(page)
    call_count = page.on.call_count
    
    await interceptor.start_intercepting(page)
    
    # Should not call again
    assert page.on.call_count == call_count


@pytest.mark.asyncio
async def test_capture_all_requests():
    """Test capturing all requests."""
    interceptor = DeepNetworkInterceptor()
    
    # Add some mock requests
    request1 = CapturedRequest(
        url="https://example.com",
        method="GET",
        headers={},
    )
    request2 = CapturedRequest(
        url="https://api.example.com",
        method="POST",
        headers={},
    )
    
    interceptor.requests = [request1, request2]
    
    captured = await interceptor.capture_all_requests()
    
    assert len(captured) == 2
    assert captured[0].url == "https://example.com"
    assert captured[1].url == "https://api.example.com"


@pytest.mark.asyncio
async def test_capture_all_responses():
    """Test capturing all responses."""
    interceptor = DeepNetworkInterceptor()
    
    response1 = CapturedResponse(
        url="https://example.com",
        status=200,
        headers={},
    )
    response2 = CapturedResponse(
        url="https://api.example.com",
        status=404,
        headers={},
    )
    
    interceptor.responses = [response1, response2]
    
    captured = await interceptor.capture_all_responses()
    
    assert len(captured) == 2
    assert captured[0].status == 200
    assert captured[1].status == 404


def test_captured_request_creation():
    """Test captured request creation."""
    request = CapturedRequest(
        url="https://example.com",
        method="GET",
        headers={"User-Agent": "test"},
        post_data="data",
    )
    
    assert request.url == "https://example.com"
    assert request.method == "GET"
    assert request.headers["User-Agent"] == "test"
    assert request.post_data == "data"
    assert isinstance(request.timestamp, datetime)


def test_captured_response_creation():
    """Test captured response creation."""
    response = CapturedResponse(
        url="https://example.com",
        status=200,
        headers={"Content-Type": "application/json"},
        body=b"response body",
    )
    
    assert response.url == "https://example.com"
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json"
    assert response.body == b"response body"


def test_websocket_message_creation():
    """Test WebSocket message creation."""
    message = WebSocketMessage(
        url="ws://example.com",
        direction="sent",
        message="test message",
        message_type="text",
    )
    
    assert message.url == "ws://example.com"
    assert message.direction == "sent"
    assert message.message == "test message"
    assert message.message_type == "text"


def test_websocket_session_creation():
    """Test WebSocket session creation."""
    session = WebSocketSession(
        url="ws://example.com",
    )
    
    assert session.url == "ws://example.com"
    assert len(session.messages) == 0
    assert session.closed_at is None
    assert isinstance(session.opened_at, datetime)


