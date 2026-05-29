"""Tests for the recursive crawling and structured extraction tools."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from src.mcp.server import handle_crawl, handle_structured_extract, list_tools, call_tool


@pytest.mark.asyncio
async def test_crawl_tool_registration():
    """Verify crawl and structured_extract are in tool list."""
    tools = await list_tools()
    tool_names = [tool.name for tool in tools]
    
    assert "crawl" in tool_names
    assert "structured_extract" in tool_names


@pytest.mark.asyncio
async def test_handle_crawl_basic():
    """Test handle_crawl with basic parameters and mock navigation."""
    arguments = {
        "url": "https://example.com",
        "max_depth": 1,
        "max_pages": 2,
        "concurrency": 1,
        "ignore_external": True,
        "save_to_file": False,
    }

    # Mock the browser context and page
    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><body><a href='https://example.com/page1'>Link 1</a></body></html>")
    mock_page.title = AsyncMock(return_value="Mock Page Title")
    
    # Mock links extraction evaluate
    mock_page.evaluate = AsyncMock(return_value=[
        {"href": "https://example.com/page1", "text": "Link 1"},
        {"href": "https://external.com", "text": "External"}
    ])

    with patch("src.mcp.server.browser_context_manager") as mock_manager:
        # Yield mock_page
        mock_manager.return_value.__aenter__.return_value = mock_page
        
        with patch("src.mcp.server.navigate_to_url") as mock_navigate:
            mock_navigate.return_value = AsyncMock()
            
            with patch("src.mcp.server.content_extractor") as mock_extractor:
                mock_extractor.extract_to_markdown.return_value = "# Mock Page Title\nLink 1"
                
                result = await handle_crawl(arguments)
                
                assert result["seed_url"] == "https://example.com"
                assert result["pages_crawled"] == 1
                assert "https://example.com" in result["results"]
                assert result["results"]["https://example.com"]["title"] == "Mock Page Title"
                assert "markdown" in result["results"]["https://example.com"]
                assert result["results"]["https://example.com"]["links"]["internal_count"] == 1
                assert result["results"]["https://example.com"]["links"]["external_count"] == 1


@pytest.mark.asyncio
async def test_handle_structured_extract_llm_disabled():
    """Verify handle_structured_extract returns appropriate error when LLM is not configured."""
    arguments = {
        "url": "https://example.com",
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"}
            }
        }
    }
    
    with patch("src.mcp.server.smart_extractor") as mock_extractor:
        mock_extractor.llm_enabled = False
        mock_extractor.client = None
        
        result = await handle_structured_extract(arguments)
        
        assert "error" in result
        assert "LLM extraction is not configured" in result["error"]


@pytest.mark.asyncio
async def test_handle_structured_extract_success():
    """Verify handle_structured_extract works when LLM is enabled and returns schema."""
    arguments = {
        "url": "https://example.com",
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "price": {"type": "number"}
            }
        },
        "instructions": "Extract product information"
    }

    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><body>Product Details</body></html>")
    
    mock_llm_response = MagicMock()
    mock_llm_response.choices = [
        MagicMock(message=MagicMock(content='{"title": "Test Product", "price": 49.99}'))
    ]

    with patch("src.mcp.server.browser_context_manager") as mock_manager:
        mock_manager.return_value.__aenter__.return_value = mock_page
        
        with patch("src.mcp.server.navigate_to_url") as mock_navigate:
            mock_navigate.return_value = AsyncMock()
            
            with patch("src.mcp.server.content_extractor") as mock_extractor:
                mock_extractor.extract_to_markdown.return_value = "Product Details"
                
                with patch("src.mcp.server.smart_extractor") as mock_smart:
                    mock_smart.llm_enabled = True
                    mock_client = MagicMock()
                    mock_client.chat.completions.create.return_value = mock_llm_response
                    mock_smart.client = mock_client
                    mock_smart.model = "gpt-4o-mini"
                    
                    result = await handle_structured_extract(arguments)
                    
                    assert "extracted_data" in result
                    assert result["extracted_data"]["title"] == "Test Product"
                    assert result["extracted_data"]["price"] == 49.99
                    assert result["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_dom_pruning_and_filtering():
    """Verify that ContentExtractor applies DOM pruning and exclusions correctly."""
    from src.intelligence.extraction.content import get_content_extractor
    
    html = """
    <html>
        <body>
            <nav>Sidebar menu</nav>
            <div id="main-content">
                <h1>Article Title</h1>
                <p>Hello world.</p>
                <div class="ads">Buy products here!</div>
            </div>
            <footer>Footer metadata</footer>
        </body>
    </html>
    """
    
    extractor = get_content_extractor()
    
    # Test exclusions (removing .ads)
    res = extractor.extract_to_markdown(html, exclude_selectors=[".ads", "nav", "footer"])
    assert "Sidebar menu" not in res
    assert "Buy products here" not in res
    assert "Footer metadata" not in res
    assert "Article Title" in res
    
    # Test targeting (css_selector)
    res_targeted = extractor.extract_to_markdown(html, css_selector="#main-content", exclude_selectors=[".ads"])
    assert "Sidebar menu" not in res_targeted
    assert "Article Title" in res_targeted
    assert "Buy products here" not in res_targeted


@pytest.mark.asyncio
async def test_handle_structured_extract_code_block_fences():
    """Verify handle_structured_extract strips markdown code blocks cleanly."""
    arguments = {
        "url": "https://example.com",
        "schema": {"type": "object", "properties": {"title": {"type": "string"}}}
    }

    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><body>Product Details</body></html>")
    
    # LLM returns content wrapped in markdown fences
    mock_llm_response = MagicMock()
    mock_llm_response.choices = [
        MagicMock(message=MagicMock(content='```json\n{"title": "Fenced Product"}\n```'))
    ]

    with patch("src.mcp.server.browser_context_manager") as mock_manager:
        mock_manager.return_value.__aenter__.return_value = mock_page
        
        with patch("src.mcp.server.navigate_to_url") as mock_navigate:
            mock_navigate.return_value = AsyncMock()
            
            with patch("src.mcp.server.content_extractor") as mock_extractor:
                mock_extractor.extract_to_markdown.return_value = "Product Details"
                
                with patch("src.mcp.server.smart_extractor") as mock_smart:
                    mock_smart.llm_enabled = True
                    mock_client = MagicMock()
                    mock_client.chat.completions.create.return_value = mock_llm_response
                    mock_smart.client = mock_client
                    mock_smart.model = "gpt-4o-mini"
                    
                    result = await handle_structured_extract(arguments)
                    
                    assert "extracted_data" in result
                    assert result["extracted_data"]["title"] == "Fenced Product"


@pytest.mark.asyncio
async def test_handle_crawl_resilience():
    """Verify handle_crawl continues gracefully when a page load fails."""
    arguments = {
        "url": "https://example.com",
        "max_depth": 2,
        "max_pages": 2,
        "concurrency": 1,
        "ignore_external": True,
        "save_to_file": False,
    }

    mock_page = AsyncMock()
    mock_page.content = AsyncMock(return_value="<html><body><a href='https://example.com/page1'>Link 1</a></body></html>")
    mock_page.title = AsyncMock(return_value="Mock Page Title")
    mock_page.evaluate = AsyncMock(return_value=[
        {"href": "https://example.com/page1", "text": "Link 1"}
    ])

    with patch("src.mcp.server.browser_context_manager") as mock_manager:
        mock_manager.return_value.__aenter__.return_value = mock_page
        
        # Make the first navigate succeed, and second navigate throw an error
        call_count = 0
        async def mock_navigate_func(page, url):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise Exception("Page navigation failed")
            return AsyncMock()

        with patch("src.mcp.server.navigate_to_url", side_effect=mock_navigate_func):
            with patch("src.mcp.server.content_extractor") as mock_extractor:
                mock_extractor.extract_to_markdown.return_value = "# Mock Page Title\nLink 1"
                
                result = await handle_crawl(arguments)
                
                # Should have tried to crawl both, pages_crawled should be 2 (seed + page1)
                assert result["pages_crawled"] == 2
                assert "https://example.com" in result["results"]
                assert "https://example.com/page1" in result["results"]
                assert "error" in result["results"]["https://example.com/page1"]
                assert "Page navigation failed" in result["results"]["https://example.com/page1"]["error"]
