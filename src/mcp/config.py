"""Configuration for MCP server."""

from dataclasses import dataclass
from typing import List, Optional
import os


# Popular OpenAI-compatible API base URLs
OPENAI_COMPATIBLE_PROVIDERS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "mistral": "https://api.mistral.ai/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "perplexity": "https://api.perplexity.ai",
    "anyscale": "https://api.endpoints.anyscale.com/v1",
    "ollama": "http://localhost:11434/v1",  # Local Ollama
}


@dataclass
class MCPServerConfig:
    """Configuration for MCP server.
    
    LLM Configuration (for smart_extract and other LLM-enhanced tools):
    -------------------------------------------------------------------
    The server supports any OpenAI-compatible API, including free/cheap alternatives:
    
    - OpenRouter (https://openrouter.ai) - Access multiple models, some free
    - Together AI (https://together.ai) - Free tier available
    - Groq (https://groq.com) - Free tier, very fast
    - DeepSeek (https://deepseek.com) - Affordable
    - Fireworks AI (https://fireworks.ai) - Pay-per-token
    - Ollama (local) - Completely free, runs on your machine
    
    Set these environment variables:
        CRAWLEMOON_LLM_API_KEY - Your API key for the provider
        CRAWLEMOON_LLM_BASE_URL - API base URL (or use CRAWLEMOON_LLM_PROVIDER shortcut)
        CRAWLEMOON_LLM_PROVIDER - Shortcut: "openrouter", "groq", "together", "ollama", etc.
        CRAWLEMOON_LLM_MODEL - Model name (default: depends on provider)
    
    Example for OpenRouter (many free models):
        CRAWLEMOON_LLM_PROVIDER=openrouter
        CRAWLEMOON_LLM_API_KEY=sk-or-v1-xxx
        CRAWLEMOON_LLM_MODEL=meta-llama/llama-3.2-3b-instruct:free
    
    Example for Groq (free tier):
        CRAWLEMOON_LLM_PROVIDER=groq
        CRAWLEMOON_LLM_API_KEY=gsk_xxx
        CRAWLEMOON_LLM_MODEL=llama-3.1-8b-instant
    
    Example for local Ollama (completely free):
        CRAWLEMOON_LLM_PROVIDER=ollama
        CRAWLEMOON_LLM_MODEL=llama3.2
        # No API key needed for local Ollama
    """
    
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
    
    # LLM settings (for smart_extract and other LLM-enhanced tools)
    # Works with any OpenAI-compatible API: OpenRouter, Groq, Together, Ollama, etc.
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: str = "gpt-4o-mini"  # Default model, can be changed per provider
    llm_provider: Optional[str] = None  # Shortcut for common providers

    # Security: dangerous tool gating
    # When set, MCP clients must present this key (env CRAWLEMOON_API_KEY) to invoke tools.
    api_key: Optional[str] = None
    # Allow execute_js / execute_cdp / deobfuscate_js. Off by default; opt in explicitly.
    allow_dangerous_js: bool = False
    # Per-script ceilings for execute_js / execute_cdp.
    js_max_length: int = 50_000
    js_exec_timeout: float = 10.0

    # Proxy settings
    proxies: Optional[List[str]] = None
    proxies_file: Optional[str] = None
    proxy_default_scheme: str = "http"
    proxy_rotation: str = "round_robin"
    proxy_health_check_interval: int = 300
    proxy_fail_closed: bool = False
    
    @classmethod
    def from_env(cls) -> "MCPServerConfig":
        """Create config from environment variables."""
        # Determine LLM base URL from provider shortcut or explicit URL
        llm_provider = os.getenv("CRAWLEMOON_LLM_PROVIDER", "").lower()
        llm_base_url = os.getenv("CRAWLEMOON_LLM_BASE_URL")
        
        if not llm_base_url and llm_provider:
            llm_base_url = OPENAI_COMPATIBLE_PROVIDERS.get(llm_provider)
        
        # Get API key (check multiple env vars for compatibility)
        llm_api_key = (
            os.getenv("CRAWLEMOON_LLM_API_KEY") or
            os.getenv("OPENAI_API_KEY") or
            os.getenv("OPENROUTER_API_KEY") or
            os.getenv("GROQ_API_KEY") or
            os.getenv("TOGETHER_API_KEY")
        )
        
        # Default models per provider
        default_models = {
            "openrouter": "meta-llama/llama-3.2-3b-instruct:free",  # Free model
            "groq": "llama-3.1-8b-instant",  # Fast free model
            "together": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
            "ollama": "llama3.2",
            "deepseek": "deepseek-chat",
        }
        
        llm_model = os.getenv("CRAWLEMOON_LLM_MODEL")
        if not llm_model:
            llm_model = default_models.get(llm_provider, "gpt-4o-mini")
        
        return cls(
            navigation_timeout=float(os.getenv("CRAWLEMOON_NAV_TIMEOUT", "30.0")),
            request_timeout=float(os.getenv("CRAWLEMOON_REQ_TIMEOUT", "30.0")),
            operation_timeout=float(os.getenv("CRAWLEMOON_OP_TIMEOUT", "60.0")),
            headless=os.getenv("CRAWLEMOON_HEADLESS", "true").lower() == "true",
            browser_type=os.getenv("CRAWLEMOON_BROWSER", "chromium"),
            max_browser_pool_size=int(os.getenv("CRAWLEMOON_POOL_SIZE", "5")),
            max_retries=int(os.getenv("CRAWLEMOON_MAX_RETRIES", "3")),
            retry_delay=float(os.getenv("CRAWLEMOON_RETRY_DELAY", "1.0")),
            recording_storage_dir=os.getenv("CRAWLEMOON_RECORDING_DIR"),
            auto_save_recordings=os.getenv("CRAWLEMOON_AUTO_SAVE", "true").lower() == "true",
            wait_for_network_idle=os.getenv("CRAWLEMOON_WAIT_NETWORK", "true").lower() == "true",
            capture_screenshots=os.getenv("CRAWLEMOON_SCREENSHOTS", "false").lower() == "true",
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_provider=llm_provider or None,
            api_key=os.getenv("CRAWLEMOON_API_KEY") or None,
            allow_dangerous_js=os.getenv("CRAWLEMOON_ALLOW_DANGEROUS_JS", "false").lower() == "true",
            js_max_length=int(os.getenv("CRAWLEMOON_JS_MAX_LENGTH", "50000")),
            js_exec_timeout=float(os.getenv("CRAWLEMOON_JS_EXEC_TIMEOUT", "10.0")),
            proxies=[
                proxy.strip()
                for proxy in os.getenv("CRAWLEMOON_PROXIES", "").replace("\n", ",").split(",")
                if proxy.strip()
            ] or None,
            proxies_file=os.getenv("CRAWLEMOON_PROXIES_FILE") or None,
            proxy_default_scheme=os.getenv("CRAWLEMOON_PROXY_SCHEME", "http"),
            proxy_rotation=os.getenv("CRAWLEMOON_PROXY_ROTATION", "round_robin"),
            proxy_health_check_interval=int(os.getenv("CRAWLEMOON_PROXY_HEALTH_CHECK_INTERVAL", "300")),
            proxy_fail_closed=os.getenv("CRAWLEMOON_PROXY_FAIL_CLOSED", "false").lower() == "true",
        )
