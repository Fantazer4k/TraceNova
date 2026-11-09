"""
Safe URL metadata analysis.

This module performs URL parsing, public DNS resolution, and (for HTTPS)
a TLS handshake. It deliberately does not fetch page content or follow
redirects, avoiding arbitrary HTTP requests from the server.
"""

import asyncio
import ipaddress
import json
import socket
import ssl
from urllib.error import URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


_DOH_ENDPOINTS = (
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
)
_DOH_TIMEOUT_SECONDS = 3


def _resolve_with_doh(hostname: str) -> list[str]:
    """Resolve A/AAAA records over HTTPS when the system DNS resolver fails."""
    addresses = []

    for record_type in ("A", "AAAA"):
        for endpoint in _DOH_ENDPOINTS:
            params = urlencode({"name": hostname, "type": record_type})
            separator = "&" if "?" in endpoint else "?"
            request = Request(
                f"{endpoint}{separator}{params}",
                headers={"Accept": "application/dns-json", "User-Agent": "TraceNova/1.0"},
            )
            try:
                with urlopen(request, timeout=_DOH_TIMEOUT_SECONDS) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload.get("Status") != 0:
                    continue

                expected_version = 4 if record_type == "A" else 6
                for answer in payload.get("Answer", []):
                    if answer.get("type") != (1 if record_type == "A" else 28):
                        continue
                    try:
                        address = ipaddress.ip_address(answer.get("data", ""))
                    except ValueError:
                        continue
                    if address.version == expected_version:
                        addresses.append(str(address))
                if any(
                    ipaddress.ip_address(address).version == expected_version
                    for address in addresses
                ):
                    break
            except (OSError, URLError, ValueError, json.JSONDecodeError):
                continue

    return list(dict.fromkeys(addresses))


def _resolve_public_addresses(hostname: str, port: int) -> list[str]:
    """Resolve a hostname and reject non-public destinations."""
    try:
        literal_ip = ipaddress.ip_address(hostname)
        addresses = [str(literal_ip)]
    except ValueError:
        try:
            records = socket.getaddrinfo(
                hostname,
                port,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )
            addresses = list(dict.fromkeys(record[4][0] for record in records))
        except socket.gaierror:
            addresses = _resolve_with_doh(hostname)

    if not addresses:
        raise socket.gaierror("No A or AAAA records were returned by the DNS resolvers.")

    parsed = [ipaddress.ip_address(address) for address in addresses]
    if any(not address.is_global for address in parsed):
        raise ValueError(
            "The URL resolves to a non-public IP address. Local and private network targets are blocked."
        )

    return addresses


def _inspect_tls(hostname: str, address: str, port: int) -> dict:
    """Perform a bounded TLS handshake against one already-validated public IP."""
    context = ssl.create_default_context()
    with socket.create_connection((address, port), timeout=3) as raw_socket:
        with context.wrap_socket(raw_socket, server_hostname=hostname) as tls_socket:
            certificate = tls_socket.getpeercert()
            return {
                "status": "success",
                "version": tls_socket.version(),
                "cipher": tls_socket.cipher()[0] if tls_socket.cipher() else None,
                "subject": certificate.get("subject", ()),
                "issuer": certificate.get("issuer", ()),
                "expires": certificate.get("notAfter"),
            }


def _analyze_url(url: str) -> dict:
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError("Only http:// and https:// URLs are supported.")
        if not parsed.hostname:
            raise ValueError("A valid hostname is required.")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("URLs containing embedded credentials are not supported.")

        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port or (443 if scheme == "https" else 80)
        if not 1 <= port <= 65535:
            raise ValueError("Invalid port number.")

        addresses = _resolve_public_addresses(hostname, port)
        result = {
            "status": "success",
            "query_type": "url",
            "url": url,
            "scheme": scheme,
            "hostname": hostname,
            "port": port,
            "path": parsed.path or "/",
            "resolved_ips": addresses,
            "tls": {"status": "not_applicable"},
            "message": (
                "URL parsed and public DNS resolution completed. Page content was not fetched."
            ),
        }

        if scheme == "https":
            try:
                result["tls"] = _inspect_tls(hostname, addresses[0], port)
            except (OSError, ssl.SSLError, TimeoutError) as exc:
                result["tls"] = {
                    "status": "unavailable",
                    "message": f"TLS handshake could not be completed: {type(exc).__name__}",
                }

        return result

    except (ValueError, UnicodeError) as exc:
        return {
            "status": "error",
            "query_type": "url",
            "url": url,
            "message": str(exc),
            "error_type": "invalid_url_or_target",
        }
    except socket.gaierror:
        return {
            "status": "error",
            "query_type": "url",
            "url": url,
            "message": "The hostname could not be resolved.",
            "error_type": "resolution_failed",
        }
    except OSError as exc:
        return {
            "status": "error",
            "query_type": "url",
            "url": url,
            "message": f"Network analysis failed: {type(exc).__name__}",
            "error_type": "network_error",
        }


async def analyze_url(url: str) -> dict:
    """Run URL analysis without blocking the FastAPI event loop."""
    return await asyncio.to_thread(_analyze_url, url.strip())
