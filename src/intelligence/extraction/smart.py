"""Smart extraction for natural language to selector generation.

This module provides pattern-based extraction that works without any paid APIs.
Optionally supports LLM enhancement via any OpenAI-compatible API:
- OpenRouter (many free models available)
- Groq (free tier, very fast)
- Together AI (free tier)
- Ollama (local, completely free)
- And more...

Configure via environment variables:
    CRAWILFY_LLM_PROVIDER=openrouter  # or groq, together, ollama, etc.
    CRAWILFY_LLM_API_KEY=your-api-key
    CRAWILFY_LLM_MODEL=meta-llama/llama-3.2-3b-instruct:free  # Optional
"""

import logging
import os
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Optional LLM support - not required for basic functionality
LLM_AVAILABLE = False
try:
    from openai import OpenAI, AsyncOpenAI
    LLM_AVAILABLE = True
except ImportError:
    OpenAI = None
    AsyncOpenAI = None

# Optional instructor for structured output (enhances LLM extraction)
INSTRUCTOR_AVAILABLE = False
try:
    from instructor import patch
    INSTRUCTOR_AVAILABLE = True
except ImportError:
    patch = None

try:
    from selectolax.parser import HTMLParser
    SELECTOLAX_AVAILABLE = True
except ImportError:
    SELECTOLAX_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ExtractionTarget:
    """Target for data extraction."""
    
    description: str
    selector_type: str  # css, xpath, text, regex
    selector: str
    attribute: Optional[str] = None  # For extracting attributes
    multiple: bool = False  # Extract multiple items or single


@dataclass
class SmartExtractionResult:
    """Result of smart extraction."""
    
    targets: List[ExtractionTarget]
    extracted_data: Dict[str, Any]
    confidence: float = 0.0


class SmartExtractor:
    """Smart extraction using pattern-based natural language queries.
    
    This extractor works without any paid APIs using pattern matching.
    Optionally supports LLM enhancement via any OpenAI-compatible API:
    
    Supported providers (via CRAWILFY_LLM_PROVIDER env var):
    - openrouter: Many free models (meta-llama/llama-3.2-3b-instruct:free)
    - groq: Free tier, very fast (llama-3.1-8b-instant)
    - together: Free tier (meta-llama/Llama-3.2-3B-Instruct-Turbo)
    - ollama: Local, completely free (llama3.2)
    - openai: Paid (gpt-4o-mini)
    - deepseek: Affordable (deepseek-chat)
    - Any custom OpenAI-compatible endpoint
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        """Initialize smart extractor.
        
        Args:
            api_key: API key for LLM provider (optional for local Ollama)
            model: Model to use (auto-selected based on provider if not specified)
            base_url: API base URL (auto-selected based on provider if not specified)
            provider: Provider shortcut: "openrouter", "groq", "together", "ollama", etc.
        """
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.client = None
        self.llm_enabled = False
        
        # Resolve provider settings
        self._resolve_provider_settings(api_key, model, base_url, provider)
        
        # Try to initialize LLM client
        self._initialize_llm_client()
        
        if self.llm_enabled:
            logger.info(f"LLM-enhanced extraction enabled (provider: {self.provider or 'custom'}, model: {self.model})")
        else:
            logger.info("Using pattern-based extraction (no LLM configured - still works great!)")
    
    def _resolve_provider_settings(
        self,
        api_key: Optional[str],
        model: Optional[str],
        base_url: Optional[str],
        provider: Optional[str],
    ):
        """Resolve provider settings from environment or parameters."""
        # Provider shortcuts to base URLs
        provider_urls = {
            "openai": "https://api.openai.com/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "together": "https://api.together.xyz/v1",
            "groq": "https://api.groq.com/openai/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "mistral": "https://api.mistral.ai/v1",
            "fireworks": "https://api.fireworks.ai/inference/v1",
            "perplexity": "https://api.perplexity.ai",
            "anyscale": "https://api.endpoints.anyscale.com/v1",
            "ollama": "http://localhost:11434/v1",
        }
        
        # Default models per provider (prefer free/cheap options)
        default_models = {
            "openrouter": "meta-llama/llama-3.2-3b-instruct:free",
            "groq": "llama-3.1-8b-instant",
            "together": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
            "ollama": "llama3.2",
            "deepseek": "deepseek-chat",
            "fireworks": "accounts/fireworks/models/llama-v3p1-8b-instruct",
            "openai": "gpt-4o-mini",
        }
        
        # Check environment variables
        env_provider = os.getenv("CRAWILFY_LLM_PROVIDER", "").lower()
        env_base_url = os.getenv("CRAWILFY_LLM_BASE_URL")
        env_model = os.getenv("CRAWILFY_LLM_MODEL")
        env_api_key = (
            os.getenv("CRAWILFY_LLM_API_KEY") or
            os.getenv("OPENAI_API_KEY") or
            os.getenv("OPENROUTER_API_KEY") or
            os.getenv("GROQ_API_KEY") or
            os.getenv("TOGETHER_API_KEY")
        )
        
        # Use parameters, fall back to environment
        self.provider = provider or env_provider or None
        self.api_key = api_key or env_api_key
        
        # Resolve base URL
        if base_url:
            self.base_url = base_url
        elif env_base_url:
            self.base_url = env_base_url
        elif self.provider and self.provider in provider_urls:
            self.base_url = provider_urls[self.provider]
        else:
            self.base_url = None
        
        # Resolve model
        if model:
            self.model = model
        elif env_model:
            self.model = env_model
        elif self.provider and self.provider in default_models:
            self.model = default_models[self.provider]
        else:
            self.model = "gpt-4o-mini"
    
    def _initialize_llm_client(self):
        """Initialize the LLM client if possible."""
        if not LLM_AVAILABLE:
            logger.debug("OpenAI library not installed - LLM features disabled")
            return
        
        # Ollama doesn't require an API key
        is_ollama = self.provider == "ollama" or (self.base_url and "localhost" in self.base_url)
        
        if not self.api_key and not is_ollama:
            logger.debug("No API key configured - LLM features disabled")
            return
        
        try:
            # Create OpenAI-compatible client
            client_kwargs = {}
            if self.api_key:
                client_kwargs["api_key"] = self.api_key
            elif is_ollama:
                client_kwargs["api_key"] = "ollama"  # Ollama needs a placeholder
            
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            
            client = OpenAI(**client_kwargs)
            
            # Optionally wrap with instructor for structured output
            if INSTRUCTOR_AVAILABLE and patch:
                self.client = patch(client)
            else:
                self.client = client
            
            self.llm_enabled = True
            
        except Exception as e:
            logger.warning(f"Failed to initialize LLM client: {e}")
            self.llm_enabled = False
    
    def generate_selectors(
        self,
        html: str,
        query: str,
    ) -> List[ExtractionTarget]:
        """Generate CSS/XPath selectors from natural language query.
        
        Args:
            html: HTML content
            query: Natural language query (e.g., "extract all product prices")
            
        Returns:
            List of ExtractionTarget objects
        """
        if not self.llm_enabled or not self.client:
            return self._pattern_based_selector_generation(html, query)
        
        try:
            # Use LLM to generate better selectors
            return self._llm_selector_generation(html, query)
        except Exception as e:
            logger.warning(f"LLM selector generation failed, using pattern fallback: {e}")
            return self._pattern_based_selector_generation(html, query)
    
    def _llm_selector_generation(
        self,
        html: str,
        query: str,
    ) -> List[ExtractionTarget]:
        """Generate selectors using LLM for better accuracy."""
        # Truncate HTML to fit context window
        html_sample = html[:8000] if len(html) > 8000 else html
        
        prompt = f"""Analyze this HTML and generate CSS selectors to extract: {query}

HTML:
{html_sample}

Respond with a JSON array of objects with these fields:
- description: what this selector extracts
- selector: the CSS selector
- multiple: true if multiple items, false for single
- attribute: attribute name if extracting an attribute (like "href", "src"), null for text content

Example response:
[{{"description": "Product titles", "selector": "h2.product-title", "multiple": true, "attribute": null}}]

Only respond with the JSON array, no other text."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000,
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON response
            import json
            # Handle markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            
            selectors_data = json.loads(content)
            
            targets = []
            for item in selectors_data:
                targets.append(ExtractionTarget(
                    description=item.get("description", "Unknown"),
                    selector_type="css",
                    selector=item.get("selector", "body"),
                    attribute=item.get("attribute"),
                    multiple=item.get("multiple", False),
                ))
            
            return targets if targets else self._pattern_based_selector_generation(html, query)
            
        except Exception as e:
            logger.warning(f"LLM response parsing failed: {e}")
            return self._pattern_based_selector_generation(html, query)
    
    def _pattern_based_selector_generation(
        self,
        html: str,
        query: str,
    ) -> List[ExtractionTarget]:
        """Generate selectors using pattern matching (fallback).
        
        Args:
            html: HTML content
            query: Natural language query
            
        Returns:
            List of ExtractionTarget objects
        """
        targets = []
        query_lower = query.lower()
        
        # Common patterns
        if "price" in query_lower or "cost" in query_lower:
            # Look for price patterns
            targets.append(ExtractionTarget(
                description="Price",
                selector_type="css",
                selector=".price, [class*='price'], [data-price]",
                multiple=True,
            ))
        
        if "title" in query_lower or "heading" in query_lower:
            targets.append(ExtractionTarget(
                description="Title",
                selector_type="css",
                selector="h1, h2, .title, [class*='title']",
                multiple=False,
            ))
        
        if "image" in query_lower or "photo" in query_lower:
            targets.append(ExtractionTarget(
                description="Images",
                selector_type="css",
                selector="img",
                attribute="src",
                multiple=True,
            ))
        
        if "link" in query_lower or "url" in query_lower:
            targets.append(ExtractionTarget(
                description="Links",
                selector_type="css",
                selector="a",
                attribute="href",
                multiple=True,
            ))
        
        if "table" in query_lower:
            targets.append(ExtractionTarget(
                description="Table data",
                selector_type="css",
                selector="table",
                multiple=True,
            ))
        
        # Default: extract all text
        if not targets:
            targets.append(ExtractionTarget(
                description="Text content",
                selector_type="css",
                selector="body",
                multiple=False,
            ))
        
        return targets
    
    def _fallback_selector_generation(
        self,
        html: str,
        query: str,
    ) -> List[ExtractionTarget]:
        """Fallback selector generation without LLM."""
        return self._pattern_based_selector_generation(html, query)
    
    def extract_with_selectors(
        self,
        html: str,
        targets: List[ExtractionTarget],
    ) -> Dict[str, Any]:
        """Extract data using generated selectors.
        
        Args:
            html: HTML content
            targets: List of ExtractionTarget objects
            
        Returns:
            Dictionary of extracted data
        """
        if not SELECTOLAX_AVAILABLE:
            logger.warning("selectolax not available, extraction will be limited")
            return {}
        
        results = {}
        tree = HTMLParser(html)
        
        for target in targets:
            try:
                if target.selector_type == "css":
                    elements = tree.css(target.selector)
                    
                    if target.multiple:
                        values = []
                        for elem in elements:
                            if target.attribute:
                                value = elem.attributes.get(target.attribute, "")
                            else:
                                value = elem.text(deep=True, separator=" ").strip()
                            if value:
                                values.append(value)
                        results[target.description] = values
                    else:
                        if elements:
                            elem = elements[0]
                            if target.attribute:
                                value = elem.attributes.get(target.attribute, "")
                            else:
                                value = elem.text(deep=True, separator=" ").strip()
                            results[target.description] = value
                
                elif target.selector_type == "xpath":
                    # XPath support would require lxml
                    logger.warning("XPath selectors not yet implemented")
                
                elif target.selector_type == "regex":
                    if target.multiple:
                        matches = re.findall(target.selector, html)
                        results[target.description] = matches
                    else:
                        match = re.search(target.selector, html)
                        results[target.description] = match.group(1) if match else None
            
            except Exception as e:
                logger.error(f"Error extracting with selector {target.selector}: {e}")
                results[target.description] = None
        
        return results
    
    def extract(
        self,
        html: str,
        query: str,
    ) -> SmartExtractionResult:
        """Extract data from HTML using natural language query.
        
        Args:
            html: HTML content
            query: Natural language query
            
        Returns:
            SmartExtractionResult object
        """
        # Generate selectors
        targets = self.generate_selectors(html, query)
        
        # Extract data
        extracted_data = self.extract_with_selectors(html, targets)
        
        # Calculate confidence (simplified)
        confidence = 0.8 if extracted_data else 0.0
        
        return SmartExtractionResult(
            targets=targets,
            extracted_data=extracted_data,
            confidence=confidence,
        )


# Global instance
_smart_extractor = None

def get_smart_extractor(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: Optional[str] = None,
) -> SmartExtractor:
    """Get global smart extractor instance.
    
    Always returns a working extractor using pattern-based extraction.
    LLM enhancement is optional and enabled when configured.
    
    Configuration via environment variables:
        CRAWILFY_LLM_PROVIDER - Provider: openrouter, groq, together, ollama, etc.
        CRAWILFY_LLM_API_KEY - API key for the provider
        CRAWILFY_LLM_BASE_URL - Custom API base URL (optional if using provider)
        CRAWILFY_LLM_MODEL - Model name (optional, auto-selected per provider)
    
    Free/cheap provider recommendations:
        - openrouter: Free models like meta-llama/llama-3.2-3b-instruct:free
        - groq: Free tier with llama-3.1-8b-instant
        - ollama: Local, completely free
    
    Args:
        api_key: API key (overrides environment)
        model: Model name (overrides environment)
        base_url: API base URL (overrides environment)
        provider: Provider shortcut (overrides environment)
    
    Returns:
        SmartExtractor instance (always works, LLM optional)
    """
    global _smart_extractor
    
    if _smart_extractor is None:
        _smart_extractor = SmartExtractor(
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider=provider,
        )
    
    return _smart_extractor


def reset_smart_extractor():
    """Reset the global smart extractor (useful for reconfiguration)."""
    global _smart_extractor
    _smart_extractor = None

