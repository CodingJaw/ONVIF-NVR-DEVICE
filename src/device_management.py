"""Device management helpers for network and NTP configuration."""
from __future__ import annotations

import logging
from pathlib import Path

from src.config import NetworkMode, NetworkSettings, NTPSettings, get_config_manager
from src.system_control import apply_all, apply_hostname, apply_network, apply_ntp, _prefix_to_netmask

logger = logging.getLogger(__name__)


_HOSTNAME_PATH = Path("/etc/hostname")
_RESOLV_CONF = Path("/etc/resolv.conf")
_DHCPCD_CONF = Path("/etc/dhcpcd.conf")
_TIMESYNCD_CONF = Path("/etc/systemd/timesyncd.conf")


def _read_hostname() -> str | None:
    try:
        return _HOSTNAME_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _read_dns_servers() -> list[str]:
    if not _RESOLV_CONF.exists():
        return []
    servers: list[str] = []
    try:
        for line in _RESOLV_CONF.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("nameserver"):
                parts = line.split()
                if len(parts) >= 2:
                    servers.append(parts[1])
    except OSError:
        return []
    return servers


def _parse_static_ip(entry: str) -> tuple[str, str] | tuple[None, None]:
    try:
        address, prefix_text = entry.split("/")
        prefix = int(prefix_text)
        netmask = _prefix_to_netmask(prefix)
        return address, netmask
    except Exception:  # pragma: no cover - defensive parsing
        return None, None


def _read_dhcpcd(interface: str) -> dict[str, str | list[str] | NetworkMode]:
    if not _DHCPCD_CONF.exists():
        return {}

    active = False
    parsed: dict[str, str | list[str] | NetworkMode] = {}

    try:
        for line in _DHCPCD_CONF.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("interface "):
                active = stripped.split()[1] == interface
                continue
            if not active:
                continue

            if stripped.startswith("static ip_address="):
                address = stripped.split("=", 1)[1]
                ip, netmask = _parse_static_ip(address)
                if ip:
                    parsed["mode"] = NetworkMode.static
                    parsed["static_ip"] = ip
                if netmask:
                    parsed["subnet_mask"] = netmask
            elif stripped.startswith("static routers="):
                parsed["gateway"] = stripped.split("=", 1)[1]
            elif stripped.startswith("static domain_name_servers="):
                dns = stripped.split("=", 1)[1]
                parsed["dns_servers"] = dns.split()
    except OSError:
        return {}

    return parsed


def _read_ntp_config() -> tuple[bool, list[str]]:
    enabled = True
    servers: list[str] = []

    if _TIMESYNCD_CONF.exists():
        try:
            for line in _TIMESYNCD_CONF.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("NTP="):
                    values = stripped.split("=", 1)[1]
                    servers.extend([entry for entry in values.split() if entry])
        except OSError:
            pass

    return enabled, servers


def _merge_network_settings(base: NetworkSettings) -> NetworkSettings:
    overrides = _read_dhcpcd(base.interface)
    hostname = _read_hostname() or base.hostname
    dns = _read_dns_servers() or base.dns_servers

    mode = overrides.get("mode", base.mode)
    static_ip = overrides.get("static_ip", base.static_ip)
    subnet_mask = overrides.get("subnet_mask", base.subnet_mask)
    gateway = overrides.get("gateway", base.gateway)
    dns_servers = overrides.get("dns_servers", dns)

    return NetworkSettings(
        mode=mode,
        interface=base.interface,
        hostname=hostname,
        static_ip=static_ip,
        subnet_mask=subnet_mask,
        gateway=gateway,
        dns_servers=list(dns_servers) if isinstance(dns_servers, list) else dns,
    )


def _merge_ntp_settings(base: NTPSettings) -> NTPSettings:
    enabled, servers = _read_ntp_config()
    merged_servers = servers or base.servers
    return NTPSettings(enabled=enabled if enabled is not None else base.enabled, servers=merged_servers)


def get_network_settings() -> NetworkSettings:
    config = get_config_manager()
    base = config.get_user_settings().network
    return _merge_network_settings(base)


def get_ntp_settings() -> NTPSettings:
    config = get_config_manager()
    base = config.get_user_settings().ntp
    return _merge_ntp_settings(base)


def set_network_settings(settings: NetworkSettings) -> NetworkSettings:
    config = get_config_manager()
    user_settings = config.get_user_settings()
    user_settings.network = settings
    config.save_user_settings(user_settings)
    apply_network(settings)
    apply_hostname(settings.hostname)
    return settings


def set_ntp_settings(settings: NTPSettings) -> NTPSettings:
    config = get_config_manager()
    user_settings = config.get_user_settings()
    user_settings.ntp = settings
    config.save_user_settings(user_settings)
    apply_ntp(settings)
    return settings


def set_hostname(hostname: str) -> str:
    config = get_config_manager()
    user_settings = config.get_user_settings()
    user_settings.network.hostname = hostname
    config.save_user_settings(user_settings)
    apply_hostname(hostname)
    return hostname


def apply_all_from_config() -> None:
    config = get_config_manager()
    settings = config.get_user_settings()
    apply_all(settings.network, settings.ntp)

