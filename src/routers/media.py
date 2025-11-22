"""Media service endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.config import MediaSourceType, get_config_manager
from src.media_pipeline import MediaPipelineManager
from src.security import require_roles

router = APIRouter(
    prefix="/media",
    tags=["media"],
    dependencies=[Depends(require_roles(["viewer", "operator", "admin"]))],
)

config_manager = get_config_manager()
pipeline_manager = MediaPipelineManager(config_manager)


class ProfileTuning(BaseModel):
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    bitrate_kbps: int | None = Field(default=None, gt=0)
    framerate: int | None = Field(default=None, gt=0)
    source_type: str | None = Field(default=None)
    source_location: str | None = Field(default=None)


@router.get("/profiles")
def list_profiles() -> list[dict[str, str | int]]:
    """Return configured ONVIF media profiles and their RTSP bindings."""

    return pipeline_manager.list_profiles()


@router.put("/profiles/{profile_token}", dependencies=[Depends(require_roles(["operator", "admin"]))])
def tune_profile(profile_token: str, tuning: ProfileTuning) -> dict[str, str | int]:
    """Adjust encoder parameters for an existing profile."""

    if all(value is None for value in tuning.model_dump().values()):
        raise HTTPException(status_code=400, detail="No parameters provided to update")

    try:
        return pipeline_manager.set_profile_parameters(
            profile_token,
            width=tuning.width,
            height=tuning.height,
            bitrate_kbps=tuning.bitrate_kbps,
            framerate=tuning.framerate,
            source_type=MediaSourceType(tuning.source_type)
            if tuning.source_type is not None
            else None,
            source_location=tuning.source_location,
        )
    except KeyError as exc:  # pragma: no cover - thin API wrapper
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/stream_uri")
def get_stream_uri(profile_token: str = Query("profile1", alias="ProfileToken")) -> dict[str, str]:
    """Return the RTSP URI bound to a media profile token."""

    try:
        uri = pipeline_manager.get_stream_uri(profile_token)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"uri": uri}

