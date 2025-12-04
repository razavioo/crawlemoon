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
    har_data: Optional[Dict] = None  # HAR file data


class SessionRecorder:
    """Records complete browser sessions."""
    
    def __init__(self):
        self._recording: Optional[SessionRecording] = None
        self._page: Optional[Page] = None
        self._enabled = False
        self._cdp_session = None
    
    async def start_recording(self, page: Page, recording_id: Optional[str] = None, enable_har: bool = True) -> SessionRecording:
        """Start recording a session.
        
        Args:
            page: Playwright page to record
            recording_id: Optional recording ID
            enable_har: Enable HAR recording (default: True)
        """
        import uuid
        
        if self._enabled:
            logger.warning("Recording already in progress")
            return self._recording
        
        self._page = page
        recording_id = recording_id or str(uuid.uuid4())
        
        self._recording = SessionRecording(id=recording_id)
        
        # Start HAR recording if enabled
        if enable_har:
            try:
                context = page.context
                await context.tracing.start(screenshots=True, snapshots=True)
                # Also enable HAR via CDP
                cdp_session = await context.new_cdp_session(page)
                await cdp_session.send('Network.enable')
                await cdp_session.send('Page.enable')
                self._cdp_session = cdp_session
            except Exception as e:
                logger.warning(f"Could not enable HAR recording: {e}")
                self._cdp_session = None
        else:
            self._cdp_session = None
        
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
        
        # Stop HAR recording and get HAR data
        if self._page and self._cdp_session:
            try:
                context = self._page.context
                # Get HAR from CDP
                har_data = await self._cdp_session.send('Network.getResponseBody', {'requestId': 'dummy'})
                # Actually, we need to collect HAR entries during recording
                # For now, generate HAR from network events
                self._recording.har_data = self._generate_har_from_network()
            except Exception as e:
                logger.warning(f"Error getting HAR data: {e}")
                self._recording.har_data = self._generate_har_from_network()
        else:
            # Generate HAR from network events
            self._recording.har_data = self._generate_har_from_network()
        
        logger.info(f"Stopped recording session: {self._recording.id} (duration: {self._recording.duration}s)")
        
        recording = self._recording
        self._recording = None
        self._page = None
        self._cdp_session = None
        
        return recording
    
    def _generate_har_from_network(self) -> Dict:
        """Generate HAR format from network events."""
        har = {
            "log": {
                "version": "1.2",
                "creator": {
                    "name": "Crawilfy",
                    "version": "1.0"
                },
                "pages": [],
                "entries": []
            }
        }
        
        # Group network events by URL
        requests = {}
        for net_event in self._recording.network:
            if net_event.type == "request":
                requests[net_event.url] = {
                    "request": net_event,
                    "response": None
                }
            elif net_event.type == "response":
                if net_event.url in requests:
                    requests[net_event.url]["response"] = net_event
        
        # Convert to HAR entries
        for url, req_resp in requests.items():
            req = req_resp["request"]
            resp = req_resp["response"]
            
            entry = {
                "startedDateTime": req.timestamp.isoformat(),
                "time": 0,
                "request": {
                    "method": req.method,
                    "url": req.url,
                    "httpVersion": "HTTP/1.1",
                    "headers": [],
                    "cookies": [],
                    "queryString": [],
                    "postData": None,
                    "headersSize": -1,
                    "bodySize": -1
                },
                "response": {
                    "status": resp.status if resp else 0,
                    "statusText": "",
                    "httpVersion": "HTTP/1.1",
                    "headers": [],
                    "cookies": [],
                    "content": {
                        "size": 0,
                        "mimeType": "text/html"
                    },
                    "redirectURL": "",
                    "headersSize": -1,
                    "bodySize": -1
                },
                "cache": {},
                "timings": {
                    "blocked": -1,
                    "dns": -1,
                    "connect": -1,
                    "send": 0,
                    "wait": 0,
                    "receive": 0
                }
            }
            
            # Add request headers
            if req.data and "headers" in req.data:
                entry["request"]["headers"] = [
                    {"name": k, "value": v} for k, v in req.data["headers"].items()
                ]
            
            # Add response headers
            if resp and resp.data and "headers" in resp.data:
                entry["response"]["headers"] = [
                    {"name": k, "value": v} for k, v in resp.data["headers"].items()
                ]
                entry["response"]["status"] = resp.data.get("status", 200)
            
            har["log"]["entries"].append(entry)
        
        return har



