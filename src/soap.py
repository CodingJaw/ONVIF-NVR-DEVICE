"""Lightweight SOAP facade that fronts the REST handlers with ONVIF-like envelopes."""
from __future__ import annotations

import logging
from typing import Callable, Dict
from xml.etree import ElementTree as ET
from xml.etree.ElementTree import Element

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.config import get_config_manager
from src.pipeline import EventPipeline
from src.routers import device as device_rest
from src.routers import events as events_rest
from src.routers import media as media_rest
from src.routers import ptz as ptz_rest
from src.routers import recording as recording_rest
from src.users import UserStore, get_user_store

logger = logging.getLogger(__name__)

SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"
WSSE_NS = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
TDS_NS = "http://www.onvif.org/ver10/device/wsdl"
TRT_NS = "http://www.onvif.org/ver10/media/wsdl"
TEV_NS = "http://www.onvif.org/ver10/events/wsdl"
TRC_NS = "http://www.onvif.org/ver10/recording/wsdl"
PTZ_NS = "http://www.onvif.org/ver20/ptz/wsdl"

ET.register_namespace("soap", SOAP_NS)
ET.register_namespace("wsse", WSSE_NS)
ET.register_namespace("tds", TDS_NS)
ET.register_namespace("trt", TRT_NS)
ET.register_namespace("tev", TEV_NS)
ET.register_namespace("trc", TRC_NS)
ET.register_namespace("tptz", PTZ_NS)


def _require_username_token(envelope: Element, store: UserStore) -> None:
    """Validate WS-Security UsernameToken credentials."""

    security = envelope.find(f".//{{{WSSE_NS}}}Security")
    if security is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing WS-Security Security header",
        )

    username_el = security.find(f".//{{{WSSE_NS}}}Username")
    password_el = security.find(f".//{{{WSSE_NS}}}Password")
    if username_el is None or password_el is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing UsernameToken credentials",
        )

    try:
        store.authenticate(username_el.text or "", password_el.text or "")
    except ValueError as exc:  # pragma: no cover - delegated validation
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from exc


def _soap_envelope(body_child: Element) -> Response:
    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    body = ET.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    body.append(body_child)
    xml = ET.tostring(envelope, encoding="utf-8", xml_declaration=True)
    return Response(content=xml, media_type="application/soap+xml")


def _fault(reason: str) -> Response:
    fault_body = ET.Element(f"{{{SOAP_NS}}}Fault")
    code_el = ET.SubElement(fault_body, "Code")
    ET.SubElement(code_el, "Value").text = "soap:Sender"
    reason_el = ET.SubElement(fault_body, "Reason")
    ET.SubElement(reason_el, "Text").text = reason
    return _soap_envelope(fault_body)


def _parse_operation(content: bytes) -> tuple[Element, str]:
    try:
        envelope = ET.fromstring(content)
    except ET.ParseError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    body = envelope.find(f".//{{{SOAP_NS}}}Body")
    if body is None or not list(body):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="SOAP Body is missing"
        )

    operation = list(body)[0]
    local_name = operation.tag.split("}")[-1]
    return envelope, local_name


# Business logic adapters -----------------------------------------------------


config_manager = get_config_manager()
pipeline = EventPipeline(config_manager)


def _device_get_capabilities() -> Response:
    capabilities = device_rest.get_capabilities()
    response = ET.Element(f"{{{TDS_NS}}}GetCapabilitiesResponse")
    caps_el = ET.SubElement(response, f"{{{TDS_NS}}}Capabilities")

    device_caps = ET.SubElement(caps_el, f"{{{TDS_NS}}}Device")
    ET.SubElement(device_caps, f"{{{TDS_NS}}}System").text = str(
        capabilities["device"].get("system", False)
    ).lower()
    ET.SubElement(device_caps, f"{{{TDS_NS}}}Network").text = str(
        capabilities["device"].get("network", False)
    ).lower()

    events_caps = ET.SubElement(caps_el, f"{{{TDS_NS}}}Events")
    ET.SubElement(events_caps, f"{{{TDS_NS}}}WSSubscription").text = str(
        capabilities["events"].get("ws_subscription", False)
    ).lower()

    media_caps = ET.SubElement(caps_el, f"{{{TDS_NS}}}Media")
    ET.SubElement(media_caps, f"{{{TDS_NS}}}Profiles").text = str(
        capabilities["media"].get("profiles", False)
    ).lower()

    ptz_caps = ET.SubElement(caps_el, f"{{{TDS_NS}}}PTZ")
    ET.SubElement(ptz_caps, f"{{{TDS_NS}}}Supported").text = str(
        capabilities["ptz"].get("supported", False)
    ).lower()

    rec_caps = ET.SubElement(caps_el, f"{{{TDS_NS}}}Recording")
    ET.SubElement(rec_caps, f"{{{TDS_NS}}}Search").text = str(
        capabilities["recording"].get("search", False)
    ).lower()

    return _soap_envelope(response)


def _device_get_information() -> Response:
    info = device_rest.get_device_information()
    response = ET.Element(f"{{{TDS_NS}}}GetDeviceInformationResponse")
    for key, value in info.items():
        child = ET.SubElement(response, f"{{{TDS_NS}}}{key.title().replace('_', '')}")
        child.text = value
    return _soap_envelope(response)


def _media_get_profiles() -> Response:
    profiles = media_rest.list_profiles()
    response = ET.Element(f"{{{TRT_NS}}}GetProfilesResponse")
    for profile in profiles:
        profile_el = ET.SubElement(response, f"{{{TRT_NS}}}Profiles")
        profile_el.set("token", profile.get("token", ""))
        ET.SubElement(profile_el, f"{{{TRT_NS}}}Name").text = profile.get("name", "")
        ve = ET.SubElement(
            profile_el,
            f"{{{TRT_NS}}}VideoEncoderConfiguration",
        )
        ET.SubElement(ve, f"{{{TRT_NS}}}Name").text = profile.get(
            "video_encoder_configuration", ""
        )
        ae = ET.SubElement(
            profile_el,
            f"{{{TRT_NS}}}AudioEncoderConfiguration",
        )
        ET.SubElement(ae, f"{{{TRT_NS}}}Name").text = profile.get(
            "audio_encoder_configuration", ""
        )
    return _soap_envelope(response)


def _media_get_stream_uri() -> Response:
    uri = media_rest.get_stream_uri()
    response = ET.Element(f"{{{TRT_NS}}}GetStreamUriResponse")
    stream = ET.SubElement(response, f"{{{TRT_NS}}}MediaUri")
    ET.SubElement(stream, f"{{{TRT_NS}}}Uri").text = uri["uri"]
    ET.SubElement(stream, f"{{{TRT_NS}}}InvalidAfterConnect").text = "false"
    ET.SubElement(stream, f"{{{TRT_NS}}}InvalidAfterReboot").text = "false"
    ET.SubElement(stream, f"{{{TRT_NS}}}Timeout").text = "PT60S"
    return _soap_envelope(response)


def _events_create_subscription() -> Response:
    result = events_rest.create_subscription()
    response = ET.Element(f"{{{TEV_NS}}}CreatePullPointSubscriptionResponse")
    sub = ET.SubElement(response, f"{{{TEV_NS}}}SubscriptionReference")
    ET.SubElement(sub, f"{{{TEV_NS}}}Address").text = result["subscription_id"]
    ET.SubElement(response, f"{{{TEV_NS}}}CurrentTime").text = result["expires"]
    ET.SubElement(response, f"{{{TEV_NS}}}TerminationTime").text = result["expires"]
    return _soap_envelope(response)


def _events_pull_messages() -> Response:
    result = events_rest.pull_messages()
    response = ET.Element(f"{{{TEV_NS}}}PullMessagesResponse")
    msg_holder = ET.SubElement(response, f"{{{TEV_NS}}}NotificationMessage")
    for message in result.get("messages", []):
        msg = ET.SubElement(msg_holder, f"{{{TEV_NS}}}Message")
        for key, value in message.items():
            ET.SubElement(msg, f"{{{TEV_NS}}}{key.title()}").text = str(value)
    return _soap_envelope(response)


def _recording_get_jobs() -> Response:
    jobs = recording_rest.list_recording_jobs()
    response = ET.Element(f"{{{TRC_NS}}}GetRecordingJobsResponse")
    for job in jobs:
        job_el = ET.SubElement(response, f"{{{TRC_NS}}}JobConfiguration")
        ET.SubElement(job_el, f"{{{TRC_NS}}}JobToken").text = job.get("id", "")
        ET.SubElement(job_el, f"{{{TRC_NS}}}RecordingToken").text = job.get(
            "source", ""
        )
        ET.SubElement(job_el, f"{{{TRC_NS}}}State").text = job.get("status", "")
    return _soap_envelope(response)


def _recording_create_job() -> Response:
    created = recording_rest.create_recording_job("profile1")
    response = ET.Element(f"{{{TRC_NS}}}CreateRecordingJobResponse")
    ET.SubElement(response, f"{{{TRC_NS}}}JobToken").text = created["id"]
    ET.SubElement(response, f"{{{TRC_NS}}}JobState").text = created["status"]
    return _soap_envelope(response)


def _ptz_continuous_move() -> Response:
    result = ptz_rest.continuous_move()
    response = ET.Element(f"{{{PTZ_NS}}}ContinuousMoveResponse")
    ET.SubElement(response, f"{{{PTZ_NS}}}Pan").text = str(result.get("pan", 0.0))
    ET.SubElement(response, f"{{{PTZ_NS}}}Tilt").text = str(result.get("tilt", 0.0))
    ET.SubElement(response, f"{{{PTZ_NS}}}Zoom").text = str(result.get("zoom", 0.0))
    ET.SubElement(response, f"{{{PTZ_NS}}}Status").text = result.get("status", "")
    return _soap_envelope(response)


def _ptz_stop() -> Response:
    result = ptz_rest.stop_move()
    response = ET.Element(f"{{{PTZ_NS}}}StopResponse")
    ET.SubElement(response, f"{{{PTZ_NS}}}Status").text = result.get("status", "")
    return _soap_envelope(response)


_DEVICE_OPERATIONS: Dict[str, Callable[[], Response]] = {
    "GetCapabilities": _device_get_capabilities,
    "GetDeviceInformation": _device_get_information,
}

_MEDIA_OPERATIONS: Dict[str, Callable[[], Response]] = {
    "GetProfiles": _media_get_profiles,
    "GetStreamUri": _media_get_stream_uri,
}

_EVENTS_OPERATIONS: Dict[str, Callable[[], Response]] = {
    "CreatePullPointSubscription": _events_create_subscription,
    "PullMessages": _events_pull_messages,
}

_RECORDING_OPERATIONS: Dict[str, Callable[[], Response]] = {
    "GetRecordingJobs": _recording_get_jobs,
    "CreateRecordingJob": _recording_create_job,
}

_PTZ_OPERATIONS: Dict[str, Callable[[], Response]] = {
    "ContinuousMove": _ptz_continuous_move,
    "Stop": _ptz_stop,
}


ServiceMap = Dict[str, Dict[str, Callable[[], Response]]]
_SERVICE_OPERATIONS: ServiceMap = {
    "device": _DEVICE_OPERATIONS,
    "media": _MEDIA_OPERATIONS,
    "events": _EVENTS_OPERATIONS,
    "recording": _RECORDING_OPERATIONS,
    "ptz": _PTZ_OPERATIONS,
}

router = APIRouter(prefix="/onvif", tags=["soap"])


async def _dispatch(service: str, request: Request, store: UserStore) -> Response:
    content = await request.body()
    envelope, operation_name = _parse_operation(content)
    _require_username_token(envelope, store)

    operations = _SERVICE_OPERATIONS.get(service)
    if not operations or operation_name not in operations:
        logger.warning("Unsupported SOAP operation %s for %s", operation_name, service)
        return _fault(f"Unsupported operation: {operation_name}")

    return operations[operation_name]()


@router.post("/device_service")
async def device_service(request: Request, store: UserStore = Depends(get_user_store)) -> Response:
    return await _dispatch("device", request, store)


@router.post("/media_service")
async def media_service(request: Request, store: UserStore = Depends(get_user_store)) -> Response:
    return await _dispatch("media", request, store)


@router.post("/events_service")
async def events_service(request: Request, store: UserStore = Depends(get_user_store)) -> Response:
    return await _dispatch("events", request, store)


@router.post("/recording_service")
async def recording_service(
    request: Request, store: UserStore = Depends(get_user_store)
) -> Response:
    return await _dispatch("recording", request, store)


@router.post("/ptz_service")
async def ptz_service(request: Request, store: UserStore = Depends(get_user_store)) -> Response:
    return await _dispatch("ptz", request, store)
