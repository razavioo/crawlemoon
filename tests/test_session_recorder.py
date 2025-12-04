"""Tests for session recorder."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from src.intelligence.recorder.session import (
    SessionRecorder,
    SessionRecording,
    Event,
    EventType,
    StateSnapshot,
    NetworkEvent,
    DOMChange,
)


def test_session_recorder_initialization():
    """Test session recorder initialization."""
    recorder = SessionRecorder()
    
    assert recorder._recording is None
    assert recorder._page is None
    assert recorder._enabled is False


@pytest.mark.asyncio
async def test_start_recording():
    """Test starting a recording."""
    recorder = SessionRecorder()
    page = AsyncMock()
    
    recording = await recorder.start_recording(page)
    
    assert recording is not None
    assert recording.id is not None
    assert recorder._enabled is True
    assert recorder._recording == recording


@pytest.mark.asyncio
async def test_start_recording_with_id():
    """Test starting recording with specific ID."""
    recorder = SessionRecorder()
    page = AsyncMock()
    recording_id = "test_recording_123"
    
    recording = await recorder.start_recording(page, recording_id=recording_id)
    
    assert recording.id == recording_id


@pytest.mark.asyncio
async def test_start_recording_already_recording():
    """Test starting recording when already recording."""
    recorder = SessionRecorder()
    page = AsyncMock()
    
    recording1 = await recorder.start_recording(page)
    recording2 = await recorder.start_recording(page)
    
    # Should return existing recording
    assert recording1 == recording2


@pytest.mark.asyncio
async def test_stop_recording():
    """Test stopping a recording."""
    recorder = SessionRecorder()
    page = AsyncMock()
    
    recording = await recorder.start_recording(page)
    stopped = await recorder.stop_recording()
    
    assert stopped is not None
    assert stopped.id == recording.id
    assert recorder._enabled is False
    assert stopped.end_time is not None


@pytest.mark.asyncio
async def test_stop_recording_not_started():
    """Test stopping recording when not started."""
    recorder = SessionRecorder()
    
    stopped = await recorder.stop_recording()
    
    assert stopped is None


def test_event_creation():
    """Test event creation."""
    event = Event(
        type=EventType.CLICK,
        timestamp=datetime.now(),
        data={"x": 100, "y": 200},
        selector="button#submit",
    )
    
    assert event.type == EventType.CLICK
    assert event.selector == "button#submit"
    assert event.data["x"] == 100


def test_state_snapshot_creation():
    """Test state snapshot creation."""
    snapshot = StateSnapshot(
        url="https://example.com",
        html="<html>Test</html>",
        timestamp=datetime.now(),
        cookies={"session": "abc123"},
        local_storage={"key": "value"},
    )
    
    assert snapshot.url == "https://example.com"
    assert snapshot.html == "<html>Test</html>"
    assert snapshot.cookies == {"session": "abc123"}
    assert snapshot.local_storage == {"key": "value"}


def test_session_recording_creation():
    """Test session recording creation."""
    recording = SessionRecording(
        id="test_123",
        events=[Event(type=EventType.CLICK, timestamp=datetime.now(), data={})],
        duration=10.5,
    )
    
    assert recording.id == "test_123"
    assert len(recording.events) == 1
    assert recording.duration == 10.5
    assert recording.end_time is None


def test_network_event_creation():
    """Test network event creation."""
    event = NetworkEvent(
        type="request",
        url="https://api.example.com",
        method="GET",
        timestamp=datetime.now(),
        data={},
    )
    
    assert event.type == "request"
    assert event.url == "https://api.example.com"
    assert event.method == "GET"


def test_dom_change_creation():
    """Test DOM change creation."""
    change = DOMChange(
        type="added",
        selector="div#new-element",
        timestamp=datetime.now(),
        snapshot="<div id='new-element'>New</div>",
    )
    
    assert change.type == "added"
    assert change.selector == "div#new-element"
    assert change.snapshot is not None


def test_event_type_enum():
    """Test event type enum values."""
    assert EventType.CLICK.value == "click"
    assert EventType.TYPE.value == "type"
    assert EventType.SCROLL.value == "scroll"
    assert EventType.NAVIGATE.value == "navigate"


