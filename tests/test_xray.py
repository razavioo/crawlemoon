"""Unit tests for Crawlemoon V2ray/Xray Core Proxy Engine."""

import os
import json
import base64
import unittest
from unittest.mock import MagicMock, patch

import pytest
import httpx

from src.core.browser.xray import (
    XrayNode,
    XrayConfigGenerator,
    XrayRunner,
    CrawlemoonV2rayManager
)
from src.core.browser.proxy_pool import ProxyPool, RotationStrategy, Proxy, ProxyType


def test_parse_vmess_node():
    """Tests parsing a base64 encoded VMess URI."""
    # Standard VMess JSON config
    vmess_json = {
        "v": "2",
        "ps": "VMess Test Server",
        "add": "1.2.3.4",
        "port": 443,
        "id": "c30932c0-82a1-11ec-a8a3-0242ac120002",
        "aid": 0,
        "scy": "auto",
        "net": "ws",
        "type": "none",
        "host": "test.vmess.com",
        "path": "/graphql",
        "tls": "tls"
    }
    
    vmess_str = json.dumps(vmess_json)
    b64_encoded = base64.b64encode(vmess_str.encode("utf-8")).decode("utf-8")
    vmess_uri = f"vmess://{b64_encoded}"
    
    node = XrayConfigGenerator.parse_uri(vmess_uri)
    
    assert node is not None
    assert node.protocol == "vmess"
    assert node.address == "1.2.3.4"
    assert node.port == 443
    assert node.name == "VMess Test Server"
    assert node.params["id"] == "c30932c0-82a1-11ec-a8a3-0242ac120002"
    assert node.params["path"] == "/graphql"
    assert node.params["tls"] == "tls"


def test_parse_vless_node():
    """Tests parsing a VLESS protocol URI."""
    vless_uri = "vless://d2907406-82a1-11ec-a8a3-0242ac120002@5.6.7.8:8443?security=tls&sni=test.vless.com&type=ws&host=test.vless.com&path=%2Fws-path#VLESS%20Test%20Server"
    
    node = XrayConfigGenerator.parse_uri(vless_uri)
    
    assert node is not None
    assert node.protocol == "vless"
    assert node.address == "5.6.7.8"
    assert node.port == 8443
    assert node.name == "VLESS Test Server"
    assert node.params["uuid"] == "d2907406-82a1-11ec-a8a3-0242ac120002"
    assert node.params["security"] == "tls"
    assert node.params["type"] == "ws"
    assert node.params["path"] == "/ws-path"
    assert node.params["sni"] == "test.vless.com"


def test_parse_trojan_node():
    """Tests parsing a Trojan protocol URI."""
    trojan_uri = "trojan://trojan-password@9.10.11.12:443?security=tls&sni=test.trojan.com#Trojan%20Test%20Server"
    
    node = XrayConfigGenerator.parse_uri(trojan_uri)
    
    assert node is not None
    assert node.protocol == "trojan"
    assert node.address == "9.10.11.12"
    assert node.port == 443
    assert node.name == "Trojan Test Server"
    assert node.params["password"] == "trojan-password"
    assert node.params["security"] == "tls"
    assert node.params["sni"] == "test.trojan.com"


def test_parse_shadowsocks_node():
    """Tests parsing a Shadowsocks protocol URI."""
    # base64(aes-256-gcm:ss-password) = YWVzLTI1Ni1nY206c3MtcGFzc3dvcmQ=
    ss_uri = "ss://YWVzLTI1Ni1nY206c3MtcGFzc3dvcmQ=@13.14.15.16:8388#Shadowsocks%20Test%20Server"
    
    node = XrayConfigGenerator.parse_uri(ss_uri)
    
    assert node is not None
    assert node.protocol == "shadowsocks"
    assert node.address == "13.14.15.16"
    assert node.port == 8388
    assert node.name == "Shadowsocks Test Server"
    assert node.params["method"] == "aes-256-gcm"
    assert node.params["password"] == "ss-password"


def test_config_generation():
    """Tests that standard client configs are properly structured for Xray-Core."""
    node = XrayNode(
        protocol="vmess",
        address="1.2.3.4",
        port=443,
        raw_url="vmess://test",
        name="Test",
        params={
            "id": "uuid",
            "aid": 0,
            "net": "ws",
            "tls": "tls",
            "host": "test.com",
            "path": "/ws"
        }
    )
    
    config = XrayConfigGenerator.generate_json_config(node, 10808)
    
    assert "log" in config
    assert "inbounds" in config
    assert "outbounds" in config
    assert "routing" in config
    
    # Assert correct SOCKS5 inbound config
    inbound = config["inbounds"][0]
    assert inbound["port"] == 10808
    assert inbound["protocol"] == "socks"
    assert inbound["listen"] == "127.0.0.1"
    
    # Assert outbound is VMess with correct TLS stream settings
    outbound = config["outbounds"][0]
    assert outbound["protocol"] == "vmess"
    assert outbound["settings"]["vnext"][0]["address"] == "1.2.3.4"
    assert outbound["settings"]["vnext"][0]["port"] == 443
    
    stream_settings = outbound["streamSettings"]
    assert stream_settings["network"] == "ws"
    assert stream_settings["security"] == "tls"
    assert stream_settings["tlsSettings"]["serverName"] == "test.com"
    assert stream_settings["wsSettings"]["path"] == "/ws"


@patch("subprocess.Popen")
def test_xray_runner_lifecycle(mock_popen):
    """Tests runner subprocess start, monitoring, and stop sequence."""
    node = XrayNode(
        protocol="trojan",
        address="1.1.1.1",
        port=443,
        raw_url="trojan://",
        name="Test Trojan",
        params={"password": "pwd"}
    )
    
    mock_process = MagicMock()
    mock_process.poll.return_value = None  # Process is running
    mock_popen.return_value = mock_process
    
    runner = XrayRunner(port=10809, binary_path="/path/to/xray")
    
    with patch("builtins.open", unittest.mock.mock_open()):
        started = runner.start(node)
        
    assert started is True
    assert runner.node == node
    mock_popen.assert_called_once()
    
    # Test stopping process
    runner.stop()
    assert runner.node is None
    mock_process.terminate.assert_called_once()


def test_manager_loading_raw_links():
    """Tests that CrawlemoonV2rayManager loads nodes list correctly from raw URLs."""
    raw_links = [
        "vless://uuid1@1.1.1.1:443#Node1",
        "trojan://pwd2@2.2.2.2:443#Node2",
        "invalid://link"
    ]
    
    manager = CrawlemoonV2rayManager()
    num_loaded = manager.load_raw_links(raw_links)
    
    assert num_loaded == 2
    assert len(manager.nodes) == 2
    assert manager.nodes[0].name == "Node1"
    assert manager.nodes[1].name == "Node2"


@patch("src.core.browser.xray.XrayRunner")
def test_manager_start_port_and_rotation(mock_runner_class):
    """Tests that starting ports and rotating nodes cycles nodes correctly."""
    mock_runner = MagicMock()
    mock_runner.start.return_value = True
    mock_runner_class.return_value = mock_runner
    
    manager = CrawlemoonV2rayManager()
    manager.binary_path = "/path/to/xray"
    
    manager.nodes = [
        XrayNode(protocol="vless", address="1.1.1.1", port=443, raw_url="vless://1", name="Node1", params={}),
        XrayNode(protocol="vless", address="2.2.2.2", port=443, raw_url="vless://2", name="Node2", params={}),
        XrayNode(protocol="vless", address="3.3.3.3", port=443, raw_url="vless://3", name="Node3", params={})
    ]
    
    # Start on port 10811
    proxy_url = manager.start_port(10811)
    assert proxy_url == "socks5://127.0.0.1:10811"
    
    # Rotate node on port 10811
    new_proxy_url = manager.rotate_node(10811)
    assert new_proxy_url == "socks5://127.0.0.1:10811"
    
    # Total runners managed
    assert len(manager.runners) == 1
    
    # Stop all
    manager.stop_all()
    assert len(manager.runners) == 0


def test_proxy_pool_integration_and_rotation():
    """Tests that dynamic Xray proxies registered in ProxyPool undergo correct routing/rotation."""
    manager = CrawlemoonV2rayManager()
    manager.nodes = [
        XrayNode(protocol="vless", address="1.1.1.1", port=443, raw_url="vless://1", name="Node1", params={}),
        XrayNode(protocol="vless", address="2.2.2.2", port=443, raw_url="vless://2", name="Node2", params={})
    ]
    manager.binary_path = "/path/to/xray"
    
    pool = ProxyPool(proxies=[], xray_manager=manager)
    
    # Register dynamic Xray proxy
    proxy = pool.add_xray_proxy(10812)
    assert proxy.is_xray is True
    assert proxy.xray_port == 10812
    assert proxy.url == "socks5://127.0.0.1:10812"
    
    # Mock rotating node on manager
    with patch.object(manager, "rotate_node") as mock_rotate:
        # Simulate health check failure or marking failure
        # In a real run, multiple failures or manual rotation calls this
        proxy.mark_failure()
        proxy.mark_failure()
        proxy.mark_failure()  # 3rd failure makes it unhealthy
        
        assert proxy.is_healthy is False
