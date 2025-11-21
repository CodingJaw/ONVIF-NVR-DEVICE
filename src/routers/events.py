"""Event subscription endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends

from src.config import get_config_manager
from src.security import verify_wsse

router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(verify_wsse)])
config_manager = get_config_manager()


@router.get("/subscription")
def create_subscription() -> dict[str, str]:
    user_settings = config_manager.get_user_settings()
    status = "Enabled" if user_settings.events_enabled else "Disabled"
    return {
        "subscription_id": "sub-001",
        "expires": datetime.utcnow().isoformat() + "Z",
        "delivery_mode": "Push",
        "status": status,
    }


@router.get("/pull")
def pull_messages() -> dict[str, list[dict[str, str]]]:
    user_settings = config_manager.get_user_settings()
    if not user_settings.events_enabled:
        return {"messages": []}

    return {
        "messages": [
            {
                "topic": "motion",
                "state": "Inactive" if user_settings.alarms_enabled else "Suppressed",
                "utc_time": datetime.utcnow().isoformat() + "Z",
            }
        ]
    }

