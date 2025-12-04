# Crawilfy MCP Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Advanced web crawling platform with deep analysis capabilities, automatic API discovery, and crawler generation. Built as an MCP (Model Context Protocol) server for seamless integration with AI assistants and development tools.

## Features

### 🔧 Core Engine
- Browser Pool Manager with context isolation
- Session & Credential Manager with rotation
- Advanced Cache Layer

### 🌐 Deep Network Engine
- Network Interceptor for HTTP/HTTPS/WebSocket
- API Discovery Engine (REST, GraphQL, Hidden APIs)
- Request Analyzer with auth and pagination analysis

### 📜 JavaScript Analysis
- Static Code Analyzer
- Dynamic Runtime Analysis
- JS Deobfuscator

### 🎬 Session Recording & Replay
- Full Session Recorder
- State Machine Generator
- Automatic Crawler Generation

### 🛡️ Security & Anti-Bot
- Bot Detection Analyzer
- Stealth Mode
- Auth Flow Analyzer

### 🔌 MCP Server
MCP Protocol support with advanced tools for analysis and crawling.

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

### CLI

```bash
# Deep analysis
python -m src.cli.main deep-analyze https://example.com --full

# Discover APIs
python -m src.cli.main discover-apis https://example.com --include-hidden

# Record session
python -m src.cli.main record https://example.com --output session.json

# Generate crawler
python -m src.cli.main generate --from-recording session.json --output crawler.yaml
```

### MCP Server

```bash
python -m src.mcp.server
```

The MCP server provides the following tools:

#### Analysis Tools
- `deep_analyze`: Comprehensive deep analysis of a website (network + JS + security)
- `discover_apis`: Discover all REST and GraphQL APIs including hidden endpoints
- `introspect_graphql`: Extract complete GraphQL schema using introspection
- `analyze_websocket`: Intercept and analyze WebSocket connections
- `analyze_auth`: Analyze authentication flow and mechanisms
- `detect_protection`: Detect anti-bot systems, CAPTCHAs, and fingerprinting

#### JavaScript Analysis
- `deobfuscate_js`: Deobfuscate JavaScript code with multiple techniques
- `extract_from_js`: Extract API endpoints, URLs, constants, and auth logic from JS

#### Session Recording & Crawler Generation
- `record_session`: Start recording an interactive browser session
- `stop_recording`: Stop an active recording and save it
- `list_recordings`: List all available recordings (active and saved)
- `get_recording_status`: Get status and details of a specific recording
- `generate_crawler`: Generate crawler script from recording (YAML, Python, Playwright)

#### System Tools
- `health_check`: Check health status of server, browser pool, and storage

#### Features
- ✅ **Input Validation**: All tools validate inputs with clear error messages
- ✅ **Timeout Handling**: Configurable timeouts for all operations
- ✅ **Retry Logic**: Automatic retries for network operations
- ✅ **Resource Management**: Proper cleanup of browser contexts and pages
- ✅ **Recording Storage**: Persistent storage for session recordings
- ✅ **Error Handling**: Comprehensive error handling with detailed messages
- ✅ **Configuration**: Environment variable support for all settings

### Python API Example

```python
import asyncio
from src.core.browser.pool import BrowserPool
from src.core.browser.stealth import create_stealth_context
from src.intelligence.network.interceptor import DeepNetworkInterceptor
from src.intelligence.network.api_discovery import APIDiscoveryEngine

async def analyze_site(url):
    pool = BrowserPool()
    await pool.initialize()
    
    try:
        context = await create_stealth_context(pool)
        page = await context.new_page()
        
        interceptor = DeepNetworkInterceptor()
        await interceptor.start_intercepting(page)
        
        await page.goto(url)
        
        requests = await interceptor.capture_all_requests()
        responses = await interceptor.capture_all_responses()
        
        discovery = APIDiscoveryEngine()
        endpoints = discovery.detect_rest_endpoints(requests, responses)
        
        print(f"Found {len(endpoints)} API endpoints")
        
        await page.close()
        await context.close()
    finally:
        await pool.close()

asyncio.run(analyze_site("https://example.com"))
```

## Project Structure

```
src/
├── core/           # Core engine
│   ├── browser/    # Browser management
│   ├── session/    # Session management
│   └── cache/      # Cache layer
├── intelligence/   # Analysis engines
│   ├── network/    # Network analysis
│   ├── js/         # JavaScript analysis
│   ├── security/   # Security analysis
│   ├── recorder/   # Session recording
│   └── generator/  # Crawler generation
├── mcp/            # MCP Server
├── cli/            # Command line interface
└── crawlers/       # Generated crawlers
```

## Configuration

The MCP server can be configured using environment variables:

```bash
# Timeouts (in seconds)
export CRAWILFY_NAV_TIMEOUT=30.0      # Navigation timeout
export CRAWILFY_REQ_TIMEOUT=30.0     # Request timeout
export CRAWILFY_OP_TIMEOUT=60.0      # Operation timeout

# Browser settings
export CRAWILFY_HEADLESS=true        # Run browser in headless mode
export CRAWILFY_BROWSER=chromium     # Browser type (chromium, firefox, webkit)
export CRAWILFY_POOL_SIZE=5           # Max browser pool size

# Retry settings
export CRAWILFY_MAX_RETRIES=3         # Max retry attempts
export CRAWILFY_RETRY_DELAY=1.0       # Delay between retries (seconds)

# Recording settings
export CRAWILFY_RECORDING_DIR=/path/to/recordings  # Custom storage directory
export CRAWILFY_AUTO_SAVE=true        # Auto-save recordings

# Analysis settings
export CRAWILFY_WAIT_NETWORK=true     # Wait for network idle
export CRAWILFY_SCREENSHOTS=false     # Capture screenshots
```

## Development

### Setup

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test module
pytest tests/test_browser_pool.py
pytest tests/test_mcp_server.py
pytest tests/test_recording_storage.py
```

### Code Quality

```bash
# Format code
black src tests

# Lint code
ruff check src tests

# Type checking
mypy src
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details.
