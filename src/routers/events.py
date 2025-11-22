"""Event subscription endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from src.config import ScheduleEntry, get_config_manager
from src.notifications import BaseNotificationManager, get_notification_manager
from src.pipeline import EventMode, EventPipeline
from src.security import require_roles

router = APIRouter(
    prefix="/events",
    tags=["events"],
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
config_manager = get_config_manager()
pipeline = EventPipeline(config_manager)
notifications: BaseNotificationManager = get_notification_manager()


@router.get("/subscription")
def create_subscription(
    topics: list[str] | None = None, termination_seconds: int | None = None
) -> dict[str, str]:
    user_settings = config_manager.get_user_settings()
    status = "Enabled" if user_settings.events_enabled else "Disabled"
    termination = datetime.now(timezone.utc) + (
        timedelta(seconds=termination_seconds) if termination_seconds else timedelta(hours=1)
    )
    subscription = notifications.create_subscription(topics=topics, termination=termination)
    return {
        "subscription_id": subscription.token,
        "expires": subscription.termination_time.isoformat(),
        "delivery_mode": "PullPoint",
        "status": status,
    }


@router.get("/pull")
def pull_messages(
    subscription_id: str | None = None, message_limit: int = 10
) -> dict[str, list[dict[str, str]]]:
    user_settings = config_manager.get_user_settings()
    if not user_settings.events_enabled:
        return {"messages": []}

    messages = notifications.pull_messages(token=subscription_id, message_limit=message_limit)
    return {"messages": messages}


@router.post("/subscription/{subscription_id}/renew")
def renew_subscription(subscription_id: str, termination_seconds: int = 3600) -> dict[str, str]:
    termination = datetime.now(timezone.utc) + timedelta(seconds=termination_seconds)
    subscription = notifications.renew(termination, token=subscription_id)
    return {"subscription_id": subscription.token, "expires": subscription.termination_time.isoformat()}


@router.post("/subscription/{subscription_id}/unsubscribe")
def unsubscribe(subscription_id: str) -> dict[str, str]:
    notifications.unsubscribe(token=subscription_id)
    return {"subscription_id": subscription_id, "unsubscribed": datetime.now(timezone.utc).isoformat()}


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

