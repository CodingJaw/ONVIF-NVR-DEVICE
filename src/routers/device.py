"""Device service endpoints."""

from fastapi import APIRouter, Depends

from src.security import verify_wsse

router = APIRouter(prefix="/device", tags=["device"], dependencies=[Depends(verify_wsse)])


@router.get("/information")
def get_device_information() -> dict[str, str]:
    return {
        "manufacturer": "OpenAI Labs",
        "model": "ONVIF Reference NVR",
        "firmware_version": "0.1.0",
        "serial_number": "DEV-0001",
        "hardware_id": "raspberrypi",
    }


@router.get("/capabilities")
def get_capabilities() -> dict[str, dict[str, bool]]:
    return {
        "device": {"system": True, "network": True},
        "events": {"ws_subscription": True},
        "media": {"profiles": True},
        "ptz": {"supported": True},
        "recording": {"search": False},
    }

