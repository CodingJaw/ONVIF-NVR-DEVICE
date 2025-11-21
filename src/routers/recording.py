"""Recording control endpoints."""

from fastapi import APIRouter, Depends

from src.config import ScheduleEntry, get_config_manager
from src.pipeline import EventPipeline
from src.security import require_roles

router = APIRouter(
    prefix="/recording",
    tags=["recording"],
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
config_manager = get_config_manager()
pipeline = EventPipeline(config_manager)


@router.get("/jobs")
def list_recording_jobs() -> list[dict[str, str]]:
    return [{"id": "job1", "status": "Idle", "source": "profile1"}]


@router.post("/jobs")
def create_recording_job(profile_token: str) -> dict[str, str]:
    pipeline.add_recording_trigger(profile_token)
    return {"id": "job2", "status": "Recording", "source": profile_token}


@router.post("/schedules")
def update_schedules(schedules: list[ScheduleEntry]) -> dict[str, int]:
    pipeline.replace_schedules(schedules)
    return {"count": len(schedules)}

