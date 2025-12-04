"""WebSocket analysis utilities."""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass

from .interceptor import WebSocketMessage, WebSocketSession

logger = logging.getLogger(__name__)


@dataclass
class DecodedWSMessage:
    """Decoded WebSocket message."""
    
    original: str
    decoded: Any
    format: str  # "json", "protobuf", "text", "binary"


class WebSocketAnalyzer:
    """Analyzer for WebSocket messages."""
    
    def decode_messages(self, messages: List[WebSocketMessage]) -> List[DecodedWSMessage]:
        """Decode WebSocket messages."""
        decoded = []
        
        for msg in messages:
            try:
                # Try JSON decode
                import json
                data = json.loads(msg.message)
                decoded.append(DecodedWSMessage(
                    original=msg.message,
                    decoded=data,
                    format="json",
                ))
            except:
                # Keep as text
                decoded.append(DecodedWSMessage(
                    original=msg.message,
                    decoded=msg.message,
                    format="text",
                ))
        
        return decoded
    
    def analyze_session(self, session: WebSocketSession) -> Dict[str, Any]:
        """Analyze WebSocket session."""
        decoded = self.decode_messages(session.messages)
        
        return {
            "url": session.url,
            "total_messages": len(session.messages),
            "sent_count": sum(1 for m in session.messages if m.direction == "sent"),
            "received_count": sum(1 for m in session.messages if m.direction == "received"),
            "decoded_messages": [
                {
                    "format": d.format,
                    "decoded": d.decoded,
                }
                for d in decoded[:10]  # First 10
            ],
        }



