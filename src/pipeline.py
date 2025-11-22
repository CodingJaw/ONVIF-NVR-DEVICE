"""In-memory event pipeline bridging ONVIF recording and event services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, List

from src.config import ConfigManager, EventPipelineMode, ScheduleEntry
from src.notifications import get_notification_manager


class EventMode(str, Enum):
    """Enumerates how the pipeline interprets incoming signals."""

    MOTION = "motion"
    EVENT = "event"
    ALARM = "alarm"


@dataclass
class DigitalChannel:
    """Represents a simple digital input or output line."""

    channel_id: int
    direction: str  # "input" or "output"
    name: str
    state: bool = False

    def toggle(self, value: bool) -> None:
        self.state = value


@dataclass
class EventPipelineState:
    """Aggregated pipeline state shared between ONVIF services."""

    mode: EventMode = EventMode.EVENT
    digital_inputs: List[DigitalChannel] = field(default_factory=list)
    digital_outputs: List[DigitalChannel] = field(default_factory=list)
    recording_triggers: List[str] = field(default_factory=list)
    schedules: List[ScheduleEntry] = field(default_factory=list)


class EventPipeline:
    """Coordinates digital IO, alarms, and schedules for ONVIF services."""

    def __init__(self, config_manager: ConfigManager) -> None:
        self._config_manager = config_manager
        self._state = self._load_from_config()
        self._notifications = get_notification_manager()

    # State helpers -----------------------------------------------------
    def _load_from_config(self) -> EventPipelineState:
        settings = self._config_manager.get_user_settings()
        return EventPipelineState(
            mode=EventMode(settings.event_pipeline_mode.value)
            if isinstance(settings.event_pipeline_mode, EventPipelineMode)
            else EventMode(settings.event_pipeline_mode),
            digital_inputs=[DigitalChannel(**channel) for channel in settings.digital_inputs],
            digital_outputs=[DigitalChannel(**channel) for channel in settings.digital_outputs],
            recording_triggers=list(settings.recording_triggers),
            schedules=list(settings.recording_schedules),
        )

    def _persist_state(self) -> None:
        settings = self._config_manager.get_user_settings()
        settings.event_pipeline_mode = EventPipelineMode(self._state.mode.value)
        settings.digital_inputs = [channel.__dict__ for channel in self._state.digital_inputs]
        settings.digital_outputs = [channel.__dict__ for channel in self._state.digital_outputs]
        settings.recording_triggers = list(self._state.recording_triggers)
        settings.recording_schedules = list(self._state.schedules)
        self._config_manager.save_user_settings(settings)

    def set_mode(self, mode: EventMode) -> EventMode:
        self._state.mode = mode
        self._persist_state()
        return mode

    def update_digital_channel(self, direction: str, channel_id: int, value: bool) -> DigitalChannel:
        channels = self._state.digital_inputs if direction == "input" else self._state.digital_outputs
        for channel in channels:
            if channel.channel_id == channel_id:
                channel.toggle(value)
                self._persist_state()
                topic = f"tns1:Device/IO/{channel.direction.title()}{channel.channel_id}/LogicalState"
                self._notifications.enqueue_notification(
                    topic,
                    {
                        "Source": channel.name,
                        "State": "true" if channel.state else "false",
                    },
                )
                return channel
        raise ValueError(f"Channel {channel_id} not found for {direction}")

    def add_schedule(self, schedule: ScheduleEntry) -> list[ScheduleEntry]:
        self._state.schedules.append(schedule)
        self._persist_state()
        self._notifications.enqueue_notification(
            "tns1:Recording/Configuration/Schedule",
            {
                "Name": schedule.name,
                "StartTime": schedule.start.isoformat(),
                "EndTime": schedule.end.isoformat(),
                "Days": ",".join(schedule.days),
            },
        )
        return self._state.schedules

    def replace_schedules(self, schedules: Iterable[ScheduleEntry]) -> list[ScheduleEntry]:
        self._state.schedules = list(schedules)
        self._persist_state()
        for schedule in self._state.schedules:
            self._notifications.enqueue_notification(
                "tns1:Recording/Configuration/Schedule",
                {
                    "Name": schedule.name,
                    "StartTime": schedule.start.isoformat(),
                    "EndTime": schedule.end.isoformat(),
                    "Days": ",".join(schedule.days),
                },
            )
        return self._state.schedules

    def add_recording_trigger(self, source: str) -> list[str]:
        self._state.recording_triggers.append(source)
        self._persist_state()
        self._notifications.enqueue_notification(
            "tns1:Recording/Control/JobState",
            {"Source": source, "State": "Active"},
        )
        return self._state.recording_triggers

    # Notifications -----------------------------------------------------
    def build_notifications(self) -> list[dict[str, str]]:
        """Return ONVIF-style event messages representing current state."""

        now = datetime.utcnow().isoformat() + "Z"
        notifications: list[dict[str, str]] = [
            {
                "topic": "pipeline/mode",
                "state": self._state.mode.value,
                "utc_time": now,
            }
        ]

        for channel in self._state.digital_inputs + self._state.digital_outputs:
            notifications.append(
                {
                    "topic": f"pipeline/digital/{channel.direction}{channel.channel_id}",
                    "state": "High" if channel.state else "Low",
                    "utc_time": now,
                }
            )

        for schedule in self._state.schedules:
            notifications.append(
                {
                    "topic": "pipeline/schedule",
                    "state": f"{schedule.name}:{schedule.start}-{schedule.end}",
                    "utc_time": now,
                }
            )

        for trigger in self._state.recording_triggers:
            notifications.append(
                {
                    "topic": "pipeline/recording_trigger",
                    "state": trigger,
                    "utc_time": now,
                }
            )

        return notifications

    # Accessors ---------------------------------------------------------
    @property
    def state(self) -> EventPipelineState:
        return self._state


__all__ = ["EventPipeline", "EventMode", "DigitalChannel", "EventPipelineState"]
