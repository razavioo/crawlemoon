"""Recording storage manager for persistent recording storage."""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from ..intelligence.recorder.session import SessionRecording, Event, EventType, StateSnapshot, NetworkEvent

logger = logging.getLogger(__name__)


class RecordingStorage:
    """Manages persistent storage of session recordings."""
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize recording storage.
        
        Args:
            storage_dir: Directory to store recordings. Defaults to ~/.crawilfy/recordings
        """
        if storage_dir is None:
            home = Path.home()
            storage_dir = str(home / ".crawilfy" / "recordings")
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache of active recordings
        self._active_recordings: Dict[str, SessionRecording] = {}
    
    def save_recording(self, recording: SessionRecording) -> str:
        """
        Save a recording to disk.
        
        Args:
            recording: The recording to save
            
        Returns:
            Path to saved recording file
        """
        file_path = self.storage_dir / f"{recording.id}.json"
        
        # Serialize recording
        data = self._serialize_recording(recording)
        
        # Write to file
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Saved recording {recording.id} to {file_path}")
        return str(file_path)
    
    def load_recording(self, recording_id: str) -> Optional[SessionRecording]:
        """
        Load a recording from disk or memory.
        
        Args:
            recording_id: ID of the recording to load
            
        Returns:
            SessionRecording if found, None otherwise
        """
        # Check in-memory cache first
        if recording_id in self._active_recordings:
            return self._active_recordings[recording_id]
        
        # Try loading from file
        file_path = self.storage_dir / f"{recording_id}.json"
        
        # Also try if recording_id is a full path
        if not file_path.exists() and os.path.exists(recording_id):
            file_path = Path(recording_id)
        
        if not file_path.exists():
            logger.warning(f"Recording {recording_id} not found")
            return None
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            recording = self._deserialize_recording(data)
            logger.info(f"Loaded recording {recording_id} from {file_path}")
            return recording
        
        except Exception as e:
            logger.error(f"Error loading recording {recording_id}: {e}", exc_info=True)
            return None
    
    def list_recordings(self) -> List[Dict[str, any]]:
        """
        List all available recordings.
        
        Returns:
            List of recording metadata dictionaries
        """
        recordings = []
        
        # Add active recordings
        for recording_id, recording in self._active_recordings.items():
            recordings.append({
                "id": recording_id,
                "status": "active",
                "start_time": recording.start_time.isoformat() if recording.start_time else None,
                "duration": recording.duration,
                "events_count": len(recording.events),
                "snapshots_count": len(recording.state_snapshots),
            })
        
        # Add saved recordings
        for file_path in self.storage_dir.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                recordings.append({
                    "id": data.get("id", file_path.stem),
                    "status": "saved",
                    "start_time": data.get("start_time"),
                    "duration": data.get("duration", 0.0),
                    "events_count": len(data.get("events", [])),
                    "snapshots_count": len(data.get("state_snapshots", [])),
                    "file_path": str(file_path),
                })
            except Exception as e:
                logger.warning(f"Error reading recording file {file_path}: {e}")
        
        return recordings
    
    def register_active_recording(self, recording: SessionRecording) -> None:
        """Register an active recording in memory."""
        self._active_recordings[recording.id] = recording
        logger.debug(f"Registered active recording: {recording.id}")
    
    def unregister_active_recording(self, recording_id: str) -> None:
        """Unregister an active recording."""
        if recording_id in self._active_recordings:
            del self._active_recordings[recording_id]
            logger.debug(f"Unregistered active recording: {recording_id}")
    
    def delete_recording(self, recording_id: str) -> bool:
        """
        Delete a recording from disk.
        
        Args:
            recording_id: ID of recording to delete
            
        Returns:
            True if deleted, False if not found
        """
        # Remove from active recordings
        self.unregister_active_recording(recording_id)
        
        # Delete file
        file_path = self.storage_dir / f"{recording_id}.json"
        
        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"Deleted recording {recording_id}")
                return True
            except Exception as e:
                logger.error(f"Error deleting recording {recording_id}: {e}")
                return False
        
        return False
    
    def _serialize_recording(self, recording: SessionRecording) -> Dict:
        """Serialize a recording to a dictionary."""
        return {
            "id": recording.id,
            "duration": recording.duration,
            "start_time": recording.start_time.isoformat() if recording.start_time else None,
            "end_time": recording.end_time.isoformat() if recording.end_time else None,
            "events": [
                {
                    "type": event.type.value,
                    "timestamp": event.timestamp.isoformat(),
                    "data": event.data,
                    "selector": event.selector,
                }
                for event in recording.events
            ],
            "network": [
                {
                    "type": net.type,
                    "url": net.url,
                    "method": net.method,
                    "timestamp": net.timestamp.isoformat(),
                    "data": net.data,
                }
                for net in recording.network
            ],
            "state_snapshots": [
                {
                    "url": snap.url,
                    "html": snap.html,
                    "timestamp": snap.timestamp.isoformat(),
                    "cookies": snap.cookies,
                    "local_storage": snap.local_storage,
                }
                for snap in recording.state_snapshots
            ],
        }
    
    def _deserialize_recording(self, data: Dict) -> SessionRecording:
        """Deserialize a dictionary to a SessionRecording."""
        # Reconstruct events
        events = []
        for event_data in data.get("events", []):
            try:
                event_type = EventType(event_data.get("type", "click"))
                events.append(Event(
                    type=event_type,
                    timestamp=datetime.fromisoformat(event_data.get("timestamp", datetime.now().isoformat())),
                    data=event_data.get("data", {}),
                    selector=event_data.get("selector"),
                ))
            except Exception as e:
                logger.warning(f"Error loading event: {e}")
        
        # Reconstruct network events
        network = []
        for net_data in data.get("network", []):
            try:
                network.append(NetworkEvent(
                    type=net_data.get("type", "request"),
                    url=net_data.get("url", ""),
                    method=net_data.get("method", "GET"),
                    timestamp=datetime.fromisoformat(net_data.get("timestamp", datetime.now().isoformat())),
                    data=net_data.get("data", {}),
                ))
            except Exception as e:
                logger.warning(f"Error loading network event: {e}")
        
        # Reconstruct state snapshots
        state_snapshots = []
        for snap_data in data.get("state_snapshots", []):
            try:
                state_snapshots.append(StateSnapshot(
                    url=snap_data.get("url", ""),
                    html=snap_data.get("html", ""),
                    timestamp=datetime.fromisoformat(snap_data.get("timestamp", datetime.now().isoformat())),
                    cookies=snap_data.get("cookies", {}),
                    local_storage=snap_data.get("local_storage", {}),
                ))
            except Exception as e:
                logger.warning(f"Error loading snapshot: {e}")
        
        recording = SessionRecording(
            id=data.get("id", "unknown"),
            events=events,
            network=network,
            state_snapshots=state_snapshots,
            duration=data.get("duration", 0.0),
            start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None,
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
        )
        
        return recording


