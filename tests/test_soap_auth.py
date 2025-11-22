import base64

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.datastructures import Headers
from xml.etree import ElementTree as ET

from src.soap import SOAP_NS, WSSE_NS, _require_username_token


class _DummyStore:
    def __init__(self, username: str = "alice", password: str = "secret"):
        self.username = username
        self.password = password

    def authenticate(self, username: str, password: str):
        if username == self.username and password == self.password:
            return
        raise ValueError("Invalid credentials")


def _http_request(headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": Headers(headers or {}).raw,
    }
    return Request(scope)


def _soap_envelope(username: str | None = None, password: str | None = None):
    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    header = ET.SubElement(envelope, f"{{{SOAP_NS}}}Header")
    if username is not None and password is not None:
        security = ET.SubElement(header, f"{{{WSSE_NS}}}Security")
        token = ET.SubElement(security, f"{{{WSSE_NS}}}UsernameToken")
        ET.SubElement(token, f"{{{WSSE_NS}}}Username").text = username
        ET.SubElement(token, f"{{{WSSE_NS}}}Password").text = password
    body = ET.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    ET.SubElement(body, "Dummy")
    return envelope


def test_accepts_wsse_security_header():
    store = _DummyStore()
    envelope = _soap_envelope("alice", "secret")

    _require_username_token(envelope, store, request=None)


def test_accepts_username_token_http_header():
    store = _DummyStore()
    envelope = _soap_envelope()  # missing wsse header
    request = _http_request({"UsernameToken": 'UsernameToken username="alice" password="secret"'})

    _require_username_token(envelope, store, request=request)


def test_accepts_basic_auth_header():
    store = _DummyStore()
    envelope = _soap_envelope()  # missing wsse header
    credentials = base64.b64encode(b"alice:secret").decode()
    request = _http_request({"Authorization": f"Basic {credentials}"})

    _require_username_token(envelope, store, request=request)


def test_missing_credentials_raises_http_exception():
    store = _DummyStore()
    envelope = _soap_envelope()
    request = _http_request()

    with pytest.raises(HTTPException) as exc:
        _require_username_token(envelope, store, request=request)

    assert exc.value.status_code == 401


def test_invalid_credentials_raise_http_exception():
    store = _DummyStore()
    envelope = _soap_envelope("alice", "wrong")

    with pytest.raises(HTTPException) as exc:
        _require_username_token(envelope, store, request=None)

    assert exc.value.status_code == 401
