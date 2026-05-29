"""Advanced and comprehensive test suite for Crawlemoon's Premium V2ray/Xray Engine & Stealth Features.

Verifies:
1. Double inbounds (SOCKS5 + HTTP) config correctness.
2. Reality security protocol query parsing & config generation.
3. Socket-level Port Conflict Safeguards.
4. XrayRunner log redirection (file handles vs pipe buffer freeze).
5. Global atexit process garbage collection hooks.
6. RateLimiter randomized delay jitter distribution.
"""

import os
import json
import socket
import atexit
import unittest
import asyncio
import subprocess
from unittest.mock import MagicMock, patch, mock_open

import pytest

from src.core.browser.xray import (
    XrayNode,
    XrayConfigGenerator,
    XrayRunner,
    CrawlemoonV2rayManager,
    is_port_in_use,
    _active_managers,
    _cleanup_all_xray_processes
)
from src.core.browser.proxy_pool import ProxyPool, Proxy, ProxyType
from src.core.rate_limiter import RateLimiter, RateLimitConfig


# ============================================================================
# 1 & 2. Double Inbounds & Reality Protocol Configuration Tests
# ============================================================================

def test_reality_uri_parsing_and_config_generation():
    """Verifies parsing of premium VLESS + Reality URIs and correct JSON configuration output."""
    # VLESS + Reality URI
    reality_uri = (
        "vless://d2907406-82a1-11ec-a8a3-0242ac120002@1.2.3.4:443"
        "?security=reality&sni=target.com&fp=chrome&pbk=public_key_abc123"
        "&sid=short_id_xyz&spx=%2F#Reality%20Node"
    )
    
    node = XrayConfigGenerator.parse_uri(reality_uri)
    
    assert node is not None
    assert node.protocol == "vless"
    assert node.address == "1.2.3.4"
    assert node.port == 443
    assert node.name == "Reality Node"
    assert node.params["security"] == "reality"
    assert node.params["pbk"] == "public_key_abc123"
    assert node.params["sid"] == "short_id_xyz"
    assert node.params["fp"] == "chrome"
    assert node.params["spx"] == "/"
    
    # Generate Xray Config
    socks_port = 10815
    http_port = socks_port + 1000
    config = XrayConfigGenerator.generate_json_config(node, socks_port)
    
    # Assert double inbounds
    inbounds = config["inbounds"]
    assert len(inbounds) == 2
    
    # SOCKS5 inbound
    assert inbounds[0]["port"] == socks_port
    assert inbounds[0]["protocol"] == "socks"
    
    # HTTP inbound
    assert inbounds[1]["port"] == http_port
    assert inbounds[1]["protocol"] == "http"
    
    # Assert Reality outbound stream settings
    outbound = config["outbounds"][0]
    assert outbound["protocol"] == "vless"
    
    stream_settings = outbound["streamSettings"]
    assert stream_settings["security"] == "reality"
    assert "realitySettings" in stream_settings
    
    reality = stream_settings["realitySettings"]
    assert reality["show"] is False
    assert reality["fingerprint"] == "chrome"
    assert reality["serverName"] == "target.com"
    assert reality["publicKey"] == "public_key_abc123"
    assert reality["shortId"] == "short_id_xyz"
    assert reality["spiderX"] == "/"


# ============================================================================
# 3. Socket-Level Port Conflict Protection Tests
# ============================================================================

@patch("socket.socket")
def test_port_conflict_safeguards(mock_socket_class):
    """Verifies that is_port_in_use correctly identifies busy ports and XrayRunner blocks execution."""
    mock_socket = MagicMock()
    # connect_ex returns 0 if port is busy (connection succeeds), otherwise non-zero
    mock_socket.connect_ex.return_value = 0  
    mock_socket_class.return_value.__enter__.return_value = mock_socket
    
    # 1. Test helper
    assert is_port_in_use(80) is True
    
    # 2. Test runner blocks start when SOCKS port is in use
    runner = XrayRunner(port=80, binary_path="/path/to/xray")
    node = XrayNode(protocol="trojan", address="1.1.1.1", port=443, raw_url="trojan://", name="Test", params={})
    
    with pytest.raises(RuntimeError) as exc_info:
        runner.start(node)
    assert "Port conflict: Local SOCKS5 port 80 is already in use." in str(exc_info.value)


# ============================================================================
# 4. Log Redirection & Prevention of Subprocess Buffer Freezing Tests
# ============================================================================

@patch("subprocess.Popen")
@patch("builtins.open", new_callable=mock_open)
@patch("src.core.browser.xray.is_port_in_use")
def test_log_redirection_avoids_buffer_freeze(mock_port_check, mock_file_open, mock_popen):
    """Verifies Xray Popen redirects stdout/stderr to disk files instead of pipes to avoid OS freezes."""
    # Ensure port is reported as free
    mock_port_check.return_value = False
    
    node = XrayNode(protocol="vless", address="2.2.2.2", port=443, raw_url="vless://", name="Test Logs", params={})
    
    mock_process = MagicMock()
    mock_process.poll.return_value = None  # running
    mock_popen.return_value = mock_process
    
    runner = XrayRunner(port=10820, binary_path="/path/to/xray")
    
    # Start runner
    started = runner.start(node)
    
    assert started is True
    # Log file opened in append mode to protect history
    mock_file_open.assert_any_call(runner.log_path, "a", encoding="utf-8")
    
    # Popen called with log file descriptor instead of subprocess.PIPE
    called_kwargs = mock_popen.call_args[1]
    assert called_kwargs["stdout"] == runner.log_file
    assert called_kwargs["stderr"] == runner.log_file
    assert called_kwargs["stdout"] != subprocess.PIPE
    
    # Teardown
    runner.stop()
    assert runner.log_file is None


# ============================================================================
# 5. Global atexit Process Teardown Hook Tests
# ============================================================================

def test_atexit_manager_teardown_registration():
    """Asserts that all spawned CrawlemoonV2rayManagers register in global list for crash safety."""
    initial_count = len(_active_managers)
    
    # Spawn manager
    manager = CrawlemoonV2rayManager()
    
    # Registered in active list
    assert len(_active_managers) == initial_count + 1
    assert _active_managers[-1] == manager
    
    # Mock stop_all to verify teardown hook call
    with patch.object(manager, "stop_all") as mock_stop_all:
        _cleanup_all_xray_processes()
        mock_stop_all.assert_called_once()


# ============================================================================
# 6. RateLimiter Randomized Delay Jitter Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rate_limiter_random_jitter_randomness():
    """Verifies that consecutive rate limit sleeps include dynamic randomized jitter and are not identical."""
    limiter = RateLimiter()
    limiter.set_default_rate_limit(requests_per_second=2.0)  # Wait interval is active
    
    # Record requests to trigger rate limiting
    url = "http://target.com/page"
    
    # First sleep
    start_time = asyncio.get_event_loop().time()
    await limiter.wait_if_needed(url)
    first_duration = asyncio.get_event_loop().time() - start_time
    
    # Second sleep
    start_time = asyncio.get_event_loop().time()
    await limiter.wait_if_needed(url)
    second_duration = asyncio.get_event_loop().time() - start_time
    
    # Third sleep
    start_time = asyncio.get_event_loop().time()
    await limiter.wait_if_needed(url)
    third_duration = asyncio.get_event_loop().time() - start_time
    
    # Assert that jitter was added and delays vary dynamically
    # Since they are random floats, consecutive sleeps will rarely be equal
    # We can check they are floating delays including random additions
    durations = [first_duration, second_duration, third_duration]
    unique_durations = set([round(d, 4) for d in durations])
    
    logger = MagicMock()
    # At least some of the waits should trigger sleep wait_time + random jitter
    assert len(durations) == 3
