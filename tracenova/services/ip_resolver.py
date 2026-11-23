"""
IP Address resolver service
Get IP address from domain using DNS lookup
"""

import socket
import ipaddress

import aiohttp
import asyncio
from typing import Dict, Optional

from services.url_analyzer import is_public_unicast

async def resolve_domain_to_ip(domain: str) -> Dict:
    """Resolve public A/AAAA records using the same protected DNS path as URL Search.

    If the local resolver fails (as seen with example.com on some routers),
    the shared resolver uses its DNS-over-HTTPS fallback.
    """
    from urllib.parse import urlsplit
    from services.url_analyzer import _resolve_public_addresses

    original = (domain or "").strip()
    if not original:
        return {"status": "error", "domain": original, "message": "Enter a domain name."}
    try:
        candidate = original if "://" in original else "https://" + original
        parts = urlsplit(candidate)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("Enter a domain hostname, not a URL with another protocol.")
        if parts.username is not None or parts.password is not None:
            raise ValueError("Embedded credentials are not supported.")
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            raise ValueError("Domain Search expects only a hostname, without path or query.")
        hostname = parts.hostname.encode("idna").decode("ascii").lower()
        if len(hostname) > 253 or not all(
            0 < len(label) <= 63 and label[0] != "-" and label[-1] != "-"
            for label in hostname.split(".")
        ):
            raise ValueError("Invalid domain hostname.")
        # Shared protection blocks private destinations and unsafe DNS answers.
        addresses = await asyncio.to_thread(_resolve_public_addresses, hostname, 443)
        v4 = [ip for ip in addresses if ipaddress.ip_address(ip).version == 4]
        v6 = [ip for ip in addresses if ipaddress.ip_address(ip).version == 6]
        return {
            "status": "success", "query_type": "domain", "domain": hostname,
            "ip_address": v4[0] if v4 else (v6[0] if v6 else None),
            "ip_addresses": v4, "ipv6_addresses": v6,
            "message": "Public DNS resolution completed. These addresses may change over time.",
        }
    except (ValueError, UnicodeError) as exc:
        return {"status": "error", "query_type": "domain", "domain": original,
                "message": str(exc), "error_type": "invalid_domain_or_target"}
    except socket.gaierror:
        return {"status": "error", "query_type": "domain", "domain": original,
                "message": "Domain could not be resolved with system DNS or configured DoH.",
                "error_type": "resolution_failed"}
    except OSError:
        return {"status": "error", "query_type": "domain", "domain": original,
                "message": "DNS lookup failed due to a network error.", "error_type": "network_error"}


async def get_additional_ip_info(ip_address: str) -> Dict:
    """
    Get additional information about IP address
    (This can be expanded later with geolocation, ASN info, etc.)

    Args:
        ip_address: IP address string

    Returns:
        Dict with IP information
    """
    try:
        # Try reverse DNS lookup
        loop = asyncio.get_event_loop()
        hostname = await loop.run_in_executor(None, socket.gethostbyaddr, ip_address)

        return {
            "ip": ip_address,
            "reverse_dns": hostname[0],
            "aliases": hostname[1],
            "addresses": hostname[2]
        }
    except Exception as e:
        return {
            "ip": ip_address,
            "reverse_dns": "N/A",
            "message": f"Could not perform reverse DNS lookup: {str(e)}"
        }


async def analyze_ip(ip_text: str) -> Dict:
    """Validate IPv4/IPv6, reverse DNS, registry and approximate network location."""
    try:
        ip = ipaddress.ip_address((ip_text or "").strip())
    except ValueError:
        return {"query_type": "ip", "status": "error", "ip_address": ip_text,
                "message": "Not a valid IPv4 or IPv6 address.", "error_type": "invalid_ip"}

    address = str(ip)
    info = await get_additional_ip_info(address)
    public_unicast = is_public_unicast(ip)
    info["address_type"] = "public" if public_unicast else "private_or_reserved"
    if public_unicast:
        rdap, geo, shodan = await asyncio.gather(
            _rdap_ip(address), _geo_ip(address), _shodan_ip(address)
        )
        info.update(rdap)
        info.update(geo)
        info["shodan"] = shodan
    else:
        info["registry_note"] = "Public network metadata requires a public unicast address."

    return {
        "query_type": "ip",
        "status": "success",
        "ip_address": address,
        "ip_version": ip.version,
        "ip_info": info,
        "message": "IP analysis completed. Location is approximate and may identify the provider, not a person.",
    }


async def _shodan_ip(address: str) -> Dict:
    """Read indexed hostname metadata from Shodan InternetDB."""
    try:
        timeout = aiohttp.ClientTimeout(total=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://internetdb.shodan.io/" + address,
                                   allow_redirects=False) as response:
                if response.status == 404:
                    return {"status": "not_found"}
                if response.status == 429:
                    return {"status": "rate_limited"}
                if response.status != 200:
                    return {"status": "unavailable"}
                data = await response.json(content_type=None)
    except asyncio.TimeoutError:
        return {"status": "timeout"}
    except (aiohttp.ClientError, ValueError):
        return {"status": "unavailable"}

    if not isinstance(data, dict) or data.get("ip") != address:
        return {"status": "unavailable"}
    hostnames = data.get("hostnames")
    if not isinstance(hostnames, list):
        return {"status": "unavailable"}
    return {"status": "checked", "hostnames": [
        name for name in hostnames if isinstance(name, str) and 0 < len(name) <= 253
    ][:20]}


async def _rdap_ip(address: str) -> Dict:
    """Public registry data, not proof of physical IP location."""
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://rdap.org/ip/" + address,
                                   headers={"Accept": "application/rdap+json", "User-Agent": "TraceNova/1.0"},
                                   allow_redirects=True, max_redirects=3) as response:
                if response.status != 200:
                    return {"registry_note": "RDAP unavailable (HTTP %s)" % response.status}
                data = await response.json(content_type=None)
        return {
            "network_name": data.get("name"),
            "network_country": data.get("country"),
            "network_range": "%s – %s" % (data.get("startAddress") or "?", data.get("endAddress") or "?"),
            "registry_source": "RDAP (rdap.org)",
        }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        return {"registry_note": "RDAP unavailable (%s)" % type(exc).__name__}


async def _geo_ip(address: str) -> Dict:
    """Best-effort IP geolocation/ASN via ipwho.is, with explicit source.

    City-level accuracy is not guaranteed. Requests are performed only for
    public IP addresses; no personal-device tracking is attempted.
    """
    try:
        timeout = aiohttp.ClientTimeout(total=6)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get("https://ipwho.is/" + address,
                                   headers={"Accept": "application/json", "User-Agent": "TraceNova/1.0"},
                                   allow_redirects=False) as response:
                if response.status != 200:
                    return {"geolocation_note": "IP metadata provider unavailable (HTTP %s)" % response.status}
                data = await response.json(content_type=None)
        if not isinstance(data, dict) or not data.get("success", False):
            return {"geolocation_note": "Approximate location/ASN not available."}
        conn = data.get("connection") or {}
        return {
            "asn": conn.get("asn"),
            "isp": conn.get("isp"),
            "geo_country": data.get("country"),
            "geo_region": data.get("region"),
            "geo_city": data.get("city"),
            "geolocation_source": "ipwho.is (approximate IP-based estimate)",
        }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        return {"geolocation_note": "Approximate location unavailable (%s)" % type(exc).__name__}
