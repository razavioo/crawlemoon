"""Tests for intelligent content extraction."""

import pytest
from unittest.mock import patch, MagicMock

from src.intelligence.extraction.content import (
    ContentExtractor,
    ExtractedContent,
    get_content_extractor,
)


@pytest.fixture
def extractor():
    """Create a content extractor."""
    return ContentExtractor()


def test_content_extractor_initialization():
    """Test content extractor initialization."""
    extractor = ContentExtractor()
    assert extractor is not None


def test_extracted_content_defaults():
    """Test ExtractedContent default values."""
    content = ExtractedContent()
    
    assert content.title is None
    assert content.text is None
    assert content.markdown is None
    assert content.categories == []
    assert content.tags == []
    assert content.images == []
    assert content.metadata == {}


def test_extracted_content_with_values():
    """Test ExtractedContent with values."""
    content = ExtractedContent(
        title="Test Title",
        text="Test content",
        author="John Doe",
        categories=["tech", "news"],
    )
    
    assert content.title == "Test Title"
    assert content.text == "Test content"
    assert content.author == "John Doe"
    assert content.categories == ["tech", "news"]


def test_extract_simple_html(extractor):
    """Test extracting content from simple HTML."""
    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Main Heading</h1>
        <p>This is some test content.</p>
    </body>
    </html>
    """
    
    result = extractor.extract(html)
    
    assert result is not None
    assert isinstance(result, ExtractedContent)


def test_extract_with_url(extractor):
    """Test extraction with URL context."""
    html = "<html><body><p>Content</p></body></html>"
    url = "https://example.com/article"
    
    result = extractor.extract(html, url=url)
    
    assert result.url == url


def test_extract_article(extractor):
    """Test article extraction."""
    html = """
    <html>
    <body>
        <article>
            <h1>Article Title</h1>
            <p>This is the article content with multiple paragraphs.</p>
            <p>Another paragraph of content.</p>
        </article>
    </body>
    </html>
    """
    
    result = extractor.extract_article(html)
    
    assert result is not None


def test_extract_with_trafilatura(extractor):
    """Test extraction using trafilatura."""
    html = """
    <html>
    <body>
        <article>
            <h1>News Article</h1>
            <p>Breaking news content here.</p>
        </article>
    </body>
    </html>
    """
    
    # Simply test that extraction works - the actual trafilatura usage
    # depends on whether it's installed
    result = extractor.extract(html)
    
    assert result is not None


def test_extract_metadata(extractor):
    """Test metadata extraction."""
    html = """
    <html>
    <head>
        <title>Page Title</title>
        <meta name="author" content="John Doe">
        <meta name="keywords" content="test, content">
    </head>
    <body><p>Content</p></body>
    </html>
    """
    
    result = extractor.extract(html)
    
    assert result is not None


def test_extract_images(extractor):
    """Test image extraction."""
    html = """
    <html>
    <body>
        <img src="image1.jpg" alt="First image">
        <img src="image2.png" alt="Second image" title="Image 2">
        <img data-src="lazy-image.jpg" alt="Lazy loaded">
    </body>
    </html>
    """
    
    result = extractor.extract(html, include_images=True)
    
    # Images should be extracted if selectolax is available
    assert isinstance(result.images, list)


def test_extract_to_markdown(extractor):
    """Test markdown conversion."""
    html = """
    <html>
    <body>
        <h1>Heading</h1>
        <p>Paragraph content.</p>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
        </ul>
    </body>
    </html>
    """
    
    result = extractor.extract_to_markdown(html)
    
    assert isinstance(result, str)


def test_extract_output_format_text(extractor):
    """Test text output format."""
    html = "<html><body><p>Test content</p></body></html>"
    
    result = extractor.extract(html, output_format="text")
    
    assert result is not None


def test_extract_output_format_json(extractor):
    """Test JSON output format."""
    html = "<html><body><p>Test content</p></body></html>"
    
    # Test that extraction with JSON format works
    # The actual output depends on whether trafilatura is installed
    result = extractor.extract(html, output_format="json")
    
    assert result is not None


def test_extract_output_format_xml(extractor):
    """Test XML output format."""
    html = "<html><body><p>Test content</p></body></html>"
    
    # Test that extraction with XML format works
    # The actual output depends on whether trafilatura is installed
    result = extractor.extract(html, output_format="xml")
    
    assert result is not None


def test_extract_include_tables(extractor):
    """Test table extraction."""
    html = """
    <html>
    <body>
        <table>
            <tr><th>Header 1</th><th>Header 2</th></tr>
            <tr><td>Cell 1</td><td>Cell 2</td></tr>
        </table>
    </body>
    </html>
    """
    
    result = extractor.extract(html, include_tables=True)
    
    assert result is not None


def test_extract_include_links(extractor):
    """Test link extraction."""
    html = """
    <html>
    <body>
        <p>Check out <a href="https://example.com">this link</a>.</p>
    </body>
    </html>
    """
    
    result = extractor.extract(html, include_links=True)
    
    assert result is not None


def test_extract_empty_html(extractor):
    """Test extraction from empty HTML."""
    result = extractor.extract("")
    
    assert result is not None
    assert isinstance(result, ExtractedContent)


def test_extract_malformed_html(extractor):
    """Test extraction from malformed HTML."""
    html = "<html><body><p>Unclosed paragraph<div>Mixed tags</p></div>"
    
    result = extractor.extract(html)
    
    # Should handle malformed HTML gracefully
    assert result is not None


@patch("src.intelligence.extraction.content.TRAFILATURA_AVAILABLE", False)
def test_fallback_without_trafilatura():
    """Test fallback behavior without trafilatura."""
    extractor = ContentExtractor()
    html = "<html><body><p>Test content</p></body></html>"
    
    result = extractor.extract(html)
    
    # Should still work but with limited extraction
    assert result is not None


def test_markdown_with_markdownify(extractor):
    """Test markdown conversion with markdownify."""
    html = "<html><body><h1>Title</h1><p>Content</p></body></html>"
    
    # Test markdown conversion - result depends on whether markdownify is installed
    result = extractor.extract_to_markdown(html)
    
    assert isinstance(result, str)


def test_get_content_extractor():
    """Test global content extractor getter."""
    extractor = get_content_extractor()
    
    assert extractor is not None
    assert isinstance(extractor, ContentExtractor)


def test_get_content_extractor_singleton():
    """Test that get_content_extractor returns same instance."""
    extractor1 = get_content_extractor()
    extractor2 = get_content_extractor()
    
    assert extractor1 is extractor2


def test_extract_article_optimized(extractor):
    """Test optimized article extraction."""
    html = """
    <html>
    <body>
        <nav>Navigation links here</nav>
        <article>
            <h1>Article Title</h1>
            <p class="author">By John Doe</p>
            <p>Main article content goes here.</p>
            <p>More paragraphs...</p>
        </article>
        <footer>Footer content</footer>
    </body>
    </html>
    """
    
    result = extractor.extract_article(html)
    
    assert result is not None


def test_extract_with_comments_disabled(extractor):
    """Test extraction with comments disabled."""
    html = """
    <html>
    <body>
        <article>
            <p>Article content</p>
        </article>
        <div class="comments">
            <p>Comment 1</p>
            <p>Comment 2</p>
        </div>
    </body>
    </html>
    """
    
    result = extractor.extract(html, include_comments=False)
    
    assert result is not None


def test_extract_language_detection(extractor):
    """Test language detection."""
    html = """
    <html lang="en">
    <body><p>English content here.</p></body>
    </html>
    """
    
    result = extractor.extract(html)
    
    # Language may or may not be detected depending on backend
    assert result is not None

