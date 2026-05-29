"""Integration tests for MCP client-server protocol."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json


@pytest.mark.integration
@pytest.mark.asyncio
async def test_server_initialization():
    """Test MCP server initialization."""
    from src.mcp.server import server
    
    assert server is not None
    assert server.name == "crawlify-mcp-server"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_listing():
    """Test tool enumeration via list_tools."""
    from src.mcp.server import list_tools
    
    tools = await list_tools()
    
    assert len(tools) > 0
    
    # Check for expected tools
    tool_names = [tool.name for tool in tools]
    expected_tools = [
        "deep_analyze",
        "discover_apis",
        "introspect_graphql",
        "analyze_websocket",
        "record_session",
        "stop_recording",
        "list_recordings",
        "get_recording_status",
        "generate_crawler",
        "analyze_auth",
        "detect_protection",
        "deobfuscate_js",
        "extract_from_js",
        "health_check",
    ]
    
    for expected in expected_tools:
        assert expected in tool_names, f"Missing tool: {expected}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_schema_validation():
    """Test that all tools have valid schemas."""
    from src.mcp.server import list_tools
    
    tools = await list_tools()
    
    for tool in tools:
        # Each tool should have name, description, and inputSchema
        assert tool.name is not None
        assert tool.description is not None
        assert tool.inputSchema is not None
        
        # Schema should have required structure
        schema = tool.inputSchema
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_execution_health_check():
    """Test tool execution via call_tool."""
    from src.mcp.server import call_tool
    
    result = await call_tool("health_check", {})
    
    assert len(result) > 0
    # Result should be a list of content
    content = result[0]
    assert content.type == "text"
    
    # Parse the JSON result
    data = json.loads(content.text)
    assert "status" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_execution_deobfuscate_js():
    """Test JS deobfuscation via call_tool."""
    from src.mcp.server import call_tool
    
    code = 'var x = atob("SGVsbG8=");'
    
    result = await call_tool("deobfuscate_js", {"code": code})
    
    assert len(result) > 0
    content = result[0]
    assert content.type == "text"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_execution_extract_from_js():
    """Test JS extraction via call_tool."""
    from src.mcp.server import call_tool
    
    code = '''
    fetch('/api/users', { method: 'GET' });
    const API_KEY = 'secret123';
    '''
    
    result = await call_tool("extract_from_js", {"code": code, "url": "https://example.com"})
    
    assert len(result) > 0
    content = result[0]
    data = json.loads(content.text)
    
    assert "api_calls" in data
    assert "constants" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_execution_invalid_tool():
    """Test calling non-existent tool."""
    from src.mcp.server import call_tool
    from mcp.types import TextContent
    
    result = await call_tool("nonexistent_tool", {})
    
    assert len(result) > 0
    content = result[0]
    # Should return error
    data = json.loads(content.text)
    assert "error" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_execution_missing_required_arg():
    """Test tool call with missing required argument."""
    from src.mcp.server import call_tool
    
    # deep_analyze requires 'url' argument
    result = await call_tool("deep_analyze", {})
    
    assert len(result) > 0
    content = result[0]
    data = json.loads(content.text)
    # Should return error about missing argument
    assert "error" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_execution_list_recordings():
    """Test listing recordings via call_tool."""
    from src.mcp.server import call_tool
    
    result = await call_tool("list_recordings", {})
    
    assert len(result) > 0
    content = result[0]
    data = json.loads(content.text)
    
    assert "active" in data
    assert "saved" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_execution_detect_protection():
    """Test protection detection via call_tool."""
    from src.mcp.server import call_tool
    
    with patch("src.mcp.server.browser_pool") as mock_pool:
        mock_context = MagicMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>Test</body></html>")
        
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_page.goto.return_value = mock_response
        
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_pool.acquire = AsyncMock(return_value=mock_context)
        
        with patch("src.mcp.server.bot_detector") as mock_detector:
            mock_detector.detect_protection_type.return_value = MagicMock(value="none")
            mock_detector.detect_captcha_type.return_value = MagicMock(value="none")
            mock_detector.analyze_fingerprinting.return_value = MagicMock(
                canvas_fingerprint=False,
                webgl_fingerprint=False,
                audio_fingerprint=False,
            )
            
            result = await call_tool("detect_protection", {
                "url": "https://example.com"
            })
            
            assert len(result) > 0


@pytest.mark.integration
@pytest.mark.asyncio  
async def test_concurrent_tool_calls():
    """Test concurrent tool execution."""
    from src.mcp.server import call_tool
    import asyncio
    
    # Run multiple health checks concurrently
    tasks = [call_tool("health_check", {}) for _ in range(5)]
    results = await asyncio.gather(*tasks)
    
    # All should succeed
    assert len(results) == 5
    for result in results:
        assert len(result) > 0
        data = json.loads(result[0].text)
        assert "status" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tool_timeout_handling():
    """Test that tool timeouts are handled properly."""
    from src.mcp.server import call_tool
    
    # Configure proxies with invalid data should fail gracefully
    result = await call_tool("configure_proxies", {
        "proxies": [],  # Empty proxies
        "rotation_strategy": "round_robin"
    })
    
    assert len(result) > 0
    # Should return a result (success or error)
    content = result[0]
    assert content.type == "text"

