"""System-level configuration application helpers."""

from __future__ import annotations

import ipaddress
import logging
import shutil
import subprocess
from pathlib import Path

from src.config import NetworkMode, NetworkSettings, NTPSettings


logger = logging.getLogger(__name__)


def _run_command(command: list[str]) -> None:
    """Run a system command if available, logging warnings on failure."""

    executable = command[0]
    if shutil.which(executable) is None:
        logger.warning("Command %s not available on this system", executable)
        return

    try:
        subprocess.run(command, check=False, timeout=5)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Failed to run %s: %s", " ".join(command), exc)


def _write_file(path: Path, content: str) -> None:
    """Safely write a configuration file if permissions allow."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Unable to write %s: %s", path, exc)


def _netmask_to_prefix(netmask: str) -> int:
    network = ipaddress.IPv4Network(f"0.0.0.0/{netmask}")
    return network.prefixlen


def apply_hostname(hostname: str) -> None:
    """Update the system hostname using hostnamectl when available."""

    if not hostname:
        return
    _run_command(["hostnamectl", "set-hostname", hostname])
    _run_command(["hostname", hostname])


def apply_ntp(settings: NTPSettings) -> None:
    """Enable or disable NTP and configure preferred servers."""

    toggle = "true" if settings.enabled else "false"
    _run_command(["timedatectl", "set-ntp", toggle])

    if settings.servers:
        timesyncd_conf = Path("/etc/systemd/timesyncd.conf")
        content = "[Time]\n" f"NTP={' '.join(settings.servers)}\n"
        _write_file(timesyncd_conf, content)
        _run_command(["systemctl", "restart", "systemd-timesyncd"])


def apply_dns(servers: list[str]) -> None:
    """Write resolv.conf entries to reflect DNS preferences."""

    if not servers:
        return

    resolv_conf = Path("/etc/resolv.conf")
    content = "\n".join([f"nameserver {server}" for server in servers]) + "\n"
    _write_file(resolv_conf, content)


def apply_network(settings: NetworkSettings) -> None:
    """Apply network settings using iproute2 utilities."""

    if settings.mode == NetworkMode.dhcp:
        _run_command(["dhclient", "-r", settings.interface])
        _run_command(["dhclient", settings.interface])
    else:
        prefix = _netmask_to_prefix(settings.subnet_mask or "255.255.255.0")
        _run_command(["ip", "addr", "flush", "dev", settings.interface])
        if settings.static_ip:
            _run_command(
                [
                    "ip",
                    "addr",
                    "add",
                    f"{settings.static_ip}/{prefix}",
                    "dev",
                    settings.interface,
                ]
            )
        if settings.gateway:
            _run_command(
                [
                    "ip",
                    "route",
                    "replace",
                    "default",
                    "via",
                    settings.gateway,
                    "dev",
                    settings.interface,
                ]
            )

    apply_dns(settings.dns_servers)


def apply_all(network: NetworkSettings, ntp: NTPSettings) -> None:
    """Apply all system-related settings in order."""

    apply_hostname(network.hostname)
    apply_network(network)
    apply_ntp(ntp)
