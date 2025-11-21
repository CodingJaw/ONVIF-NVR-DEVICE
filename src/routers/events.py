"""Event subscription endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from src.config import ScheduleEntry, get_config_manager
from src.pipeline import EventMode, EventPipeline
from src.security import require_roles

router = APIRouter(
    prefix="/events",
    tags=["events"],
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
config_manager = get_config_manager()
pipeline = EventPipeline(config_manager)


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

    return {"messages": pipeline.build_notifications()}


@router.post("/mode/{mode}")
def set_mode(mode: EventMode) -> dict[str, str]:
    pipeline.set_mode(mode)
    return {"mode": mode.value, "updated": datetime.utcnow().isoformat() + "Z"}


@router.post("/digital/{direction}/{channel_id}")
def set_digital_state(direction: str, channel_id: int, state: bool) -> dict[str, str | int]:
    try:
        channel = pipeline.update_digital_channel(direction, channel_id, state)
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "channel": channel.channel_id,
        "direction": channel.direction,
        "state": channel.state,
        "utc_time": datetime.utcnow().isoformat() + "Z",
    }


@router.post("/schedules")
def replace_schedules(schedules: list[ScheduleEntry]) -> dict[str, list[dict[str, str]]]:
    pipeline.replace_schedules(schedules)
    return {
        "schedules": [
            {
                "name": schedule.name,
                "start": schedule.start.isoformat(),
                "end": schedule.end.isoformat(),
                "days": schedule.days,
            }
            for schedule in pipeline.state.schedules
        ]
    }

