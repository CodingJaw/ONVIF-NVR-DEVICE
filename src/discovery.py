"""WS-Discovery responder to announce the ONVIF service."""

import socket
import threading
import uuid
from datetime import datetime

WS_DISCOVERY_MULTICAST_GROUP = ("239.255.255.250", 3702)


class WSDiscoveryResponder:
    """
    Minimal WS-Discovery responder that listens for Probe requests and returns
    a static SOAP response. This is suitable for lab/testing environments and
    Raspberry Pi deployments where a lightweight announcement service is needed.
    """

    def __init__(self, service_address: str) -> None:
        self.service_address = service_address
        self.running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self.running:
            return

        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

    def _run(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", WS_DISCOVERY_MULTICAST_GROUP[1]))

            mreq = socket.inet_aton(WS_DISCOVERY_MULTICAST_GROUP[0]) + socket.inet_aton("0.0.0.0")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            while self.running:
                try:
                    data, addr = sock.recvfrom(4096)
                except OSError:
                    break

                if b"Probe" not in data:
                    continue

                response = self._build_probe_match_response()
                try:
                    sock.sendto(response, addr)
                except OSError:
                    continue

    def _build_probe_match_response(self) -> bytes:
        message_id = f"uuid:{uuid.uuid4()}"
        relates_to = f"uuid:{uuid.uuid4()}"
        body = f"""
        <s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing" xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
          <s:Header>
            <a:MessageID>{message_id}</a:MessageID>
            <a:RelatesTo>{relates_to}</a:RelatesTo>
            <a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>
            <a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</a:Action>
          </s:Header>
          <s:Body>
            <d:ProbeMatches>
              <d:ProbeMatch>
                <a:EndpointReference>
                  <a:Address>urn:uuid:{uuid.uuid4()}</a:Address>
                </a:EndpointReference>
                <d:Types>dn:NetworkVideoTransmitter</d:Types>
                <d:Scopes>onvif://www.onvif.org/type/video_encoder</d:Scopes>
                <d:XAddrs>{self.service_address}</d:XAddrs>
                <d:MetadataVersion>{int(datetime.utcnow().timestamp())}</d:MetadataVersion>
              </d:ProbeMatch>
            </d:ProbeMatches>
          </s:Body>
        </s:Envelope>
        """
        return body.encode()

