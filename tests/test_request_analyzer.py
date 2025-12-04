"""Tests for request analyzer."""

import pytest
from unittest.mock import MagicMock

from src.intelligence.network.analyzer import RequestAnalyzer
from src.intelligence.network.interceptor import CapturedRequest


def test_request_analyzer_initialization():
    """Test request analyzer initialization."""
    analyzer = RequestAnalyzer()
    
    assert analyzer is not None


def test_analyze_request():
    """Test analyzing a request."""
    analyzer = RequestAnalyzer()
    
    request = CapturedRequest(
        url="https://api.example.com/data",
        method="GET",
        headers={"Authorization": "Bearer token123"},
    )
    
    analyzed = analyzer.analyze(request)
    
    assert analyzed is not None
    assert analyzed.url == request.url
    assert analyzed.method == request.method


def test_analyze_request_with_auth():
    """Test analyzing request with authentication."""
    analyzer = RequestAnalyzer()
    
    request = CapturedRequest(
        url="https://api.example.com/data",
        method="GET",
        headers={
            "Authorization": "Bearer token123",
            "Content-Type": "application/json",
        },
    )
    
    analyzed = analyzer.analyze(request)
    
    assert analyzed is not None
    # Should detect auth type
    assert analyzed.auth_type is not None


def test_analyze_request_no_auth():
    """Test analyzing request without authentication."""
    analyzer = RequestAnalyzer()
    
    request = CapturedRequest(
        url="https://example.com",
        method="GET",
        headers={},
    )
    
    analyzed = analyzer.analyze(request)
    
    assert analyzed is not None
    assert analyzed.url == request.url


