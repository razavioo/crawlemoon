"""Crawler generator from state machines and recordings."""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from ..recorder.session import SessionRecording

logger = logging.getLogger(__name__)


@dataclass
class CrawlerDefinition:
    """Crawler definition."""
    
    name: str
    description: str
    steps: list
    config: Dict[str, Any]


class CrawlerGenerator:
    """Generates crawlers from recordings or state machines."""
    
    def from_state_machine(self, sm) -> CrawlerDefinition:
        """Generate crawler from state machine."""
        # Placeholder implementation
        logger.info("Generating crawler from state machine")
        return CrawlerDefinition(
            name="generated_crawler",
            description="Generated from state machine",
            steps=[],
            config={},
        )
    
    def from_recording(self, recording: SessionRecording) -> CrawlerDefinition:
        """Generate crawler from recording."""
        steps = []
        
        # Convert events to steps
        for event in recording.events:
            if event.type.value == "click":
                steps.append({
                    "action": "click",
                    "selector": event.selector or "",
                    "data": event.data,
                })
            elif event.type.value == "navigate":
                steps.append({
                    "action": "navigate",
                    "url": event.data.get("url", ""),
                })
        
        return CrawlerDefinition(
            name=f"crawler_{recording.id}",
            description=f"Generated from recording {recording.id}",
            steps=steps,
            config={
                "initial_url": recording.state_snapshots[0].url if recording.state_snapshots else "",
            },
        )
    
    def optimize_crawler(self, crawler: CrawlerDefinition) -> CrawlerDefinition:
        """Optimize crawler definition."""
        # Remove redundant steps, optimize selectors, etc.
        logger.info("Optimizing crawler")
        return crawler
    
    def to_yaml(self, crawler: CrawlerDefinition) -> str:
        """Convert crawler to YAML format."""
        import yaml
        return yaml.dump({
            "name": crawler.name,
            "description": crawler.description,
            "config": crawler.config,
            "steps": crawler.steps,
        }, default_flow_style=False)
    
    def to_python_code(self, crawler: CrawlerDefinition) -> str:
        """Convert crawler to Python code."""
        code = f"""# Generated crawler: {crawler.name}
from playwright.async_api import async_playwright

async def run_crawler():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
"""
        
        for step in crawler.steps:
            if step.get("action") == "navigate":
                code += f'        await page.goto("{step.get("url")}")\n'
            elif step.get("action") == "click":
                code += f'        await page.click("{step.get("selector")}")\n'
        
        code += """
        await browser.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_crawler())
"""
        return code
    
    def to_playwright_script(self, crawler: CrawlerDefinition) -> str:
        """Convert crawler to Playwright script."""
        # Similar to Python code but in Playwright test format
        return self.to_python_code(crawler)


