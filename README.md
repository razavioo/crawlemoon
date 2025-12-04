# Crawilfy MCP Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/crawilfy-mcp-server.svg)](https://pypi.org/project/crawilfy-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Advanced web crawling platform with deep analysis capabilities, automatic API discovery, and crawler generation. Built as an MCP (Model Context Protocol) server for seamless integration with AI assistants like **Cursor**, **Claude Code**, and **Windsurf**.

---

## ⚡ Quick Start (Single Command)

### Option 1: Using uvx (Recommended - No Installation Required)

The simplest way to use Crawilfy. Just add this to your MCP configuration:

```json
{
  "mcpServers": {
    "crawilfy": {
      "command": "uvx",
      "args": ["crawilfy-mcp-server"]
    }
  }
}
```

> **Note:** Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) to be installed. Install with: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Option 2: Using pipx

```json
{
  "mcpServers": {
    "crawilfy": {
      "command": "pipx",
      "args": ["run", "crawilfy-mcp-server"]
    }
  }
}
```

### Option 3: Using pip (Global Install)

```bash
pip install crawilfy-mcp-server
playwright install chromium
```

Then add to your MCP configuration:

```json
{
  "mcpServers": {
    "crawilfy": {
      "command": "python",
      "args": ["-m", "src.mcp.server"]
    }
  }
}
```

---

## 🔧 Where to Add MCP Configuration

### For Cursor IDE
1. Open Settings (`Cmd/Ctrl + ,`)
2. Search for "MCP" 
3. Click "Edit in settings.json"
4. Add the configuration under `mcpServers`

### For Claude Code
1. Open the MCP settings file at `~/.config/claude/mcp_settings.json`
2. Add the configuration

### For Windsurf
1. Open Settings → MCP Servers
2. Add the configuration

---

## 🛠️ Available Tools (55 Total)

### 🔍 Deep Analysis & Discovery
| Tool | Description |
|------|-------------|
| `deep_analyze` | Comprehensive analysis of a website (network + JS + security) |
| `discover_apis` | Discover all REST and GraphQL APIs including hidden endpoints |
| `introspect_graphql` | Extract complete GraphQL schema using introspection |
| `execute_graphql` | Execute GraphQL queries and mutations |
| `analyze_websocket` | Intercept and analyze WebSocket connections |
| `analyze_auth` | Analyze authentication flow and mechanisms |
| `detect_protection` | Detect anti-bot systems, CAPTCHAs, and fingerprinting |
| `detect_technology` | Detect technology stack (CMS, frameworks, CDN, analytics) |

### 📜 JavaScript Analysis
| Tool | Description |
|------|-------------|
| `deobfuscate_js` | Deobfuscate JavaScript code with multiple techniques |
| `extract_from_js` | Extract API endpoints, URLs, constants, and auth logic from JS |

### 🎬 Session Recording & Crawlers
| Tool | Description |
|------|-------------|
| `record_session` | Start recording an interactive browser session |
| `stop_recording` | Stop an active recording and save it |
| `list_recordings` | List all available recordings (active and saved) |
| `get_recording_status` | Get status and details of a specific recording |
| `delete_recording` | Delete a saved recording |
| `export_recording` | Export recording to JSON, HAR, or Playwright test format |
| `generate_crawler` | Generate crawler script from recording (YAML, Python, Playwright) |

### 📄 Content Extraction
| Tool | Description |
|------|-------------|
| `extract_article` | Extract clean article content with intelligent parsing |
| `convert_to_markdown` | Convert webpage to clean markdown for LLM consumption |
| `smart_extract` | Extract data using natural language queries (AI-powered) |
| `extract_links` | Extract all links with filtering options |
| `extract_forms` | Extract all forms with field details |
| `extract_metadata` | Extract OG tags, Twitter cards, JSON-LD structured data |
| `extract_tables` | Extract tables as JSON, CSV, or Markdown |
| `wait_and_extract` | Wait for dynamic elements and extract content |

### 🌐 Network & Sitemap
| Tool | Description |
|------|-------------|
| `analyze_sitemap` | Analyze sitemap.xml to extract URLs and metadata |
| `check_robots` | Analyze robots.txt for crawl rules and sitemaps |
| `monitor_network` | Monitor network traffic for a specified duration |

### 🖥️ Page Interaction
| Tool | Description |
|------|-------------|
| `take_screenshot` | Take full-page or viewport screenshots |
| `execute_js` | Execute JavaScript on a page and return results |
| `get_cookies` | Get all cookies from a page/domain |
| `get_storage` | Get localStorage and sessionStorage |
| `fill_form` | Automatically fill form fields with provided data |

### 🔐 Session & Proxy Management
| Tool | Description |
|------|-------------|
| `save_session` | Save browser session (cookies, storage) for reuse |
| `load_session` | Load a previously saved session |
| `list_sessions` | List all saved sessions |
| `configure_proxies` | Configure proxy pool with rotation strategies |
| `get_proxy_stats` | Get proxy pool health and usage statistics |
| `add_proxy` | Add a proxy to the pool |
| `remove_proxy` | Remove a proxy from the pool |
| `test_proxy` | Test a proxy's connectivity |

### 📊 Performance & Analysis
| Tool | Description |
|------|-------------|
| `measure_performance` | Measure page load timing and Core Web Vitals |
| `analyze_resources` | Analyze all loaded resources (scripts, images, fonts) |
| `check_accessibility` | Run accessibility checks and report issues |
| `compare_pages` | Compare two pages for structure/content differences |

### 🛡️ Stealth & Anti-Detection
| Tool | Description |
|------|-------------|
| `stealth_request` | Make HTTP requests with TLS fingerprint impersonation |
| `solve_captcha` | Detect and solve CAPTCHAs (reCAPTCHA, hCaptcha, Turnstile) |

### ⚙️ Advanced (CDP & Cache)
| Tool | Description |
|------|-------------|
| `execute_cdp` | Execute raw Chrome DevTools Protocol commands |
| `get_dom_tree` | Get full DOM tree via CDP |
| `clear_cache` | Clear cached pages, responses, or state snapshots |
| `get_cache_stats` | Get cache statistics |
| `configure_rate_limit` | Configure rate limiting per domain |
| `get_rate_limit_stats` | Get rate limiter statistics |

### 🔧 System
| Tool | Description |
|------|-------------|
| `health_check` | Check health of server, browser pool, and storage |

---

## ✨ Features

- ✅ **55 Powerful Tools** - From deep analysis to crawler generation
- ✅ **Stealth Mode** - TLS fingerprint impersonation, anti-detection
- ✅ **AI-Powered Extraction** - Natural language queries for data extraction
- ✅ **Session Recording** - Record and replay browser sessions
- ✅ **Auto Crawler Generation** - Generate Python/Playwright/YAML crawlers
- ✅ **Proxy Pool** - Rotation strategies, health checking
- ✅ **Rate Limiting** - Per-domain rate limits with backoff
- ✅ **CAPTCHA Solving** - reCAPTCHA, hCaptcha, Cloudflare Turnstile
- ✅ **Technology Detection** - Detect CMS, frameworks, CDNs
- ✅ **Performance Metrics** - Core Web Vitals, resource analysis
- ✅ **Accessibility Checks** - Automated a11y auditing

---

## 🔧 Configuration (Optional)

Customize behavior with environment variables:

```json
{
  "mcpServers": {
    "crawilfy": {
      "command": "uvx",
      "args": ["crawilfy-mcp-server"],
      "env": {
        "CRAWILFY_HEADLESS": "true",
        "CRAWILFY_BROWSER": "chromium",
        "CRAWILFY_NAV_TIMEOUT": "30.0",
        "CRAWILFY_OP_TIMEOUT": "60.0",
        "CRAWILFY_POOL_SIZE": "5",
        "CRAWILFY_RATE_LIMIT_RPS": "1.0",
        "CRAWILFY_PROXIES": "http://proxy1:8080,http://proxy2:8080",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

| Variable | Description | Default |
|----------|-------------|---------|
| `CRAWILFY_HEADLESS` | Run browser in background | `true` |
| `CRAWILFY_BROWSER` | Browser type (chromium/firefox/webkit) | `chromium` |
| `CRAWILFY_NAV_TIMEOUT` | Page load timeout (seconds) | `30.0` |
| `CRAWILFY_OP_TIMEOUT` | Operation timeout (seconds) | `60.0` |
| `CRAWILFY_POOL_SIZE` | Max browser instances | `5` |
| `CRAWILFY_RATE_LIMIT_RPS` | Requests per second | `1.0` |
| `CRAWILFY_PROXIES` | Comma-separated proxy URLs | - |
| `OPENAI_API_KEY` | For AI-powered smart extraction | - |

---

## 📦 Manual Installation (For Development)

```bash
# Clone the repository
git clone https://github.com/emad-dev/crawilfy-mcp-server.git
cd crawilfy-mcp-server

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install with dependencies
pip install -e .

# Install browser
playwright install chromium
```

Then configure MCP with local path:

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

---

## 💻 Python API

Use Crawilfy programmatically in your own code:

```python
import asyncio
from src.core.browser.pool import BrowserPool
from src.core.browser.stealth import create_stealth_context
from src.intelligence.network.api_discovery import APIDiscoveryEngine

async def analyze_site(url):
    pool = BrowserPool()
    await pool.initialize()
    
    try:
        context = await create_stealth_context(pool)
        page = await context.new_page()
        
        await page.goto(url)
        
        # Your analysis code here
        
        await context.close()
    finally:
        await pool.close()

asyncio.run(analyze_site("https://example.com"))
```

---

## 🧪 CLI Usage

```bash
# Deep analysis
crawl deep-analyze https://example.com --full

# Discover APIs
crawl discover-apis https://example.com --include-hidden

# Record session
crawl record https://example.com --output session.json

# Generate crawler
crawl generate --from-recording session.json --output crawler.yaml
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

```bash
# Development setup
pip install -e ".[dev]"

# Run tests
pytest

# Code formatting
black src tests
ruff check src tests
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with ❤️ by <a href="https://emad.dev">emad.dev</a>
</p>
