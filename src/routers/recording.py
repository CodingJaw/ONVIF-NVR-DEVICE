"""Recording control endpoints."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.config import ScheduleEntry, get_config_manager
from src.pipeline import EventPipeline
from src.recordings import RecordingStore, get_recording_store
from src.security import require_roles

router = APIRouter(
    prefix="/recording",
    tags=["recording"],
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
config_manager = get_config_manager()
pipeline = EventPipeline(config_manager)
recordings: RecordingStore = get_recording_store()


@router.get("/jobs")
def list_recording_jobs() -> list[dict[str, object]]:
    return [
        {
            "id": job.job_token,
            "status": job.state,
            "source": job.source_token,
            "recording_token": job.recording_token,
            "tracks": job.track_states,
        }
        for job in recordings.list_jobs()
    ]


@router.post("/jobs")
def create_recording_job(profile_token: str) -> dict[str, str]:
    pipeline.add_recording_trigger(profile_token)
    job = recordings.create_job(profile_token)
    return {
        "id": job.job_token,
        "status": job.state,
        "source": job.source_token,
        "recording_token": job.recording_token,
    }


@router.put("/jobs/{job_token}/state")
def set_job_state(job_token: str, state: str) -> dict[str, str]:
    try:
        job = recordings.update_job_state(job_token, state)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc))
    return {"id": job.job_token, "status": job.state}


@router.put("/jobs/{job_token}/tracks/{track_token}")
def set_track_state(job_token: str, track_token: str, state: str) -> dict[str, object]:
    try:
        job = recordings.update_track_state(job_token, track_token, state)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc))
    return {"id": job.job_token, "tracks": job.track_states}


@router.post("/schedules")
def update_schedules(schedules: list[ScheduleEntry]) -> dict[str, int]:
    pipeline.replace_schedules(schedules)
    return {"count": len(schedules)}


@router.post("/index")
def index_recording(
    source_token: str,
    start_time: datetime,
    end_time: datetime,
    track_token: str = "track1",
    file_path: Optional[str] = None,
    recording_token: Optional[str] = None,
) -> dict[str, object]:
    recording = recordings.index_recording(
        source_token=source_token,
        start_time=start_time,
        end_time=end_time,
        track_token=track_token,
        file_path=file_path,
        recording_token=recording_token,
    )
    return {
        "recording_token": recording.recording_token,
        "source_token": recording.source_token,
        "start_time": recording.start_time,
        "end_time": recording.end_time,
    }


@router.get("/search")
def search_recordings(
    start_time: datetime = Query(...),
    end_time: datetime = Query(...),
    source_token: Optional[str] = None,
) -> list[dict[str, object]]:
    results = recordings.search_recordings(start_time, end_time, source_token)
    return [
        {
            "recording_token": rec.recording_token,
            "source_token": rec.source_token,
            "start_time": rec.start_time,
            "end_time": rec.end_time,
            "tracks": [track.to_dict() for track in rec.tracks],
        }
        for rec in results
    ]


@router.get("/recordings/{recording_token}")
def get_recording(recording_token: str) -> dict[str, object]:
    try:
        rec = recordings.get_recording(recording_token)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "recording_token": rec.recording_token,
        "source_token": rec.source_token,
        "start_time": rec.start_time,
        "end_time": rec.end_time,
        "tracks": [track.to_dict() for track in rec.tracks],
    }


@router.get("/replay/{recording_token}")
def get_replay_uri(recording_token: str) -> dict[str, str]:
    try:
        recordings.get_recording(recording_token)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc))
    return {"uri": f"rtsp://localhost:8554/{recording_token}"}


@router.post("/export/{recording_token}")
def export_recording(recording_token: str, track_token: Optional[str] = None) -> dict[str, str]:
    try:
        job = recordings.create_export_job(recording_token, track_token)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc))
    return {"job_token": job.job_token, "state": job.state}


@router.get("/exports")
def list_exports() -> list[dict[str, str]]:
    return [
        {
            "job_token": job.job_token,
            "recording_token": job.recording_token,
            "track_token": job.track_token or "",
            "state": job.state,
        }
        for job in recordings.list_exports()
    ]

