"""Subscription and notification manager for ONVIF pull-point delivery."""
from __future__ import annotations

import os
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

import yaml


@dataclass
class NotificationRecord:
    """A single ONVIF notification instance."""

    topic: str
    message: dict[str, str]
    utc_time: datetime
    sequence: int

    def as_payload(self) -> dict[str, object]:
        return {
            "Topic": self.topic,
            "Message": self.message,
            "UtcTime": self.utc_time.replace(tzinfo=timezone.utc).isoformat(),
            "Sequence": self.sequence,
        }


@dataclass
class SubscriptionState:
    """Persisted subscription configuration and runtime queue."""

    token: str
    termination_time: datetime
    topics: set[str] = field(default_factory=set)
    sequence: int = 0
    queue: list[NotificationRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "token": self.token,
            "termination_time": self.termination_time.replace(tzinfo=timezone.utc).isoformat(),
            "topics": sorted(self.topics),
            "sequence": self.sequence,
            "queue": [
                {
                    "topic": record.topic,
                    "message": record.message,
                    "utc_time": record.utc_time.replace(tzinfo=timezone.utc).isoformat(),
                    "sequence": record.sequence,
                }
                for record in self.queue
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SubscriptionState":
        return cls(
            token=str(payload.get("token", "")),
            termination_time=datetime.fromisoformat(str(payload.get("termination_time"))).replace(
                tzinfo=timezone.utc
            ),
            topics=set(payload.get("topics", []) or []),
            sequence=int(payload.get("sequence", 0)),
            queue=[
                NotificationRecord(
                    topic=entry.get("topic", ""),
                    message=entry.get("message", {}),
                    utc_time=datetime.fromisoformat(entry.get("utc_time", datetime.utcnow().isoformat())),
                    sequence=int(entry.get("sequence", 0)),
                )
                for entry in payload.get("queue", [])
                if isinstance(entry, dict)
            ],
        )


class BaseNotificationManager:
    """Manages subscriptions and notification delivery with persistence."""

    def __init__(self, storage_path: Path | str = Path("config/subscriptions.yaml")) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._subscriptions: dict[str, SubscriptionState] = {}
        self._default_token: str | None = None
        self._load()

    # Persistence -----------------------------------------------------
    def _load(self) -> None:
        if not self.storage_path.exists():
            return
        with self.storage_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        subs = {}
        now = datetime.now(timezone.utc)
        for token, entry in payload.get("subscriptions", {}).items():
            try:
                state = SubscriptionState.from_dict(entry)
            except Exception:
                continue
            if state.termination_time < now:
                continue
            subs[token] = state
        self._subscriptions = subs
        self._default_token = payload.get("default_token") if subs else None

    def _persist(self) -> None:
        payload = {
            "default_token": self._default_token,
            "subscriptions": {token: sub.to_dict() for token, sub in self._subscriptions.items()},
        }
        fd, tmp_path = tempfile.mkstemp(
            dir=self.storage_path.parent, prefix=".subscriptions.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                yaml.safe_dump(payload, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.storage_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # Helpers ---------------------------------------------------------
    def _cleanup_expired(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [token for token, sub in self._subscriptions.items() if sub.termination_time < now]
        for token in expired:
            self._subscriptions.pop(token, None)
        if self._default_token in expired:
            self._default_token = next(iter(self._subscriptions), None)
        if expired:
            self._persist()

    def _ensure_subscription(self, token: Optional[str]) -> SubscriptionState:
        self._cleanup_expired()
        if token:
            if token not in self._subscriptions:
                raise ValueError(f"Subscription {token} not found")
            return self._subscriptions[token]
        if self._default_token and self._default_token in self._subscriptions:
            return self._subscriptions[self._default_token]
        # Auto-create a default subscription if none exist
        return self.create_subscription()

    def _topic_matches(self, topic: str, topics: set[str]) -> bool:
        if not topics:
            return True
        return any(topic.startswith(filter_topic) for filter_topic in topics)

    def _next_sequence(self, subscription: SubscriptionState) -> int:
        subscription.sequence += 1
        return subscription.sequence

    # Public API ------------------------------------------------------
    def create_subscription(
        self, topics: Optional[Iterable[str]] = None, termination: Optional[datetime] = None
    ) -> SubscriptionState:
        with self._lock:
            self._cleanup_expired()
            token = str(uuid.uuid4())
            termination_time = termination or datetime.now(timezone.utc) + timedelta(hours=1)
            state = SubscriptionState(
                token=token,
                termination_time=termination_time,
                topics=set(topics or []),
            )
            self._subscriptions[token] = state
            self._default_token = token
            self._persist()
            return state

    def renew(self, termination: datetime, token: Optional[str] = None) -> SubscriptionState:
        with self._lock:
            subscription = self._ensure_subscription(token)
            subscription.termination_time = termination
            self._persist()
            return subscription

    def unsubscribe(self, token: Optional[str] = None) -> None:
        with self._lock:
            subscription = self._ensure_subscription(token)
            self._subscriptions.pop(subscription.token, None)
            if self._default_token == subscription.token:
                self._default_token = next(iter(self._subscriptions), None)
            self._persist()

    def enqueue_notification(
        self, topic: str, message: dict[str, str], utc_time: Optional[datetime] = None
    ) -> None:
        with self._lock:
            self._cleanup_expired()
            timestamp = utc_time or datetime.now(timezone.utc)
            for subscription in self._subscriptions.values():
                if not self._topic_matches(topic, subscription.topics):
                    continue
                sequence = self._next_sequence(subscription)
                record = NotificationRecord(
                    topic=topic, message=message, utc_time=timestamp, sequence=sequence
                )
                subscription.queue.append(record)
            self._persist()

    def pull_messages(
        self, token: Optional[str] = None, message_limit: int = 10
    ) -> list[dict[str, object]]:
        with self._lock:
            subscription = self._ensure_subscription(token)
            messages: list[dict[str, object]] = []
            while subscription.queue and len(messages) < message_limit:
                record = subscription.queue.pop(0)
                messages.append(record.as_payload())
            self._persist()
            return messages


_notification_manager: BaseNotificationManager | None = None


def get_notification_manager() -> BaseNotificationManager:
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = BaseNotificationManager()
    return _notification_manager


__all__ = [
    "BaseNotificationManager",
    "NotificationRecord",
    "SubscriptionState",
    "get_notification_manager",
]
