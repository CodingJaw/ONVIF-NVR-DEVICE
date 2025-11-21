"""Device service endpoints."""

from fastapi import APIRouter, Depends

from src.config import get_config_manager
from src.security import require_roles

router = APIRouter(
    prefix="/device",
    tags=["device"],
    dependencies=[Depends(require_roles(["viewer", "operator", "admin"]))],
)

config_manager = get_config_manager()


@router.get("/information")
def get_device_information() -> dict[str, str]:
    metadata = config_manager.get_device_metadata()
    response = metadata.model_dump()
    return {key: str(value) for key, value in response.items() if value is not None}


@router.get("/capabilities")
def get_capabilities() -> dict[str, dict[str, bool]]:
    return {
        "device": {"system": True, "network": True},
        "events": {"ws_subscription": True},
        "media": {"profiles": True},
        "ptz": {"supported": True},
        "recording": {"search": False},
    }

