"""Dynamic JavaScript analysis at runtime."""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass
from playwright.async_api import Page

logger = logging.getLogger(__name__)


@dataclass
class FunctionCall:
    """Function call trace."""
    
    function_name: str
    arguments: List[Any]
    return_value: Any
    timestamp: float


@dataclass
class CryptoOp:
    """Crypto operation."""
    
    operation: str
    algorithm: str
    input_data: Any
    output_data: Any


class DynamicJSAnalyzer:
    """Dynamic JavaScript analyzer for runtime analysis."""
    
    def __init__(self):
        self.function_calls: List[FunctionCall] = []
        self.crypto_operations: List[CryptoOp] = []
    
    async def hook_fetch_xhr(self, page: Page) -> None:
        """Inject hooks to intercept fetch and XHR calls."""
        hook_script = """
        (function() {
            // Hook fetch
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                console.log('[FETCH]', args[0], args[1]);
                return originalFetch.apply(this, args);
            };
            
            // Hook XMLHttpRequest
            const originalOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, ...args) {
                console.log('[XHR]', method, url);
                return originalOpen.apply(this, [method, url, ...args]);
            };
        })();
        """
        
        await page.add_init_script(hook_script)
        logger.info("Fetch and XHR hooks installed")
    
    async def trace_function_calls(self, page: Page, function_name: str) -> List[FunctionCall]:
        """Trace calls to a specific function."""
        trace_script = f"""
        (function() {{
            const calls = [];
            const original = window.{function_name};
            if (original) {{
                window.{function_name} = function(...args) {{
                    calls.push({{
                        function: '{function_name}',
                        arguments: args,
                        timestamp: Date.now()
                    }});
                    return original.apply(this, args);
                }};
            }}
            return calls;
        }})();
        """
        
        result = await page.evaluate(trace_script)
        return []
    
    async def capture_crypto_operations(self, page: Page) -> List[CryptoOp]:
        """Capture cryptographic operations."""
        crypto_script = """
        (function() {
            const ops = [];
            if (window.crypto && window.crypto.subtle) {
                // Hook crypto.subtle operations
                const originalEncrypt = window.crypto.subtle.encrypt;
                window.crypto.subtle.encrypt = function(...args) {
                    ops.push({
                        operation: 'encrypt',
                        algorithm: args[0],
                    });
                    return originalEncrypt.apply(this, args);
                };
            }
            return ops;
        })();
        """
        
        await page.add_init_script(crypto_script)
        return []


