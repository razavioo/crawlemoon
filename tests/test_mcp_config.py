"""Tests for MCP server configuration."""

import pytest
import os
from unittest.mock import patch

from src.mcp.config import MCPServerConfig


def test_config_initialization():
    """Test config initialization with defaults."""
    config = MCPServerConfig()
    
    assert config is not None
    assert config.navigation_timeout == 30.0
    assert config.request_timeout == 30.0
    assert config.operation_timeout == 60.0


def test_config_timeout_defaults():
    """Test default timeout values."""
    config = MCPServerConfig()
    
    assert config.navigation_timeout == 30.0
    assert config.request_timeout == 30.0
    assert config.operation_timeout == 60.0


def test_config_browser_defaults():
    """Test default browser settings."""
    config = MCPServerConfig()
    
    assert config.headless is True
    assert config.browser_type == "chromium"
    assert config.max_browser_pool_size == 5


def test_config_retry_defaults():
    """Test default retry settings."""
    config = MCPServerConfig()
    
    assert config.max_retries == 3
    assert config.retry_delay == 1.0


def test_config_recording_defaults():
    """Test default recording settings."""
    config = MCPServerConfig()
    
    assert config.recording_storage_dir is None
    assert config.auto_save_recordings is True


def test_config_analysis_defaults():
    """Test default analysis settings."""
    config = MCPServerConfig()
    
    assert config.wait_for_network_idle is True
    assert config.capture_screenshots is False


def test_config_custom_values():
    """Test config with custom values."""
    config = MCPServerConfig(
        navigation_timeout=60.0,
        request_timeout=45.0,
        operation_timeout=120.0,
        headless=False,
        browser_type="firefox",
        max_browser_pool_size=10,
        max_retries=5,
        retry_delay=2.0,
    )
    
    assert config.navigation_timeout == 60.0
    assert config.request_timeout == 45.0
    assert config.operation_timeout == 120.0
    assert config.headless is False
    assert config.browser_type == "firefox"
    assert config.max_browser_pool_size == 10
    assert config.max_retries == 5
    assert config.retry_delay == 2.0


def test_config_from_env_defaults():
    """Test config from environment with no env vars set."""
    # Clear relevant env vars
    env_vars = [
        "CRAWILFY_NAV_TIMEOUT",
        "CRAWILFY_REQ_TIMEOUT",
        "CRAWILFY_OP_TIMEOUT",
        "CRAWILFY_HEADLESS",
        "CRAWILFY_BROWSER",
        "CRAWILFY_POOL_SIZE",
        "CRAWILFY_MAX_RETRIES",
        "CRAWILFY_RETRY_DELAY",
        "CRAWILFY_RECORDING_DIR",
        "CRAWILFY_AUTO_SAVE",
        "CRAWILFY_WAIT_NETWORK",
        "CRAWILFY_SCREENSHOTS",
    ]
    
    with patch.dict(os.environ, {}, clear=True):
        # Remove vars if they exist
        for var in env_vars:
            os.environ.pop(var, None)
        
        config = MCPServerConfig.from_env()
        
        # Should use defaults
        assert config.navigation_timeout == 30.0
        assert config.headless is True


@patch.dict(os.environ, {"CRAWILFY_NAV_TIMEOUT": "45.0"})
def test_config_from_env_nav_timeout():
    """Test navigation timeout from env."""
    config = MCPServerConfig.from_env()
    
    assert config.navigation_timeout == 45.0


@patch.dict(os.environ, {"CRAWILFY_REQ_TIMEOUT": "20.0"})
def test_config_from_env_req_timeout():
    """Test request timeout from env."""
    config = MCPServerConfig.from_env()
    
    assert config.request_timeout == 20.0


@patch.dict(os.environ, {"CRAWILFY_OP_TIMEOUT": "90.0"})
def test_config_from_env_op_timeout():
    """Test operation timeout from env."""
    config = MCPServerConfig.from_env()
    
    assert config.operation_timeout == 90.0


@patch.dict(os.environ, {"CRAWILFY_HEADLESS": "false"})
def test_config_from_env_headless_false():
    """Test headless=false from env."""
    config = MCPServerConfig.from_env()
    
    assert config.headless is False


@patch.dict(os.environ, {"CRAWILFY_HEADLESS": "true"})
def test_config_from_env_headless_true():
    """Test headless=true from env."""
    config = MCPServerConfig.from_env()
    
    assert config.headless is True


@patch.dict(os.environ, {"CRAWILFY_BROWSER": "firefox"})
def test_config_from_env_browser():
    """Test browser type from env."""
    config = MCPServerConfig.from_env()
    
    assert config.browser_type == "firefox"


@patch.dict(os.environ, {"CRAWILFY_POOL_SIZE": "10"})
def test_config_from_env_pool_size():
    """Test pool size from env."""
    config = MCPServerConfig.from_env()
    
    assert config.max_browser_pool_size == 10


@patch.dict(os.environ, {"CRAWILFY_MAX_RETRIES": "5"})
def test_config_from_env_max_retries():
    """Test max retries from env."""
    config = MCPServerConfig.from_env()
    
    assert config.max_retries == 5


@patch.dict(os.environ, {"CRAWILFY_RETRY_DELAY": "2.5"})
def test_config_from_env_retry_delay():
    """Test retry delay from env."""
    config = MCPServerConfig.from_env()
    
    assert config.retry_delay == 2.5


@patch.dict(os.environ, {"CRAWILFY_RECORDING_DIR": "/custom/path"})
def test_config_from_env_recording_dir():
    """Test recording directory from env."""
    config = MCPServerConfig.from_env()
    
    assert config.recording_storage_dir == "/custom/path"


@patch.dict(os.environ, {"CRAWILFY_AUTO_SAVE": "false"})
def test_config_from_env_auto_save_false():
    """Test auto save disabled from env."""
    config = MCPServerConfig.from_env()
    
    assert config.auto_save_recordings is False


@patch.dict(os.environ, {"CRAWILFY_AUTO_SAVE": "true"})
def test_config_from_env_auto_save_true():
    """Test auto save enabled from env."""
    config = MCPServerConfig.from_env()
    
    assert config.auto_save_recordings is True


@patch.dict(os.environ, {"CRAWILFY_WAIT_NETWORK": "false"})
def test_config_from_env_wait_network_false():
    """Test wait for network idle disabled from env."""
    config = MCPServerConfig.from_env()
    
    assert config.wait_for_network_idle is False


@patch.dict(os.environ, {"CRAWILFY_SCREENSHOTS": "true"})
def test_config_from_env_screenshots_true():
    """Test screenshot capture enabled from env."""
    config = MCPServerConfig.from_env()
    
    assert config.capture_screenshots is True


@patch.dict(os.environ, {
    "CRAWILFY_NAV_TIMEOUT": "60.0",
    "CRAWILFY_REQ_TIMEOUT": "45.0",
    "CRAWILFY_OP_TIMEOUT": "120.0",
    "CRAWILFY_HEADLESS": "false",
    "CRAWILFY_BROWSER": "webkit",
    "CRAWILFY_POOL_SIZE": "8",
    "CRAWILFY_MAX_RETRIES": "4",
    "CRAWILFY_RETRY_DELAY": "1.5",
})
def test_config_from_env_multiple():
    """Test multiple env vars at once."""
    config = MCPServerConfig.from_env()
    
    assert config.navigation_timeout == 60.0
    assert config.request_timeout == 45.0
    assert config.operation_timeout == 120.0
    assert config.headless is False
    assert config.browser_type == "webkit"
    assert config.max_browser_pool_size == 8
    assert config.max_retries == 4
    assert config.retry_delay == 1.5


def test_config_is_dataclass():
    """Test that config is a dataclass."""
    from dataclasses import is_dataclass
    
    assert is_dataclass(MCPServerConfig)


def test_config_fields():
    """Test that all expected fields exist."""
    config = MCPServerConfig()
    
    # All fields should be accessible
    _ = config.navigation_timeout
    _ = config.request_timeout
    _ = config.operation_timeout
    _ = config.headless
    _ = config.browser_type
    _ = config.max_browser_pool_size
    _ = config.max_retries
    _ = config.retry_delay
    _ = config.recording_storage_dir
    _ = config.auto_save_recordings
    _ = config.wait_for_network_idle
    _ = config.capture_screenshots


def test_config_immutability():
    """Test that config values can be modified."""
    config = MCPServerConfig()
    
    # Should be able to modify values (dataclass is mutable by default)
    config.navigation_timeout = 100.0
    assert config.navigation_timeout == 100.0


@patch.dict(os.environ, {"CRAWILFY_HEADLESS": "TRUE"})
def test_config_case_insensitive_bool():
    """Test boolean parsing is case-insensitive."""
    config = MCPServerConfig.from_env()
    
    # Should handle uppercase TRUE
    assert config.headless is True


@patch.dict(os.environ, {"CRAWILFY_HEADLESS": "False"})
def test_config_case_insensitive_bool_false():
    """Test false boolean parsing is case-insensitive."""
    config = MCPServerConfig.from_env()
    
    # Should handle mixed case False
    assert config.headless is False

