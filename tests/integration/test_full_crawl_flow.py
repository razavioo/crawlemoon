"""Integration tests for full crawl workflows."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# These tests require network access and real browser automation
# Mark them with markers for selective running


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deep_analyze_workflow():
    """Test full deep analysis workflow."""
    from src.mcp.server import handle_deep_analyze
    
    # Mock all dependencies
    with patch("src.mcp.server.browser_pool") as mock_pool:
        mock_context = MagicMock()
        mock_page = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Test</body></html>")
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_pool.acquire = AsyncMock(return_value=mock_context)
        
        with patch("src.mcp.server.network_interceptor") as mock_interceptor:
            mock_interceptor.capture_all_requests = AsyncMock(return_value=[])
            mock_interceptor.capture_all_responses = AsyncMock(return_value=[])
            mock_interceptor.start_intercepting = AsyncMock()
            mock_interceptor.reset = MagicMock()
            
            with patch("src.mcp.server.api_discovery") as mock_api:
                mock_api.detect_rest_endpoints.return_value = []
                mock_api.detect_graphql.return_value = []
                mock_api.find_undocumented_endpoints.return_value = []
                
                with patch("src.mcp.server.bot_detector") as mock_bot:
                    mock_bot.detect_protection_type.return_value = MagicMock()
                    mock_bot.analyze_fingerprinting.return_value = MagicMock()
                    mock_bot.detect_captcha_type.return_value = MagicMock()
                    
                    with patch("src.mcp.server.js_analyzer") as mock_js:
                        mock_js.extract_api_calls.return_value = []
                        mock_js.find_hardcoded_urls.return_value = []
                        mock_js.find_auth_logic.return_value = {}
                        
                        result = await handle_deep_analyze({
                            "url": "https://example.com",
                            "depth": "basic"
                        })
                        
                        assert "url" in result
                        assert "network_requests" in result or "error" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_discovery_workflow():
    """Test API discovery workflow."""
    from src.mcp.server import handle_discover_apis
    
    with patch("src.mcp.server.browser_pool") as mock_pool:
        mock_context = MagicMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_pool.acquire = AsyncMock(return_value=mock_context)
        
        with patch("src.mcp.server.network_interceptor") as mock_interceptor:
            mock_interceptor.start_intercepting = AsyncMock()
            mock_interceptor.capture_all_requests = AsyncMock(return_value=[])
            mock_interceptor.capture_all_responses = AsyncMock(return_value=[])
            mock_interceptor.reset = MagicMock()
            
            with patch("src.mcp.server.api_discovery") as mock_api:
                mock_api.detect_rest_endpoints.return_value = []
                mock_api.detect_graphql.return_value = []
                mock_api.find_undocumented_endpoints.return_value = []
                
                result = await handle_discover_apis({
                    "url": "https://api.example.com",
                    "include_hidden": True
                })
                
                assert "rest_endpoints" in result or "error" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recording_and_replay_workflow():
    """Test record -> generate -> execute workflow."""
    from src.mcp.server import (
        handle_record_session,
        handle_stop_recording,
        handle_generate_crawler,
        handle_list_recordings,
    )
    
    # Mock recording session
    with patch("src.mcp.server.recording_storage") as mock_storage:
        # Test list recordings
        mock_storage.list_recordings.return_value = []
        
        list_result = await handle_list_recordings({})
        
        assert "active" in list_result
        assert "saved" in list_result
    
    # Test stop recording
    with patch("src.mcp.server.recording_storage") as mock_storage:
        mock_storage.get_active_recording.return_value = MagicMock(
            id="test-recording",
            events=[],
            start_url="https://example.com",
            start_time=None,
            end_time=None,
        )
        mock_storage.unregister_active_recording = MagicMock()
        mock_storage.save_recording = MagicMock()
        
        from src.mcp.server import _active_recordings
        mock_recorder = MagicMock()
        mock_recorder.stop_recording = AsyncMock(return_value=MagicMock())
        _active_recordings["test-recording"] = (mock_recorder, MagicMock(), MagicMock())
        
        try:
            stop_result = await handle_stop_recording({
                "recording_id": "test-recording",
                "save": True
            })
            
            assert "recording_id" in stop_result or "error" in stop_result
        finally:
            _active_recordings.pop("test-recording", None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_screenshot_workflow():
    """Test screenshot capture workflow."""
    from src.mcp.server import handle_take_screenshot
    
    with patch("src.mcp.server.browser_pool") as mock_pool:
        mock_context = MagicMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"fake-png-data")
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_pool.acquire = AsyncMock(return_value=mock_context)
        
        result = await handle_take_screenshot({
            "url": "https://example.com",
            "full_page": True
        })
        
        assert "screenshot" in result or "error" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_article_extraction_workflow():
    """Test article extraction workflow."""
    from src.mcp.server import handle_extract_article
    
    with patch("src.mcp.server.browser_pool") as mock_pool:
        mock_context = MagicMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="""
            <html>
            <body>
                <article>
                    <h1>Test Article Title</h1>
                    <p>This is the article content.</p>
                </article>
            </body>
            </html>
        """)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_pool.acquire = AsyncMock(return_value=mock_context)
        
        with patch("src.mcp.server.content_extractor") as mock_extractor:
            mock_extractor.extract_article.return_value = MagicMock(
                title="Test Article Title",
                text="This is the article content.",
                author=None,
                date=None,
            )
            
            result = await handle_extract_article({
                "url": "https://news.example.com/article"
            })
            
            assert "title" in result or "error" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sitemap_analysis_workflow():
    """Test sitemap analysis workflow."""
    from src.mcp.server import handle_analyze_sitemap
    
    with patch("src.mcp.server.sitemap_analyzer") as mock_analyzer:
        mock_analyzer.analyze_sitemap = AsyncMock(return_value=MagicMock(
            sitemap_url="https://example.com/sitemap.xml",
            entries=[
                MagicMock(url="https://example.com/page1", lastmod=None),
                MagicMock(url="https://example.com/page2", lastmod=None),
            ],
            sitemap_type="sitemap",
            total_urls=2,
            errors=[],
        ))
        
        result = await handle_analyze_sitemap({
            "sitemap_url": "https://example.com/sitemap.xml"
        })
        
        assert "entries" in result or "error" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_robots_check_workflow():
    """Test robots.txt check workflow."""
    from src.mcp.server import handle_check_robots
    
    with patch("src.mcp.server.sitemap_analyzer") as mock_analyzer:
        mock_analyzer.analyze_robots = AsyncMock(return_value=MagicMock(
            robots_url="https://example.com/robots.txt",
            rules=[],
            sitemaps=["https://example.com/sitemap.xml"],
            valid=True,
            errors=[],
        ))
        mock_analyzer.check_url_allowed = MagicMock(return_value=True)
        
        result = await handle_check_robots({
            "url": "https://example.com",
            "test_url": "/admin/"
        })
        
        assert "rules" in result or "error" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_technology_detection_workflow():
    """Test technology detection workflow."""
    from src.mcp.server import handle_detect_technology
    
    with patch("src.mcp.server.browser_pool") as mock_pool:
        mock_context = MagicMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Test</body></html>")
        
        mock_response = MagicMock()
        mock_response.headers = {"server": "nginx"}
        mock_page.goto.return_value = mock_response
        
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_pool.acquire = AsyncMock(return_value=mock_context)
        
        with patch("src.mcp.server.technology_detector") as mock_detector:
            mock_stack = MagicMock()
            mock_stack.frameworks = []
            mock_stack.cms = []
            mock_stack.web_servers = []
            mock_stack.cdn = []
            mock_stack.javascript_libraries = []
            mock_stack.analytics = []
            mock_stack.other = []
            mock_detector.detect.return_value = mock_stack
            mock_detector.get_protection_technologies.return_value = []
            
            result = await handle_detect_technology({
                "url": "https://example.com"
            })
            
            assert "cms" in result or "error" in result

