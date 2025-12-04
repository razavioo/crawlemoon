"""Deep Network Interceptor for HTTP/HTTPS/WebSocket traffic."""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
from enum import Enum

from playwright.async_api import Page, Request, Response

logger = logging.getLogger(__name__)


@dataclass
class CapturedRequest:
    """Captured HTTP request."""
    
    url: str
    method: str
    headers: Dict[str, str]
    post_data: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    frame_url: Optional[str] = None
    resource_type: Optional[str] = None


@dataclass
class CapturedResponse:
    """Captured HTTP response."""
    
    url: str
    status: int
    headers: Dict[str, str]
    body: Optional[bytes] = None
    timestamp: datetime = field(default_factory=datetime.now)
    request_id: Optional[str] = None


@dataclass
class WebSocketMessage:
    """WebSocket message."""
    
    url: str
    direction: str  # "sent" or "received"
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    message_type: Optional[str] = None  # "text" or "binary"


@dataclass
class WebSocketSession:
    """WebSocket session."""
    
    url: str
    messages: List[WebSocketMessage] = field(default_factory=list)
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None


@dataclass
class ServiceWorkerRequest:
    """Service worker request."""
    
    url: str
    method: str
    headers: Dict[str, str]
    timestamp: datetime = field(default_factory=datetime.now)


class DeepNetworkInterceptor:
    """Intercepts all network traffic including WebSocket and service workers."""
    
    def __init__(self):
        self.requests: List[CapturedRequest] = []
        self.responses: List[CapturedResponse] = []
        self.websockets: Dict[str, WebSocketSession] = {}
        self.service_worker_requests: List[ServiceWorkerRequest] = []
        self.background_fetch_requests: List[CapturedRequest] = []
        
        self._enabled = False
    
    async def start_intercepting(self, page: Page) -> None:
        """Start intercepting network traffic."""
        if self._enabled:
            return
        
        # Intercept all requests
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("websocket", self._on_websocket)
        
        # Service worker support
        page.context.on("serviceworker", self._on_service_worker)
        
        self._enabled = True
        logger.info("Network interception started")
    
    async def _on_request(self, request: Request) -> None:
        """Handle request event."""
        try:
            headers = request.headers
            post_data = None
            
            if request.method in ["POST", "PUT", "PATCH"]:
                post_data = request.post_data
            
            captured = CapturedRequest(
                url=request.url,
                method=request.method,
                headers=headers,
                post_data=post_data,
                frame_url=request.frame.url if request.frame else None,
                resource_type=request.resource_type,
            )
            
            self.requests.append(captured)
            logger.debug(f"Captured request: {request.method} {request.url}")
        
        except Exception as e:
            logger.error(f"Error capturing request: {e}")
    
    async def _on_response(self, response: Response) -> None:
        """Handle response event."""
        try:
            headers = response.headers
            
            # Try to get body (may be None for binary or large responses)
            body = None
            try:
                body = await response.body()
            except Exception:
                pass
            
            captured = CapturedResponse(
                url=response.url,
                status=response.status,
                headers=headers,
                body=body,
                request_id=response.request.url if response.request else None,
            )
            
            self.responses.append(captured)
            logger.debug(f"Captured response: {response.status} {response.url}")
        
        except Exception as e:
            logger.error(f"Error capturing response: {e}")
    
    async def _on_websocket(self, websocket) -> None:
        """Handle WebSocket connection."""
        try:
            url = websocket.url
            session = WebSocketSession(url=url)
            self.websockets[url] = session
            
            # Listen to messages
            websocket.on("framesent", lambda event: self._on_ws_message_sent(url, event))
            websocket.on("framereceived", lambda event: self._on_ws_message_received(url, event))
            
            websocket.on("close", lambda: self._on_ws_close(url))
            
            logger.info(f"WebSocket connected: {url}")
        
        except Exception as e:
            logger.error(f"Error handling WebSocket: {e}")
    
    def _on_ws_message_sent(self, url: str, event) -> None:
        """Handle WebSocket message sent."""
        if url not in self.websockets:
            return
        
        message = WebSocketMessage(
            url=url,
            direction="sent",
            message=str(event.payload),
            message_type="text" if isinstance(event.payload, str) else "binary",
        )
        
        self.websockets[url].messages.append(message)
        logger.debug(f"WebSocket message sent to {url}")
    
    def _on_ws_message_received(self, url: str, event) -> None:
        """Handle WebSocket message received."""
        if url not in self.websockets:
            return
        
        message = WebSocketMessage(
            url=url,
            direction="received",
            message=str(event.payload),
            message_type="text" if isinstance(event.payload, str) else "binary",
        )
        
        self.websockets[url].messages.append(message)
        logger.debug(f"WebSocket message received from {url}")
    
    def _on_ws_close(self, url: str) -> None:
        """Handle WebSocket close."""
        if url in self.websockets:
            self.websockets[url].closed_at = datetime.now()
            logger.info(f"WebSocket closed: {url}")
    
    async def _on_service_worker(self, worker) -> None:
        """Handle service worker registration."""
        try:
            logger.info(f"Service worker registered: {worker.url}")
            # Additional service worker monitoring can be added here
        except Exception as e:
            logger.error(f"Error handling service worker: {e}")
    
    async def capture_all_requests(self) -> List[CapturedRequest]:
        """Get all captured requests."""
        return self.requests.copy()
    
    async def capture_all_responses(self) -> List[CapturedResponse]:
        """Get all captured responses."""
        return self.responses.copy()
    
    async def intercept_websocket(self, url: Optional[str] = None) -> Optional[WebSocketSession]:
        """Get WebSocket session(s)."""
        if url:
            return self.websockets.get(url)
        # Return first WebSocket if multiple exist
        return next(iter(self.websockets.values()), None)
    
    async def decode_ws_messages(self, ws_url: str) -> List[WebSocketMessage]:
        """Decode WebSocket messages for a session."""
        session = self.websockets.get(ws_url)
        if not session:
            return []
        
        return session.messages.copy()
    
    async def capture_service_workers(self) -> List[ServiceWorkerRequest]:
        """Get service worker requests."""
        return self.service_worker_requests.copy()
    
    async def capture_background_fetch(self) -> List[CapturedRequest]:
        """Get background fetch requests."""
        return self.background_fetch_requests.copy()
    
    def reset(self) -> None:
        """Reset all captured data."""
        self.requests.clear()
        self.responses.clear()
        self.websockets.clear()
        self.service_worker_requests.clear()
        self.background_fetch_requests.clear()
        logger.info("Network interceptor reset")



