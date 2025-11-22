"""Media pipeline helpers for RTSP streams and snapshot artifacts."""

from __future__ import annotations

import base64
import logging
import os
import socket
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from src.config import ConfigManager, MediaProfileSettings, MediaSourceType

logger = logging.getLogger(__name__)

_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg=="
)

@dataclass
class LightweightRTSPServer:
    """Represents the minimal RTSP endpoint used by ONVIF clients."""

    host: str = "0.0.0.0"
    port: int = 8554

    def build_stream_uri(self, profile_token: str) -> str:
        return f"rtsp://{self.host}:{self.port}/{profile_token}"


@dataclass
class MediaPipelineInstance:
    """Runtime representation of a media profile and its encoder pipeline."""

    profile: MediaProfileSettings
    rtsp_server: LightweightRTSPServer
    snapshot_dir: Path
    hostname: str
    running: bool = field(default=False, init=False)
    last_pipeline: str = field(default="", init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    @property
    def rtsp_uri(self) -> str:
        return self.rtsp_server.build_stream_uri(self.profile.token)

    @property
    def snapshot_path(self) -> Path:
        path = self.snapshot_dir / f"{self.profile.token}.png"
        if not path.exists():
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(_PLACEHOLDER_PNG)
        return path

    def ensure_running(self) -> None:
        """Start the backing pipeline if it isn't already active."""

        with self._lock:
            if self.running:
                return

            self.last_pipeline = self._build_gstreamer_pipeline()
            self.running = True
            logger.info(
                "Launching media pipeline for %s with RTSP URI %s", self.profile.token, self.rtsp_uri
            )
            logger.debug("Pipeline command: %s", self.last_pipeline)

    def _build_gstreamer_pipeline(self) -> str:
        """Construct a libcamera-friendly H.264 pipeline string."""

        bitrate = self.profile.bitrate_kbps * 1000
        source = self._build_source()
        overlays = self._build_overlays()
        return (
            f"{source} ! videoconvert ! "
            f"video/x-raw,width={self.profile.width},height={self.profile.height},"
            f"framerate={self.profile.framerate}/1 ! "
            f"{overlays} "
            f"v4l2h264enc bitrate={bitrate} ! "
            "video/x-h264,profile=main ! "
            "h264parse config-interval=1 ! "
            "rtph264pay name=pay0 pt=96"
        )

    def _build_source(self) -> str:
        if self.profile.source_type == MediaSourceType.camera:
            return "libcamerasrc"
        if self.profile.source_type == MediaSourceType.testscreen:
            return "videotestsrc is-live=true pattern=smpte"
        if self.profile.source_type == MediaSourceType.bouncing_ball:
            return "videotestsrc is-live=true pattern=ball"
        if self.profile.source_type == MediaSourceType.image:
            location = self.profile.source_location or "image.png"
            return f"filesrc location={location} ! decodebin ! imagefreeze"
        if self.profile.source_type == MediaSourceType.mpeg:
            location = self.profile.source_location or "video.mp4"
            return " ".join(
                [
                    f"filesrc location={location}",
                    "! decodebin",
                    "! videoconvert",
                ]
            )
        return "videotestsrc is-live=true"

    def _build_overlays(self) -> str:
        return " ".join(
            [
                "clockoverlay time-format=%\"%Y-%m-%d %H:%M:%S\"",
                "halign=left valign=top shaded-background=true font-desc=\"Sans 16\"",
                "! textoverlay",
                f"text=\"{self.hostname}\"",
                "halign=right valign=top shaded-background=true font-desc=\"Sans 16\"",
                "!",
            ]
        )


class MediaPipelineManager:
    """Coordinates ONVIF media profiles and their backing RTSP pipelines."""

    def __init__(
        self,
        config_manager: ConfigManager,
        *,
        rtsp_host: str | None = None,
        rtsp_port: int | None = None,
    ) -> None:
        self._config_manager = config_manager
        user_settings = self._config_manager.get_user_settings()
        host = rtsp_host or os.getenv("RTSP_HOST", os.getenv("SERVICE_HOST", "0.0.0.0"))
        port = int(rtsp_port or os.getenv("RTSP_PORT", "8554"))
        snapshot_dir = Path(os.getenv("SNAPSHOT_DIR", self._config_manager.base_dir / "snapshots"))
        self._rtsp_server = LightweightRTSPServer(host=host, port=port)
        self._hostname = os.getenv("DEVICE_HOSTNAME", socket.gethostname())
        self._pipelines: Dict[str, MediaPipelineInstance] = {}
        profiles = list(user_settings.media_profiles or self._default_profiles())
        if not user_settings.media_profiles:
            user_settings.media_profiles = profiles
            self._config_manager.save_user_settings(user_settings)

        for profile in profiles:
            self._pipelines[profile.token] = MediaPipelineInstance(
                profile=profile,
                rtsp_server=self._rtsp_server,
                snapshot_dir=snapshot_dir,
                hostname=self._hostname,
            )

    def list_profiles(self) -> list[dict[str, str | int]]:
        return [self._serialize(pipeline) for pipeline in self._pipelines.values()]

    def get_stream_uri(self, profile_token: str) -> str:
        pipeline = self._pipelines.get(profile_token)
        if pipeline is None:
            raise KeyError(f"Unknown profile token {profile_token}")

        pipeline.ensure_running()
        return pipeline.rtsp_uri

    def set_profile_parameters(
        self,
        profile_token: str,
        *,
        width: int | None = None,
        height: int | None = None,
        bitrate_kbps: int | None = None,
        framerate: int | None = None,
        source_type: MediaSourceType | None = None,
        source_location: str | None = None,
    ) -> dict[str, str | int]:
        """Update runtime encoder parameters and persist them to disk."""

        pipeline = self._pipelines.get(profile_token)
        if pipeline is None:
            raise KeyError(f"Unknown profile token {profile_token}")

        updated_profile = pipeline.profile.model_copy(
            update={
                k: v
                for k, v in {
                    "width": width,
                    "height": height,
                    "bitrate_kbps": bitrate_kbps,
                    "framerate": framerate,
                    "source_type": source_type,
                    "source_location": source_location,
                }.items()
                if v is not None
            }
        )
        pipeline.profile = updated_profile
        self._persist_profiles()
        return self._serialize(pipeline)

    def _persist_profiles(self) -> None:
        settings = self._config_manager.get_user_settings()
        settings.media_profiles = [pipeline.profile for pipeline in self._pipelines.values()]
        self._config_manager.save_user_settings(settings)

    def _serialize(self, pipeline: MediaPipelineInstance) -> dict[str, str | int]:
        return {
            "name": pipeline.profile.name,
            "token": pipeline.profile.token,
            "rtsp_uri": pipeline.rtsp_uri,
            "snapshot_path": str(pipeline.snapshot_path),
            "resolution": f"{pipeline.profile.width}x{pipeline.profile.height}",
            "bitrate_kbps": pipeline.profile.bitrate_kbps,
            "framerate": pipeline.profile.framerate,
            "source_type": pipeline.profile.source_type.value,
            "source_location": pipeline.profile.source_location,
            "pipeline": pipeline.last_pipeline or self._pipeline_preview(pipeline),
        }

    def _pipeline_preview(self, pipeline: MediaPipelineInstance) -> str:
        source_preview = pipeline.profile.source_type.value
        location = (
            f" ({pipeline.profile.source_location})" if pipeline.profile.source_location else ""
        )
        return (
            f"{source_preview}{location} ! video/x-raw,width={pipeline.profile.width},"
            f"height={pipeline.profile.height},framerate={pipeline.profile.framerate}/1 ! overlays ..."
        )

    def _default_profiles(self) -> list[MediaProfileSettings]:
        return [
            MediaProfileSettings(
                name="Primary 1080p",
                token="profile1",
                width=1920,
                height=1080,
                bitrate_kbps=8000,
                framerate=30,
            ),
            MediaProfileSettings(
                name="Secondary 720p",
                token="profile2",
                width=1280,
                height=720,
                bitrate_kbps=4000,
                framerate=15,
            ),
        ]


__all__ = ["MediaPipelineManager", "MediaPipelineInstance", "LightweightRTSPServer"]
