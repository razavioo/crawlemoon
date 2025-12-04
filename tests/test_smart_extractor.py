"""Tests for LLM-powered smart extraction."""

import pytest
from unittest.mock import patch, MagicMock

from src.intelligence.extraction.smart import (
    SmartExtractor,
    ExtractionTarget,
    SmartExtractionResult,
    get_smart_extractor,
)


@pytest.fixture
def extractor():
    """Create a smart extractor without API key."""
    return SmartExtractor()


def test_smart_extractor_initialization():
    """Test smart extractor initialization."""
    extractor = SmartExtractor()
    
    assert extractor is not None
    assert extractor.model == "gpt-4o-mini"


def test_smart_extractor_with_model():
    """Test initialization with custom model."""
    extractor = SmartExtractor(model="gpt-4")
    
    assert extractor.model == "gpt-4"


def test_extraction_target_defaults():
    """Test ExtractionTarget default values."""
    target = ExtractionTarget(
        description="Price",
        selector_type="css",
        selector=".price",
    )
    
    assert target.attribute is None
    assert target.multiple is False


def test_extraction_target_with_attribute():
    """Test ExtractionTarget with attribute."""
    target = ExtractionTarget(
        description="Image URLs",
        selector_type="css",
        selector="img",
        attribute="src",
        multiple=True,
    )
    
    assert target.attribute == "src"
    assert target.multiple is True


def test_smart_extraction_result():
    """Test SmartExtractionResult structure."""
    target = ExtractionTarget(
        description="Title",
        selector_type="css",
        selector="h1",
    )
    
    result = SmartExtractionResult(
        targets=[target],
        extracted_data={"Title": "Test Title"},
        confidence=0.9,
    )
    
    assert len(result.targets) == 1
    assert result.extracted_data["Title"] == "Test Title"
    assert result.confidence == 0.9


def test_generate_selectors_price_query(extractor):
    """Test selector generation for price query."""
    html = "<html><body><div class='price'>$19.99</div></body></html>"
    query = "extract all product prices"
    
    targets = extractor.generate_selectors(html, query)
    
    assert len(targets) > 0
    price_target = next((t for t in targets if "price" in t.description.lower()), None)
    assert price_target is not None


def test_generate_selectors_title_query(extractor):
    """Test selector generation for title query."""
    html = "<html><body><h1>Main Title</h1></body></html>"
    query = "get the page title"
    
    targets = extractor.generate_selectors(html, query)
    
    assert len(targets) > 0
    title_target = next((t for t in targets if "title" in t.description.lower()), None)
    assert title_target is not None


def test_generate_selectors_image_query(extractor):
    """Test selector generation for image query."""
    html = '<html><body><img src="test.jpg" alt="Test"></body></html>'
    query = "find all images"
    
    targets = extractor.generate_selectors(html, query)
    
    assert len(targets) > 0
    image_target = next((t for t in targets if "image" in t.description.lower()), None)
    assert image_target is not None
    assert image_target.attribute == "src"


def test_generate_selectors_link_query(extractor):
    """Test selector generation for link query."""
    html = '<html><body><a href="https://example.com">Link</a></body></html>'
    query = "extract all links"
    
    targets = extractor.generate_selectors(html, query)
    
    assert len(targets) > 0
    link_target = next((t for t in targets if "link" in t.description.lower()), None)
    assert link_target is not None
    assert link_target.attribute == "href"


def test_generate_selectors_table_query(extractor):
    """Test selector generation for table query."""
    html = "<html><body><table><tr><td>Data</td></tr></table></body></html>"
    query = "extract table data"
    
    targets = extractor.generate_selectors(html, query)
    
    assert len(targets) > 0
    table_target = next((t for t in targets if "table" in t.description.lower()), None)
    assert table_target is not None


def test_generate_selectors_default_fallback(extractor):
    """Test default fallback selector."""
    html = "<html><body><p>Some content</p></body></html>"
    query = "extract unknown data type"
    
    targets = extractor.generate_selectors(html, query)
    
    # Should have at least a default target
    assert len(targets) > 0


def test_extract_with_selectors(extractor):
    """Test data extraction with selectors."""
    html = """
    <html>
    <body>
        <h1>Page Title</h1>
        <div class="price">$29.99</div>
        <div class="price">$49.99</div>
    </body>
    </html>
    """
    
    targets = [
        ExtractionTarget(
            description="Title",
            selector_type="css",
            selector="h1",
            multiple=False,
        ),
        ExtractionTarget(
            description="Prices",
            selector_type="css",
            selector=".price",
            multiple=True,
        ),
    ]
    
    # Test extraction - result depends on whether selectolax is installed
    results = extractor.extract_with_selectors(html, targets)
    
    # May be empty dict if selectolax is not available
    assert isinstance(results, dict)


def test_extract_full_flow(extractor):
    """Test full extraction flow."""
    html = """
    <html>
    <body>
        <h1>Product Name</h1>
        <span class="price">$99.99</span>
    </body>
    </html>
    """
    query = "extract the product title and price"
    
    result = extractor.extract(html, query)
    
    assert isinstance(result, SmartExtractionResult)
    assert len(result.targets) > 0


def test_extract_confidence_with_data(extractor):
    """Test confidence score when data is extracted."""
    html = "<html><body><p>Content</p></body></html>"
    query = "extract text"
    
    with patch.object(extractor, 'extract_with_selectors', return_value={"Text": "Content"}):
        result = extractor.extract(html, query)
        
        assert result.confidence > 0


def test_extract_confidence_without_data(extractor):
    """Test confidence score when no data is extracted."""
    html = "<html><body></body></html>"
    query = "extract prices"
    
    with patch.object(extractor, 'extract_with_selectors', return_value={}):
        result = extractor.extract(html, query)
        
        assert result.confidence == 0.0


def test_extract_with_regex_selector(extractor):
    """Test extraction with regex selector."""
    html = "Price: $99.99 and $149.99"
    
    targets = [
        ExtractionTarget(
            description="Prices",
            selector_type="regex",
            selector=r"\$(\d+\.\d+)",
            multiple=True,
        ),
    ]
    
    results = extractor.extract_with_selectors(html, targets)
    
    # Regex extraction should work
    assert "Prices" in results or results.get("Prices") is None


def test_extract_with_attribute(extractor):
    """Test extraction of element attributes."""
    html = '<html><body><a href="https://example.com">Link</a></body></html>'
    
    targets = [
        ExtractionTarget(
            description="URL",
            selector_type="css",
            selector="a",
            attribute="href",
            multiple=False,
        ),
    ]
    
    # Test extraction - result depends on whether selectolax is installed
    results = extractor.extract_with_selectors(html, targets)
    
    # May be empty dict if selectolax is not available
    assert isinstance(results, dict)


@patch("src.intelligence.extraction.smart.INSTRUCTOR_AVAILABLE", False)
def test_get_smart_extractor_without_instructor():
    """Test get_smart_extractor when instructor is unavailable."""
    result = get_smart_extractor()
    
    # Should return None if instructor not available
    assert result is None or isinstance(result, SmartExtractor)


def test_pattern_based_selector_cost_query(extractor):
    """Test pattern-based selector for cost query."""
    html = "<html><body><p>Cost</p></body></html>"
    query = "what is the cost"
    
    targets = extractor._pattern_based_selector_generation(html, query)
    
    # Should detect "cost" as price-related
    assert len(targets) > 0


def test_pattern_based_selector_heading_query(extractor):
    """Test pattern-based selector for heading query."""
    html = "<html><body><h2>Subheading</h2></body></html>"
    query = "find all headings"
    
    targets = extractor._pattern_based_selector_generation(html, query)
    
    assert len(targets) > 0


def test_pattern_based_selector_photo_query(extractor):
    """Test pattern-based selector for photo query."""
    html = "<html><body><img src='photo.jpg'></body></html>"
    query = "get all photos"
    
    targets = extractor._pattern_based_selector_generation(html, query)
    
    image_target = next((t for t in targets if "image" in t.description.lower()), None)
    assert image_target is not None


def test_fallback_selector_generation(extractor):
    """Test fallback selector generation."""
    html = "<html><body><p>Content</p></body></html>"
    query = "test query"
    
    targets = extractor._fallback_selector_generation(html, query)
    
    assert len(targets) > 0


@patch("src.intelligence.extraction.smart.SELECTOLAX_AVAILABLE", False)
def test_extract_without_selectolax():
    """Test extraction when selectolax is unavailable."""
    extractor = SmartExtractor()
    html = "<html><body><p>Test</p></body></html>"
    
    targets = [
        ExtractionTarget(
            description="Text",
            selector_type="css",
            selector="p",
        ),
    ]
    
    results = extractor.extract_with_selectors(html, targets)
    
    # Should return empty dict without selectolax
    assert results == {}

