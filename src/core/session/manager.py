"""Session & Credential Manager with rotation and health scoring."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import json

logger = logging.getLogger(__name__)


class AuthType(Enum):
    """Authentication type."""
    COOKIE = "cookie"
    BEARER = "bearer"
    API_KEY = "api_key"
    OAUTH = "oauth"
    BASIC = "basic"
    NONE = "none"


@dataclass
class Credential:
    """Represents a credential set."""
    
    id: str
    auth_type: AuthType
    cookies: Dict[str, str] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    tokens: Dict[str, str] = field(default_factory=dict)
    
    # Health tracking
    health_score: float = 100.0  # 0-100
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    failure_count: int = 0
    success_count: int = 0
    
    # Rate limiting
    requests_per_minute: int = 0
    last_request_time: Optional[datetime] = None
    rate_limit_window: timedelta = timedelta(minutes=1)
    
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def update_health(self, success: bool) -> None:
        """Update health score based on success/failure."""
        if success:
            self.success_count += 1
            self.last_success = datetime.now()
            # Gradually increase health score
            self.health_score = min(100.0, self.health_score + 1.0)
        else:
            self.failure_count += 1
            self.last_failure = datetime.now()
            # Decrease health score more aggressively
            self.health_score = max(0.0, self.health_score - 10.0)
        
        self.updated_at = datetime.now()
    
    def can_use(self, max_requests_per_minute: int = 60) -> bool:
        """Check if credential can be used (health and rate limits)."""
        if self.health_score < 20.0:
            return False
        
        now = datetime.now()
        if self.last_request_time:
            time_since = now - self.last_request_time
            if time_since < self.rate_limit_window:
                if self.requests_per_minute >= max_requests_per_minute:
                    return False
            else:
                # Reset counter
                self.requests_per_minute = 0
        
        return True
    
    def record_request(self) -> None:
        """Record a request for rate limiting."""
        now = datetime.now()
        if self.last_request_time:
            time_since = now - self.last_request_time
            if time_since < self.rate_limit_window:
                self.requests_per_minute += 1
            else:
                self.requests_per_minute = 1
        else:
            self.requests_per_minute = 1
        
        self.last_request_time = now


@dataclass
class Session:
    """Represents a crawling session."""
    
    id: str
    credential_id: Optional[str] = None
    cookies: Dict[str, str] = field(default_factory=dict)
    local_storage: Dict[str, str] = field(default_factory=dict)
    session_storage: Dict[str, str] = field(default_factory=dict)
    indexed_db: Dict[str, Any] = field(default_factory=dict)
    
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict:
        """Convert session to dictionary for storage."""
        return {
            "id": self.id,
            "credential_id": self.credential_id,
            "cookies": self.cookies,
            "local_storage": self.local_storage,
            "session_storage": self.session_storage,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Session":
        """Create session from dictionary."""
        return cls(
            id=data["id"],
            credential_id=data.get("credential_id"),
            cookies=data.get("cookies", {}),
            local_storage=data.get("local_storage", {}),
            session_storage=data.get("session_storage", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_used=datetime.fromisoformat(data.get("last_used", data["created_at"])),
        )


class SessionManager:
    """Manages sessions and credentials with rotation."""
    
    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or ".sessions"
        self._credentials: Dict[str, Credential] = {}
        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
    
    async def add_credential(self, credential: Credential) -> None:
        """Add a credential to the manager."""
        async with self._lock:
            self._credentials[credential.id] = credential
            logger.info(f"Added credential: {credential.id}")
    
    async def get_best_credential(self) -> Optional[Credential]:
        """Get the best available credential based on health score."""
        async with self._lock:
            available = [
                cred for cred in self._credentials.values()
                if cred.can_use()
            ]
            
            if not available:
                return None
            
            # Sort by health score (descending)
            available.sort(key=lambda x: x.health_score, reverse=True)
            return available[0]
    
    async def rotate_credential(self) -> Optional[Credential]:
        """Rotate to next best credential."""
        return await self.get_best_credential()
    
    async def create_session(
        self,
        credential_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Session:
        """Create a new session."""
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
        
        session = Session(id=session_id, credential_id=credential_id)
        
        async with self._lock:
            self._sessions[session_id] = session
        
        logger.info(f"Created session: {session_id}")
        return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        async with self._lock:
            return self._sessions.get(session_id)
    
    async def update_session(self, session: Session) -> None:
        """Update a session."""
        async with self._lock:
            session.last_used = datetime.now()
            self._sessions[session.id] = session
    
    async def save_session_state(
        self,
        session_id: str,
        cookies: Dict,
        local_storage: Optional[Dict] = None,
        session_storage: Optional[Dict] = None,
    ) -> None:
        """Save session state."""
        session = await self.get_session(session_id)
        if not session:
            session = await self.create_session(session_id=session_id)
        
        session.cookies.update(cookies)
        if local_storage:
            session.local_storage.update(local_storage)
        if session_storage:
            session.session_storage.update(session_storage)
        
        await self.update_session(session)
    
    async def load_session_state(self, session_id: str) -> Optional[Session]:
        """Load session state."""
        return await self.get_session(session_id)
    
    async def persist_to_disk(self) -> None:
        """Persist sessions to disk."""
        import os
        os.makedirs(self.storage_path, exist_ok=True)
        
        # Save credentials
        creds_path = os.path.join(self.storage_path, "credentials.json")
        creds_data = {
            cred_id: {
                "id": cred.id,
                "auth_type": cred.auth_type.value,
                "cookies": cred.cookies,
                "headers": cred.headers,
                "tokens": cred.tokens,
                "health_score": cred.health_score,
                "created_at": cred.created_at.isoformat(),
            }
            for cred_id, cred in self._credentials.items()
        }
        
        with open(creds_path, "w") as f:
            json.dump(creds_data, f, indent=2)
        
        # Save sessions
        sessions_path = os.path.join(self.storage_path, "sessions.json")
        sessions_data = {
            session_id: session.to_dict()
            for session_id, session in self._sessions.items()
        }
        
        with open(sessions_path, "w") as f:
            json.dump(sessions_data, f, indent=2)
        
        logger.info(f"Persisted {len(self._credentials)} credentials and {len(self._sessions)} sessions")



