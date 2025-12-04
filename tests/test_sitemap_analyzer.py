"""Tests for sitemap and robots.txt analyzer."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.intelligence.network.sitemap import (
    SitemapAnalyzer,
    SitemapEntry,
    SitemapAnalysis,
    RobotsRule,
    RobotsAnalysis,
)


@pytest.fixture
def analyzer():
    """Create a sitemap analyzer."""
    return SitemapAnalyzer()


def test_sitemap_entry_defaults():
    """Test SitemapEntry default values."""
    entry = SitemapEntry(url="https://example.com/page1")
    
    assert entry.url == "https://example.com/page1"
    assert entry.lastmod is None
    assert entry.changefreq is None
    assert entry.priority is None


def test_sitemap_entry_with_values():
    """Test SitemapEntry with all values."""
    entry = SitemapEntry(
        url="https://example.com/page1",
        lastmod="2024-01-01",
        changefreq="daily",
        priority=0.8,
    )
    
    assert entry.lastmod == "2024-01-01"
    assert entry.changefreq == "daily"
    assert entry.priority == 0.8


def test_sitemap_analysis_defaults():
    """Test SitemapAnalysis default values."""
    analysis = SitemapAnalysis(sitemap_url="https://example.com/sitemap.xml")
    
    assert analysis.entries == []
    assert analysis.sitemap_type == "sitemap"
    assert analysis.total_urls == 0
    assert analysis.errors == []


def test_robots_rule_defaults():
    """Test RobotsRule default values."""
    rule = RobotsRule(user_agent="*")
    
    assert rule.user_agent == "*"
    assert rule.allow == []
    assert rule.disallow == []
    assert rule.crawl_delay is None


def test_robots_analysis_defaults():
    """Test RobotsAnalysis default values."""
    analysis = RobotsAnalysis(robots_url="https://example.com/robots.txt")
    
    assert analysis.rules == []
    assert analysis.sitemaps == []
    assert analysis.valid is True
    assert analysis.errors == []


@pytest.mark.asyncio
async def test_analyze_sitemap_basic(analyzer):
    """Test basic sitemap parsing."""
    sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url>
            <loc>https://example.com/page1</loc>
            <lastmod>2024-01-01</lastmod>
            <changefreq>daily</changefreq>
            <priority>0.8</priority>
        </url>
        <url>
            <loc>https://example.com/page2</loc>
        </url>
    </urlset>
    """
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.text = sitemap_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await analyzer.analyze_sitemap("https://example.com/sitemap.xml")
        
        assert result.sitemap_type == "sitemap"
        assert result.total_urls == 2
        assert len(result.entries) == 2
        assert result.entries[0].url == "https://example.com/page1"
        assert result.entries[0].lastmod == "2024-01-01"
        assert result.entries[0].priority == 0.8


@pytest.mark.asyncio
async def test_analyze_sitemap_index(analyzer):
    """Test sitemap index parsing."""
    sitemap_index_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap>
            <loc>https://example.com/sitemap1.xml</loc>
        </sitemap>
    </sitemapindex>
    """
    
    nested_sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url>
            <loc>https://example.com/page1</loc>
        </url>
    </urlset>
    """
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response_index = MagicMock()
        mock_response_index.text = sitemap_index_xml
        mock_response_index.raise_for_status = MagicMock()
        
        mock_response_nested = MagicMock()
        mock_response_nested.text = nested_sitemap_xml
        mock_response_nested.raise_for_status = MagicMock()
        
        mock_get = AsyncMock(side_effect=[mock_response_index, mock_response_nested])
        mock_client.return_value.__aenter__.return_value.get = mock_get
        
        result = await analyzer.analyze_sitemap("https://example.com/sitemap_index.xml")
        
        assert result.sitemap_type == "sitemap_index"


@pytest.mark.asyncio
async def test_analyze_rss_as_sitemap(analyzer):
    """Test RSS feed parsing as sitemap."""
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item>
                <link>https://example.com/post1</link>
            </item>
            <item>
                <link>https://example.com/post2</link>
            </item>
        </channel>
    </rss>
    """
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.text = rss_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await analyzer.analyze_sitemap("https://example.com/feed.xml")
        
        assert result.sitemap_type == "rss"
        assert result.total_urls == 2


@pytest.mark.asyncio
async def test_analyze_robots(analyzer):
    """Test robots.txt parsing."""
    robots_txt = """
    User-agent: *
    Allow: /
    Disallow: /admin/
    Disallow: /private/
    Crawl-delay: 10
    
    User-agent: Googlebot
    Allow: /
    
    Sitemap: https://example.com/sitemap.xml
    """
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.text = robots_txt
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await analyzer.analyze_robots("https://example.com")
        
        assert result.valid is True
        assert len(result.rules) >= 1
        assert "https://example.com/sitemap.xml" in result.sitemaps


@pytest.mark.asyncio
async def test_analyze_robots_disallow_rules(analyzer):
    """Test robots.txt disallow rules parsing."""
    robots_txt = """
    User-agent: *
    Disallow: /admin/
    Disallow: /private/
    Disallow: /temp/
    """
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.text = robots_txt
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await analyzer.analyze_robots("https://example.com")
        
        # Find the * user agent rule
        wildcard_rule = next((r for r in result.rules if r.user_agent == "*"), None)
        assert wildcard_rule is not None
        assert "/admin/" in wildcard_rule.disallow
        assert "/private/" in wildcard_rule.disallow


def test_check_url_allowed_basic(analyzer):
    """Test URL allowance checking."""
    analysis = RobotsAnalysis(
        robots_url="https://example.com/robots.txt",
        rules=[
            RobotsRule(
                user_agent="*",
                allow=["/public/"],
                disallow=["/admin/", "/private/"],
            ),
        ],
    )
    
    assert analyzer.check_url_allowed(analysis, "https://example.com/public/page") is True
    assert analyzer.check_url_allowed(analysis, "https://example.com/admin/dashboard") is False
    assert analyzer.check_url_allowed(analysis, "https://example.com/home") is True


def test_check_url_allowed_specific_allow(analyzer):
    """Test URL allowance with specific allow overriding disallow."""
    analysis = RobotsAnalysis(
        robots_url="https://example.com/robots.txt",
        rules=[
            RobotsRule(
                user_agent="*",
                allow=["/admin/public/"],
                disallow=["/admin/"],
            ),
        ],
    )
    
    # /admin/public/ should be allowed even though /admin/ is disallowed
    assert analyzer.check_url_allowed(analysis, "https://example.com/admin/public/page") is True
    assert analyzer.check_url_allowed(analysis, "https://example.com/admin/secret") is False


def test_check_url_allowed_no_rules(analyzer):
    """Test URL allowance when no rules exist."""
    analysis = RobotsAnalysis(
        robots_url="https://example.com/robots.txt",
        rules=[],
    )
    
    # No rules = everything allowed
    assert analyzer.check_url_allowed(analysis, "https://example.com/anything") is True


def test_check_url_allowed_specific_user_agent(analyzer):
    """Test URL allowance with specific user agent."""
    analysis = RobotsAnalysis(
        robots_url="https://example.com/robots.txt",
        rules=[
            RobotsRule(
                user_agent="Googlebot",
                allow=["/"],
                disallow=[],
            ),
            RobotsRule(
                user_agent="*",
                allow=[],
                disallow=["/admin/"],
            ),
        ],
    )
    
    # Googlebot should be allowed
    assert analyzer.check_url_allowed(analysis, "https://example.com/admin/", "Googlebot") is True
    # Other bots should be disallowed
    assert analyzer.check_url_allowed(analysis, "https://example.com/admin/", "*") is False


@pytest.mark.asyncio
async def test_analyze_robots_crawl_delay(analyzer):
    """Test crawl delay extraction."""
    robots_txt = """
    User-agent: *
    Crawl-delay: 5
    """
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.text = robots_txt
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await analyzer.analyze_robots("https://example.com")
        
        wildcard_rule = next((r for r in result.rules if r.user_agent == "*"), None)
        assert wildcard_rule is not None
        assert wildcard_rule.crawl_delay == 5.0


@pytest.mark.asyncio
async def test_analyze_robots_multiple_sitemaps(analyzer):
    """Test extraction of multiple sitemaps from robots.txt."""
    robots_txt = """
    User-agent: *
    Disallow:
    
    Sitemap: https://example.com/sitemap.xml
    Sitemap: https://example.com/sitemap-news.xml
    Sitemap: https://example.com/sitemap-images.xml
    """
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.text = robots_txt
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await analyzer.analyze_robots("https://example.com")
        
        assert len(result.sitemaps) == 3


@pytest.mark.asyncio
async def test_analyze_invalid_sitemap(analyzer):
    """Test handling of invalid sitemap XML."""
    invalid_xml = "Not valid XML at all <broken>"
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.text = invalid_xml
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await analyzer.analyze_sitemap("https://example.com/sitemap.xml")
        
        # Should have error logged
        assert len(result.errors) > 0


@pytest.mark.asyncio
async def test_analyze_robots_not_found(analyzer):
    """Test handling of missing robots.txt."""
    import httpx
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_response)
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=error)
        
        result = await analyzer.analyze_robots("https://example.com")
        
        assert "not found" in result.errors[0].lower() or len(result.errors) > 0


@pytest.mark.asyncio
async def test_analyze_sitemap_network_error(analyzer):
    """Test handling of network errors."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=Exception("Network error")
        )
        
        result = await analyzer.analyze_sitemap("https://example.com/sitemap.xml")
        
        assert len(result.errors) > 0


@pytest.mark.asyncio
async def test_analyze_robots_comments(analyzer):
    """Test robots.txt with comments."""
    robots_txt = """
    # This is a comment
    User-agent: * # inline comment
    Disallow: /admin/ # admin area
    
    # Another comment
    Sitemap: https://example.com/sitemap.xml
    """
    
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.text = robots_txt
        mock_response.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
        
        result = await analyzer.analyze_robots("https://example.com")
        
        # Should parse correctly ignoring comments
        assert result.valid is True


def test_sitemap_analyzer_initialization():
    """Test SitemapAnalyzer initialization."""
    analyzer = SitemapAnalyzer()
    assert analyzer is not None

