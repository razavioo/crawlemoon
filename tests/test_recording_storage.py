"""Tests for recording storage."""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from src.core.recording_storage import RecordingStorage
from src.intelligence.recorder.session import SessionRecording, Event, EventType, StateSnapshot, NetworkEvent


@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def storage(temp_storage_dir):
    """Create a RecordingStorage instance."""
    return RecordingStorage(storage_dir=temp_storage_dir)


@pytest.fixture
def sample_recording():
    """Create a sample recording."""
    return SessionRecording(
        id="test-recording-123",
        events=[
            Event(
                type=EventType.CLICK,
                timestamp=datetime.now(),
                data={"x": 100, "y": 200},
                selector="button#submit",
            )
        ],
        state_snapshots=[
            StateSnapshot(
                url="https://example.com",
                html="<html><body>Test</body></html>",
                timestamp=datetime.now(),
                cookies={"session": "abc123"},
                local_storage={"key": "value"},
            )
        ],
        duration=10.5,
        start_time=datetime.now(),
    )


def test_save_and_load_recording(storage, sample_recording):
    """Test saving and loading a recording."""
    # Save recording
    file_path = storage.save_recording(sample_recording)
    assert Path(file_path).exists()
    
    # Load recording
    loaded = storage.load_recording(sample_recording.id)
    assert loaded is not None
    assert loaded.id == sample_recording.id
    assert len(loaded.events) == len(sample_recording.events)
    assert len(loaded.state_snapshots) == len(sample_recording.state_snapshots)


def test_list_recordings(storage, sample_recording):
    """Test listing recordings."""
    # Initially empty
    recordings = storage.list_recordings()
    assert len(recordings) == 0
    
    # Save a recording
    storage.save_recording(sample_recording)
    
    # List recordings
    recordings = storage.list_recordings()
    assert len(recordings) == 1
    assert recordings[0]["id"] == sample_recording.id
    assert recordings[0]["status"] == "saved"


def test_register_active_recording(storage, sample_recording):
    """Test registering an active recording."""
    storage.register_active_recording(sample_recording)
    
    # Should be in list
    recordings = storage.list_recordings()
    assert len(recordings) == 1
    assert recordings[0]["status"] == "active"


def test_unregister_active_recording(storage, sample_recording):
    """Test unregistering an active recording."""
    storage.register_active_recording(sample_recording)
    storage.unregister_active_recording(sample_recording.id)
    
    # Should not be in active list
    recordings = storage.list_recordings()
    active = [r for r in recordings if r.get("status") == "active"]
    assert len(active) == 0


def test_delete_recording(storage, sample_recording):
    """Test deleting a recording."""
    # Save recording
    file_path = storage.save_recording(sample_recording)
    assert Path(file_path).exists()
    
    # Delete recording
    deleted = storage.delete_recording(sample_recording.id)
    assert deleted is True
    assert not Path(file_path).exists()
    
    # Should not be loadable
    loaded = storage.load_recording(sample_recording.id)
    assert loaded is None


def test_load_nonexistent_recording(storage):
    """Test loading a non-existent recording."""
    loaded = storage.load_recording("nonexistent-id")
    assert loaded is None


def test_load_recording_by_path(storage, sample_recording, temp_storage_dir):
    """Test loading recording by file path."""
    # Save recording
    file_path = storage.save_recording(sample_recording)
    
    # Load by full path
    loaded = storage.load_recording(file_path)
    assert loaded is not None
    assert loaded.id == sample_recording.id


