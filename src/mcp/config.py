"""Configuration for MCP server."""

from dataclasses import dataclass
from typing import Optional
import os


@dataclass
class MCPServerConfig:
    """Configuration for MCP server."""
    
    # Timeouts (in seconds)
    navigation_timeout: float = 30.0
    request_timeout: float = 30.0
    operation_timeout: float = 60.0
    
    # Browser settings
    headless: bool = True
    browser_type: str = "chromium"
    max_browser_pool_size: int = 5
    
    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Recording settings
    recording_storage_dir: Optional[str] = None
    auto_save_recordings: bool = True
    
    # Analysis settings
    wait_for_network_idle: bool = True
    capture_screenshots: bool = False
    
    @classmethod
    def from_env(cls) -> "MCPServerConfig":
        """Create config from environment variables."""
        return cls(
            navigation_timeout=float(os.getenv("CRAWILFY_NAV_TIMEOUT", "30.0")),
            request_timeout=float(os.getenv("CRAWILFY_REQ_TIMEOUT", "30.0")),
            operation_timeout=float(os.getenv("CRAWILFY_OP_TIMEOUT", "60.0")),
            headless=os.getenv("CRAWILFY_HEADLESS", "true").lower() == "true",
            browser_type=os.getenv("CRAWILFY_BROWSER", "chromium"),
            max_browser_pool_size=int(os.getenv("CRAWILFY_POOL_SIZE", "5")),
            max_retries=int(os.getenv("CRAWILFY_MAX_RETRIES", "3")),
            retry_delay=float(os.getenv("CRAWILFY_RETRY_DELAY", "1.0")),
            recording_storage_dir=os.getenv("CRAWILFY_RECORDING_DIR"),
            auto_save_recordings=os.getenv("CRAWILFY_AUTO_SAVE", "true").lower() == "true",
            wait_for_network_idle=os.getenv("CRAWILFY_WAIT_NETWORK", "true").lower() == "true",
            capture_screenshots=os.getenv("CRAWILFY_SCREENSHOTS", "false").lower() == "true",
        )

