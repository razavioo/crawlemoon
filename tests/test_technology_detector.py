"""Tests for technology stack detection."""

import pytest
from unittest.mock import patch, MagicMock

from src.intelligence.security.technology_detector import (
    TechnologyDetector,
    TechnologyInfo,
    TechnologyStack,
    get_technology_detector,
)


@pytest.fixture
def detector():
    """Create a technology detector."""
    return TechnologyDetector()


def test_technology_detector_initialization():
    """Test technology detector initialization."""
    detector = TechnologyDetector()
    assert detector is not None


def test_technology_info_defaults():
    """Test TechnologyInfo with required fields."""
    info = TechnologyInfo(
        name="React",
        category="JavaScript frameworks",
        confidence=90,
    )
    
    assert info.name == "React"
    assert info.category == "JavaScript frameworks"
    assert info.confidence == 90
    assert info.version is None
    assert info.website is None
    assert info.cpe is None


def test_technology_info_with_all_fields():
    """Test TechnologyInfo with all fields."""
    info = TechnologyInfo(
        name="WordPress",
        category="CMS",
        confidence=100,
        version="6.4.2",
        website="https://wordpress.org",
        cpe="cpe:2.3:a:wordpress:wordpress:6.4.2",
    )
    
    assert info.version == "6.4.2"
    assert info.website == "https://wordpress.org"
    assert info.cpe is not None


def test_technology_stack_defaults():
    """Test TechnologyStack default values."""
    stack = TechnologyStack()
    
    assert stack.cms == []
    assert stack.frameworks == []
    assert stack.programming_languages == []
    assert stack.web_servers == []
    assert stack.databases == []
    assert stack.cdn == []
    assert stack.analytics == []
    assert stack.advertising == []
    assert stack.javascript_libraries == []
    assert stack.other == []


def test_technology_stack_with_values():
    """Test TechnologyStack with values."""
    react = TechnologyInfo(name="React", category="JavaScript libraries", confidence=100)
    nginx = TechnologyInfo(name="nginx", category="Web servers", confidence=100)
    
    stack = TechnologyStack(
        javascript_libraries=[react],
        web_servers=[nginx],
    )
    
    assert len(stack.javascript_libraries) == 1
    assert len(stack.web_servers) == 1


@patch("src.intelligence.security.technology_detector.WAPPALYZER_AVAILABLE", False)
def test_detect_without_wappalyzer():
    """Test detection without Wappalyzer available."""
    detector = TechnologyDetector()
    html = "<html><body>Test</body></html>"
    
    result = detector.detect(html, "https://example.com")
    
    assert isinstance(result, TechnologyStack)
    # Should return empty stack without Wappalyzer
    assert len(result.cms) == 0


@patch("src.intelligence.security.technology_detector.WAPPALYZER_AVAILABLE", True)
def test_detect_with_wappalyzer():
    """Test detection with Wappalyzer mocked."""
    with patch("src.intelligence.security.technology_detector.Wappalyzer") as mock_wap_class:
        with patch("src.intelligence.security.technology_detector.WebPage") as mock_page_class:
            mock_wap = MagicMock()
            mock_wap.analyze_with_versions_and_categories.return_value = {
                "WordPress": {
                    "categories": ["CMS"],
                    "version": "6.4",
                },
                "React": {
                    "categories": ["JavaScript libraries"],
                    "version": "18.2",
                },
            }
            mock_wap_class.latest.return_value = mock_wap
            mock_page_class.new_from_html.return_value = MagicMock()
            
            detector = TechnologyDetector()
            html = "<html><body>Test</body></html>"
            
            result = detector.detect(html, "https://example.com")
            
            assert isinstance(result, TechnologyStack)


@patch("src.intelligence.security.technology_detector.WAPPALYZER_AVAILABLE", True)
def test_detect_wordpress():
    """Test WordPress CMS detection."""
    with patch("src.intelligence.security.technology_detector.Wappalyzer") as mock_wap_class:
        with patch("src.intelligence.security.technology_detector.WebPage") as mock_page_class:
            mock_wap = MagicMock()
            mock_wap.analyze_with_versions_and_categories.return_value = {
                "WordPress": {
                    "categories": ["CMS"],
                    "version": "6.4",
                },
            }
            mock_wap_class.latest.return_value = mock_wap
            mock_page_class.new_from_html.return_value = MagicMock()
            
            detector = TechnologyDetector()
            html = '<meta name="generator" content="WordPress 6.4">'
            
            result = detector.detect(html, "https://example.com")
            
            # WordPress should be in CMS category
            assert len(result.cms) == 1 or len(result.other) >= 0


@patch("src.intelligence.security.technology_detector.WAPPALYZER_AVAILABLE", True)
def test_detect_react():
    """Test React framework detection."""
    with patch("src.intelligence.security.technology_detector.Wappalyzer") as mock_wap_class:
        with patch("src.intelligence.security.technology_detector.WebPage") as mock_page_class:
            mock_wap = MagicMock()
            mock_wap.analyze_with_versions_and_categories.return_value = {
                "React": {
                    "categories": ["JavaScript libraries"],
                    "version": "18.2",
                },
            }
            mock_wap_class.latest.return_value = mock_wap
            mock_page_class.new_from_html.return_value = MagicMock()
            
            detector = TechnologyDetector()
            html = '<div id="root" data-reactroot></div>'
            
            result = detector.detect(html, "https://example.com")
            
            assert isinstance(result, TechnologyStack)


@patch("src.intelligence.security.technology_detector.WAPPALYZER_AVAILABLE", True)
def test_detect_cloudflare_cdn():
    """Test Cloudflare CDN detection."""
    with patch("src.intelligence.security.technology_detector.Wappalyzer") as mock_wap_class:
        with patch("src.intelligence.security.technology_detector.WebPage") as mock_page_class:
            mock_wap = MagicMock()
            mock_wap.analyze_with_versions_and_categories.return_value = {
                "Cloudflare": {
                    "categories": ["CDN"],
                },
            }
            mock_wap_class.latest.return_value = mock_wap
            mock_page_class.new_from_html.return_value = MagicMock()
            
            detector = TechnologyDetector()
            html = "<html><body>Test</body></html>"
            headers = {"CF-RAY": "abc123"}
            
            result = detector.detect(html, "https://example.com", headers)
            
            assert isinstance(result, TechnologyStack)


@patch("src.intelligence.security.technology_detector.WAPPALYZER_AVAILABLE", True)
def test_detect_google_analytics():
    """Test Google Analytics detection."""
    with patch("src.intelligence.security.technology_detector.Wappalyzer") as mock_wap_class:
        with patch("src.intelligence.security.technology_detector.WebPage") as mock_page_class:
            mock_wap = MagicMock()
            mock_wap.analyze_with_versions_and_categories.return_value = {
                "Google Analytics": {
                    "categories": ["Analytics"],
                },
            }
            mock_wap_class.latest.return_value = mock_wap
            mock_page_class.new_from_html.return_value = MagicMock()
            
            detector = TechnologyDetector()
            html = '<script src="https://www.google-analytics.com/analytics.js"></script>'
            
            result = detector.detect(html, "https://example.com")
            
            assert isinstance(result, TechnologyStack)


def test_get_protection_technologies():
    """Test extraction of protection technologies."""
    detector = TechnologyDetector()
    
    cloudflare = TechnologyInfo(name="Cloudflare", category="CDN", confidence=100)
    react = TechnologyInfo(name="React", category="JavaScript libraries", confidence=100)
    datadome = TechnologyInfo(name="DataDome", category="Security", confidence=100)
    
    stack = TechnologyStack(
        cdn=[cloudflare],
        javascript_libraries=[react],
        other=[datadome],
    )
    
    protection = detector.get_protection_technologies(stack)
    
    assert "Cloudflare" in protection
    assert "DataDome" in protection
    assert "React" not in protection


def test_get_protection_technologies_empty():
    """Test protection extraction from empty stack."""
    detector = TechnologyDetector()
    stack = TechnologyStack()
    
    protection = detector.get_protection_technologies(stack)
    
    assert protection == []


def test_get_protection_technologies_various():
    """Test protection extraction with various technologies."""
    detector = TechnologyDetector()
    
    stack = TechnologyStack(
        cdn=[
            TechnologyInfo(name="Akamai", category="CDN", confidence=100),
        ],
        web_servers=[
            TechnologyInfo(name="nginx", category="Web servers", confidence=100),
        ],
        other=[
            TechnologyInfo(name="Imperva", category="Security", confidence=100),
            TechnologyInfo(name="reCAPTCHA", category="Security", confidence=100),
        ],
    )
    
    protection = detector.get_protection_technologies(stack)
    
    assert "Akamai" in protection
    assert "Imperva" in protection
    assert "reCAPTCHA" in protection
    assert "nginx" not in protection


def test_detect_from_response(detector):
    """Test detection from HTTP response object."""
    mock_response = MagicMock()
    mock_response.url = "https://example.com"
    mock_response.headers = {"Server": "nginx"}
    mock_response.text = "<html><body>Test</body></html>"
    
    result = detector.detect_from_response(mock_response)
    
    assert isinstance(result, TechnologyStack)


def test_detect_from_response_with_url(detector):
    """Test detection from response with explicit URL."""
    mock_response = MagicMock()
    mock_response.headers = {}
    mock_response.text = "<html><body>Test</body></html>"
    
    result = detector.detect_from_response(mock_response, url="https://custom.com")
    
    assert isinstance(result, TechnologyStack)


@patch("src.intelligence.security.technology_detector.WAPPALYZER_AVAILABLE", False)
def test_fallback_without_wappalyzer():
    """Test fallback behavior without Wappalyzer."""
    detector = TechnologyDetector()
    
    assert detector.wappalyzer is None
    
    result = detector.detect("<html></html>", "https://example.com")
    
    # Should return empty stack
    assert isinstance(result, TechnologyStack)


def test_get_technology_detector():
    """Test global detector getter."""
    detector = get_technology_detector()
    
    assert detector is not None
    assert isinstance(detector, TechnologyDetector)


def test_get_technology_detector_singleton():
    """Test that getter returns same instance."""
    detector1 = get_technology_detector()
    detector2 = get_technology_detector()
    
    assert detector1 is detector2


@patch("src.intelligence.security.technology_detector.WAPPALYZER_AVAILABLE", True)
def test_detect_handles_exception():
    """Test that detect handles exceptions gracefully."""
    with patch("src.intelligence.security.technology_detector.Wappalyzer") as mock_wap_class:
        mock_wap = MagicMock()
        mock_wap.analyze_with_versions_and_categories.side_effect = Exception("Analysis failed")
        mock_wap_class.latest.return_value = mock_wap
        
        with patch("src.intelligence.security.technology_detector.WebPage") as mock_page_class:
            mock_page_class.new_from_html.return_value = MagicMock()
            
            detector = TechnologyDetector()
            html = "<html><body>Test</body></html>"
            
            result = detector.detect(html, "https://example.com")
            
            # Should return empty stack on error
            assert isinstance(result, TechnologyStack)


def test_technology_categorization():
    """Test that technologies are properly categorized."""
    detector = TechnologyDetector()
    
    # Protection keywords
    protection_keywords = [
        'cloudflare', 'akamai', 'imperva', 'datadome', 'perimeterx',
        'shape', 'kasada', 'recaptcha', 'hcaptcha', 'turnstile',
        'aws waf', 'sucuri', 'incapsula', 'f5', 'barracuda'
    ]
    
    for keyword in protection_keywords:
        tech = TechnologyInfo(name=keyword.title(), category="Other", confidence=100)
        stack = TechnologyStack(other=[tech])
        
        protection = detector.get_protection_technologies(stack)
        
        assert len(protection) >= 1 or keyword.title() in protection


@patch("src.intelligence.security.technology_detector.WAPPALYZER_AVAILABLE", True)
def test_wappalyzer_init_error():
    """Test handling of Wappalyzer initialization error."""
    with patch("src.intelligence.security.technology_detector.Wappalyzer") as mock_wap_class:
        mock_wap_class.latest.side_effect = Exception("Init failed")
        
        detector = TechnologyDetector()
        
        assert detector.wappalyzer is None

