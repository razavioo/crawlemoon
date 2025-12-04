"""Full session recorder."""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Event type."""
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    WAIT = "wait"
    HOVER = "hover"


@dataclass
class Event:
    """Recorded event."""
    
    type: EventType
    timestamp: datetime
    data: Dict[str, Any]
    selector: Optional[str] = None


@dataclass
class NetworkEvent:
    """Network event."""
    
    type: str  # "request", "response"
    url: str
    method: str
    timestamp: datetime
    data: Dict[str, Any]


@dataclass
class DOMChange:
    """DOM change event."""
    
    type: str  # "added", "removed", "modified"
    selector: str
    timestamp: datetime
    snapshot: Optional[str] = None


@dataclass
class StateSnapshot:
    """State snapshot."""
    
    url: str
    html: str
    timestamp: datetime
    cookies: Dict[str, str] = field(default_factory=dict)
    local_storage: Dict[str, str] = field(default_factory=dict)


@dataclass
class SessionRecording:
    """Complete session recording."""
    
    id: str
    events: List[Event] = field(default_factory=list)
    network: List[NetworkEvent] = field(default_factory=list)
    dom_changes: List[DOMChange] = field(default_factory=list)
    state_snapshots: List[StateSnapshot] = field(default_factory=list)
    duration: float = 0.0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None


class SessionRecorder:
    """Records complete browser sessions."""
    
    def __init__(self):
        self._recording: Optional[SessionRecording] = None
        self._page: Optional[Page] = None
        self._enabled = False
    
    async def start_recording(self, page: Page, recording_id: Optional[str] = None) -> SessionRecording:
        """Start recording a session."""
        import uuid
        
        if self._enabled:
            logger.warning("Recording already in progress")
            return self._recording
        
        self._page = page
        recording_id = recording_id or str(uuid.uuid4())
        
        self._recording = SessionRecording(id=recording_id)
        
        # Set up event listeners
        await self._setup_listeners()
        
        self._enabled = True
        logger.info(f"Started recording session: {recording_id}")
        
        return self._recording
    
    async def _setup_listeners(self) -> None:
        """Set up event listeners on page."""
        if not self._page:
            return
        
        # Click events
        self._page.on("click", self._on_click)
        
        # Navigation
        self._page.on("navigated", self._on_navigate)
        
        # Network events
        self._page.on("request", self._on_request)
        self._page.on("response", self._on_response)
    
    def _on_click(self, event) -> None:
        """Handle click event."""
        if not self._recording or not self._enabled:
            return
        
        # Get selector if possible
        selector = None
        try:
            if hasattr(event, 'target'):
                selector = str(event.target)
        except:
            pass
        
        event_obj = Event(
            type=EventType.CLICK,
            timestamp=datetime.now(),
            data={"x": getattr(event, 'client_x', 0), "y": getattr(event, 'client_y', 0)},
            selector=selector,
        )
        
        self._recording.events.append(event_obj)
    
    def _on_navigate(self, url: str) -> None:
        """Handle navigation event."""
        if not self._recording or not self._enabled:
            return
        
        event_obj = Event(
            type=EventType.NAVIGATE,
            timestamp=datetime.now(),
            data={"url": url},
        )
        
        self._recording.events.append(event_obj)
    
    def _on_request(self, request) -> None:
        """Handle request event."""
        if not self._recording or not self._enabled:
            return
        
        network_event = NetworkEvent(
            type="request",
            url=request.url,
            method=request.method,
            timestamp=datetime.now(),
            data={
                "headers": request.headers,
                "post_data": request.post_data,
            },
        )
        
        self._recording.network.append(network_event)
    
    def _on_response(self, response) -> None:
        """Handle response event."""
        if not self._recording or not self._enabled:
            return
        
        network_event = NetworkEvent(
            type="response",
            url=response.url,
            method=response.request.method if response.request else "GET",
            timestamp=datetime.now(),
            data={
                "status": response.status,
                "headers": response.headers,
            },
        )
        
        self._recording.network.append(network_event)
    
    async def take_snapshot(self) -> None:
        """Take a state snapshot."""
        if not self._recording or not self._page or not self._enabled:
            return
        
        try:
            html = await self._page.content()
            url = self._page.url
            
            cookies = {}
            context = self._page.context
            browser_cookies = await context.cookies()
            for cookie in browser_cookies:
                cookies[cookie["name"]] = cookie["value"]
            
            # Get local storage (requires JavaScript evaluation)
            local_storage = {}
            try:
                storage = await self._page.evaluate("""() => {
                    const storage = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        storage[key] = localStorage.getItem(key);
                    }
                    return storage;
                }""")
                local_storage = storage or {}
            except:
                pass
            
            snapshot = StateSnapshot(
                url=url,
                html=html,
                timestamp=datetime.now(),
                cookies=cookies,
                local_storage=local_storage,
            )
            
            self._recording.state_snapshots.append(snapshot)
            logger.debug("State snapshot taken")
        
        except Exception as e:
            logger.error(f"Error taking snapshot: {e}")
    
    async def stop_recording(self) -> SessionRecording:
        """Stop recording and return session recording."""
        if not self._enabled or not self._recording:
            return None
        
        self._enabled = False
        self._recording.end_time = datetime.now()
        
        if self._recording.start_time:
            duration = (self._recording.end_time - self._recording.start_time).total_seconds()
            self._recording.duration = duration
        
        logger.info(f"Stopped recording session: {self._recording.id} (duration: {self._recording.duration}s)")
        
        recording = self._recording
        self._recording = None
        self._page = None
        
        return recording


