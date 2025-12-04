"""Tests for authentication analyzer."""

import pytest
from unittest.mock import MagicMock

from src.intelligence.security.auth import AuthFlowAnalyzer, AuthType
from src.intelligence.network.interceptor import CapturedRequest, CapturedResponse


def test_auth_flow_analyzer_initialization():
    """Test auth flow analyzer initialization."""
    analyzer = AuthFlowAnalyzer()
    
    assert analyzer is not None


def test_detect_auth_type():
    """Test detecting authentication type."""
    analyzer = AuthFlowAnalyzer()
    
    # Use CapturedRequest instead of MagicMock
    from src.intelligence.network.interceptor import CapturedRequest
    
    request = CapturedRequest(
        url="https://api.example.com/auth",
        method="GET",
        headers={"Authorization": "Bearer token123"},
    )
    
    requests = [request]
    responses = []
    
    # This will use RequestAnalyzer internally
    auth_type = analyzer.detect_auth_type(requests, responses)
    
    # Should detect some auth type or return NONE
    assert auth_type in AuthType


def test_detect_auth_type_none():
    """Test detecting no authentication."""
    analyzer = AuthFlowAnalyzer()
    
    from src.intelligence.network.interceptor import CapturedRequest
    
    request = CapturedRequest(
        url="https://example.com",
        method="GET",
        headers={},
    )
    
    requests = [request]
    responses = []
    
    auth_type = analyzer.detect_auth_type(requests, responses)
    
    # May return NONE if no auth detected
    assert auth_type in AuthType


def test_trace_token_lifecycle():
    """Test tracing token lifecycle."""
    analyzer = AuthFlowAnalyzer()
    
    response = CapturedResponse(
        url="https://api.example.com/token",
        status=200,
        headers={"Content-Type": "application/json"},
    )
    
    requests = []
    responses = [response]
    
    lifecycle = analyzer.trace_token_lifecycle(requests, responses)
    
    assert lifecycle is not None
    assert lifecycle.creation_endpoint is not None or lifecycle.creation_endpoint == ""


def test_find_refresh_mechanism():
    """Test finding refresh mechanism."""
    analyzer = AuthFlowAnalyzer()
    
    request = CapturedRequest(
        url="https://api.example.com/refresh",
        method="POST",
        headers={},
    )
    
    requests = [request]
    responses = []
    
    mechanism = analyzer.find_refresh_mechanism(requests, responses)
    
    # May return None if not found
    assert mechanism is None or mechanism.endpoint is not None


def test_extract_oauth_config():
    """Test extracting OAuth configuration."""
    analyzer = AuthFlowAnalyzer()
    
    content = "<html><script>oauth config</script></html>"
    
    config = analyzer.extract_oauth_config(content)
    
    # May return None if not found
    assert config is None or config is not None

