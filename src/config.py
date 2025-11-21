"""Configuration management for user settings and device metadata."""

from __future__ import annotations

import os
import tempfile
import threading
from datetime import time
from pathlib import Path
from typing import Any, Callable, Optional, Type, TypeVar

import yaml
from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator


_ALLOWED_DAYS = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}


class ScheduleEntry(BaseModel):
    """Represents a recurring recording schedule window."""

    name: str
    start: time
    end: time
    days: list[str] = Field(default_factory=lambda: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])

    @field_validator("days")
    @classmethod
    def validate_days(cls, value: list[str]) -> list[str]:
        invalid = sorted(set(value) - _ALLOWED_DAYS)
        if invalid:
            raise ValueError(f"Invalid days: {', '.join(invalid)}")
        if not value:
            raise ValueError("At least one day must be provided")
        return value

    @field_validator("end")
    @classmethod
    def validate_time_range(cls, end_value: time, info: ValidationInfo) -> time:
        start_value = info.data.get("start")
        if isinstance(start_value, time) and end_value <= start_value:
            raise ValueError("End time must be after start time")
        return end_value


class UserSettings(BaseModel):
    """User-tunable runtime settings."""

    recording_schedules: list[ScheduleEntry] = Field(default_factory=list)
    events_enabled: bool = True
    alarms_enabled: bool = True


class DeviceMetadata(BaseModel):
    """Developer-provided metadata describing the device."""

    manufacturer: str = "OpenAI Labs"
    model: str = "ONVIF Reference NVR"
    firmware_version: str = "0.1.0"
    serial_number: str = "DEV-0001"
    hardware_id: str = "raspberrypi"
    developer_notes: Optional[str] = None


T = TypeVar("T", bound=BaseModel)


class ConfigManager:
    """Loads and persists configuration files with validation and atomic writes."""

    def __init__(self, base_dir: Path | str = Path("config")) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.user_config_path = self.base_dir / "user.yaml"
        self.device_config_path = self.base_dir / "device.yaml"
        self._lock = threading.RLock()
        self._user_settings: Optional[UserSettings] = None
        self._device_metadata: Optional[DeviceMetadata] = None
        self._ensure_defaults()

    # Public API -----------------------------------------------------------
    def get_user_settings(self) -> UserSettings:
        """Return validated user settings, reloading from disk if needed."""

        with self._lock:
            if self._user_settings is None:
                self._user_settings = self._load_model(
                    self.user_config_path, UserSettings, self._default_user_settings
                )
            return self._user_settings

    def save_user_settings(self, settings: UserSettings) -> None:
        """Persist user settings to disk with atomic replace."""

        with self._lock:
            self._write_yaml(self.user_config_path, settings.model_dump())
            self._user_settings = settings

    def get_device_metadata(self) -> DeviceMetadata:
        """Return validated device metadata, reloading from disk if needed."""

        with self._lock:
            if self._device_metadata is None:
                self._device_metadata = self._load_model(
                    self.device_config_path, DeviceMetadata, self._default_device_metadata
                )
            return self._device_metadata

    def save_device_metadata(self, metadata: DeviceMetadata) -> None:
        """Persist device metadata to disk with atomic replace."""

        with self._lock:
            self._write_yaml(self.device_config_path, metadata.model_dump())
            self._device_metadata = metadata

    # Internal helpers ----------------------------------------------------
    def _ensure_defaults(self) -> None:
        """Generate configuration files if they are missing."""

        with self._lock:
            if not self.user_config_path.exists():
                self._user_settings = self._default_user_settings()
                self._write_yaml(self.user_config_path, self._user_settings.model_dump())
            if not self.device_config_path.exists():
                self._device_metadata = self._default_device_metadata()
                self._write_yaml(
                    self.device_config_path, self._device_metadata.model_dump()
                )

    def _default_user_settings(self) -> UserSettings:
        return UserSettings(
            recording_schedules=[
                ScheduleEntry(
                    name="Always",
                    start=time(hour=0, minute=0),
                    end=time(hour=23, minute=59),
                    days=list(_ALLOWED_DAYS),
                )
            ],
            events_enabled=True,
            alarms_enabled=True,
        )

    def _default_device_metadata(self) -> DeviceMetadata:
        return DeviceMetadata()

    def _load_model(
        self,
        path: Path,
        model_cls: Type[T],
        default_factory: Callable[[], T],
    ) -> T:
        if not path.exists():
            model = default_factory()
            self._write_yaml(path, model.model_dump())
            return model

        raw_data = self._read_yaml(path)
        try:
            return model_cls.model_validate(raw_data)
        except ValidationError as exc:  # pragma: no cover - explicit error path
            raise ValueError(f"Invalid data in {path}: {exc}") from exc

    def _read_yaml(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Configuration file {path} must contain a mapping at the top level")
        return data

    def _write_yaml(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                yaml.safe_dump(data, tmp_file, sort_keys=False)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Provide a singleton ConfigManager for application modules."""

    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
