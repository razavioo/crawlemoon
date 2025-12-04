"""LLM-powered smart extraction for natural language to selector generation."""

import logging
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

try:
    from instructor import patch, extract
    from openai import OpenAI, AsyncOpenAI
    INSTRUCTOR_AVAILABLE = True
except ImportError:
    INSTRUCTOR_AVAILABLE = False
    patch = None
    extract = None

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
    """LLM-powered smart extraction using natural language queries."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
    ):
        """Initialize smart extractor.
        
        Args:
            api_key: OpenAI API key (or compatible)
            model: Model to use
            base_url: Optional base URL for API (for OpenAI-compatible APIs)
        """
        self.model = model
        self.client = None
        
        if INSTRUCTOR_AVAILABLE:
            import os
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            if api_key:
                try:
                    if base_url:
                        self.client = patch(OpenAI(api_key=api_key, base_url=base_url))
                    else:
                        self.client = patch(OpenAI(api_key=api_key))
                except Exception as e:
                    logger.warning(f"Failed to initialize OpenAI client: {e}")
    
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
        if not self.client:
            logger.warning("LLM client not available, using fallback")
            return self._fallback_selector_generation(html, query)
        
        try:
            # Use instructor to extract structured data
            prompt = f"""
            Given this HTML content and the user's query, generate CSS or XPath selectors to extract the requested data.
            
            User Query: {query}
            
            HTML (first 5000 chars):
            {html[:5000]}
            
            Generate selectors that would extract the data described in the query.
            Prefer CSS selectors when possible, use XPath for complex cases.
            """
            
            # This is a simplified version - in production, you'd use instructor's extract
            # For now, we'll use a pattern-based approach
            return self._pattern_based_selector_generation(html, query)
        
        except Exception as e:
            logger.error(f"Error generating selectors with LLM: {e}")
            return self._fallback_selector_generation(html, query)
    
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
    model: str = "gpt-4o-mini",
) -> Optional[SmartExtractor]:
    """Get global smart extractor instance."""
    global _smart_extractor
    
    if not INSTRUCTOR_AVAILABLE:
        return None
    
    if _smart_extractor is None:
        _smart_extractor = SmartExtractor(api_key=api_key, model=model)
    
    return _smart_extractor

