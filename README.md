# ONVIF Reference NVR Device (Raspberry Pi ready)

Minimal ONVIF Profile S-style reference service intended for DVR/NVR interoperability experiments. It exposes REST endpoints that mirror common ONVIF capabilities (device, media, events, recording, PTZ) and a lightweight WS-Discovery responder suitable for Raspberry Pi deployments.

> **Status:** Early prototype. Several ONVIF operations are stubbed or simplified; see ["What's missing for full ONVIF compliance"](#whats-missing-for-full-onvif-compliance).

## Recently merged updates
- Consolidated REST stubs for device/media/events/recording/PTZ into a single service entrypoint (`src/main.py`).
- Added YAML-backed persistence for device metadata and user-facing schedules/alarms so settings survive restarts.
- Introduced WS-Security UsernameToken parsing with role-based authorization and default admin bootstrap.
- Added a lightweight media pipeline manager that binds ONVIF profiles to RTSP URIs and snapshot placeholders.

## Features implemented
- WS-Discovery responder announcing the service address on UDP 3702.
- FastAPI service exposing ONVIF-like routes for device info, media profiles/RTSP URI, PTZ controls, event pull/notifications, and recording triggers.
- YAML-backed configuration for user settings (`config/user.yaml`) and device metadata (`config/device.yaml`) with atomic writes and validation.
- WS-Security UsernameToken parsing plus role-based access control (`viewer`, `operator`, `admin`).
- User management API and CLI with PBKDF2-hashed passwords; default admin account `admin/admin123` generated on first run.
- Event/recording pipeline with schedulable windows, four digital inputs/outputs, and in-memory notifications persisted back to `config/user.yaml`.

## Prerequisites
- Python 3.11+
- (Optional) Docker if you prefer containerized deployment

## Local virtual environment setup
Create an isolated Python environment to avoid polluting the system interpreter.

1. Create the environment (replace `python` with `python3` on some systems):
   ```bash
   python -m venv .venv
   ```
2. Activate it:
   - **Linux/macOS:**
     ```bash
     source .venv/bin/activate
     ```
   - **Windows PowerShell:**
     ```powershell
     .venv\\Scripts\\Activate.ps1
     ```
3. Upgrade pip and install project dependencies:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
    If you installed dependencies before this change, rerun the install so the
    updated password hashing dependencies are applied.
4. (Optional) Inspect or edit default configuration generated on first run:
   - `config/device.yaml` – manufacturer/model/firmware/serial metadata
   - `config/user.yaml` – recording schedules, digital IO state, pipeline mode

## Running the service (local)
Start the FastAPI app with the built-in WS-Discovery responder. The helper runner
reads `SERVICE_HOST`/`SERVICE_PORT` and passes them to Uvicorn automatically:
```bash
SERVICE_HOST=0.0.0.0 SERVICE_PORT=8000 ./scripts/run_uvicorn.sh
```
If you prefer the raw Uvicorn CLI, include the flags explicitly so the binding
matches your environment:
```bash
uvicorn src.main:app --host "${SERVICE_HOST:-0.0.0.0}" --port "${SERVICE_PORT:-8000}"
```
- REST API: `http://<host>:8000`
- RTSP server: `rtsp://<host>:8554/<profile_token>`
- WS-Discovery: UDP 3702 multicast responses announcing the above address

### Example WS-Security header
All protected routes require a WS-Security UsernameToken header. Example using the default admin account:
```
UsernameToken username="admin" password="admin123"
```

## Docker deployment
Build and run the container (ports 8000/TCP for API and 3702/UDP for discovery):
```bash
docker build -t onvif-nvr-device .
docker run --rm -p 8000:8000 -p 3702:3702/udp \
  -v $(pwd)/config:/app/config \
  -e SERVICE_HOST=0.0.0.0 -e SERVICE_PORT=8000 \
  onvif-nvr-device
```
Mounting `./config` keeps device/user settings persistent across restarts.

## User management
### REST API
- `GET /users/` – list users (admin only)
- `POST /users/` – create user (`{"username": ..., "password": ..., "roles": ["viewer"|"operator"|"admin"]}`)
- `PUT /users/{username}` – update password and/or roles
- `DELETE /users/{username}` – remove a user

### CLI helper
Manage users without hitting the API:
```bash
python -m src.users list
python -m src.users create alice s3cret --roles admin operator
python -m src.users update alice --password newpass --roles viewer
python -m src.users delete alice
```
All commands read/write `config/users.yaml` with atomic updates.

## API highlights
- **Device**: `GET /device/information`, `GET /device/capabilities`
- **Media**: `GET /media/profiles`, `GET /media/stream_uri?profile_token=profile1`, `PUT /media/profiles/{token}` to tune resolution/bitrate/frame rate
- **Events**: `GET /events/subscription`, `GET /events/pull`, `POST /events/mode/{motion|event|alarm}`, `POST /events/digital/{input|output}/{channel_id}`, `POST /events/schedules`
- **Recording**: `GET /recording/jobs`, `POST /recording/jobs`, `POST /recording/schedules`
- **PTZ**: `POST /ptz/move`, `POST /ptz/stop`

## Configuration files
- `config/user.yaml`
  - `recording_schedules`: named start/end windows with day-of-week filters
  - `digital_inputs` / `digital_outputs`: four channels each (`channel_id`, `direction`, `name`, `state`)
  - `recording_triggers`: tokens pushed by `/recording/jobs`
  - `event_pipeline_mode`: `event`/`motion`/`alarm`
  - `events_enabled` / `alarms_enabled`: master switches for notification flow
  - `media_profiles`: encoder settings (token, resolution, bitrate, frame rate)
- `config/device.yaml`
  - `manufacturer`, `model`, `firmware_version`, `serial_number`, `hardware_id`, optional `developer_notes`
  - `config/users.yaml`
    - Auto-created with admin account; stores PBKDF2 hashes and role assignments

## Media pipeline
- Default profiles loaded from `config/user.yaml`:
  - `profile1` – 1920x1080 @ 30fps, 8Mbps
  - `profile2` – 1280x720 @ 15fps, 4Mbps
- `GET /media/profiles` returns the configured profiles, RTSP URI, source type (camera/testscreen/bouncing_ball/image/mpeg), and last-known pipeline string with overlays.
- `GET /media/stream_uri?profile_token=...` starts or reuses the mapped pipeline and returns the RTSP URI.
- `PUT /media/profiles/{token}` adjusts resolution/bitrate/frame rate and source material (test screens, bouncing ball, static image, MPEG file) and persists the change back to `config/user.yaml`.
- Snapshot placeholders are emitted to `config/snapshots/<token>.png` for basic ONVIF snapshot interoperability.
- All generated pipelines stamp the hostname and live date/time in the top overlay for easy identification when testing.

## What's missing for full ONVIF compliance
- SOAP service surfaces for Device/Media/Event/Recording/PTZ (currently REST-only stubs).
- Hardware-validated media streaming and snapshot capture (current pipelines are libcamera/GStreamer examples).
- Event delivery filters, pull-point/subscription lifecycles, and full topic set.
- Recording search, export, and NVR-side state transitions beyond simple triggers.
- Network/NTP configuration plumbing for Raspberry Pi (DHCP/static, DNS, hostname updates).
- GUI setup pages and hardening (audit logs, rate limits, TLS termination).

## Contributing
Pull requests are welcome. Please add tests for new behavior and keep configuration changes backward compatible.
