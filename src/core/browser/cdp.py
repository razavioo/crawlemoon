"""Chrome DevTools Protocol (CDP) direct access."""

import logging
from typing import Dict, Any, Optional, List
from playwright.async_api import Browser, BrowserContext, CDPSession

logger = logging.getLogger(__name__)


class CDPClient:
    """Wrapper for CDP access through Playwright."""
    
    def __init__(self, context: BrowserContext):
        self.context = context
        self._cdp_session: Optional[CDPSession] = None
    
    async def connect(self) -> None:
        """Establish CDP session."""
        if not self._cdp_session:
            self._cdp_session = await self.context.new_cdp_session(
                await self.context.pages[0] if self.context.pages else None
            )
            logger.info("CDP session established")
    
    async def send_command(self, method: str, params: Optional[Dict] = None) -> Any:
        """Send a CDP command."""
        if not self._cdp_session:
            await self.connect()
        
        params = params or {}
        result = await self._cdp_session.send(method, params)
        logger.debug(f"CDP command: {method}")
        return result
    
    async def enable_network_domain(self) -> None:
        """Enable Network domain for network interception."""
        await self.send_command("Network.enable")
        logger.debug("Network domain enabled")
    
    async def enable_runtime_domain(self) -> None:
        """Enable Runtime domain for JavaScript execution."""
        await self.send_command("Runtime.enable")
        logger.debug("Runtime domain enabled")
    
    async def enable_page_domain(self) -> None:
        """Enable Page domain for page events."""
        await self.send_command("Page.enable")
        logger.debug("Page domain enabled")
    
    async def enable_dom_domain(self) -> None:
        """Enable DOM domain for DOM manipulation."""
        await self.send_command("DOM.enable")
        logger.debug("DOM domain enabled")
    
    async def on_event(self, event_name: str, callback) -> None:
        """Register event listener."""
        if not self._cdp_session:
            await self.connect()
        
        self._cdp_session.on(event_name, callback)
        logger.debug(f"Registered listener for {event_name}")
    
    async def evaluate_expression(self, expression: str, return_by_value: bool = True) -> Any:
        """Evaluate JavaScript expression via CDP."""
        result = await self.send_command(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": return_by_value,
            }
        )
        return result.get("result", {}).get("value")
    
    async def add_script_to_evaluate_on_new_document(self, source: str) -> str:
        """Add script to be evaluated on every new document."""
        result = await self.send_command(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": source}
        )
        script_id = result.get("identifier")
        logger.debug(f"Added script to evaluate on new document: {script_id}")
        return script_id
    
    async def get_dom_tree(self, depth: int = -1) -> Dict:
        """Get DOM tree via CDP."""
        document = await self.send_command("DOM.getDocument", {"depth": depth})
        return document
    
    async def close(self) -> None:
        """Close CDP session."""
        if self._cdp_session:
            # CDP session is closed automatically with context
            self._cdp_session = None
            logger.debug("CDP session closed")


