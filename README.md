# Crawilfy MCP Server

<p align="center">
  <img src="https://raw.githubusercontent.com/razavioo/crawilfy-mcp-server/main/assets/hero.png" alt="Crawilfy MCP Server — free, AI-native web crawling for the agent era" width="100%"/>
</p>

<p align="left">
  <img alt="python 3.10+ · pypi 1.1.0 · MIT · MCP-native · code style black" src="https://raw.githubusercontent.com/razavioo/crawilfy-mcp-server/main/assets/badges.png" height="22"/>
</p>

A **free, open-source MCP server** that gives any agent (Claude Code, Cursor, Windsurf, …) **55 production-grade tools** for the full web-crawling stack: deep analysis, stealth, API discovery, session recording → runnable crawler, smart extraction. No proprietary API. No per-request fee.

<p align="center">
  <img src="https://raw.githubusercontent.com/razavioo/crawilfy-mcp-server/main/assets/features.png" alt="Crawilfy capabilities — deep analysis, stealth, record→crawler, smart extraction" width="100%"/>
</p>

---

## Quick start

<p align="center">
  <img src="https://raw.githubusercontent.com/razavioo/crawilfy-mcp-server/main/assets/install.png" alt="Three install paths — uvx, pipx, pip" width="100%"/>
</p>

The recommended path needs no install — `uvx` runs straight from PyPI:

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

> Requires [`uv`](https://docs.astral.sh/uv/getting-started/installation/). Install once: `curl -LsSf https://astral.sh/uv/install.sh | sh`. Or use `pipx run crawilfy-mcp-server` / `pip install crawilfy-mcp-server` instead.

**Where to put that JSON:** Cursor → Settings → MCP. Claude Code → `~/.config/claude/mcp_settings.json`. Windsurf → Settings → MCP Servers.

---

## How it works

<p align="center">
  <img src="https://raw.githubusercontent.com/razavioo/crawilfy-mcp-server/main/assets/architecture.png" alt="Agent → Crawilfy → Browser/HTTP/Proxy → target web" width="100%"/>
</p>

Your agent talks to Crawilfy over the Model Context Protocol. Crawilfy owns a hardened browser pool, an HTTP stack with TLS fingerprinting, and a rotating proxy pool. While it fetches pages, it captures network traffic, reads scripts, and introspects schemas — so the agent gets clean structured data, not raw HTML.

---

## What's in the box

A short list — see the source for the full set of 55 tools.

| Group | Tools |
|---|---|
| **Deep analysis** | `deep_analyze`, `discover_apis`, `introspect_graphql`, `analyze_websocket`, `analyze_auth`, `detect_protection`, `detect_technology` |
| **Stealth** | `stealth_request`, `configure_proxies`, `configure_rate_limit`, `add_proxy`, `test_proxy` |
| **Record → crawler** | `record_session`, `stop_recording`, `export_recording`, `generate_crawler` |
| **Extraction** | `smart_extract`, `extract_article`, `extract_tables`, `extract_links`, `extract_forms`, `extract_metadata`, `convert_to_markdown` |
| **Page interaction** | `take_screenshot`, `fill_form`, `wait_and_extract`, `compare_pages`, `measure_performance`, `check_accessibility`, `get_dom_tree` |
| **Sessions & cache** | `save_session`, `load_session`, `get_cookies`, `get_storage`, `clear_cache`, `get_cache_stats` |
| **Advanced (opt-in)** | `execute_js`, `execute_cdp`, `deobfuscate_js`, `extract_from_js`, `solve_captcha` |

---

## Smart extraction — bring any LLM, including free ones

`smart_extract` works **without any API key** using pattern matching. Plug in any OpenAI-compatible endpoint for higher accuracy — including FREE tiers:

```bash
# OpenRouter (free models exist)
CRAWILFY_LLM_PROVIDER=openrouter
CRAWILFY_LLM_API_KEY=sk-or-v1-xxx
CRAWILFY_LLM_MODEL=meta-llama/llama-3.2-3b-instruct:free

# Groq (free, very fast)
CRAWILFY_LLM_PROVIDER=groq
CRAWILFY_LLM_API_KEY=gsk_xxx

# Local Ollama (no key needed)
CRAWILFY_LLM_PROVIDER=ollama
CRAWILFY_LLM_MODEL=llama3.2
```

Together, DeepSeek, Mistral, Fireworks, and standard OpenAI also work via `CRAWILFY_LLM_BASE_URL`.

---

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `CRAWILFY_HEADLESS` | `true` | Run browser without UI |
| `CRAWILFY_BROWSER` | `chromium` | `chromium` / `firefox` / `webkit` |
| `CRAWILFY_POOL_SIZE` | `5` | Max concurrent browsers |
| `CRAWILFY_NAV_TIMEOUT` | `30.0` | Page-load timeout (s) |
| `CRAWILFY_API_KEY` | _unset_ | If set, every tool call must include matching `_api_key` |
| `CRAWILFY_ALLOW_DANGEROUS_JS` | `false` | Required for `execute_js` / `execute_cdp` / `deobfuscate_js` |
| `CRAWILFY_JS_MAX_LENGTH` | `50000` | Length cap for JS payloads |
| `CRAWILFY_JS_EXEC_TIMEOUT` | `10.0` | Per-script timeout (s) |

---

## Security

`execute_js`, `execute_cdp`, and `deobfuscate_js` are **disabled by default** — they execute or operate on arbitrary code in a real browser. Enable on trusted networks with `CRAWILFY_ALLOW_DANGEROUS_JS=true`. Even then, payloads are length-capped, time-bounded, and a denylist rejects `eval`, `new Function`, dynamic `import()`, `document.write`, `importScripts`, and `WebAssembly.{compile,instantiate}`. Set `CRAWILFY_API_KEY` so MCP clients must present a matching `_api_key`.

These are mitigations, not a sandbox: do not expose this server to untrusted clients.

---

## Develop

```bash
git clone https://github.com/razavioo/crawilfy-mcp-server.git
cd crawilfy-mcp-server
make dev-install      # editable install + dev/captcha/ocr extras + pre-commit
make test             # pytest
make lint             # ruff + mypy
```

PRs welcome. Particularly interested in: distributed mode (Redis queue), result sinks (Postgres / S3), Prometheus metrics. See [`MIT License`](LICENSE).

<p align="center"><sub>Made by <a href="https://emad.dev">emad.dev</a></sub></p>
