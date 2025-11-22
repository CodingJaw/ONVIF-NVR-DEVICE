"""Device service endpoints."""

from fastapi import APIRouter, Depends

from src.config import NetworkSettings, NTPSettings, get_config_manager
from src.device_management import (
    get_network_settings,
    get_ntp_settings,
    set_hostname,
    set_network_settings,
    set_ntp_settings,
)
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


@router.get("/network")
def get_network_configuration() -> dict:
    settings = get_network_settings()
    return settings.model_dump()


@router.put(
    "/network",
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
def set_network_configuration(payload: NetworkSettings) -> dict:
    updated = set_network_settings(payload)
    return {"status": "updated", "network": updated.model_dump()}


@router.get("/ntp")
def get_ntp_configuration() -> dict:
    settings = get_ntp_settings()
    return settings.model_dump()


@router.put("/ntp", dependencies=[Depends(require_roles(["operator", "admin"]))])
def set_ntp_configuration(payload: NTPSettings) -> dict:
    updated = set_ntp_settings(payload)
    return {"status": "updated", "ntp": updated.model_dump()}


@router.get("/hostname")
def get_hostname() -> dict[str, str]:
    return {"hostname": get_network_settings().hostname}


@router.put(
    "/hostname",
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
def set_hostname_value(hostname: str) -> dict[str, str]:
    updated = set_hostname(hostname)
    return {"status": "updated", "hostname": updated}

