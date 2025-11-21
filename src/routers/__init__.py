"""Router exports for ONVIF service domains."""

from src.routers import device, events, media, ptz, recording

__all__ = [
    "device",
    "events",
    "media",
    "ptz",
    "recording",
]

