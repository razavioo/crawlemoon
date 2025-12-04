"""Tests for crawler generator."""

import pytest
import yaml
from datetime import datetime

from src.intelligence.generator.crawler_gen import CrawlerGenerator, CrawlerDefinition
from src.intelligence.recorder.session import (
    SessionRecording,
    Event,
    EventType,
    StateSnapshot,
)


def test_crawler_generator_initialization():
    """Test crawler generator initialization."""
    generator = CrawlerGenerator()
    
    assert generator is not None


def test_from_recording():
    """Test generating crawler from recording."""
    generator = CrawlerGenerator()
    
    recording = SessionRecording(
        id="test_recording",
        events=[
            Event(
                type=EventType.NAVIGATE,
                timestamp=datetime.now(),
                data={"url": "https://example.com"},
            ),
            Event(
                type=EventType.CLICK,
                timestamp=datetime.now(),
                data={},
                selector="button#submit",
            ),
        ],
        state_snapshots=[
            StateSnapshot(
                url="https://example.com",
                html="<html>Test</html>",
                timestamp=datetime.now(),
            ),
        ],
    )
    
    crawler = generator.from_recording(recording)
    
    assert crawler is not None
    assert isinstance(crawler, CrawlerDefinition)
    assert crawler.name == f"crawler_{recording.id}"
    assert len(crawler.steps) == 2


def test_from_recording_empty():
    """Test generating crawler from empty recording."""
    generator = CrawlerGenerator()
    
    recording = SessionRecording(
        id="empty_recording",
        events=[],
    )
    
    crawler = generator.from_recording(recording)
    
    assert crawler is not None
    assert len(crawler.steps) == 0


def test_optimize_crawler():
    """Test optimizing crawler."""
    generator = CrawlerGenerator()
    
    crawler = CrawlerDefinition(
        name="test_crawler",
        description="Test",
        steps=[
            {"action": "navigate", "url": "https://example.com"},
            {"action": "click", "selector": "button"},
        ],
        config={},
    )
    
    optimized = generator.optimize_crawler(crawler)
    
    assert optimized is not None
    assert isinstance(optimized, CrawlerDefinition)


def test_to_yaml():
    """Test converting crawler to YAML."""
    generator = CrawlerGenerator()
    
    crawler = CrawlerDefinition(
        name="test_crawler",
        description="Test crawler",
        steps=[
            {"action": "navigate", "url": "https://example.com"},
        ],
        config={"timeout": 30},
    )
    
    yaml_output = generator.to_yaml(crawler)
    
    assert yaml_output is not None
    assert "test_crawler" in yaml_output
    assert "navigate" in yaml_output
    
    # Verify it's valid YAML
    parsed = yaml.safe_load(yaml_output)
    assert parsed["name"] == "test_crawler"


def test_to_python_code():
    """Test converting crawler to Python code."""
    generator = CrawlerGenerator()
    
    crawler = CrawlerDefinition(
        name="test_crawler",
        description="Test",
        steps=[
            {"action": "navigate", "url": "https://example.com"},
            {"action": "click", "selector": "button#submit"},
        ],
        config={},
    )
    
    code = generator.to_python_code(crawler)
    
    assert code is not None
    assert "async def run_crawler" in code
    assert "https://example.com" in code
    assert "button#submit" in code


def test_to_playwright_script():
    """Test converting crawler to Playwright script."""
    generator = CrawlerGenerator()
    
    crawler = CrawlerDefinition(
        name="test_crawler",
        description="Test",
        steps=[
            {"action": "navigate", "url": "https://example.com"},
        ],
        config={},
    )
    
    script = generator.to_playwright_script(crawler)
    
    assert script is not None
    assert "playwright" in script.lower() or "page" in script.lower()


def test_crawler_definition():
    """Test crawler definition dataclass."""
    crawler = CrawlerDefinition(
        name="test",
        description="Test description",
        steps=[],
        config={"key": "value"},
    )
    
    assert crawler.name == "test"
    assert crawler.description == "Test description"
    assert crawler.steps == []
    assert crawler.config == {"key": "value"}


def test_from_state_machine():
    """Test generating crawler from state machine."""
    generator = CrawlerGenerator()
    
    # Mock state machine (placeholder)
    sm = None
    
    crawler = generator.from_state_machine(sm)
    
    assert crawler is not None
    assert isinstance(crawler, CrawlerDefinition)


