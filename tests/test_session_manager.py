"""Tests for session manager."""

import pytest
from datetime import datetime, timedelta

from src.core.session.manager import SessionManager, Session, Credential, AuthType


@pytest.mark.asyncio
async def test_session_manager_initialization(session_manager):
    """Test session manager initialization."""
    from pathlib import Path
    assert session_manager.storage_path == Path(".test_sessions")
    assert len(session_manager._credentials) == 0
    assert len(session_manager._sessions) == 0


@pytest.mark.asyncio
async def test_add_credential(session_manager):
    """Test adding credentials."""
    credential = Credential(
        id="cred_1",
        auth_type=AuthType.COOKIE,
        cookies={"session": "abc123"},
    )
    
    await session_manager.add_credential(credential)
    
    assert len(session_manager._credentials) == 1
    assert session_manager._credentials["cred_1"] == credential


@pytest.mark.asyncio
async def test_get_best_credential(session_manager):
    """Test getting best credential by health score."""
    cred1 = Credential(
        id="cred_1",
        auth_type=AuthType.COOKIE,
        health_score=50.0,
    )
    cred2 = Credential(
        id="cred_2",
        auth_type=AuthType.BEARER,
        health_score=90.0,
    )
    
    await session_manager.add_credential(cred1)
    await session_manager.add_credential(cred2)
    
    best = await session_manager.get_best_credential()
    
    assert best is not None
    assert best.id == "cred_2"  # Higher health score


@pytest.mark.asyncio
async def test_get_best_credential_none_available(session_manager):
    """Test getting credential when none are available."""
    cred = Credential(
        id="cred_1",
        auth_type=AuthType.COOKIE,
        health_score=10.0,  # Too low
    )
    
    await session_manager.add_credential(cred)
    
    best = await session_manager.get_best_credential()
    
    assert best is None


@pytest.mark.asyncio
async def test_create_session(session_manager):
    """Test creating a session."""
    session = await session_manager.create_session()
    
    assert session is not None
    assert session.id is not None
    assert len(session_manager._sessions) == 1


@pytest.mark.asyncio
async def test_create_session_with_id(session_manager):
    """Test creating session with specific ID."""
    session_id = "test_session_123"
    session = await session_manager.create_session(session_id=session_id)
    
    assert session.id == session_id


@pytest.mark.asyncio
async def test_get_session(session_manager):
    """Test getting a session."""
    session = await session_manager.create_session()
    session_id = session.id
    
    retrieved = await session_manager.get_session(session_id)
    
    assert retrieved is not None
    assert retrieved.id == session_id


@pytest.mark.asyncio
async def test_update_session(session_manager):
    """Test updating a session."""
    session = await session_manager.create_session()
    session.cookies["test"] = "value"
    
    await session_manager.update_session(session)
    
    retrieved = await session_manager.get_session(session.id)
    assert retrieved.cookies["test"] == "value"


@pytest.mark.asyncio
async def test_save_session_state(session_manager):
    """Test saving session state."""
    session = await session_manager.create_session()
    
    cookies = {"session": "abc123"}
    local_storage = {"key": "value"}
    
    await session_manager.save_session_state(
        session.id,
        cookies,
        local_storage=local_storage,
    )
    
    retrieved = await session_manager.get_session(session.id)
    assert retrieved.cookies == cookies
    assert retrieved.local_storage == local_storage


@pytest.mark.asyncio
async def test_load_session_state(session_manager):
    """Test loading session state."""
    session = await session_manager.create_session()
    session.cookies = {"session": "abc123"}
    
    await session_manager.update_session(session)
    
    loaded = await session_manager.load_session_state(session.id)
    
    assert loaded is not None
    assert loaded.cookies == {"session": "abc123"}


@pytest.mark.asyncio
async def test_credential_health_update():
    """Test credential health score update."""
    cred = Credential(
        id="cred_1",
        auth_type=AuthType.COOKIE,
        health_score=50.0,
    )
    
    initial_score = cred.health_score
    cred.update_health(success=True)
    
    assert cred.health_score > initial_score
    assert cred.success_count == 1
    assert cred.last_success is not None


@pytest.mark.asyncio
async def test_credential_health_update_failure():
    """Test credential health score update on failure."""
    cred = Credential(
        id="cred_1",
        auth_type=AuthType.COOKIE,
        health_score=50.0,
    )
    
    initial_score = cred.health_score
    cred.update_health(success=False)
    
    assert cred.health_score < initial_score
    assert cred.failure_count == 1
    assert cred.last_failure is not None


def test_credential_can_use():
    """Test credential can_use check."""
    cred = Credential(
        id="cred_1",
        auth_type=AuthType.COOKIE,
        health_score=50.0,
    )
    
    assert cred.can_use() is True
    
    cred.health_score = 10.0
    assert cred.can_use() is False


def test_credential_rate_limiting():
    """Test credential rate limiting."""
    cred = Credential(
        id="cred_1",
        auth_type=AuthType.COOKIE,
    )
    
    # Record multiple requests
    for _ in range(70):
        cred.record_request()
    
    # Should be rate limited
    assert cred.can_use(max_requests_per_minute=60) is False


def test_session_to_dict():
    """Test session serialization."""
    session = Session(
        id="test_123",
        credential_id="cred_1",
        cookies={"session": "abc"},
    )
    
    data = session.to_dict()
    
    assert data["id"] == "test_123"
    assert data["credential_id"] == "cred_1"
    assert data["cookies"] == {"session": "abc"}


def test_session_from_dict():
    """Test session deserialization."""
    data = {
        "id": "test_123",
        "credential_id": "cred_1",
        "cookies": {"session": "abc"},
        "created_at": datetime.now().isoformat(),
        "last_used": datetime.now().isoformat(),
    }
    
    session = Session.from_dict(data)
    
    assert session.id == "test_123"
    assert session.credential_id == "cred_1"
    assert session.cookies == {"session": "abc"}


@pytest.mark.asyncio
async def test_rotate_credential(session_manager):
    """Test credential rotation."""
    cred1 = Credential(
        id="cred_1",
        auth_type=AuthType.COOKIE,
        health_score=30.0,
    )
    cred2 = Credential(
        id="cred_2",
        auth_type=AuthType.BEARER,
        health_score=80.0,
    )
    
    await session_manager.add_credential(cred1)
    await session_manager.add_credential(cred2)
    
    rotated = await session_manager.rotate_credential()
    
    assert rotated is not None
    assert rotated.id == "cred_2"  # Best health score


@pytest.mark.asyncio
async def test_list_sessions(session_manager):
    """Test listing all sessions."""
    await session_manager.create_session(session_id="session1")
    await session_manager.create_session(session_id="session2")
    
    sessions = await session_manager.list_sessions()
    
    assert len(sessions) == 2


@pytest.mark.asyncio
async def test_delete_session(session_manager):
    """Test session deletion with cleanup."""
    session = await session_manager.create_session(session_id="to_delete")
    
    result = await session_manager.delete_session("to_delete")
    
    assert result["status"] == "deleted"
    assert await session_manager.get_session("to_delete") is None


@pytest.mark.asyncio
async def test_delete_session_not_found(session_manager):
    """Test deleting non-existent session."""
    result = await session_manager.delete_session("nonexistent")
    
    assert "error" in result


def test_get_user_data_dir():
    """Test browser profile paths."""
    from pathlib import Path
    
    manager = SessionManager(
        storage_path=".test_sessions",
        user_data_dir="/tmp/user_data"
    )
    
    path = manager.get_user_data_dir("session1")
    
    assert path == Path("/tmp/user_data/session1")


def test_get_user_data_dir_none():
    """Test user data dir when not configured."""
    manager = SessionManager(storage_path=".test_sessions")
    
    path = manager.get_user_data_dir("session1")
    
    assert path is None


@pytest.mark.asyncio
async def test_persist_and_load(session_manager):
    """Test disk persistence."""
    # Create session with data
    session = await session_manager.create_session(session_id="persist_test")
    session.cookies["test_cookie"] = "test_value"
    await session_manager.update_session(session)
    
    # Persist to disk
    await session_manager.persist_to_disk()
    
    # Verify file exists
    import os
    sessions_file = session_manager.storage_path / "sessions.json"
    assert os.path.exists(sessions_file)


