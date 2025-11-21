"""Media service endpoints."""

from fastapi import APIRouter, Depends

from src.security import verify_wsse

router = APIRouter(prefix="/media", tags=["media"], dependencies=[Depends(verify_wsse)])


@router.get("/profiles")
def list_profiles() -> list[dict[str, str]]:
    return [
        {
            "name": "primary",
            "token": "profile1",
            "video_encoder_configuration": "h264_1080p",
            "audio_encoder_configuration": "aac_128k",
        }
    ]


@router.get("/stream_uri")
def get_stream_uri(profile_token: str = "profile1") -> dict[str, str]:
    return {"uri": f"rtsp://0.0.0.0:8554/{profile_token}"}

