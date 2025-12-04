"""Intelligent content extraction using trafilatura and other libraries."""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False

try:
    from markdownify import markdownify as md
    MARKDOWNIFY_AVAILABLE = True
except ImportError:
    MARKDOWNIFY_AVAILABLE = False

try:
    from selectolax.parser import HTMLParser
    SELECTOLAX_AVAILABLE = True
except ImportError:
    SELECTOLAX_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContent:
    """Extracted content from a webpage."""
    
    title: Optional[str] = None
    text: Optional[str] = None
    markdown: Optional[str] = None
    html: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    url: Optional[str] = None
    language: Optional[str] = None
    categories: list = None
    tags: list = None
    images: list = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = []
        if self.tags is None:
            self.tags = []
        if self.images is None:
            self.images = []
        if self.metadata is None:
            self.metadata = {}


class ContentExtractor:
    """Extract clean content from web pages using multiple strategies."""
    
    def __init__(self):
        """Initialize content extractor."""
        if not TRAFILATURA_AVAILABLE:
            logger.warning("trafilatura not available, content extraction will be limited")
        if not MARKDOWNIFY_AVAILABLE:
            logger.warning("markdownify not available, markdown conversion will be limited")
        if not SELECTOLAX_AVAILABLE:
            logger.warning("selectolax not available, using fallback parser")
    
    def extract(
        self,
        html: str,
        url: Optional[str] = None,
        include_comments: bool = False,
        include_tables: bool = True,
        include_images: bool = True,
        include_links: bool = True,
        output_format: str = "text",
    ) -> ExtractedContent:
        """Extract content from HTML.
        
        Args:
            html: HTML content to extract from
            url: Optional URL for context
            include_comments: Include comments in extraction
            include_tables: Include tables in extraction
            include_images: Include image references
            include_links: Include links
            output_format: Output format (text, markdown, json, xml)
            
        Returns:
            ExtractedContent object
        """
        extracted = ExtractedContent(url=url)
        
        if TRAFILATURA_AVAILABLE:
            try:
                # Use trafilatura for main content extraction
                extracted_content = trafilatura.extract(
                    html,
                    url=url,
                    include_comments=include_comments,
                    include_tables=include_tables,
                    include_images=include_images,
                    include_links=include_links,
                    output_format=output_format,
                )
                
                if extracted_content:
                    if output_format == "json":
                        import json
                        data = json.loads(extracted_content)
                        extracted.text = data.get("text", "")
                        extracted.title = data.get("title")
                        extracted.author = data.get("author")
                        extracted.date = data.get("date")
                        extracted.language = data.get("language")
                        extracted.metadata = data.get("metadata", {})
                    elif output_format == "xml":
                        extracted.html = extracted_content
                    else:
                        extracted.text = extracted_content
                
                # Get metadata separately
                metadata = trafilatura.extract_metadata(html, url=url)
                if metadata:
                    if not extracted.title:
                        extracted.title = metadata.title
                    if not extracted.author:
                        extracted.author = metadata.author
                    if not extracted.date:
                        extracted.date = metadata.date
                    if not extracted.language:
                        extracted.language = metadata.language
                    if metadata.categories:
                        extracted.categories = metadata.categories
                    if metadata.tags:
                        extracted.tags = metadata.tags
                
            except Exception as e:
                logger.error(f"Error extracting with trafilatura: {e}")
        
        # Convert to markdown if requested and available
        if MARKDOWNIFY_AVAILABLE and extracted.html:
            try:
                extracted.markdown = md(
                    extracted.html,
                    heading_style="ATX",
                    bullets="•",
                )
            except Exception as e:
                logger.warning(f"Error converting to markdown: {e}")
        elif MARKDOWNIFY_AVAILABLE and html:
            try:
                extracted.markdown = md(
                    html,
                    heading_style="ATX",
                    bullets="•",
                )
            except Exception as e:
                logger.warning(f"Error converting to markdown: {e}")
        
        # Extract images using selectolax if available
        if SELECTOLAX_AVAILABLE and include_images:
            try:
                tree = HTMLParser(html)
                images = []
                for img in tree.css("img"):
                    src = img.attributes.get("src") or img.attributes.get("data-src")
                    if src:
                        images.append({
                            "src": src,
                            "alt": img.attributes.get("alt", ""),
                            "title": img.attributes.get("title", ""),
                        })
                extracted.images = images
            except Exception as e:
                logger.warning(f"Error extracting images: {e}")
        
        return extracted
    
    def extract_article(
        self,
        html: str,
        url: Optional[str] = None,
    ) -> ExtractedContent:
        """Extract article content (optimized for news/blog posts).
        
        Args:
            html: HTML content
            url: Optional URL for context
            
        Returns:
            ExtractedContent object
        """
        return self.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            include_images=True,
            include_links=True,
            output_format="text",
        )
    
    def extract_to_markdown(
        self,
        html: str,
        url: Optional[str] = None,
    ) -> str:
        """Extract content and convert to markdown (LLM-ready).
        
        Args:
            html: HTML content
            url: Optional URL for context
            
        Returns:
            Markdown string
        """
        extracted = self.extract(html, url=url, output_format="text")
        
        if extracted.markdown:
            return extracted.markdown
        
        # Fallback: convert HTML to markdown
        if MARKDOWNIFY_AVAILABLE:
            try:
                return md(html, heading_style="ATX", bullets="•")
            except Exception as e:
                logger.warning(f"Error converting to markdown: {e}")
        
        # Last resort: return text
        return extracted.text or ""


# Global instance
_content_extractor = None

def get_content_extractor() -> ContentExtractor:
    """Get global content extractor instance."""
    global _content_extractor
    if _content_extractor is None:
        _content_extractor = ContentExtractor()
    return _content_extractor

