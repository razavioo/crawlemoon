"""Configuration for MCP server."""

from dataclasses import dataclass
from typing import Optional
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
        CRAWILFY_LLM_API_KEY - Your API key for the provider
        CRAWILFY_LLM_BASE_URL - API base URL (or use CRAWILFY_LLM_PROVIDER shortcut)
        CRAWILFY_LLM_PROVIDER - Shortcut: "openrouter", "groq", "together", "ollama", etc.
        CRAWILFY_LLM_MODEL - Model name (default: depends on provider)
    
    Example for OpenRouter (many free models):
        CRAWILFY_LLM_PROVIDER=openrouter
        CRAWILFY_LLM_API_KEY=sk-or-v1-xxx
        CRAWILFY_LLM_MODEL=meta-llama/llama-3.2-3b-instruct:free
    
    Example for Groq (free tier):
        CRAWILFY_LLM_PROVIDER=groq
        CRAWILFY_LLM_API_KEY=gsk_xxx
        CRAWILFY_LLM_MODEL=llama-3.1-8b-instant
    
    Example for local Ollama (completely free):
        CRAWILFY_LLM_PROVIDER=ollama
        CRAWILFY_LLM_MODEL=llama3.2
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
    
    @classmethod
    def from_env(cls) -> "MCPServerConfig":
        """Create config from environment variables."""
        # Determine LLM base URL from provider shortcut or explicit URL
        llm_provider = os.getenv("CRAWILFY_LLM_PROVIDER", "").lower()
        llm_base_url = os.getenv("CRAWILFY_LLM_BASE_URL")
        
        if not llm_base_url and llm_provider:
            llm_base_url = OPENAI_COMPATIBLE_PROVIDERS.get(llm_provider)
        
        # Get API key (check multiple env vars for compatibility)
        llm_api_key = (
            os.getenv("CRAWILFY_LLM_API_KEY") or
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
        
        llm_model = os.getenv("CRAWILFY_LLM_MODEL")
        if not llm_model:
            llm_model = default_models.get(llm_provider, "gpt-4o-mini")
        
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
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_provider=llm_provider or None,
        )




