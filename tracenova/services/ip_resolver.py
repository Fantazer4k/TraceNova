"""
IP Address resolver service
Get IP address from domain using DNS lookup
"""

import socket
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
