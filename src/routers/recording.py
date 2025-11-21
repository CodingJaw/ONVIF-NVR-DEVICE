"""Recording control endpoints."""

from fastapi import APIRouter, Depends

from src.security import require_roles

router = APIRouter(
    prefix="/recording",
    tags=["recording"],
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)


@router.get("/jobs")
def list_recording_jobs() -> list[dict[str, str]]:
    return [{"id": "job1", "status": "Idle", "source": "profile1"}]


@router.post("/jobs")
def create_recording_job(profile_token: str) -> dict[str, str]:
    return {"id": "job2", "status": "Recording", "source": profile_token}

