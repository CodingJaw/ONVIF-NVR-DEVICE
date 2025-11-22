# ONVIF Reference NVR Device (Raspberry Pi ready)

Minimal ONVIF Profile S-style reference service intended for DVR/NVR interoperability experiments. It exposes REST endpoints that mirror common ONVIF capabilities (device, media, events, recording, PTZ) and a lightweight WS-Discovery responder suitable for Raspberry Pi deployments.

> **Status:** Early prototype. Several ONVIF operations are stubbed or simplified; see ["What's missing for full ONVIF compliance"](#whats-missing-for-full-onvif-compliance).

## Recently merged updates
- Consolidated REST stubs for device/media/events/recording/PTZ into a single service entrypoint (`src/main.py`).
- Added YAML-backed persistence for device metadata and user-facing schedules/alarms so settings survive restarts.
- Introduced WS-Security UsernameToken parsing with role-based authorization and default admin bootstrap.
- Added configuration validation and atomic writes so the device state remains consistent after power loss or reboots.

## Project layout
- `src/` – FastAPI app, ONVIF-like routers, WS-Discovery responder, WS-Security helpers, and CLI utilities.
- `config/` – YAML files for device metadata (`device.yaml`), user settings (`user.yaml`), and user database (`users.yaml`).
- `deploy/` – Docker and systemd-friendly assets for running the service on Raspberry Pi.
- `requirements.txt` – Python dependencies for the service and tooling.

## Features implemented
- WS-Discovery responder announcing the service address on UDP 3702.
- FastAPI service exposing ONVIF-like routes for device info, media profiles/RTSP URI, PTZ controls, event pull/notifications, and recording triggers.
- YAML-backed configuration for user settings (`config/user.yaml`) and device metadata (`config/device.yaml`) with atomic writes and validation.
- WS-Security UsernameToken parsing plus role-based access control (`viewer`, `operator`, `admin`).
- User management API and CLI with bcrypt-hashed passwords; default admin account `admin/admin123` generated on first run.
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
4. (Optional) Inspect or edit default configuration generated on first run:
   - `config/device.yaml` – manufacturer/model/firmware/serial metadata
   - `config/user.yaml` – recording schedules, digital IO state, pipeline mode

## Running the service (local)
Start the FastAPI app with the built-in WS-Discovery responder:
```bash
SERVICE_HOST=0.0.0.0 SERVICE_PORT=8000 uvicorn src.main:app
```
- REST API: `http://<host>:8000`
- RTSP placeholder URI: `rtsp://<host>:8554/profile1` (no media pipeline yet)
- WS-Discovery: UDP 3702 multicast responses announcing the above address

### Development tips
- Run the service with auto-reload while iterating:
  ```bash
  SERVICE_HOST=0.0.0.0 SERVICE_PORT=8000 uvicorn src.main:app --reload
  ```
- Lint and type-check before committing:
  ```bash
  ruff src
  mypy src
  ```
- Run the lightweight test suite (if you add tests under `tests/`):
  ```bash
  pytest
  ```

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
- **Media**: `GET /media/profiles`, `GET /media/stream_uri?profile_token=profile1`
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
- `config/device.yaml`
  - `manufacturer`, `model`, `firmware_version`, `serial_number`, `hardware_id`, optional `developer_notes`
- `config/users.yaml`
  - Auto-created with admin account; stores bcrypt hashes and role assignments

## What's missing for full ONVIF compliance
- SOAP service surfaces for Device/Media/Event/Recording/PTZ (currently REST-only stubs).
- Real media pipeline (encoder settings, RTSP/RTP streaming, snapshots) instead of static URIs.
- Event delivery filters, pull-point/subscription lifecycles, and full topic set.
- Recording search, export, and NVR-side state transitions beyond simple triggers.
- Network/NTP configuration plumbing for Raspberry Pi (DHCP/static, DNS, hostname updates).
- GUI setup pages and hardening (audit logs, rate limits, TLS termination).

## Roadmap to full device readiness
- **Short term**: Implement ONVIF SOAP surfaces for Device/Media/Event/Recording/PTZ; back them with the existing FastAPI logic; add conformance responses and WS-Security enforcement.
- **Media pipeline**: Integrate a real encoder (e.g., GStreamer/libcamera on RPi) that serves H.264 RTSP streams and snapshots; expose configurable media profiles.
- **Events**: Build pull-point subscription lifecycles with topic filters, renewals, and notification sequencing; wire digital IO and scheduler events to ONVIF topics.
- **Recording**: Add search/export jobs with indexed recordings and ONVIF Recording service operations; persist metadata for NVR control flows.
- **Device mgmt**: Apply DHCP/static IP, DNS, NTP, and hostname changes via Raspberry Pi tooling; mirror settings in REST and SOAP operations.
- **UX & hardening**: Provide a minimal web UI for setup, plus audit logging, rate limits, and optional TLS termination.

## Contributing
Pull requests are welcome. Please add tests for new behavior and keep configuration changes backward compatible.
