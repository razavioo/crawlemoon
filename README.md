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

## Quick Start: Setting Up in Cursor or Claude Code

Follow these simple steps to add Crawilfy MCP Server to your AI assistant.

### Step 1: Download and Navigate to the Project

1. Download or clone this project to your computer
2. Open Terminal (Mac) or Command Prompt (Windows)
3. Navigate to the project folder:
   ```bash
   cd /path/to/crawilfy-mcp-server
   ```
   *(Replace `/path/to/` with the actual location where you saved the project)*

### Step 2: Create a Virtual Environment

A virtual environment keeps this project's packages separate from other Python projects on your computer.

**On Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

You'll know it worked when you see `(venv)` at the beginning of your terminal prompt.

### Step 3: Install Dependencies

With the virtual environment activated, run:

```bash
# Install the package and all required libraries
pip install -e .

# Install the browser (this may take a few minutes)
playwright install chromium
```

### Step 4: Configure in Cursor or Claude Code

1. **Open Cursor/Claude Code Settings:**
   - Press `Cmd + ,` (Mac) or `Ctrl + ,` (Windows) to open settings
   - Search for "MCP" or "Model Context Protocol"

2. **Add the MCP Server:**
   
   Click "Add MCP Server" or edit the MCP settings JSON file, then add this configuration:

   ```json
   {
     "mcpServers": {
       "crawilfy": {
         "command": "/path/to/crawilfy-mcp-server/venv/bin/python",
         "args": ["-m", "src.mcp.server"],
         "cwd": "/path/to/crawilfy-mcp-server"
       }
     }
   }
   ```

   **Important:** Replace `/path/to/crawilfy-mcp-server` with the actual path where you saved the project.
   
   **On Windows:** Use `venv\Scripts\python.exe` instead of `venv/bin/python`

3. **Save and Restart:**
   - Save the configuration
   - Restart Cursor/Claude Code completely
   - The server should now be available!

### Step 5: Verify It's Working

After restarting, you should see the Crawilfy tools available in your AI assistant. Try asking:
- "Can you analyze a website for me?"
- "Discover APIs on example.com"
- "Check the health of the crawilfy server"

### Troubleshooting

**Problem:** "python command not found"
- **Solution:** Use `python3` instead of `python`, or use the full path to your Python installation

**Problem:** "ModuleNotFoundError: No module named 'src'"
- **Solution:** Make sure you ran `pip install -e .` in Step 3, and that the `cwd` path in your MCP config is correct

**Problem:** "ENOENT" or "spawn error"
- **Solution:** Check that the path to `venv/bin/python` (or `venv\Scripts\python.exe` on Windows) is correct in your MCP configuration

**Still having issues?** Check the MCP server logs in Cursor/Claude Code settings for detailed error messages.

---

## Available Tools

Once set up, the MCP server provides these tools you can use through your AI assistant:

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

---

## Python API (For Developers)

If you want to use Crawilfy programmatically in your own Python code:

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

## Advanced Configuration (Optional)

The MCP server works with default settings, but you can customize it by adding environment variables to your MCP configuration:

```json
{
  "mcpServers": {
    "crawilfy": {
      "command": "/path/to/crawilfy-mcp-server/venv/bin/python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/path/to/crawilfy-mcp-server",
      "env": {
        "CRAWILFY_HEADLESS": "true",
        "CRAWILFY_BROWSER": "chromium",
        "CRAWILFY_NAV_TIMEOUT": "30.0",
        "CRAWILFY_OP_TIMEOUT": "60.0"
      }
    }
  }
}
```

**Available settings:**
- `CRAWILFY_HEADLESS`: Run browser in background (`true` or `false`, default: `true`)
- `CRAWILFY_BROWSER`: Browser type (`chromium`, `firefox`, or `webkit`, default: `chromium`)
- `CRAWILFY_NAV_TIMEOUT`: Page load timeout in seconds (default: `30.0`)
- `CRAWILFY_OP_TIMEOUT`: Operation timeout in seconds (default: `60.0`)
- `CRAWILFY_POOL_SIZE`: Maximum number of browsers (default: `5`)

Most users don't need to change these settings.

---

## For Developers

### Development Setup

If you're contributing to or modifying this project:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium
```

### Command Line Interface

You can also use Crawilfy from the command line:

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
