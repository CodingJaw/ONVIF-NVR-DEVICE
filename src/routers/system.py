"""System configuration endpoints and lightweight UI."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, status
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, RedirectResponse

from src.config import (
    DeviceMetadata,
    EventPipelineMode,
    NetworkMode,
    NetworkSettings,
    NTPSettings,
    RecordingMode,
    UserSettings,
    get_config_manager,
)
from src.security import require_roles
from src.system_control import apply_all, apply_hostname, apply_network, apply_ntp


router = APIRouter(
    prefix="/system",
    tags=["system"],
    dependencies=[Depends(require_roles(["viewer", "operator", "admin"]))],
)

config_manager = get_config_manager()


def _html_page(title: str, body: str) -> HTMLResponse:
    template = f"""
    <html>
      <head>
        <title>{title}</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 2rem; }}
          section {{ margin-bottom: 2rem; }}
          form {{ display: grid; grid-template-columns: 200px 1fr; gap: 0.5rem 1rem; max-width: 720px; }}
          h1 {{ margin-bottom: 0.5rem; }}
          input[type=text], select {{ padding: 0.35rem; }}
          .actions {{ grid-column: 1 / -1; margin-top: 0.5rem; }}
          .card {{ border: 1px solid #ddd; padding: 1rem; border-radius: 8px; }}
          .status {{ font-family: monospace; background: #f8f8f8; padding: 0.5rem; }}
          nav a {{ margin-right: 1rem; }}
        </style>
      </head>
      <body>
        <nav>
          <a href="/system/ui">Status</a>
          <a href="/system/ui/network">Network</a>
          <a href="/system/ui/ntp">NTP</a>
          <a href="/system/ui/metadata">Device Metadata</a>
          <a href="/system/ui/events">Events & Recording</a>
        </nav>
        {body}
      </body>
    </html>
    """
    return HTMLResponse(content=template)


def _load_settings() -> UserSettings:
    return config_manager.get_user_settings()


class EventUpdate(BaseModel):
    events_enabled: Optional[bool] = None
    alarms_enabled: Optional[bool] = None
    event_pipeline_mode: Optional[EventPipelineMode] = None


class RecordingUpdate(BaseModel):
    recording_mode: Optional[RecordingMode] = None
    recording_enabled: Optional[bool] = None
    recording_triggers: Optional[list[str]] = None


@router.get("/status")
def get_status() -> dict:
    settings = _load_settings()
    metadata = config_manager.get_device_metadata()
    return {
        "network": settings.network.model_dump(),
        "ntp": settings.ntp.model_dump(),
        "hostname": settings.network.hostname,
        "events": {
            "events_enabled": settings.events_enabled,
            "alarms_enabled": settings.alarms_enabled,
            "pipeline_mode": settings.event_pipeline_mode,
        },
        "recording": {
            "mode": settings.recording_mode,
            "enabled": settings.recording_enabled,
            "triggers": settings.recording_triggers,
        },
        "metadata": metadata.model_dump(),
    }


@router.get("/network")
def get_network() -> NetworkSettings:
    return _load_settings().network


@router.put(
    "/network",
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
def update_network(payload: NetworkSettings) -> dict:
    settings = _load_settings()
    settings.network = payload
    config_manager.save_user_settings(settings)
    apply_network(payload)
    apply_hostname(payload.hostname)
    return {"status": "updated", "network": payload}


@router.get("/ntp")
def get_ntp() -> NTPSettings:
    return _load_settings().ntp


@router.put("/ntp", dependencies=[Depends(require_roles(["operator", "admin"]))])
def update_ntp(payload: NTPSettings) -> dict:
    settings = _load_settings()
    settings.ntp = payload
    config_manager.save_user_settings(settings)
    apply_ntp(payload)
    return {"status": "updated", "ntp": payload}


@router.put(
    "/hostname",
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
def update_hostname(hostname: str) -> dict:
    settings = _load_settings()
    settings.network.hostname = hostname
    config_manager.save_user_settings(settings)
    apply_hostname(hostname)
    return {"status": "updated", "hostname": hostname}


@router.get("/metadata")
def get_metadata() -> DeviceMetadata:
    return config_manager.get_device_metadata()


@router.put(
    "/metadata",
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
def update_metadata(payload: DeviceMetadata) -> dict:
    config_manager.save_device_metadata(payload)
    return {"status": "updated", "metadata": payload}


def _apply_event_update(update: EventUpdate) -> UserSettings:
    settings = _load_settings()
    if update.events_enabled is not None:
        settings.events_enabled = update.events_enabled
    if update.alarms_enabled is not None:
        settings.alarms_enabled = update.alarms_enabled
    if update.event_pipeline_mode is not None:
        settings.event_pipeline_mode = update.event_pipeline_mode
    config_manager.save_user_settings(settings)
    return settings


@router.put(
    "/events",
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
def update_event_flags(update: EventUpdate) -> dict:
    settings = _apply_event_update(update)
    return {
        "status": "updated",
        "events": {
            "events_enabled": settings.events_enabled,
            "alarms_enabled": settings.alarms_enabled,
            "event_pipeline_mode": settings.event_pipeline_mode,
        },
    }


def _apply_recording_update(update: RecordingUpdate) -> UserSettings:
    settings = _load_settings()
    if update.recording_mode is not None:
        settings.recording_mode = update.recording_mode
    if update.recording_enabled is not None:
        settings.recording_enabled = update.recording_enabled
    if update.recording_triggers is not None:
        settings.recording_triggers = update.recording_triggers
    config_manager.save_user_settings(settings)
    return settings


@router.put(
    "/recording",
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
def update_recording(update: RecordingUpdate) -> dict:
    settings = _apply_recording_update(update)
    return {
        "status": "updated",
        "recording": settings.recording_mode,
        "recording_enabled": settings.recording_enabled,
        "recording_triggers": settings.recording_triggers,
    }


@router.post(
    "/apply",
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
def apply_changes() -> dict:
    settings = _load_settings()
    apply_all(settings.network, settings.ntp)
    return {"status": "applied"}


@router.get("/ui", response_class=HTMLResponse)
async def ui_status() -> HTMLResponse:
    status_payload = get_status()
    body = f"""
    <h1>System Status</h1>
    <section class="card">
      <h2>Runtime</h2>
      <pre class="status">{status_payload}</pre>
      <p>Use the navigation links to update configuration using the built-in forms.</p>
    </section>
    """
    return _html_page("System Status", body)


@router.get("/ui/network", response_class=HTMLResponse)
async def ui_network() -> HTMLResponse:
    settings = _load_settings().network
    dns_value = ",".join(settings.dns_servers)
    body = f"""
    <h1>Network Configuration</h1>
    <section class="card">
      <form method="post" action="/system/ui/network">
        <label for="hostname">Hostname</label>
        <input type="text" id="hostname" name="hostname" value="{settings.hostname}" />
        <label for="interface">Interface</label>
        <input type="text" id="interface" name="interface" value="{settings.interface}" />
        <label for="mode">Mode</label>
        <select id="mode" name="mode">
          <option value="dhcp" {'selected' if settings.mode == NetworkMode.dhcp else ''}>DHCP</option>
          <option value="static" {'selected' if settings.mode == NetworkMode.static else ''}>Static</option>
        </select>
        <label for="static_ip">Static IP</label>
        <input type="text" id="static_ip" name="static_ip" value="{settings.static_ip or ''}" />
        <label for="subnet_mask">Subnet Mask</label>
        <input type="text" id="subnet_mask" name="subnet_mask" value="{settings.subnet_mask or ''}" />
        <label for="gateway">Gateway</label>
        <input type="text" id="gateway" name="gateway" value="{settings.gateway or ''}" />
        <label for="dns_servers">DNS Servers (comma separated)</label>
        <input type="text" id="dns_servers" name="dns_servers" value="{dns_value}" />
        <div class="actions">
          <button type="submit">Save Network Settings</button>
        </div>
      </form>
    </section>
    """
    return _html_page("Network Configuration", body)


@router.post(
    "/ui/network",
    response_class=HTMLResponse,
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
async def ui_network_submit(
    hostname: str = Form(...),
    interface: str = Form(...),
    mode: NetworkMode = Form(...),
    static_ip: Optional[str] = Form(None),
    subnet_mask: Optional[str] = Form(None),
    gateway: Optional[str] = Form(None),
    dns_servers: Optional[str] = Form(None),
) -> RedirectResponse:
    dns_list = [entry.strip() for entry in (dns_servers or "").split(",") if entry.strip()]
    payload = NetworkSettings(
        hostname=hostname,
        interface=interface,
        mode=mode,
        static_ip=static_ip or None,
        subnet_mask=subnet_mask or None,
        gateway=gateway or None,
        dns_servers=dns_list,
    )
    update_network(payload)
    return RedirectResponse("/system/ui", status_code=status.HTTP_302_FOUND)


@router.get("/ui/ntp", response_class=HTMLResponse)
async def ui_ntp() -> HTMLResponse:
    settings = _load_settings().ntp
    servers = ",".join(settings.servers)
    body = f"""
    <h1>NTP Configuration</h1>
    <section class="card">
      <form method="post" action="/system/ui/ntp">
        <label for="enabled">NTP Enabled</label>
        <select id="enabled" name="enabled">
          <option value="true" {'selected' if settings.enabled else ''}>Enabled</option>
          <option value="false" {'selected' if not settings.enabled else ''}>Disabled</option>
        </select>
        <label for="servers">Servers (comma separated)</label>
        <input type="text" id="servers" name="servers" value="{servers}" />
        <div class="actions">
          <button type="submit">Save NTP Settings</button>
        </div>
      </form>
    </section>
    """
    return _html_page("NTP Configuration", body)


@router.post(
    "/ui/ntp",
    response_class=HTMLResponse,
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
async def ui_ntp_submit(
    enabled: str = Form(...),
    servers: Optional[str] = Form(None),
) -> RedirectResponse:
    server_list = [entry.strip() for entry in (servers or "").split(",") if entry.strip()]
    payload = NTPSettings(enabled=enabled.lower() == "true", servers=server_list)
    update_ntp(payload)
    return RedirectResponse("/system/ui", status_code=status.HTTP_302_FOUND)


@router.get("/ui/metadata", response_class=HTMLResponse)
async def ui_metadata() -> HTMLResponse:
    metadata = config_manager.get_device_metadata()
    body = f"""
    <h1>Device Metadata</h1>
    <section class="card">
      <form method="post" action="/system/ui/metadata">
        <label for="manufacturer">Manufacturer</label>
        <input type="text" id="manufacturer" name="manufacturer" value="{metadata.manufacturer}" />
        <label for="model">Model</label>
        <input type="text" id="model" name="model" value="{metadata.model}" />
        <label for="firmware_version">Firmware Version</label>
        <input type="text" id="firmware_version" name="firmware_version" value="{metadata.firmware_version}" />
        <label for="serial_number">Serial Number</label>
        <input type="text" id="serial_number" name="serial_number" value="{metadata.serial_number}" />
        <label for="hardware_id">Hardware ID</label>
        <input type="text" id="hardware_id" name="hardware_id" value="{metadata.hardware_id}" />
        <label for="developer_notes">Developer Notes</label>
        <input type="text" id="developer_notes" name="developer_notes" value="{metadata.developer_notes or ''}" />
        <div class="actions">
          <button type="submit">Save Metadata</button>
        </div>
      </form>
    </section>
    """
    return _html_page("Device Metadata", body)


@router.post(
    "/ui/metadata",
    response_class=HTMLResponse,
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
async def ui_metadata_submit(
    manufacturer: str = Form(...),
    model: str = Form(...),
    firmware_version: str = Form(...),
    serial_number: str = Form(...),
    hardware_id: str = Form(...),
    developer_notes: Optional[str] = Form(None),
) -> RedirectResponse:
    payload = DeviceMetadata(
        manufacturer=manufacturer,
        model=model,
        firmware_version=firmware_version,
        serial_number=serial_number,
        hardware_id=hardware_id,
        developer_notes=developer_notes or None,
    )
    update_metadata(payload)
    return RedirectResponse("/system/ui", status_code=status.HTTP_302_FOUND)


@router.get("/ui/events", response_class=HTMLResponse)
async def ui_events() -> HTMLResponse:
    settings = _load_settings()
    triggers = ",".join(settings.recording_triggers)
    body = f"""
    <h1>Events & Recording</h1>
    <section class="card">
      <form method="post" action="/system/ui/events">
        <label for="events_enabled">Events Enabled</label>
        <select id="events_enabled" name="events_enabled">
          <option value="true" {'selected' if settings.events_enabled else ''}>Enabled</option>
          <option value="false" {'selected' if not settings.events_enabled else ''}>Disabled</option>
        </select>
        <label for="alarms_enabled">Alarms Enabled</label>
        <select id="alarms_enabled" name="alarms_enabled">
          <option value="true" {'selected' if settings.alarms_enabled else ''}>Enabled</option>
          <option value="false" {'selected' if not settings.alarms_enabled else ''}>Disabled</option>
        </select>
        <label for="event_pipeline_mode">Pipeline Mode</label>
        <select id="event_pipeline_mode" name="event_pipeline_mode">
          <option value="motion" {'selected' if settings.event_pipeline_mode == EventPipelineMode.motion else ''}>Motion</option>
          <option value="event" {'selected' if settings.event_pipeline_mode == EventPipelineMode.event else ''}>Event</option>
          <option value="alarm" {'selected' if settings.event_pipeline_mode == EventPipelineMode.alarm else ''}>Alarm</option>
        </select>
        <label for="recording_mode">Recording Mode</label>
        <select id="recording_mode" name="recording_mode">
          <option value="continuous" {'selected' if settings.recording_mode == RecordingMode.continuous else ''}>Continuous</option>
          <option value="schedule" {'selected' if settings.recording_mode == RecordingMode.schedule else ''}>Schedule</option>
          <option value="on_event" {'selected' if settings.recording_mode == RecordingMode.on_event else ''}>On Event</option>
        </select>
        <label for="recording_enabled">Recording Enabled</label>
        <select id="recording_enabled" name="recording_enabled">
          <option value="true" {'selected' if settings.recording_enabled else ''}>Enabled</option>
          <option value="false" {'selected' if not settings.recording_enabled else ''}>Disabled</option>
        </select>
        <label for="recording_triggers">Recording Triggers</label>
        <input type="text" id="recording_triggers" name="recording_triggers" value="{triggers}" />
        <div class="actions">
          <button type="submit">Save Event & Recording</button>
        </div>
      </form>
    </section>
    """
    return _html_page("Events and Recording", body)


@router.post(
    "/ui/events",
    response_class=HTMLResponse,
    dependencies=[Depends(require_roles(["operator", "admin"]))],
)
async def ui_events_submit(
    events_enabled: str = Form(...),
    alarms_enabled: str = Form(...),
    event_pipeline_mode: EventPipelineMode = Form(...),
    recording_mode: RecordingMode = Form(...),
    recording_enabled: str = Form(...),
    recording_triggers: Optional[str] = Form(None),
) -> RedirectResponse:
    trigger_list = [entry.strip() for entry in (recording_triggers or "").split(",") if entry.strip()]
    _apply_event_update(
        EventUpdate(
            events_enabled=events_enabled.lower() == "true",
            alarms_enabled=alarms_enabled.lower() == "true",
            event_pipeline_mode=event_pipeline_mode,
        )
    )
    _apply_recording_update(
        RecordingUpdate(
            recording_mode=recording_mode,
            recording_enabled=recording_enabled.lower() == "true",
            recording_triggers=trigger_list,
        )
    )
    return RedirectResponse("/system/ui", status_code=status.HTTP_302_FOUND)

