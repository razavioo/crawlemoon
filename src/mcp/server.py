"""MCP Server implementation for Crawilfy - Enhanced and Production-Ready."""

import asyncio
import logging
import json
import os
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from contextlib import asynccontextmanager

from mcp.server import Server
from mcp.types import Tool, TextContent

from ..core.browser.pool import BrowserPool
from ..core.browser.stealth import create_stealth_context
from ..core.recording_storage import RecordingStorage
from ..intelligence.network.interceptor import DeepNetworkInterceptor
from ..intelligence.network.api_discovery import APIDiscoveryEngine
from ..intelligence.network.analyzer import RequestAnalyzer
from ..intelligence.js.analyzer import JSAnalyzer
from ..intelligence.js.deobfuscator import JSDeobfuscator
from ..intelligence.recorder.session import SessionRecorder, SessionRecording, Event, EventType, StateSnapshot
from ..intelligence.security.bot_detection import BotDetectionAnalyzer
from ..intelligence.generator.crawler_gen import CrawlerGenerator
from .config import MCPServerConfig
from .utils import validate_url, validate_arguments, with_timeout, with_retry

logger = logging.getLogger(__name__)

# Global configuration
config = MCPServerConfig.from_env()

# Initialize global instances
browser_pool = BrowserPool(
    max_size=config.max_browser_pool_size,
    headless=config.headless,
    browser_type=config.browser_type,
)
network_interceptor = DeepNetworkInterceptor()
api_discovery = APIDiscoveryEngine()
request_analyzer = RequestAnalyzer()
js_analyzer = JSAnalyzer()
js_deobfuscator = JSDeobfuscator()
bot_detector = BotDetectionAnalyzer()
recording_storage = RecordingStorage(storage_dir=config.recording_storage_dir)

# Active recordings tracking
_active_recordings: Dict[str, Tuple[SessionRecorder, Any, Any]] = {}  # recording_id -> (recorder, page, context)

# Initialize browser pool
async def init_browser_pool():
    """Initialize browser pool."""
    await browser_pool.initialize()
    logger.info("Browser pool initialized")

# MCP Server
server = Server("crawilfy-mcp-server")


@asynccontextmanager
async def browser_context_manager():
    """Context manager for browser operations with proper cleanup."""
    context = None
    page = None
    try:
        context = await create_stealth_context(browser_pool)
        page = await context.new_page()
        page.set_default_timeout(config.navigation_timeout * 1000)  # Playwright uses milliseconds
        yield page
    finally:
        if page:
            try:
                await page.close()
            except Exception as e:
                logger.warning(f"Error closing page: {e}")
        if context:
            try:
                await context.close()
            except Exception as e:
                logger.warning(f"Error closing context: {e}")


@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="deep_analyze",
            description="Perform comprehensive deep analysis of a website including network traffic, JavaScript analysis, and security detection. Returns detailed insights about APIs, protection mechanisms, and fingerprinting techniques.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the website to analyze (must be a valid HTTP/HTTPS URL)"
                    },
                    "depth": {
                        "type": "string",
                        "enum": ["basic", "full"],
                        "description": "Analysis depth: 'basic' for quick analysis, 'full' for comprehensive analysis",
                        "default": "full"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="discover_apis",
            description="Discover all REST and GraphQL APIs on a website, including hidden and undocumented endpoints. Useful for API reverse engineering and documentation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Website URL to analyze for API endpoints"
                    },
                    "include_hidden": {
                        "type": "boolean",
                        "description": "Include hidden/internal APIs that may not be publicly documented",
                        "default": True
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="introspect_graphql",
            description="Extract complete GraphQL schema from an endpoint using introspection. Returns schema, queries, mutations, and subscriptions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "endpoint": {
                        "type": "string",
                        "description": "GraphQL endpoint URL (e.g., https://api.example.com/graphql)"
                    }
                },
                "required": ["endpoint"]
            }
        ),
        Tool(
            name="analyze_websocket",
            description="Intercept and analyze WebSocket connections on a page. Captures messages, connection details, and message patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Page URL that establishes WebSocket connections"
                    },
                    "wait_time": {
                        "type": "number",
                        "description": "Time in seconds to wait for WebSocket connections (default: 5)",
                        "default": 5
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="record_session",
            description="Start recording an interactive browser session. Records all user interactions, network requests, and page state changes. Use stop_recording to finish.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Starting URL for the recording session"
                    },
                    "auto_save": {
                        "type": "boolean",
                        "description": "Automatically save recording when stopped (default: true)",
                        "default": True
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="stop_recording",
            description="Stop an active recording session and optionally save it. Returns recording ID and statistics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recording_id": {
                        "type": "string",
                        "description": "ID of the recording to stop"
                    },
                    "save": {
                        "type": "boolean",
                        "description": "Save recording to storage (default: true)",
                        "default": True
                    }
                },
                "required": ["recording_id"]
            }
        ),
        Tool(
            name="list_recordings",
            description="List all available recordings (both active and saved). Returns metadata about each recording.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["all", "active", "saved"],
                        "description": "Filter by recording status (default: all)",
                        "default": "all"
                    }
                }
            }
        ),
        Tool(
            name="get_recording_status",
            description="Get status and details of a specific recording session.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recording_id": {
                        "type": "string",
                        "description": "ID of the recording to check"
                    }
                },
                "required": ["recording_id"]
            }
        ),
        Tool(
            name="generate_crawler",
            description="Generate a crawler script from a recorded session. Supports multiple output formats including YAML, Python, and Playwright.",
            inputSchema={
                "type": "object",
                "properties": {
                    "recording_id": {
                        "type": "string",
                        "description": "Recording ID or file path to the recording JSON file"
                    },
                    "output_format": {
                        "type": "string",
                        "enum": ["yaml", "python", "playwright"],
                        "description": "Output format for the generated crawler",
                        "default": "yaml"
                    }
                },
                "required": ["recording_id"]
            }
        ),
        Tool(
            name="analyze_auth",
            description="Analyze authentication flow on a login page. Identifies auth mechanisms, token handling, and authentication endpoints.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Login page URL to analyze"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="detect_protection",
            description="Detect anti-bot systems, CAPTCHAs, and fingerprinting techniques used on a website.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Website URL to analyze for protection mechanisms"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="deobfuscate_js",
            description="Deobfuscate JavaScript code. Detects obfuscation techniques and attempts to restore readable code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Obfuscated JavaScript code to deobfuscate"
                    }
                },
                "required": ["code"]
            }
        ),
        Tool(
            name="extract_from_js",
            description="Extract API endpoints, URLs, constants, and authentication logic from JavaScript code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "JavaScript code to analyze"
                    }
                },
                "required": ["code"]
            }
        ),
        Tool(
            name="health_check",
            description="Check the health status of the MCP server, browser pool, and storage systems.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls with comprehensive error handling."""
    try:
        # Get tool schema for validation
        tools = await list_tools()
        tool_schema = next((t for t in tools if t.name == name), None)
        
        if not tool_schema:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
            )]
        
        # Validate arguments
        required = tool_schema.inputSchema.get("required", [])
        is_valid, error_msg = validate_arguments(arguments, required, tool_schema.inputSchema)
        
        if not is_valid:
            return [TextContent(
                type="text",
                text=json.dumps({"error": error_msg}, ensure_ascii=False)
            )]
        
        # Route to handler
        handler_map = {
            "deep_analyze": handle_deep_analyze,
            "discover_apis": handle_discover_apis,
            "introspect_graphql": handle_introspect_graphql,
            "analyze_websocket": handle_analyze_websocket,
            "record_session": handle_record_session,
            "stop_recording": handle_stop_recording,
            "list_recordings": handle_list_recordings,
            "get_recording_status": handle_get_recording_status,
            "generate_crawler": handle_generate_crawler,
            "analyze_auth": handle_analyze_auth,
            "detect_protection": handle_detect_protection,
            "deobfuscate_js": handle_deobfuscate_js,
            "extract_from_js": handle_extract_from_js,
            "health_check": handle_health_check,
        }
        
        handler = handler_map.get(name)
        if not handler:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Handler not implemented for tool: {name}"}, ensure_ascii=False)
            )]
        
        # Execute handler with timeout
        result = await asyncio.wait_for(
            handler(arguments),
            timeout=config.operation_timeout
        )
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, ensure_ascii=False, default=str)
        )]
    
    except asyncio.TimeoutError:
        logger.error(f"Tool {name} timed out after {config.operation_timeout}s")
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": f"Operation timed out after {config.operation_timeout} seconds",
                "tool": name
            }, ensure_ascii=False)
        )]
    except Exception as e:
        logger.error(f"Error in tool {name}: {e}", exc_info=True)
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": str(e),
                "tool": name,
                "type": type(e).__name__
            }, ensure_ascii=False)
        )]


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_deep_analyze(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle deep_analyze tool with comprehensive error handling."""
    url = arguments["url"]
    depth = arguments.get("depth", "full")
    
    async with browser_context_manager() as page:
        try:
            # Start network interception
            await network_interceptor.start_intercepting(page)
            
            # Navigate to URL
            wait_until = "networkidle" if config.wait_for_network_idle else "load"
            await page.goto(url, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
            
            # Get page content
            content = await page.content()
            
            # Analyze network
            requests = await network_interceptor.capture_all_requests()
            responses = await network_interceptor.capture_all_responses()
            
            # Discover APIs
            api_discovery.detect_rest_endpoints(requests, responses)
            graphql_endpoint = api_discovery.detect_graphql(requests, responses)
            
            # Analyze security
            protection_type = bot_detector.detect_protection_type(content, {})
            fingerprinting = bot_detector.analyze_fingerprinting(content)
            
            # Analyze JavaScript
            js_code = await page.evaluate("() => document.documentElement.outerHTML")
            api_calls = js_analyzer.extract_api_calls(js_code)
            
            result = {
                "url": url,
                "depth": depth,
                "apis": {
                    "rest": len(api_discovery.discovered_apis),
                    "graphql": 1 if graphql_endpoint else 0,
                    "websocket": len(network_interceptor.websockets),
                },
                "protection": protection_type.value if protection_type else "none",
                "fingerprinting": {
                    "canvas": fingerprinting.canvas_fingerprint,
                    "webgl": fingerprinting.webgl_fingerprint,
                    "audio": fingerprinting.audio_fingerprint,
                },
                "network_requests": len(requests),
                "api_calls_found": len(api_calls),
                "timestamp": datetime.now().isoformat(),
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Error in deep_analyze for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_discover_apis(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle discover_apis tool."""
    url = arguments["url"]
    include_hidden = arguments.get("include_hidden", True)
    
    async with browser_context_manager() as page:
        try:
            await network_interceptor.start_intercepting(page)
            wait_until = "networkidle" if config.wait_for_network_idle else "load"
            await page.goto(url, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
            
            requests = await network_interceptor.capture_all_requests()
            responses = await network_interceptor.capture_all_responses()
            
            # Discover APIs
            rest_endpoints = api_discovery.detect_rest_endpoints(requests, responses)
            graphql_endpoint = api_discovery.detect_graphql(requests, responses)
            
            internal_apis = []
            if include_hidden:
                internal_apis = api_discovery.find_undocumented_endpoints(requests)
            
            result = {
                "url": url,
                "rest_endpoints": [
                    {
                        "url": ep.url,
                        "method": ep.method,
                        "path": ep.path,
                    }
                    for ep in rest_endpoints
                ],
                "graphql": {
                    "url": graphql_endpoint.url if graphql_endpoint else None,
                },
                "internal_apis": [
                    {
                        "url": api.url,
                        "method": api.method,
                        "confidence": api.confidence,
                    }
                    for api in internal_apis
                ],
                "timestamp": datetime.now().isoformat(),
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Error in discover_apis for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_introspect_graphql(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle introspect_graphql tool."""
    endpoint = arguments["endpoint"]
    
    try:
        schema = await asyncio.wait_for(
            api_discovery.run_introspection(endpoint),
            timeout=config.request_timeout
        )
        
        if schema:
            operations = api_discovery.extract_queries_mutations(schema)
            return {
                "endpoint": endpoint,
                "schema": schema,
                "operations": [
                    {
                        "name": op.name,
                        "type": op.type,
                    }
                    for op in operations
                ],
                "timestamp": datetime.now().isoformat(),
            }
        else:
            return {
                "endpoint": endpoint,
                "error": "Introspection failed or not enabled",
                "timestamp": datetime.now().isoformat(),
            }
    
    except Exception as e:
        logger.error(f"Error in introspect_graphql for {endpoint}: {e}", exc_info=True)
        raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_analyze_websocket(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analyze_websocket tool."""
    url = arguments["url"]
    wait_time = arguments.get("wait_time", 5)
    
    async with browser_context_manager() as page:
        try:
            await network_interceptor.start_intercepting(page)
            wait_until = "networkidle" if config.wait_for_network_idle else "load"
            await page.goto(url, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
            
            # Wait for WebSocket connections
            await asyncio.sleep(wait_time)
            
            ws_session = await network_interceptor.intercept_websocket()
            
            if ws_session:
                messages = await network_interceptor.decode_ws_messages(ws_session.url)
                return {
                    "url": ws_session.url,
                    "messages": [
                        {
                            "direction": msg.direction,
                            "message": msg.message[:100] + "..." if len(msg.message) > 100 else msg.message,
                            "type": msg.message_type,
                        }
                        for msg in messages[:10]  # Limit to first 10
                    ],
                    "total_messages": len(messages),
                    "timestamp": datetime.now().isoformat(),
                }
            else:
                return {
                    "url": url,
                    "error": "No WebSocket connections found",
                    "timestamp": datetime.now().isoformat(),
                }
        
        except Exception as e:
            logger.error(f"Error in analyze_websocket for {url}: {e}", exc_info=True)
            raise


async def handle_record_session(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle record_session tool."""
    url = arguments["url"]
    auto_save = arguments.get("auto_save", True)
    
    try:
        context = await create_stealth_context(browser_pool)
        page = await context.new_page()
        page.set_default_timeout(config.navigation_timeout * 1000)
        
        recorder = SessionRecorder()
        recording = await recorder.start_recording(page)
        
        # Register with storage
        recording_storage.register_active_recording(recording)
        
        # Navigate to URL
        wait_until = "networkidle" if config.wait_for_network_idle else "load"
        await page.goto(url, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
        
        # Store active recording
        _active_recordings[recording.id] = (recorder, page, context)
        
        return {
            "recording_id": recording.id,
            "status": "recording",
            "url": url,
            "auto_save": auto_save,
            "message": "Session recording started. Use stop_recording to finish.",
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error starting recording for {url}: {e}", exc_info=True)
        raise


async def handle_stop_recording(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle stop_recording tool."""
    recording_id = arguments["recording_id"]
    save = arguments.get("save", True)
    
    if recording_id not in _active_recordings:
        return {
            "error": f"Recording {recording_id} not found or already stopped",
            "recording_id": recording_id,
        }
    
    try:
        recorder, page, context = _active_recordings[recording_id]
        
        # Stop recording
        recording = await recorder.stop_recording()
        
        if not recording:
            return {
                "error": "Failed to stop recording",
                "recording_id": recording_id,
            }
        
        # Save if requested
        file_path = None
        if save or config.auto_save_recordings:
            file_path = recording_storage.save_recording(recording)
        
        # Cleanup
        try:
            await page.close()
            await context.close()
        except Exception as e:
            logger.warning(f"Error cleaning up recording {recording_id}: {e}")
        
        # Remove from active recordings
        del _active_recordings[recording_id]
        recording_storage.unregister_active_recording(recording_id)
        
        return {
            "recording_id": recording_id,
            "status": "stopped",
            "duration": recording.duration,
            "events_count": len(recording.events),
            "snapshots_count": len(recording.state_snapshots),
            "network_events_count": len(recording.network),
            "saved": save or config.auto_save_recordings,
            "file_path": file_path,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error stopping recording {recording_id}: {e}", exc_info=True)
        raise


async def handle_list_recordings(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle list_recordings tool."""
    status_filter = arguments.get("status", "all")
    
    try:
        all_recordings = recording_storage.list_recordings()
        
        if status_filter == "active":
            recordings = [r for r in all_recordings if r.get("status") == "active"]
        elif status_filter == "saved":
            recordings = [r for r in all_recordings if r.get("status") == "saved"]
        else:
            recordings = all_recordings
        
        return {
            "recordings": recordings,
            "total": len(recordings),
            "active": len([r for r in recordings if r.get("status") == "active"]),
            "saved": len([r for r in recordings if r.get("status") == "saved"]),
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error listing recordings: {e}", exc_info=True)
        raise


async def handle_get_recording_status(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle get_recording_status tool."""
    recording_id = arguments["recording_id"]
    
    try:
        # Check if active
        if recording_id in _active_recordings:
            recorder, page, context = _active_recordings[recording_id]
            recording = recorder._recording if recorder._recording else None
            
            if recording:
                return {
                    "recording_id": recording_id,
                    "status": "active",
                    "start_time": recording.start_time.isoformat() if recording.start_time else None,
                    "duration": recording.duration,
                    "events_count": len(recording.events),
                    "snapshots_count": len(recording.state_snapshots),
                    "network_events_count": len(recording.network),
                }
        
        # Try loading from storage
        recording = recording_storage.load_recording(recording_id)
        
        if recording:
            return {
                "recording_id": recording_id,
                "status": "saved",
                "start_time": recording.start_time.isoformat() if recording.start_time else None,
                "end_time": recording.end_time.isoformat() if recording.end_time else None,
                "duration": recording.duration,
                "events_count": len(recording.events),
                "snapshots_count": len(recording.state_snapshots),
                "network_events_count": len(recording.network),
            }
        else:
            return {
                "error": f"Recording {recording_id} not found",
                "recording_id": recording_id,
            }
    
    except Exception as e:
        logger.error(f"Error getting recording status for {recording_id}: {e}", exc_info=True)
        raise


async def handle_generate_crawler(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle generate_crawler tool."""
    recording_id = arguments["recording_id"]
    output_format = arguments.get("output_format", "yaml")
    
    try:
        # Load recording from storage
        recording = recording_storage.load_recording(recording_id)
        
        if not recording:
            return {
                "error": f"Recording {recording_id} not found. Please provide a valid recording ID or file path.",
                "recording_id": recording_id,
            }
        
        # Generate crawler
        generator = CrawlerGenerator()
        crawler_def = generator.from_recording(recording)
        crawler_def = generator.optimize_crawler(crawler_def)
        
        # Convert to requested format
        if output_format == "yaml":
            output = generator.to_yaml(crawler_def)
        elif output_format == "python":
            output = generator.to_python_code(crawler_def)
        elif output_format == "playwright":
            output = generator.to_playwright_script(crawler_def)
        else:
            output = generator.to_yaml(crawler_def)
        
        return {
            "recording_id": recording_id,
            "output_format": output_format,
            "status": "generated",
            "crawler": {
                "name": crawler_def.name,
                "description": crawler_def.description,
                "steps_count": len(crawler_def.steps),
            },
            "output": output,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error generating crawler from {recording_id}: {e}", exc_info=True)
        raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_analyze_auth(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analyze_auth tool."""
    url = arguments["url"]
    
    async with browser_context_manager() as page:
        try:
            await network_interceptor.start_intercepting(page)
            wait_until = "networkidle" if config.wait_for_network_idle else "load"
            await page.goto(url, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
            
            requests = await network_interceptor.capture_all_requests()
            
            auth_requests = []
            for req in requests:
                analyzed = request_analyzer.analyze(req)
                if analyzed.auth_type.value != "none":
                    auth_requests.append({
                        "url": analyzed.url,
                        "auth_type": analyzed.auth_type.value,
                    })
            
            return {
                "url": url,
                "auth_flows": auth_requests,
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Error in analyze_auth for {url}: {e}", exc_info=True)
            raise


@with_retry(max_retries=config.max_retries, delay=config.retry_delay)
async def handle_detect_protection(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle detect_protection tool."""
    url = arguments["url"]
    
    async with browser_context_manager() as page:
        try:
            wait_until = "networkidle" if config.wait_for_network_idle else "load"
            response = await page.goto(url, wait_until=wait_until, timeout=config.navigation_timeout * 1000)
            content = await page.content()
            
            headers = response.headers if response else {}
            
            protection_type = bot_detector.detect_protection_type(content, headers)
            fingerprinting = bot_detector.analyze_fingerprinting(content)
            captcha_type = bot_detector.detect_captcha_type(content)
            
            return {
                "url": url,
                "protection_type": protection_type.value if protection_type else "none",
                "captcha_type": captcha_type.value if captcha_type else "none",
                "fingerprinting": {
                    "canvas": fingerprinting.canvas_fingerprint,
                    "webgl": fingerprinting.webgl_fingerprint,
                    "audio": fingerprinting.audio_fingerprint,
                },
                "timestamp": datetime.now().isoformat(),
            }
        
        except Exception as e:
            logger.error(f"Error in detect_protection for {url}: {e}", exc_info=True)
            raise


async def handle_deobfuscate_js(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle deobfuscate_js tool."""
    code = arguments["code"]
    
    if not code or not isinstance(code, str):
        return {
            "error": "Invalid code: must be a non-empty string",
        }
    
    try:
        # Detect obfuscation type
        obfuscation_type = js_deobfuscator.detect_obfuscation_type(code)
        
        # Deobfuscate based on type
        deobfuscated = code
        if obfuscation_type.value == "string_encoding":
            deobfuscated = js_deobfuscator.deobfuscate_strings(code)
        elif obfuscation_type.value == "control_flow_flattening":
            deobfuscated = js_deobfuscator.simplify_control_flow(code)
        else:
            # Try all deobfuscation methods
            deobfuscated = js_deobfuscator.deobfuscate_strings(code)
            deobfuscated = js_deobfuscator.simplify_control_flow(deobfuscated)
        
        # Extract original names if possible
        name_map = js_deobfuscator.extract_original_names(code)
        
        improvement = "0%"
        if code:
            size_change = ((len(code) - len(deobfuscated)) / len(code) * 100)
            improvement = f"{size_change:.1f}% size change"
        
        return {
            "original_length": len(code),
            "deobfuscated_length": len(deobfuscated),
            "obfuscation_type": obfuscation_type.value,
            "deobfuscated": deobfuscated,
            "extracted_names": name_map,
            "improvement": improvement,
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error deobfuscating JS: {e}", exc_info=True)
        raise


async def handle_extract_from_js(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle extract_from_js tool."""
    code = arguments["code"]
    
    if not code or not isinstance(code, str):
        return {
            "error": "Invalid code: must be a non-empty string",
        }
    
    try:
        api_calls = js_analyzer.extract_api_calls(code)
        urls = js_analyzer.find_hardcoded_urls(code)
        constants = js_analyzer.extract_constants(code)
        auth_logic = js_analyzer.find_auth_logic(code)
        
        return {
            "api_calls": [
                {
                    "url": call.url,
                    "method": call.method,
                    "type": call.type,
                }
                for call in api_calls
            ],
            "hardcoded_urls": urls,
            "constants": constants,
            "auth_logic": {
                "flow_type": auth_logic.flow_type if auth_logic else None,
                "token_storage": auth_logic.token_storage if auth_logic else None,
            },
            "timestamp": datetime.now().isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Error extracting from JS: {e}", exc_info=True)
        raise


async def handle_health_check(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle health_check tool."""
    try:
        # Check browser pool
        pool_stats = browser_pool.get_stats()
        
        # Check storage
        recordings = recording_storage.list_recordings()
        
        # Check active recordings
        active_count = len(_active_recordings)
        
        health_status = {
            "status": "healthy",
            "browser_pool": {
                "size": pool_stats["size"],
                "max_size": pool_stats["max_size"],
                "healthy": pool_stats["size"] <= pool_stats["max_size"],
            },
            "storage": {
                "recordings_count": len(recordings),
                "active_recordings": active_count,
                "healthy": True,
            },
            "config": {
                "navigation_timeout": config.navigation_timeout,
                "operation_timeout": config.operation_timeout,
                "max_retries": config.max_retries,
            },
            "timestamp": datetime.now().isoformat(),
        }
        
        # Determine overall health
        if not health_status["browser_pool"]["healthy"]:
            health_status["status"] = "degraded"
        
        return health_status
    
    except Exception as e:
        logger.error(f"Error in health check: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


async def main():
    """Main entry point for MCP server."""
    await init_browser_pool()
    
    from mcp.server.stdio import stdio_server
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    finally:
        # Cleanup on shutdown
        await browser_pool.close()
        logger.info("MCP server shutdown complete")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())
