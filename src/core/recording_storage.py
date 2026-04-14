"""Recording storage manager for persistent recording storage.

Adds data-retention support: recordings older than ``max_age_days`` are
automatically pruned on ``list_recordings()`` and ``purge_expired()``.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..intelligence.recorder.session import (
    SessionRecording,
    Event,
    EventType,
    StateSnapshot,
    NetworkEvent,
)
from ..exceptions import RecordingNotFoundError, RecordingSerializationError, RecordingExpiredError

logger = logging.getLogger(__name__)

# Default retention period; can be overridden per-instance or via env-var.
_DEFAULT_MAX_AGE_DAYS: int = 30


class RecordingStorage:
    """Manages persistent storage of session recordings.

    Args:
        storage_dir: Directory to store recordings.  Defaults to
            ``~/.crawilfy/recordings``.
        max_age_days: Recordings older than this many days are considered
            expired and eligible for purging.  Set to ``None`` to disable
            automatic expiry.  Defaults to ``CRAWILFY_RECORDING_MAX_AGE_DAYS``
            env-var or :data:`_DEFAULT_MAX_AGE_DAYS`.
    """

    #: Sentinel meaning "use environment variable or built-in default".
    _UNSET = object()

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        max_age_days=_UNSET,  # type: ignore[assignment]
    ):
        if storage_dir is None:
            home = Path.home()
            storage_dir = str(home / ".crawilfy" / "recordings")

        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        if max_age_days is RecordingStorage._UNSET:
            env_val = os.getenv("CRAWILFY_RECORDING_MAX_AGE_DAYS")
            max_age_days = int(env_val) if env_val and env_val.isdigit() else _DEFAULT_MAX_AGE_DAYS
        # Callers may pass None to explicitly disable retention
        self.max_age_days: Optional[int] = max_age_days

        # In-memory cache of active recordings
        self._active_recordings: Dict[str, SessionRecording] = {}

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _recording_path(self, recording_id: str) -> Path:
        return self.storage_dir / f"{recording_id}.json"

    def _har_path(self, recording_id: str) -> Path:
        return self.storage_dir / f"{recording_id}.har"

    def _is_expired(self, start_time: Optional[datetime]) -> bool:
        """Return ``True`` if the recording exceeds the retention window."""
        if self.max_age_days is None or start_time is None:
            return False
        age = datetime.now() - start_time
        return age > timedelta(days=self.max_age_days)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_recording(self, recording: SessionRecording, export_har: bool = True) -> str:
        """Save a recording to disk.

        Args:
            recording: The recording to save.
            export_har: Also export a ``.har`` file when HAR data is present.

        Returns:
            Absolute path of the saved ``.json`` file.
        """
        file_path = self._recording_path(recording.id)

        try:
            data = self._serialize_recording(recording)
            if recording.har_data:
                data["har"] = recording.har_data

            with open(file_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
        except (OSError, TypeError, ValueError) as exc:
            raise RecordingSerializationError(
                f"Failed to save recording {recording.id}: {exc}"
            ) from exc

        if export_har and recording.har_data:
            har_path = self._har_path(recording.id)
            try:
                with open(har_path, "w", encoding="utf-8") as fh:
                    json.dump(recording.har_data, fh, indent=2)
                logger.info("Exported HAR file: %s", har_path)
            except OSError as exc:
                logger.warning("Failed to export HAR file: %s", exc)

        logger.info("Saved recording %s to %s", recording.id, file_path)
        return str(file_path)

    def load_recording(self, recording_id: str) -> SessionRecording:
        """Load a recording from disk or in-memory cache.

        Args:
            recording_id: ID of the recording to load.

        Returns:
            The loaded :class:`~intelligence.recorder.session.SessionRecording`.

        Raises:
            RecordingNotFoundError: When the recording cannot be found.
            RecordingExpiredError: When the recording exists but is past retention.
            RecordingSerializationError: When the file cannot be parsed.
        """
        if recording_id in self._active_recordings:
            return self._active_recordings[recording_id]

        file_path = self._recording_path(recording_id)
        if not file_path.exists() and os.path.exists(recording_id):
            file_path = Path(recording_id)

        if not file_path.exists():
            raise RecordingNotFoundError(f"Recording not found: {recording_id}")

        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise RecordingSerializationError(
                f"Failed to read recording {recording_id}: {exc}"
            ) from exc

        try:
            recording = self._deserialize_recording(data)
        except Exception as exc:
            raise RecordingSerializationError(
                f"Failed to deserialise recording {recording_id}: {exc}"
            ) from exc

        if self._is_expired(recording.start_time):
            raise RecordingExpiredError(
                f"Recording {recording_id} has exceeded the {self.max_age_days}-day "
                "retention window. Delete it or increase max_age_days."
            )

        logger.info("Loaded recording %s from %s", recording_id, file_path)
        return recording

    def list_recordings(self) -> List[Dict[str, Any]]:
        """List all available recordings (active and saved).

        Expired recordings are flagged with ``"expired": true`` but not deleted.
        Call :meth:`purge_expired` to remove them.

        Returns:
            List of recording metadata dictionaries.
        """
        recordings: List[Dict[str, Any]] = []

        for recording_id, recording in self._active_recordings.items():
            recordings.append({
                "id": recording_id,
                "status": "active",
                "start_time": recording.start_time.isoformat() if recording.start_time else None,
                "duration": recording.duration,
                "events_count": len(recording.events),
                "snapshots_count": len(recording.state_snapshots),
                "expired": self._is_expired(recording.start_time),
            })

        for file_path in sorted(self.storage_dir.glob("*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                start_str = data.get("start_time")
                start_dt = datetime.fromisoformat(start_str) if start_str else None
                recordings.append({
                    "id": data.get("id", file_path.stem),
                    "status": "saved",
                    "start_time": start_str,
                    "duration": data.get("duration", 0.0),
                    "events_count": len(data.get("events", [])),
                    "snapshots_count": len(data.get("state_snapshots", [])),
                    "file_path": str(file_path),
                    "expired": self._is_expired(start_dt),
                })
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                logger.warning("Error reading recording file %s: %s", file_path, exc)

        return recordings

    def purge_expired(self) -> int:
        """Delete all on-disk recordings that have exceeded the retention window.

        Returns:
            Number of recordings deleted.
        """
        if self.max_age_days is None:
            logger.debug("Recording retention disabled; nothing to purge.")
            return 0

        deleted = 0
        cutoff = datetime.now() - timedelta(days=self.max_age_days)

        for file_path in list(self.storage_dir.glob("*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                start_str = data.get("start_time")
                if not start_str:
                    continue
                start_dt = datetime.fromisoformat(start_str)
                if start_dt < cutoff:
                    file_path.unlink(missing_ok=True)
                    har = self._har_path(data.get("id", file_path.stem))
                    har.unlink(missing_ok=True)
                    logger.info("Purged expired recording: %s", file_path.stem)
                    deleted += 1
            except Exception as exc:
                logger.warning("Error during purge of %s: %s", file_path, exc)

        logger.info("Purged %d expired recording(s)", deleted)
        return deleted

    def register_active_recording(self, recording: SessionRecording) -> None:
        """Register an in-progress recording in the in-memory cache."""
        self._active_recordings[recording.id] = recording
        logger.debug("Registered active recording: %s", recording.id)

    def unregister_active_recording(self, recording_id: str) -> None:
        """Remove a recording from the in-memory cache."""
        self._active_recordings.pop(recording_id, None)
        logger.debug("Unregistered active recording: %s", recording_id)

    def delete_recording(self, recording_id: str) -> bool:
        """Delete a recording from disk and memory.

        Args:
            recording_id: ID of the recording to delete.

        Returns:
            ``True`` if the file was deleted, ``False`` if it was not found.
        """
        self.unregister_active_recording(recording_id)

        file_path = self._recording_path(recording_id)
        if not file_path.exists():
            return False

        try:
            file_path.unlink()
            self._har_path(recording_id).unlink(missing_ok=True)
            logger.info("Deleted recording %s", recording_id)
            return True
        except OSError as exc:
            logger.error("Error deleting recording %s: %s", recording_id, exc)
            return False

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def _serialize_recording(self, recording: SessionRecording) -> Dict:
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
        events: List[Event] = []
        for event_data in data.get("events", []):
            try:
                event_type = EventType(event_data.get("type", "click"))
                events.append(Event(
                    type=event_type,
                    timestamp=datetime.fromisoformat(
                        event_data.get("timestamp", datetime.now().isoformat())
                    ),
                    data=event_data.get("data", {}),
                    selector=event_data.get("selector"),
                ))
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed event: %s", exc)

        network: List[NetworkEvent] = []
        for net_data in data.get("network", []):
            try:
                network.append(NetworkEvent(
                    type=net_data.get("type", "request"),
                    url=net_data.get("url", ""),
                    method=net_data.get("method", "GET"),
                    timestamp=datetime.fromisoformat(
                        net_data.get("timestamp", datetime.now().isoformat())
                    ),
                    data=net_data.get("data", {}),
                ))
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed network event: %s", exc)

        state_snapshots: List[StateSnapshot] = []
        for snap_data in data.get("state_snapshots", []):
            try:
                state_snapshots.append(StateSnapshot(
                    url=snap_data.get("url", ""),
                    html=snap_data.get("html", ""),
                    timestamp=datetime.fromisoformat(
                        snap_data.get("timestamp", datetime.now().isoformat())
                    ),
                    cookies=snap_data.get("cookies", {}),
                    local_storage=snap_data.get("local_storage", {}),
                ))
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed snapshot: %s", exc)

        return SessionRecording(
            id=data.get("id", "unknown"),
            events=events,
            network=network,
            state_snapshots=state_snapshots,
            duration=data.get("duration", 0.0),
            start_time=datetime.fromisoformat(data["start_time"]) if data.get("start_time") else None,
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
        )
