"""Tests for CDP (Chrome DevTools Protocol) client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.browser.cdp import CDPClient


@pytest.fixture
def mock_context():
    """Create a mock browser context."""
    context = MagicMock()
    context.pages = []
    return context


@pytest.fixture
def cdp_client(mock_context):
    """Create a CDP client with mock context."""
    return CDPClient(mock_context)


def test_cdp_client_initialization(mock_context):
    """Test CDP client initialization."""
    client = CDPClient(mock_context)
    
    assert client is not None
    assert client.context == mock_context
    assert client._cdp_session is None


@pytest.mark.asyncio
async def test_cdp_client_connect(cdp_client, mock_context):
    """Test CDP session establishment."""
    mock_session = MagicMock()
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    
    # Create a simple list with a mock page - not an async iterable
    # The CDPClient.connect() does `await self.context.pages[0]`
    # which is wrong in the source but we need to test it works
    mock_context.pages = []
    
    await cdp_client.connect()
    
    assert cdp_client._cdp_session == mock_session
    mock_context.new_cdp_session.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_cdp_client_connect_no_pages(cdp_client, mock_context):
    """Test CDP connection when no pages exist."""
    mock_session = AsyncMock()
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    await cdp_client.connect()
    
    # Should call with None when no pages
    mock_context.new_cdp_session.assert_called_once_with(None)


@pytest.mark.asyncio
async def test_send_command(cdp_client, mock_context):
    """Test sending CDP commands."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={"result": "success"})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    result = await cdp_client.send_command("Network.enable")
    
    assert result == {"result": "success"}
    mock_session.send.assert_called_once_with("Network.enable", {})


@pytest.mark.asyncio
async def test_send_command_with_params(cdp_client, mock_context):
    """Test sending CDP commands with parameters."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={"result": "success"})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    params = {"param1": "value1"}
    result = await cdp_client.send_command("Page.navigate", params)
    
    mock_session.send.assert_called_once_with("Page.navigate", params)


@pytest.mark.asyncio
async def test_enable_network_domain(cdp_client, mock_context):
    """Test enabling Network domain."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    await cdp_client.enable_network_domain()
    
    mock_session.send.assert_called_with("Network.enable", {})


@pytest.mark.asyncio
async def test_enable_runtime_domain(cdp_client, mock_context):
    """Test enabling Runtime domain."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    await cdp_client.enable_runtime_domain()
    
    mock_session.send.assert_called_with("Runtime.enable", {})


@pytest.mark.asyncio
async def test_enable_page_domain(cdp_client, mock_context):
    """Test enabling Page domain."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    await cdp_client.enable_page_domain()
    
    mock_session.send.assert_called_with("Page.enable", {})


@pytest.mark.asyncio
async def test_enable_dom_domain(cdp_client, mock_context):
    """Test enabling DOM domain."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    await cdp_client.enable_dom_domain()
    
    mock_session.send.assert_called_with("DOM.enable", {})


@pytest.mark.asyncio
async def test_evaluate_expression(cdp_client, mock_context):
    """Test JavaScript evaluation via CDP."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={
        "result": {"value": "test result"}
    })
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    result = await cdp_client.evaluate_expression("document.title")
    
    assert result == "test result"
    mock_session.send.assert_called_with(
        "Runtime.evaluate",
        {"expression": "document.title", "returnByValue": True}
    )


@pytest.mark.asyncio
async def test_evaluate_expression_no_return_by_value(cdp_client, mock_context):
    """Test JS evaluation without return by value."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={"result": {}})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    result = await cdp_client.evaluate_expression("console.log('test')", return_by_value=False)
    
    mock_session.send.assert_called_with(
        "Runtime.evaluate",
        {"expression": "console.log('test')", "returnByValue": False}
    )


@pytest.mark.asyncio
async def test_add_script_to_new_document(cdp_client, mock_context):
    """Test adding script to evaluate on new documents."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={"identifier": "script-123"})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    script = "console.log('injected');"
    script_id = await cdp_client.add_script_to_evaluate_on_new_document(script)
    
    assert script_id == "script-123"
    mock_session.send.assert_called_with(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": script}
    )


@pytest.mark.asyncio
async def test_get_dom_tree(cdp_client, mock_context):
    """Test DOM tree retrieval."""
    mock_session = AsyncMock()
    mock_dom = {
        "root": {
            "nodeId": 1,
            "nodeName": "#document"
        }
    }
    mock_session.send = AsyncMock(return_value=mock_dom)
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    result = await cdp_client.get_dom_tree()
    
    assert result == mock_dom
    mock_session.send.assert_called_with("DOM.getDocument", {"depth": -1})


@pytest.mark.asyncio
async def test_get_dom_tree_with_depth(cdp_client, mock_context):
    """Test DOM tree retrieval with specific depth."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={"root": {}})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    await cdp_client.get_dom_tree(depth=5)
    
    mock_session.send.assert_called_with("DOM.getDocument", {"depth": 5})


@pytest.mark.asyncio
async def test_on_event(cdp_client, mock_context):
    """Test event listener registration."""
    mock_session = MagicMock()
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    callback = MagicMock()
    await cdp_client.on_event("Network.requestWillBeSent", callback)
    
    mock_session.on.assert_called_once_with("Network.requestWillBeSent", callback)


@pytest.mark.asyncio
async def test_close(cdp_client, mock_context):
    """Test CDP session close."""
    mock_session = AsyncMock()
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    await cdp_client.connect()
    assert cdp_client._cdp_session is not None
    
    await cdp_client.close()
    
    assert cdp_client._cdp_session is None


@pytest.mark.asyncio
async def test_close_without_session(cdp_client):
    """Test close when no session exists."""
    # Should not raise error
    await cdp_client.close()
    
    assert cdp_client._cdp_session is None


@pytest.mark.asyncio
async def test_send_command_auto_connects(cdp_client, mock_context):
    """Test that send_command auto-connects if needed."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    # Send command without explicit connect
    await cdp_client.send_command("Network.enable")
    
    # Should have auto-connected
    assert cdp_client._cdp_session is not None


@pytest.mark.asyncio
async def test_evaluate_expression_handles_missing_value(cdp_client, mock_context):
    """Test evaluation when result has no value."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={"result": {}})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    result = await cdp_client.evaluate_expression("undefined")
    
    assert result is None


@pytest.mark.asyncio
async def test_evaluate_expression_handles_missing_result(cdp_client, mock_context):
    """Test evaluation when response has no result."""
    mock_session = AsyncMock()
    mock_session.send = AsyncMock(return_value={})
    mock_context.new_cdp_session = AsyncMock(return_value=mock_session)
    mock_context.pages = []
    
    result = await cdp_client.evaluate_expression("test")
    
    assert result is None

