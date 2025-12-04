"""Tests for MCP server."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.mcp.server import (
    server,
    list_tools,
    call_tool,
    handle_deep_analyze,
    handle_discover_apis,
    handle_deobfuscate_js,
    handle_extract_from_js,
    handle_stop_recording,
    handle_list_recordings,
    handle_get_recording_status,
    handle_health_check,
    _active_recordings,
    recording_storage,
)


@pytest.mark.asyncio
async def test_list_tools():
    """Test listing available tools."""
    tools = await list_tools()
    
    assert len(tools) > 0
    assert any(tool.name == "deep_analyze" for tool in tools)
    assert any(tool.name == "discover_apis" for tool in tools)
    assert any(tool.name == "deobfuscate_js" for tool in tools)


@pytest.mark.asyncio
async def test_tool_schemas():
    """Test tool input schemas are valid."""
    tools = await list_tools()
    
    for tool in tools:
        assert tool.inputSchema is not None
        assert "type" in tool.inputSchema
        assert tool.inputSchema["type"] == "object"
        assert "properties" in tool.inputSchema


@pytest.mark.asyncio
async def test_call_tool_deep_analyze():
    """Test calling deep_analyze tool."""
    arguments = {
        "url": "https://example.com",
        "depth": "full",
    }
    
    with patch("src.mcp.server.handle_deep_analyze") as mock_handle:
        mock_handle.return_value = {"status": "success"}
        
        result = await call_tool("deep_analyze", arguments)
        
        assert len(result) > 0
        assert result[0].type == "text"
        mock_handle.assert_called_once_with(arguments)


@pytest.mark.asyncio
async def test_call_tool_unknown():
    """Test calling unknown tool."""
    arguments = {}
    
    result = await call_tool("unknown_tool", arguments)
    
    assert len(result) > 0
    data = json.loads(result[0].text)
    assert "error" in data


@pytest.mark.asyncio
async def test_call_tool_exception():
    """Test tool call with exception."""
    arguments = {"url": "https://example.com"}
    
    with patch("src.mcp.server.handle_deep_analyze") as mock_handle:
        mock_handle.side_effect = Exception("Test error")
        
        result = await call_tool("deep_analyze", arguments)
        
        assert len(result) > 0
        data = json.loads(result[0].text)
        assert "error" in data


@pytest.mark.asyncio
async def test_handle_deobfuscate_js():
    """Test deobfuscate_js handler."""
    arguments = {
        "code": "var _0x1234=['test'];",
    }
    
    result = await handle_deobfuscate_js(arguments)
    
    assert "deobfuscated" in result
    assert "obfuscation_type" in result
    assert "original_length" in result


@pytest.mark.asyncio
async def test_handle_extract_from_js():
    """Test extract_from_js handler."""
    arguments = {
        "code": "fetch('https://api.example.com');",
    }
    
    result = await handle_extract_from_js(arguments)
    
    assert "api_calls" in result
    assert "hardcoded_urls" in result
    assert "constants" in result


@pytest.mark.asyncio
async def test_handle_discover_apis():
    """Test discover_apis handler."""
    arguments = {
        "url": "https://example.com",
        "include_hidden": True,
    }
    
    with patch("src.mcp.server.browser_pool") as mock_pool:
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_pool.acquire = AsyncMock(return_value=mock_context)
        
        with patch("src.mcp.server.network_interceptor") as mock_interceptor:
            mock_interceptor.start_intercepting = AsyncMock()
            mock_interceptor.capture_all_requests = AsyncMock(return_value=[])
            mock_interceptor.capture_all_responses = AsyncMock(return_value=[])
            
            with patch("src.mcp.server.api_discovery") as mock_discovery:
                mock_discovery.detect_rest_endpoints.return_value = []
                mock_discovery.detect_graphql.return_value = None
                mock_discovery.find_undocumented_endpoints.return_value = []
                
                result = await handle_discover_apis(arguments)
                
                assert "rest_endpoints" in result
                assert "graphql" in result
                assert "internal_apis" in result


@pytest.mark.asyncio
async def test_tool_descriptions():
    """Test all tools have descriptions."""
    tools = await list_tools()
    
    for tool in tools:
        assert tool.description is not None
        assert len(tool.description) > 0


@pytest.mark.asyncio
async def test_tool_required_fields():
    """Test tool required fields are properly defined."""
    tools = await list_tools()
    
    for tool in tools:
        if "required" in tool.inputSchema:
            required = tool.inputSchema["required"]
            assert isinstance(required, list)
            assert all(field in tool.inputSchema["properties"] for field in required)


@pytest.mark.asyncio
async def test_new_tools_exist():
    """Test that new tools are available."""
    tools = await list_tools()
    tool_names = [tool.name for tool in tools]
    
    assert "stop_recording" in tool_names
    assert "list_recordings" in tool_names
    assert "get_recording_status" in tool_names
    assert "health_check" in tool_names


@pytest.mark.asyncio
async def test_call_tool_validation():
    """Test tool call with invalid arguments."""
    # Missing required field
    result = await call_tool("deep_analyze", {})
    data = json.loads(result[0].text)
    assert "error" in data
    
    # Invalid URL
    result = await call_tool("deep_analyze", {"url": "not-a-url"})
    data = json.loads(result[0].text)
    assert "error" in data


@pytest.mark.asyncio
async def test_call_tool_timeout():
    """Test tool call timeout handling."""
    arguments = {"url": "https://example.com"}
    
    with patch("src.mcp.server.handle_deep_analyze") as mock_handle:
        import asyncio
        async def slow_handler(*args, **kwargs):
            await asyncio.sleep(100)  # Simulate slow operation
            return {}
        
        mock_handle.side_effect = slow_handler
        
        with patch("src.mcp.server.config") as mock_config:
            mock_config.operation_timeout = 0.1  # Very short timeout
            
            result = await call_tool("deep_analyze", arguments)
            data = json.loads(result[0].text)
            assert "error" in data or "timeout" in data.get("error", "").lower()


@pytest.mark.asyncio
async def test_handle_list_recordings():
    """Test list_recordings handler."""
    arguments = {"status": "all"}
    
    result = await handle_list_recordings(arguments)
    
    assert "recordings" in result
    assert "total" in result
    assert "active" in result
    assert "saved" in result
    assert isinstance(result["recordings"], list)


@pytest.mark.asyncio
async def test_handle_get_recording_status_nonexistent():
    """Test get_recording_status for non-existent recording."""
    arguments = {"recording_id": "nonexistent-id"}
    
    result = await handle_get_recording_status(arguments)
    
    assert "error" in result
    assert result["recording_id"] == "nonexistent-id"


@pytest.mark.asyncio
async def test_handle_stop_recording_nonexistent():
    """Test stop_recording for non-existent recording."""
    arguments = {"recording_id": "nonexistent-id"}
    
    result = await handle_stop_recording(arguments)
    
    assert "error" in result
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_handle_health_check():
    """Test health_check handler."""
    arguments = {}
    
    result = await handle_health_check(arguments)
    
    assert "status" in result
    assert "browser_pool" in result
    assert "storage" in result
    assert "config" in result
    assert result["status"] in ["healthy", "degraded", "unhealthy"]


@pytest.mark.asyncio
async def test_handle_deobfuscate_js_invalid_input():
    """Test deobfuscate_js with invalid input."""
    # Empty code
    result = await handle_deobfuscate_js({"code": ""})
    assert "error" in result
    
    # None code
    result = await handle_deobfuscate_js({"code": None})
    assert "error" in result


@pytest.mark.asyncio
async def test_handle_extract_from_js_invalid_input():
    """Test extract_from_js with invalid input."""
    # Empty code
    result = await handle_extract_from_js({"code": ""})
    assert "error" in result
    
    # None code
    result = await handle_extract_from_js({"code": None})
    assert "error" in result


@pytest.mark.asyncio
async def test_tool_descriptions_enhanced():
    """Test that tool descriptions are detailed."""
    tools = await list_tools()
    
    for tool in tools:
        assert tool.description is not None
        assert len(tool.description) > 20  # Should be detailed


@pytest.mark.asyncio
async def test_browser_context_manager_cleanup():
    """Test that browser context manager properly cleans up."""
    from src.mcp.server import browser_context_manager
    
    with patch("src.mcp.server.create_stealth_context") as mock_create:
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_create.return_value = mock_context
        
        async with browser_context_manager() as page:
            assert page == mock_page
        
        # Should have closed page and context
        mock_page.close.assert_called_once()
        mock_context.close.assert_called_once()

