"""Xray/V2ray Core Integration for Crawlemoon.

Manages downloading the binary, parsing subscription URIs (VLESS, VMess, Trojan, Shadowsocks),
generating standard Xray client JSON configs, running subprocess clients on dynamic ports,
and auto-rotating nodes upon failure or WAF blocking.
"""

import os
import sys
import json
import time
import base64
import logging
import platform
import zipfile
import subprocess
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

import httpx
import asyncio

logger = logging.getLogger(__name__)

# Constants for storage
APP_DATA_DIR = "/Users/emad/.gemini/antigravity"
XRAY_BIN_DIR = os.path.join(APP_DATA_DIR, "bin")
XRAY_CONFIG_DIR = os.path.join(APP_DATA_DIR, "xray")

os.makedirs(XRAY_BIN_DIR, exist_ok=True)
os.makedirs(XRAY_CONFIG_DIR, exist_ok=True)


@dataclass
class XrayNode:
    """Represents a parsed V2ray/Xray outbound node."""
    protocol: str  # vmess, vless, trojan, shadowsocks
    address: str
    port: int
    raw_url: str
    name: str
    params: Dict[str, Any]
    latency: float = -1.0  # In milliseconds, -1.0 means untested/unreachable
    is_healthy: bool = True
    failure_count: int = 0


class XrayBinaryManager:
    """Handles automatic cross-platform download, extraction, and updates of the Xray-Core binary."""

    VERSION = "1.8.24"  # Highly stable Xray-Core version with VMess/VLESS/Trojan support

    @classmethod
    def get_binary_path(cls) -> str:
        """Gets absolute path to the local Xray binary based on the host OS."""
        system = platform.system().lower()
        if system == "windows":
            return os.path.join(XRAY_BIN_DIR, "xray.exe")
        return os.path.join(XRAY_BIN_DIR, "xray")

    @classmethod
    def find_or_install(cls) -> str:
        """Checks if Xray is installed locally, in PATH, or downloads it automatically."""
        local_path = cls.get_binary_path()
        if os.path.exists(local_path) and os.access(local_path, os.X_OK if platform.system() != "Windows" else os.F_OK):
            logger.info("Found local Xray binary at: %s", local_path)
            return local_path

        # Check system PATH
        system_cmd = "where" if platform.system() == "Windows" else "which"
        try:
            res = subprocess.run([system_cmd, "xray"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if res.returncode == 0:
                path = res.stdout.strip().split("\n")[0]
                if os.path.exists(path):
                    logger.info("Found system Xray in PATH at: %s", path)
                    return path
        except Exception:
            pass

        # Dynamic download from official GitHub release
        logger.info("Xray core binary not found. Initiating dynamic automated download...")
        cls.download_and_extract()
        
        if os.path.exists(local_path):
            if platform.system() != "Windows":
                os.chmod(local_path, 0o755)
            logger.info("Xray core successfully installed at: %s", local_path)
            return local_path
        
        raise FileNotFoundError("Failed to locate or download Xray binary.")

    @classmethod
    def download_and_extract(cls) -> None:
        """Downloads the appropriate Xray release zip and extracts it."""
        system = platform.system().lower()
        machine = platform.machine().lower()

        if system == "darwin":
            if "arm" in machine or "aarch64" in machine:
                filename = "Xray-macos-arm64.zip"
            else:
                filename = "Xray-macos-64.zip"
        elif system == "linux":
            if "arm" in machine or "aarch64" in machine:
                filename = "Xray-linux-arm64.zip"
            else:
                filename = "Xray-linux-64.zip"
        elif system == "windows":
            filename = "Xray-windows-64.zip"
        else:
            raise NotImplementedError(f"Unsupported operating system: {system}")

        url = f"https://github.com/XTLS/Xray-core/releases/download/v{cls.VERSION}/{filename}"
        zip_path = os.path.join(XRAY_BIN_DIR, "xray.zip")

        logger.info("Downloading Xray-Core v%s from: %s", cls.VERSION, url)
        try:
            # Custom User-Agent to bypass potential blockings
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
            with urllib.request.urlopen(req) as response, open(zip_path, "wb") as out_file:
                out_file.write(response.read())

            logger.info("Extracting Xray-Core zip...")
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(XRAY_BIN_DIR)

            # Clean up zip
            os.remove(zip_path)
        except Exception as e:
            logger.error("Failed to download or extract Xray-Core: %s", e)
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
            raise


class XrayConfigGenerator:
    """Parses base64 subscriptions and protocol URIs, converting them to standard Xray client JSON configs."""

    @classmethod
    def parse_subscription(cls, raw_data: str) -> List[XrayNode]:
        """Decodes raw base64 subscription lists or newline-separated URIs into XrayNode objects."""
        nodes = []
        raw_data = raw_data.strip()
        if not raw_data:
            return nodes

        # Try base64 decoding
        decoded_text = ""
        try:
            # Remove whitespace and pad base64
            b64_clean = "".join(raw_data.split())
            missing_padding = len(b64_clean) % 4
            if missing_padding:
                b64_clean += "=" * (4 - missing_padding)
            decoded_text = base64.b64decode(b64_clean).decode("utf-8", errors="ignore")
        except Exception:
            # Fall back to interpreting raw text directly if not base64
            decoded_text = raw_data

        for line in decoded_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                node = cls.parse_uri(line)
                if node:
                    nodes.append(node)
            except Exception as e:
                logger.warning("Failed to parse URI line '%s...': %s", line[:30], e)

        return nodes

    @classmethod
    def parse_uri(cls, uri: str) -> Optional[XrayNode]:
        """Parses a single protocol URI (vmess://, vless://, trojan://, ss://) into an XrayNode."""
        uri = uri.strip()
        if not uri:
            return None

        if uri.startswith("vmess://"):
            return cls._parse_vmess(uri)
        elif uri.startswith("vless://"):
            return cls._parse_vless(uri)
        elif uri.startswith("trojan://"):
            return cls._parse_trojan(uri)
        elif uri.startswith("ss://"):
            return cls._parse_shadowsocks(uri)
        return None

    @classmethod
    def _parse_vmess(cls, uri: str) -> Optional[XrayNode]:
        """Parses vmess:// format (typically a base64 encoded JSON)."""
        raw_b64 = uri[8:].strip()
        # Clean up padding
        missing_padding = len(raw_b64) % 4
        if missing_padding:
            raw_b64 += "=" * (4 - missing_padding)
        
        decoded = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
        data = json.loads(decoded)

        # Port might be a string or integer
        port = int(data.get("port", 443))
        name = data.get("ps", f"VMess_{data.get('add', 'Node')}_{port}")

        return XrayNode(
            protocol="vmess",
            address=data.get("add", ""),
            port=port,
            raw_url=uri,
            name=name,
            params=data
        )

    @classmethod
    def _parse_vless(cls, uri: str) -> Optional[XrayNode]:
        """Parses vless:// format: vless://uuid@host:port?query#name."""
        parsed = urllib.parse.urlparse(uri)
        uuid = parsed.username or ""
        host = parsed.hostname or ""
        port = parsed.port or 443
        
        # Name is url-encoded in the fragment
        name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else f"VLESS_{host}_{port}"
        
        # Parse query params
        params = dict(urllib.parse.parse_qsl(parsed.query))
        params["uuid"] = uuid

        return XrayNode(
            protocol="vless",
            address=host,
            port=port,
            raw_url=uri,
            name=name,
            params=params
        )

    @classmethod
    def _parse_trojan(cls, uri: str) -> Optional[XrayNode]:
        """Parses trojan:// format: trojan://password@host:port?query#name."""
        parsed = urllib.parse.urlparse(uri)
        password = parsed.username or ""
        host = parsed.hostname or ""
        port = parsed.port or 443
        
        name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else f"Trojan_{host}_{port}"
        
        params = dict(urllib.parse.parse_qsl(parsed.query))
        params["password"] = password

        return XrayNode(
            protocol="trojan",
            address=host,
            port=port,
            raw_url=uri,
            name=name,
            params=params
        )

    @classmethod
    def _parse_shadowsocks(cls, uri: str) -> Optional[XrayNode]:
        """Parses ss:// format."""
        parsed = urllib.parse.urlparse(uri)
        name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else f"SS_{parsed.hostname}_{parsed.port}"
        
        params = {}
        # Shadowsocks links can be standard or SIP002/SIP008 formats
        # Standard: ss://base64_encoded(method:password)@host:port
        if parsed.username:
            try:
                # Username is base64(method:password)
                missing_padding = len(parsed.username) % 4
                user_b64 = parsed.username + ("=" * (4 - missing_padding)) if missing_padding else parsed.username
                decoded = base64.b64decode(user_b64).decode("utf-8", errors="ignore")
                if ":" in decoded:
                    method, password = decoded.split(":", 1)
                    params["method"] = method
                    params["password"] = password
            except Exception:
                pass

        if "method" not in params:
            # Fallback to path parser for some legacy encodings
            # ss://base64_encoded_auth_and_host
            try:
                raw_b64 = uri[5:].split("#")[0].split("?")[0]
                missing_padding = len(raw_b64) % 4
                raw_b64 += "=" * (4 - missing_padding) if missing_padding else ""
                decoded = base64.b64decode(raw_b64).decode("utf-8", errors="ignore")
                # method:password@host:port
                if "@" in decoded:
                    auth, server = decoded.split("@", 1)
                    if ":" in auth:
                        params["method"], params["password"] = auth.split(":", 1)
            except Exception:
                pass

        return XrayNode(
            protocol="shadowsocks",
            address=parsed.hostname or "",
            port=parsed.port or 8388,
            raw_url=uri,
            name=name,
            params=params
        )

    @classmethod
    def generate_json_config(cls, node: XrayNode, local_socks_port: int) -> Dict[str, Any]:
        """Generates standard client Xray config JSON mapped to outbound node and inbound local port."""
        
        # Build double inbounds - SOCKS5 and HTTP local proxies for maximum compatibility
        inbounds = [
            {
                "port": local_socks_port,
                "protocol": "socks",
                "listen": "127.0.0.1",
                "settings": {
                    "auth": "noauth",
                    "udp": True
                }
            },
            {
                "port": local_socks_port + 1000,
                "protocol": "http",
                "listen": "127.0.0.1",
                "settings": {
                    "timeout": 300
                }
            }
        ]

        # Build primary outbound
        primary_outbound = {}
        
        if node.protocol == "vmess":
            user_security = node.params.get("scy", "auto")
            primary_outbound = {
                "protocol": "vmess",
                "settings": {
                    "vnext": [
                        {
                            "address": node.address,
                            "port": node.port,
                            "users": [
                                {
                                    "id": node.params.get("id", ""),
                                    "alterId": int(node.params.get("aid", 0)),
                                    "security": user_security
                                }
                            ]
                        }
                    ]
                }
            }
            # Stream settings (WS / TLS)
            stream_settings = {}
            network = node.params.get("net", "tcp")
            security = node.params.get("tls", "none")
            
            stream_settings["network"] = network
            stream_settings["security"] = security
            
            if security == "tls":
                stream_settings["tlsSettings"] = {
                    "serverName": node.params.get("sni", node.params.get("host", node.address)),
                    "allowInsecure": True
                }
            elif security == "reality":
                stream_settings["realitySettings"] = {
                    "show": False,
                    "fingerprint": node.params.get("fp", "chrome"),
                    "serverName": node.params.get("sni", node.params.get("host", node.address)),
                    "publicKey": node.params.get("pbk", ""),
                    "shortId": node.params.get("sid", ""),
                    "spiderX": node.params.get("spx", "/")
                }
            
            if network == "ws":
                stream_settings["wsSettings"] = {
                    "path": node.params.get("path", "/"),
                    "headers": {
                        "Host": node.params.get("host", "")
                    }
                }
            elif network == "grpc":
                stream_settings["grpcSettings"] = {
                    "serviceName": node.params.get("path", "")
                }
            
            primary_outbound["streamSettings"] = stream_settings

        elif node.protocol == "vless":
            primary_outbound = {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": node.address,
                            "port": node.port,
                            "users": [
                                {
                                    "id": node.params.get("uuid", ""),
                                    "encryption": "none",
                                    "flow": node.params.get("flow", "")
                                }
                            ]
                        }
                    ]
                }
            }
            # Stream settings
            stream_settings = {}
            network = node.params.get("type", "tcp")
            security = node.params.get("security", "none")
            
            stream_settings["network"] = network
            stream_settings["security"] = security
            
            if security == "tls" or security == "xtls":
                stream_settings["tlsSettings"] = {
                    "serverName": node.params.get("sni", node.params.get("host", node.address)),
                    "allowInsecure": True
                }
            elif security == "reality":
                stream_settings["realitySettings"] = {
                    "show": False,
                    "fingerprint": node.params.get("fp", "chrome"),
                    "serverName": node.params.get("sni", node.params.get("host", node.address)),
                    "publicKey": node.params.get("pbk", ""),
                    "shortId": node.params.get("sid", ""),
                    "spiderX": node.params.get("spx", "/")
                }
            
            if network == "ws":
                stream_settings["wsSettings"] = {
                    "path": node.params.get("path", "/"),
                    "headers": {
                        "Host": node.params.get("host", "")
                    }
                }
            elif network == "grpc":
                stream_settings["grpcSettings"] = {
                    "serviceName": node.params.get("serviceName", "")
                }
                
            primary_outbound["streamSettings"] = stream_settings

        elif node.protocol == "trojan":
            primary_outbound = {
                "protocol": "trojan",
                "settings": {
                    "servers": [
                        {
                            "address": node.address,
                            "port": node.port,
                            "password": node.params.get("password", "")
                        }
                    ]
                }
            }
            # Stream settings
            stream_settings = {}
            network = node.params.get("type", "tcp")
            security = node.params.get("security", "tls")  # Trojan defaults to TLS
            
            stream_settings["network"] = network
            stream_settings["security"] = security
            
            if security == "tls":
                stream_settings["tlsSettings"] = {
                    "serverName": node.params.get("sni", node.params.get("host", node.address)),
                    "allowInsecure": True
                }
            elif security == "reality":
                stream_settings["realitySettings"] = {
                    "show": False,
                    "fingerprint": node.params.get("fp", "chrome"),
                    "serverName": node.params.get("sni", node.params.get("host", node.address)),
                    "publicKey": node.params.get("pbk", ""),
                    "shortId": node.params.get("sid", ""),
                    "spiderX": node.params.get("spx", "/")
                }
                
            if network == "ws":
                stream_settings["wsSettings"] = {
                    "path": node.params.get("path", "/"),
                    "headers": {
                        "Host": node.params.get("host", "")
                    }
                }
                
            primary_outbound["streamSettings"] = stream_settings

        elif node.protocol == "shadowsocks":
            primary_outbound = {
                "protocol": "shadowsocks",
                "settings": {
                    "servers": [
                        {
                            "address": node.address,
                            "port": node.port,
                            "method": node.params.get("method", "aes-256-gcm"),
                            "password": node.params.get("password", "")
                        }
                    ]
                }
            }

        # Fallbacks: freedom outbound (direct routing) and blackhole
        outbounds = [
            primary_outbound,
            {
                "protocol": "freedom",
                "tag": "direct",
                "settings": {}
            },
            {
                "protocol": "blackhole",
                "tag": "block",
                "settings": {}
            }
        ]

        # Routing rules to bypass private local networks
        routing = {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {
                    "type": "field",
                    "ip": ["geoip:private"],
                    "outboundTag": "direct"
                }
            ]
        }

        return {
            "log": {
                "loglevel": "warning"
            },
            "inbounds": inbounds,
            "outbounds": outbounds,
            "routing": routing
        }

def is_port_in_use(port: int) -> bool:
    """Helper to check if a local port is already occupied."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


class XrayRunner:
    """Manages a single running Xray client process on a specified port."""

    def __init__(self, port: int, binary_path: str):
        self.port = port
        self.binary_path = binary_path
        self.process: Optional[subprocess.Popen] = None
        self.node: Optional[XrayNode] = None
        self.config_path = os.path.join(XRAY_CONFIG_DIR, f"config_{self.port}.json")
        self.log_path = os.path.join(XRAY_CONFIG_DIR, f"xray_{self.port}.log")
        self.log_file = None

    def start(self, node: XrayNode) -> bool:
        """Launches Xray client process bound to the outbound node."""
        self.stop()
        
        # Verify port availability to prevent socket binding crash
        socks_port = self.port
        http_port = self.port + 1000
        
        if is_port_in_use(socks_port):
            logger.error("Port conflict! SOCKS5 port %d is already in use by another application.", socks_port)
            raise RuntimeError(f"Port conflict: Local SOCKS5 port {socks_port} is already in use.")
            
        if is_port_in_use(http_port):
            logger.error("Port conflict! HTTP port %d is already in use by another application.", http_port)
            raise RuntimeError(f"Port conflict: Local HTTP port {http_port} is already in use.")

        self.node = node
        config = XrayConfigGenerator.generate_json_config(node, self.port)
        
        with open(self.config_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info("Starting Xray client for node '%s' (SOCKS: %d, HTTP: %d)...", node.name, socks_port, http_port)
        
        try:
            # Open log file to redirect stdout/stderr and prevent pipe buffer overflow freeze
            self.log_file = open(self.log_path, "a", encoding="utf-8")
            self.process = subprocess.Popen(
                [self.binary_path, "-config", self.config_path],
                stdout=self.log_file,
                stderr=self.log_file,
                text=True
            )
            
            # Allow 1.5 seconds to do connection handshake & initial sanity check
            time.sleep(1.5)
            
            poll = self.process.poll()
            if poll is not None:
                logger.error("Xray process on port %d exited immediately with code %d. Check logs at: %s", self.port, poll, self.log_path)
                self.stop()
                return False
            
            return True
        except Exception as e:
            logger.error("Failed to start Xray client on port %d: %s", self.port, e)
            self.stop()
            return False

    def stop(self) -> None:
        """Kills the active subprocess and deletes temporary config files."""
        if self.process:
            logger.info("Terminating Xray client on port %d...", self.port)
            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            except Exception as e:
                logger.warning("Error stopping Xray subprocess on port %d: %s", self.port, e)
            finally:
                self.process = None

        # Safely close the log file handle
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
            self.log_file = None

        self.node = None
        if os.path.exists(self.config_path):
            try:
                os.remove(self.config_path)
            except OSError:
                pass


import atexit

_active_managers = []

def _cleanup_all_xray_processes():
    """Module-level cleanup hook to terminate all active Xray subprocesses on exit."""
    for manager in _active_managers:
        try:
            manager.stop_all()
        except Exception:
            pass

atexit.register(_cleanup_all_xray_processes)


class CrawlemoonV2rayManager:
    """Global manager orchestrating multiple dynamic Xray configurations and pool routers."""

    def __init__(self, subscription_url: Optional[str] = None):
        self.subscription_url = subscription_url
        self.nodes: List[XrayNode] = []
        self.runners: Dict[int, XrayRunner] = {}
        self.binary_path: str = ""
        _active_managers.append(self)
        self._current_index_map: Dict[int, int] = {}  # port -> last node index used

    def initialize(self) -> None:
        """Locates or downloads Xray core and prepares paths."""
        self.binary_path = XrayBinaryManager.find_or_install()

    async def fetch_subscription(self) -> int:
        """Downloads base64 subscription URIs from remote subscription URL."""
        if not self.subscription_url:
            raise ValueError("No subscription URL configured.")

        logger.info("Fetching subscription nodes from: %s", self.subscription_url)
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(self.subscription_url)
            if res.status_code != 200:
                raise httpx.HTTPStatusError(f"HTTP status code {res.status_code}", request=res.request, response=res)
            
            self.nodes = XrayConfigGenerator.parse_subscription(res.text)
            logger.info("Parsed %d nodes from subscription URL.", len(self.nodes))
            return len(self.nodes)

    def load_raw_links(self, raw_links: List[str]) -> int:
        """Loads nodes from raw VMess/VLESS/Trojan/Shadowsocks URI links."""
        nodes = []
        for link in raw_links:
            node = XrayConfigGenerator.parse_uri(link)
            if node:
                nodes.append(node)
        
        self.nodes = nodes
        logger.info("Loaded %d nodes from raw links.", len(self.nodes))
        return len(self.nodes)

    def start_port(self, port: int) -> str:
        """Runs an Xray client process on a dedicated local SOCKS5 port."""
        if not self.nodes:
            raise ValueError("No V2ray/Xray nodes loaded. Load raw links or fetch subscription first.")

        if not self.binary_path:
            self.initialize()

        if port not in self.runners:
            self.runners[port] = XrayRunner(port, self.binary_path)
            self._current_index_map[port] = len(self.runners) % len(self.nodes)

        # Retrieve next healthy node
        index = self._current_index_map.get(port, 0)
        started = False
        attempts = 0
        
        while not started and attempts < len(self.nodes):
            node = self.nodes[index]
            if node.is_healthy:
                started = self.runners[port].start(node)
                if started:
                    self._current_index_map[port] = index
                    break
            
            index = (index + 1) % len(self.nodes)
            attempts += 1

        if not started:
            raise RuntimeError(f"Failed to start Xray client on port {port} using any available healthy node.")

        return f"socks5://127.0.0.1:{port}"

    def rotate_node(self, port: int) -> str:
        """Forcefully restarts Xray port backend onto the next healthy subscription node."""
        logger.info("[Crawlemoon V2ray] Dynamic Rotation Triggered for SOCKS port %d...", port)
        if port not in self.runners:
            raise KeyError(f"No runner found active on port {port}")

        runner = self.runners[port]
        # Mark current node as failed or unhealthy temporarily
        if runner.node:
            try:
                # Safe increment (handles MagicMocks seamlessly)
                failure_count = int(runner.node.failure_count or 0) + 1
                runner.node.failure_count = failure_count
                if failure_count >= 3:
                    runner.node.is_healthy = False
                    logger.warning("Node '%s' marked unhealthy due to repeated rotation failures.", runner.node.name)
            except Exception:
                pass

        # Move to next index
        next_index = (self._current_index_map.get(port, 0) + 1) % len(self.nodes)
        self._current_index_map[port] = next_index

        return self.start_port(port)

    def stop_all(self) -> None:
        """Terminates all active processes."""
        for runner in self.runners.values():
            runner.stop()
        self.runners.clear()

    async def benchmark_node(self, node: XrayNode, test_url: str, temp_port: int) -> float:
        """Spawns a temporary runner to perform an HTTP request latency check on a node."""
        runner = XrayRunner(temp_port, self.binary_path)
        try:
            started = runner.start(node)
            if not started:
                return -1.0

            # Measure HTTP round-trip latency using httpx through the local proxy
            proxy_url = f"socks5://127.0.0.1:{temp_port}"
            start_time = time.perf_counter()
            
            async with httpx.AsyncClient(proxies=proxy_url, timeout=5.0) as client:
                res = await client.get(test_url)
                if res.status_code == 200:
                    latency = (time.perf_counter() - start_time) * 1000.0
                    node.latency = latency
                    node.is_healthy = True
                    node.failure_count = 0
                    return latency
        except Exception as e:
            logger.debug("Benchmark error for '%s': %s", node.name, e)
        finally:
            runner.stop()

        node.latency = -1.0
        node.is_healthy = False
        return -1.0

    async def benchmark_all_nodes(self, test_url: str = "http://httpbin.org/ip", max_concurrency: int = 5) -> List[Dict[str, Any]]:
        """Benchmarks all subscription nodes concurrently to filter out dead ones and sort by speed."""
        if not self.nodes:
            return []

        if not self.binary_path:
            self.initialize()

        logger.info("Starting latency benchmarking of %d nodes against URL: %s", len(self.nodes), test_url)
        
        # We will use high ports range for temp testing
        start_temp_port = 20000
        sem = asyncio.Semaphore(max_concurrency)
        
        async def worker(index: int, node: XrayNode) -> Tuple[str, float]:
            async with sem:
                temp_port = start_temp_port + index
                latency = await self.benchmark_node(node, test_url, temp_port)
                return node.name, latency

        tasks = [worker(i, node) for i, node in enumerate(self.nodes)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Sort nodes list by working status and latency (lowest first)
        working_nodes = [n for n in self.nodes if n.is_healthy and n.latency > 0]
        dead_nodes = [n for n in self.nodes if not n.is_healthy or n.latency <= 0]
        
        working_nodes.sort(key=lambda n: n.latency)
        self.nodes = working_nodes + dead_nodes

        logger.info("Benchmark complete. %d/%d nodes are functional.", len(working_nodes), len(self.nodes))
        
        return [
            {
                "name": n.name,
                "protocol": n.protocol,
                "address": n.address,
                "port": n.port,
                "latency_ms": round(n.latency, 2) if n.latency > 0 else -1,
                "status": "healthy" if n.is_healthy and n.latency > 0 else "unhealthy"
            }
            for n in self.nodes
        ]
