"""Event subscription endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends

from src.security import verify_wsse

router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(verify_wsse)])


@router.get("/subscription")
def create_subscription() -> dict[str, str]:
    return {
        "subscription_id": "sub-001",
        "expires": datetime.utcnow().isoformat() + "Z",
        "delivery_mode": "Push",
    }


@router.get("/pull")
def pull_messages() -> dict[str, list[dict[str, str]]]:
    return {
        "messages": [
            {"topic": "motion", "state": "Inactive", "utc_time": datetime.utcnow().isoformat() + "Z"}
        ]
    }

