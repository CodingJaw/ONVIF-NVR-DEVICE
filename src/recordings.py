"""Recording metadata store and ONVIF-aligned helpers."""

from __future__ import annotations

import os
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


def _parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass
class TrackMetadata:
    track_token: str
    start_time: datetime
    end_time: datetime
    state: str = "Completed"
    file_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "track_token": self.track_token,
            "start_time": self.start_time.replace(tzinfo=timezone.utc).isoformat(),
            "end_time": self.end_time.replace(tzinfo=timezone.utc).isoformat(),
            "state": self.state,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "TrackMetadata":
        return cls(
            track_token=str(payload.get("track_token", "")),
            start_time=_parse_time(payload.get("start_time", datetime.utcnow().isoformat())),
            end_time=_parse_time(payload.get("end_time", datetime.utcnow().isoformat())),
            state=str(payload.get("state", "Completed")),
            file_path=payload.get("file_path"),
        )


@dataclass
class RecordingMetadata:
    recording_token: str
    source_token: str
    start_time: datetime
    end_time: datetime
    tracks: list[TrackMetadata] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "recording_token": self.recording_token,
            "source_token": self.source_token,
            "start_time": self.start_time.replace(tzinfo=timezone.utc).isoformat(),
            "end_time": self.end_time.replace(tzinfo=timezone.utc).isoformat(),
            "tracks": [track.to_dict() for track in self.tracks],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RecordingMetadata":
        return cls(
            recording_token=str(payload.get("recording_token", "")),
            source_token=str(payload.get("source_token", "")),
            start_time=_parse_time(payload.get("start_time", datetime.utcnow().isoformat())),
            end_time=_parse_time(payload.get("end_time", datetime.utcnow().isoformat())),
            tracks=[
                TrackMetadata.from_dict(track)
                for track in payload.get("tracks", [])
                if isinstance(track, dict)
            ],
        )


@dataclass
class RecordingJob:
    job_token: str
    recording_token: str
    source_token: str
    state: str = "Idle"
    track_states: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "job_token": self.job_token,
            "recording_token": self.recording_token,
            "source_token": self.source_token,
            "state": self.state,
            "track_states": self.track_states,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RecordingJob":
        return cls(
            job_token=str(payload.get("job_token", "")),
            recording_token=str(payload.get("recording_token", "")),
            source_token=str(payload.get("source_token", "")),
            state=str(payload.get("state", "Idle")),
            track_states=dict(payload.get("track_states", {}) or {}),
        )


@dataclass
class ExportJob:
    job_token: str
    recording_token: str
    track_token: Optional[str]
    state: str = "Queued"

    def to_dict(self) -> dict[str, object]:
        return {
            "job_token": self.job_token,
            "recording_token": self.recording_token,
            "track_token": self.track_token,
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ExportJob":
        return cls(
            job_token=str(payload.get("job_token", "")),
            recording_token=str(payload.get("recording_token", "")),
            track_token=payload.get("track_token"),
            state=str(payload.get("state", "Queued")),
        )


class RecordingStore:
    """Thread-safe recording metadata registry persisted to disk."""

    def __init__(self, storage_path: Path | str = Path("config/recordings.yaml")) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._recordings: dict[str, RecordingMetadata] = {}
        self._jobs: dict[str, RecordingJob] = {}
        self._exports: dict[str, ExportJob] = {}
        self._load()

    # Persistence helpers -------------------------------------------------
    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        with self.storage_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        self._recordings = {
            token: RecordingMetadata.from_dict(entry)
            for token, entry in (payload.get("recordings", {}) or {}).items()
            if isinstance(entry, dict)
        }
        self._jobs = {
            token: RecordingJob.from_dict(entry)
            for token, entry in (payload.get("jobs", {}) or {}).items()
            if isinstance(entry, dict)
        }
        self._exports = {
            token: ExportJob.from_dict(entry)
            for token, entry in (payload.get("exports", {}) or {}).items()
            if isinstance(entry, dict)
        }

    def _persist(self) -> None:
        payload = {
            "recordings": {k: v.to_dict() for k, v in self._recordings.items()},
            "jobs": {k: v.to_dict() for k, v in self._jobs.items()},
            "exports": {k: v.to_dict() for k, v in self._exports.items()},
        }
        fd, tmp_path = tempfile.mkstemp(
            dir=self.storage_path.parent, prefix=".recordings.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump(payload, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.storage_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # Recording indexing --------------------------------------------------
    def index_recording(
        self,
        source_token: str,
        start_time: datetime,
        end_time: datetime,
        track_token: str = "track1",
        file_path: str | None = None,
        recording_token: Optional[str] = None,
    ) -> RecordingMetadata:
        with self._lock:
            token = recording_token or f"rec-{uuid.uuid4()}"
            track = TrackMetadata(
                track_token=track_token,
                start_time=start_time,
                end_time=end_time,
                state="Completed",
                file_path=file_path,
            )
            recording = RecordingMetadata(
                recording_token=token,
                source_token=source_token,
                start_time=start_time,
                end_time=end_time,
                tracks=[track],
            )
            self._recordings[token] = recording
            self._persist()
            return recording

    def list_recordings(self) -> list[RecordingMetadata]:
        with self._lock:
            return list(self._recordings.values())

    def get_recording(self, recording_token: str) -> RecordingMetadata:
        with self._lock:
            if recording_token not in self._recordings:
                raise ValueError(f"Recording {recording_token} not found")
            return self._recordings[recording_token]

    def search_recordings(
        self, start_time: datetime, end_time: datetime, source_token: Optional[str] = None
    ) -> list[RecordingMetadata]:
        with self._lock:
            results = []
            for recording in self._recordings.values():
                if source_token and recording.source_token != source_token:
                    continue
                overlaps = recording.start_time <= end_time and recording.end_time >= start_time
                if overlaps:
                    results.append(recording)
            return sorted(results, key=lambda rec: rec.start_time)

    # Job and track control ----------------------------------------------
    def create_job(self, source_token: str, recording_token: Optional[str] = None) -> RecordingJob:
        with self._lock:
            recording_id = recording_token or f"rec-{uuid.uuid4()}"
            job = RecordingJob(
                job_token=f"job-{uuid.uuid4()}",
                recording_token=recording_id,
                source_token=source_token,
                state="Recording",
                track_states={"track1": "Recording"},
            )
            self._jobs[job.job_token] = job
            if recording_id not in self._recordings:
                now = datetime.now(timezone.utc)
                self._recordings[recording_id] = RecordingMetadata(
                    recording_token=recording_id,
                    source_token=source_token,
                    start_time=now,
                    end_time=now,
                    tracks=[
                        TrackMetadata(
                            track_token="track1",
                            start_time=now,
                            end_time=now,
                            state="Recording",
                        )
                    ],
                )
            self._persist()
            return job

    def list_jobs(self) -> list[RecordingJob]:
        with self._lock:
            return list(self._jobs.values())

    def get_job(self, job_token: str) -> RecordingJob:
        with self._lock:
            if job_token not in self._jobs:
                raise ValueError(f"Job {job_token} not found")
            return self._jobs[job_token]

    def update_job_state(self, job_token: str, state: str) -> RecordingJob:
        with self._lock:
            if job_token not in self._jobs:
                raise ValueError(f"Job {job_token} not found")
            job = self._jobs[job_token]
            job.state = state
            self._persist()
            return job

    def update_track_state(self, job_token: str, track_token: str, state: str) -> RecordingJob:
        with self._lock:
            if job_token not in self._jobs:
                raise ValueError(f"Job {job_token} not found")
            job = self._jobs[job_token]
            job.track_states[track_token] = state
            self._persist()
            return job

    # Export -------------------------------------------------------------
    def create_export_job(self, recording_token: str, track_token: Optional[str]) -> ExportJob:
        with self._lock:
            if recording_token not in self._recordings:
                raise ValueError(f"Recording {recording_token} not found")
            job = ExportJob(
                job_token=f"export-{uuid.uuid4()}",
                recording_token=recording_token,
                track_token=track_token,
                state="Processing",
            )
            self._exports[job.job_token] = job
            self._persist()
            return job

    def list_exports(self) -> list[ExportJob]:
        with self._lock:
            return list(self._exports.values())

    def update_export_state(self, job_token: str, state: str) -> ExportJob:
        with self._lock:
            if job_token not in self._exports:
                raise ValueError(f"Export job {job_token} not found")
            job = self._exports[job_token]
            job.state = state
            self._persist()
            return job


_recording_store: RecordingStore | None = None


def get_recording_store() -> RecordingStore:
    global _recording_store
    if _recording_store is None:
        _recording_store = RecordingStore()
    return _recording_store


__all__ = [
    "ExportJob",
    "RecordingJob",
    "RecordingMetadata",
    "RecordingStore",
    "TrackMetadata",
    "get_recording_store",
]
