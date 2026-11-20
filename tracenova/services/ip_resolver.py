"""
IP Address resolver service
Get IP address from domain using DNS lookup
"""

import socket
import ipaddress

import aiohttp
import asyncio
from typing import Dict, Optional

async def resolve_domain_to_ip(domain: str) -> Dict:
    """
    Resolve domain name to IP address

    Args:
        domain: Domain name (e.g., example.com)

    Returns:
        Dict with IP address and metadata
    """
    try:
        # Remove protocol if present
        domain = domain.replace("http://", "").replace("https://", "").split("/")[0]

        # Resolve using socket in async context
        loop = asyncio.get_event_loop()
        ip_address = await loop.run_in_executor(None, socket.gethostbyname, domain)

        return {
            "status": "success",
            "domain": domain,
            "ip_address": ip_address,
            "message": f"Successfully resolved {domain} to {ip_address}"
        }

    except socket.gaierror as e:
        return {
            "status": "error",
            "domain": domain,
            "message": f"Domain not found or invalid: {str(e)}",
            "error_type": "resolution_failed"
        }

    except Exception as e:
        return {
            "status": "error",
            "domain": domain,
            "message": f"Error resolving domain: {str(e)}",
            "error_type": "unknown_error"
        }


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
    info["address_type"] = "public" if ip.is_global else "private_or_reserved"
    if ip.is_global:
        rdap, geo = await asyncio.gather(_rdap_ip(address), _geo_ip(address))
        info.update(rdap)
        info.update(geo)
    else:
        info["registry_note"] = "Private/reserved address: public network metadata not applicable."

    return {
        "query_type": "ip",
        "status": "success",
        "ip_address": address,
        "ip_version": ip.version,
        "ip_info": info,
        "message": "IP analysis completed. Location is approximate and may identify the provider, not a person.",
    }


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
