"""Tests for MCP utilities."""

import pytest
from src.mcp.utils import validate_url, validate_arguments


def test_validate_url_valid():
    """Test URL validation with valid URLs."""
    assert validate_url("https://example.com") is True
    assert validate_url("http://example.com") is True
    assert validate_url("https://example.com/path?query=1") is True
    assert validate_url("http://localhost:8000") is True


def test_validate_url_invalid():
    """Test URL validation with invalid URLs."""
    assert validate_url("not-a-url") is False
    assert validate_url("") is False
    assert validate_url("example.com") is False  # Missing scheme
    assert validate_url("https://") is False  # Missing netloc


def test_validate_arguments_success():
    """Test argument validation with valid arguments."""
    arguments = {
        "url": "https://example.com",
        "depth": "full",
    }
    required = ["url"]
    
    is_valid, error = validate_arguments(arguments, required)
    assert is_valid is True
    assert error is None


def test_validate_arguments_missing_required():
    """Test argument validation with missing required field."""
    arguments = {
        "depth": "full",
    }
    required = ["url"]
    
    is_valid, error = validate_arguments(arguments, required)
    assert is_valid is False
    assert "Missing required argument" in error


def test_validate_arguments_none_value():
    """Test argument validation with None value."""
    arguments = {
        "url": None,
    }
    required = ["url"]
    
    is_valid, error = validate_arguments(arguments, required)
    assert is_valid is False
    assert "cannot be None" in error


def test_validate_arguments_invalid_url():
    """Test argument validation with invalid URL."""
    arguments = {
        "url": "not-a-url",
    }
    required = ["url"]
    
    is_valid, error = validate_arguments(arguments, required)
    assert is_valid is False
    assert "Invalid URL format" in error


def test_validate_arguments_valid_endpoint():
    """Test argument validation with valid endpoint."""
    arguments = {
        "endpoint": "https://api.example.com/graphql",
    }
    required = ["endpoint"]
    
    is_valid, error = validate_arguments(arguments, required)
    assert is_valid is True

