"""Session & Credential Manager with rotation and health scoring."""

import asyncio
import logging
import os
import json
import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

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
    """Manages sessions and credentials with rotation and encryption."""
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        encryption_key: Optional[str] = None,
        user_data_dir: Optional[str] = None,
    ):
        self.storage_path = Path(storage_path or ".sessions")
        self.user_data_dir = Path(user_data_dir) if user_data_dir else None
        self._credentials: Dict[str, Credential] = {}
        self._sessions: Dict[str, Session] = {}
        self._lock = asyncio.Lock()
        
        # Initialize encryption
        self._cipher = None
        if encryption_key:
            self._init_encryption(encryption_key)
        elif os.getenv("CRAWILFY_ENCRYPTION_KEY"):
            self._init_encryption(os.getenv("CRAWILFY_ENCRYPTION_KEY"))
        
        # Load persisted sessions
        self._load_from_disk()
    
    def _init_encryption(self, key: str) -> None:
        """Initialize encryption with provided key."""
        try:
            # Derive key from password using PBKDF2
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'crawilfy_salt',  # In production, use random salt per session
                iterations=100000,
            )
            key_bytes = kdf.derive(key.encode())
            key_b64 = base64.urlsafe_b64encode(key_bytes)
            self._cipher = Fernet(key_b64)
            logger.info("Encryption initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize encryption: {e}")
            self._cipher = None
    
    def _encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        if not self._cipher:
            return data
        try:
            return self._cipher.encrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return data
    
    def _decrypt(self, data: str) -> str:
        """Decrypt sensitive data."""
        if not self._cipher:
            return data
        try:
            return self._cipher.decrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return data
    
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
        """Persist sessions to disk with encryption."""
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Save credentials (encrypt sensitive fields)
        creds_path = self.storage_path / "credentials.json"
        creds_data = {}
        for cred_id, cred in self._credentials.items():
            # Encrypt sensitive data
            encrypted_cookies = {k: self._encrypt(v) for k, v in cred.cookies.items()}
            encrypted_tokens = {k: self._encrypt(v) for k, v in cred.tokens.items()}
            encrypted_headers = {k: self._encrypt(v) for k, v in cred.headers.items()}
            
            creds_data[cred_id] = {
                "id": cred.id,
                "auth_type": cred.auth_type.value,
                "cookies": encrypted_cookies,
                "headers": encrypted_headers,
                "tokens": encrypted_tokens,
                "health_score": cred.health_score,
                "created_at": cred.created_at.isoformat(),
            }
        
        with open(creds_path, "w") as f:
            json.dump(creds_data, f, indent=2)
        
        # Save sessions (encrypt sensitive fields)
        sessions_path = self.storage_path / "sessions.json"
        sessions_data = {}
        for session_id, session in self._sessions.items():
            session_dict = session.to_dict()
            # Encrypt cookies and storage
            session_dict["cookies"] = {k: self._encrypt(v) for k, v in session.cookies.items()}
            session_dict["local_storage"] = {k: self._encrypt(str(v)) for k, v in session.local_storage.items()}
            session_dict["session_storage"] = {k: self._encrypt(str(v)) for k, v in session.session_storage.items()}
            sessions_data[session_id] = session_dict
        
        with open(sessions_path, "w") as f:
            json.dump(sessions_data, f, indent=2)
        
        logger.info(f"Persisted {len(self._credentials)} credentials and {len(self._sessions)} sessions")
    
    def _load_from_disk(self) -> None:
        """Load sessions from disk."""
        creds_path = self.storage_path / "credentials.json"
        sessions_path = self.storage_path / "sessions.json"
        
        # Load credentials
        if creds_path.exists():
            try:
                with open(creds_path, "r") as f:
                    creds_data = json.load(f)
                
                for cred_id, data in creds_data.items():
                    # Decrypt sensitive data
                    cookies = {k: self._decrypt(v) for k, v in data.get("cookies", {}).items()}
                    tokens = {k: self._decrypt(v) for k, v in data.get("tokens", {}).items()}
                    headers = {k: self._decrypt(v) for k, v in data.get("headers", {}).items()}
                    
                    cred = Credential(
                        id=data["id"],
                        auth_type=AuthType(data["auth_type"]),
                        cookies=cookies,
                        headers=headers,
                        tokens=tokens,
                        health_score=data.get("health_score", 100.0),
                        created_at=datetime.fromisoformat(data["created_at"]),
                    )
                    self._credentials[cred_id] = cred
                
                logger.info(f"Loaded {len(self._credentials)} credentials from disk")
            except Exception as e:
                logger.error(f"Error loading credentials: {e}")
        
        # Load sessions
        if sessions_path.exists():
            try:
                with open(sessions_path, "r") as f:
                    sessions_data = json.load(f)
                
                for session_id, data in sessions_data.items():
                    # Decrypt sensitive data
                    cookies = {k: self._decrypt(v) for k, v in data.get("cookies", {}).items()}
                    local_storage = {k: self._decrypt(v) for k, v in data.get("local_storage", {}).items()}
                    session_storage = {k: self._decrypt(v) for k, v in data.get("session_storage", {}).items()}
                    
                    session = Session(
                        id=data["id"],
                        credential_id=data.get("credential_id"),
                        cookies=cookies,
                        local_storage=local_storage,
                        session_storage=session_storage,
                        created_at=datetime.fromisoformat(data["created_at"]),
                        last_used=datetime.fromisoformat(data.get("last_used", data["created_at"])),
                    )
                    self._sessions[session_id] = session
                
                logger.info(f"Loaded {len(self._sessions)} sessions from disk")
            except Exception as e:
                logger.error(f"Error loading sessions: {e}")
    
    def get_user_data_dir(self, session_id: str) -> Optional[Path]:
        """Get user data directory path for a session (browser profile persistence)."""
        if not self.user_data_dir:
            return None
        return self.user_data_dir / session_id
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions with metadata."""
        async with self._lock:
            return [
                {
                    "id": session.id,
                    "credential_id": session.cookies.get("credential_id"),
                    "cookies_count": len(session.cookies),
                    "local_storage_count": len(session.local_storage),
                    "created_at": session.created_at.isoformat(),
                    "last_used": session.last_used.isoformat(),
                }
                for session in self._sessions.values()
            ]
    
    async def save_session(self, session_id: str) -> Dict[str, Any]:
        """Save a session to disk."""
        session = await self.get_session(session_id)
        if not session:
            return {"error": f"Session {session_id} not found"}
        
        await self.persist_to_disk()
        return {
            "status": "saved",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        }
    
    async def delete_session(self, session_id: str) -> Dict[str, Any]:
        """Delete a session."""
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                # Also delete user data directory if it exists
                user_data_path = self.get_user_data_dir(session_id)
                if user_data_path and user_data_path.exists():
                    import shutil
                    shutil.rmtree(user_data_path)
                await self.persist_to_disk()
                return {"status": "deleted", "session_id": session_id}
            return {"error": f"Session {session_id} not found"}



