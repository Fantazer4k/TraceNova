"""
Email intelligence services.

The module separates confirmed public-source matches from technical checks.
It never treats a search-engine URL, HTTP 200, or email-format validity as
proof that an address belongs to a person.

Optional integrations are enabled only when their API keys are configured.
"""

import asyncio
import hashlib
import os
import re
from typing import Dict, List, Optional
from urllib.parse import quote

import aiohttp

EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
DNS_RESOLVERS = (
    "https://cloudflare-dns.com/dns-query",
    "https://dns.google/resolve",
)


def _source_check(source: str, status: str, description: str) -> Dict:
    return {"category": "technical", "source": source, "status": status, "description": description}


def _http_failure(source: str, response) -> Dict:
    limited = response.status == 429 or (
        response.status == 403 and response.headers.get("X-RateLimit-Remaining") == "0"
    )
    return _source_check(
        source, "rate_limited" if limited else "unavailable",
        f"Provider returned HTTP {response.status}.",
    )


async def _check_source(source: str, operation) -> Dict:
    try:
        result = await operation
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return _provider_exception(source, exc)
    return result or _source_check(source, "error", "The provider check returned no status.")


def _provider_exception(source: str, exc: Exception) -> Dict:
    if isinstance(exc, asyncio.TimeoutError):
        return _source_check(source, "timeout", "The provider request timed out.")
    if isinstance(exc, (aiohttp.ContentTypeError, ValueError, TypeError, AttributeError, KeyError)):
        return _source_check(source, "error", "The provider returned an invalid response.")
    return _source_check(source, "unavailable", "The provider could not be reached.")


async def search_email(email: str) -> Dict:
    """Collect public-source and technical intelligence for an email."""
    if not email or "@" not in email:
        return {"status": "error", "email": email, "message": "Please enter a valid email"}

    email = email.lower().strip()
    if not re.match(EMAIL_REGEX, email):
        return {"status": "error", "email": email, "message": "Invalid email format"}

    local_part, domain = email.rsplit("@", 1)
    found_sources: List[Dict] = []
    technical_checks: List[Dict] = []
    manual_sources: List[Dict] = []

    timeout = aiohttp.ClientTimeout(total=8)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            _check_source("GitHub", _search_github(session, email)),
            _check_source("GitHub Code", _search_github_code(session, email)),
            _check_source("Have I Been Pwned", _check_hibp(session, email)),
            _check_source("DNS / MX", _check_domain_mx(session, domain)),
            _check_source("Gravatar", _check_gravatar(session, email)),
        ]

        # These integrations are useful when configured, but never pretend
        # that a placeholder/free key is a real verification service.
        if os.getenv("ZEROBOUNCE_API_KEY"):
            tasks.append(_check_source("ZeroBounce", _verify_email_zerobounce(session, email)))
        else:
            technical_checks.append({
                "source": "ZeroBounce",
                "status": "not_configured",
                "description": "Optional email verification API key is not configured.",
            })

        results = await asyncio.gather(*tasks)

        for result in results:
            if not isinstance(result, dict):
                continue
            if result.get("found") is True:
                found_sources.append(result)
            elif result.get("category") == "technical":
                technical_checks.append(result)
            elif result.get("status") == "manual":
                manual_sources.append(result)

    # Use an API-backed search provider when configured. Otherwise keep manual links.
    if os.getenv("BRAVE_SEARCH_API_KEY"):
        async with aiohttp.ClientSession(timeout=timeout) as web_session:
            web_result = await _check_source("Brave Search", _search_public_web(web_session, email))
        if web_result:
            if web_result.get("found") is True:
                found_sources.append(web_result)
            elif web_result.get("category") == "technical":
                technical_checks.append(web_result)
    else:
        technical_checks.append(_source_check(
            "Brave Search", "not_configured", "Optional web search API key is not configured.",
        ))
    manual_sources.extend(_manual_web_searches(email))

    found_sources = _deduplicate_sources(found_sources)
    found_sources.sort(key=lambda item: item.get("priority", 0), reverse=True)

    breach_status = next(
        (item for item in found_sources if item.get("type") == "security_alert"),
        None,
    )

    if found_sources:
        status = "success"
        summary = (
            f"Found {len(found_sources)} public-source result(s). "
            f"Technical checks: {len(technical_checks)}."
        )
    else:
        status = "no_results"
        summary = (
            "No confirmed matches were returned by these checks. "
            "See individual source statuses for gaps in coverage."
        )

    return {
        "status": status,
        "email": email,
        "local_part": local_part,
        "domain": domain,
        "format_valid": True,
        "found_in_sources": found_sources,
        "technical_checks": technical_checks,
        "manual_sources": manual_sources,
        "total_sources": len(found_sources),
        "breach_detected": breach_status is not None,
        "summary": summary,
    }


async def _search_github(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """Find public GitHub accounts returned by an email search query."""
    try:
        url = f"https://api.github.com/search/users?q={quote(email)}+in:email&per_page=10"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "TraceNova/1.0",
        }
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with session.get(url, headers=headers, allow_redirects=False) as response:
            if response.status != 200:
                return _http_failure("GitHub", response)

            data = await response.json()
            total_count = data["total_count"]
            if total_count <= 0:
                if data.get("incomplete_results"):
                    return _source_check("GitHub", "incomplete", "GitHub reported incomplete search results.")
                return _source_check("GitHub", "checked_no_match", "GitHub returned no profile candidates.")

            return {
                "category": "technical",
                "status": "candidates_unverified",
                "source": "GitHub",
                "source_url": "https://github.com",
                "icon": "🐙",
                "description": (
                    f"GitHub search returned {total_count} candidate result(s). "
                    "The exact email was not verified in any profile; these are NOT confirmed email matches."
                    + (" GitHub reported incomplete coverage." if data.get("incomplete_results") else "")
                ),
                "profiles": [
                    {
                        "username": user.get("login"),
                        "profile_url": user.get("html_url"),
                        "avatar": user.get("avatar_url"),
                    }
                    for user in data.get("items", [])[:10]
                ],
                "type": "real_search",
                "priority": 100,
                "confidence": "unverified",
            }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return _provider_exception("GitHub", exc)


async def _search_github_code(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """Search public GitHub code for an exact email occurrence."""
    try:
        url = f"https://api.github.com/search/code?q={quote(chr(34) + email + chr(34))}&per_page=10"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "TraceNova/1.0",
        }
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        async with session.get(url, headers=headers, allow_redirects=False) as response:
            if response.status != 200:
                return _http_failure("GitHub Code", response)

            data = await response.json()
            total_count = data["total_count"]
            if total_count <= 0:
                if data.get("incomplete_results"):
                    return _source_check("GitHub Code", "incomplete", "GitHub reported incomplete code search results.")
                return _source_check("GitHub Code", "checked_no_match", "GitHub returned no code candidates.")

            return {
                "category": "technical",
                "status": "candidates_unverified",
                "source": "GitHub Code",
                "source_url": f"https://github.com/search?q={quote(chr(34) + email + chr(34))}&type=code",
                "icon": "📄",
                "description": (
                    f"GitHub code search returned {total_count} candidate(s), but exact occurrences "
                    "were not verified in source content."
                    + (" GitHub reported incomplete coverage." if data.get("incomplete_results") else "")
                ),
                "type": "code_search",
                "priority": 85,
                "confidence": "unverified",
            }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, TypeError, AttributeError, KeyError) as exc:
        return _provider_exception("GitHub Code", exc)


async def _check_hibp(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """Check HIBP when a valid API key is configured."""
    api_key = os.getenv("HIBP_API_KEY")
    if not api_key:
        return {
            "category": "technical",
            "source": "Have I Been Pwned",
            "status": "not_configured",
            "description": "HIBP breach lookup requires an API key.",
        }

    try:
        url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote(email, safe='')}"
        headers = {
            "User-Agent": "TraceNova/1.0",
            "hibp-api-key": api_key,
        }

        async with session.get(url, headers=headers, allow_redirects=False) as response:
            if response.status == 404:
                return {
                    "category": "technical",
                    "source": "Have I Been Pwned",
                    "status": "checked_no_match",
                    "description": "No breach match was returned for this email.",
                }

            if response.status == 200:
                breaches = await response.json()
                if not isinstance(breaches, list) or any(
                    not isinstance(item, dict) or not isinstance(item.get("Name"), str)
                    for item in breaches
                ):
                    return _source_check("Have I Been Pwned", "error", "Invalid breach response.")
                if not breaches:
                    return _source_check("Have I Been Pwned", "checked_no_match", "No breach was returned.")
                return {
                    "found": True,
                    "source": "Data Breaches (HIBP)",
                    "source_url": "https://haveibeenpwned.com",
                    "icon": "⚠️",
                    "warning": "FOUND IN BREACHES",
                    "description": f"Found in {len(breaches)} breach(es).",
                    "breaches": [item.get("Name") for item in breaches],
                    "type": "security_alert",
                    "priority": 95,
                    "confidence": "verification_only",
                }

            return _http_failure("Have I Been Pwned", response)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        return _provider_exception("Have I Been Pwned", exc)


async def _verify_email_zerobounce(
    session: aiohttp.ClientSession,
    email: str,
) -> Optional[Dict]:
    """Use ZeroBounce only when the user supplies a real API key."""
    api_key = os.getenv("ZEROBOUNCE_API_KEY")
    if not api_key:
        return None

    try:
        url = (
            "https://api.zerobounce.net/v2/validate"
            f"?email={quote(email)}&api_key={quote(api_key)}"
        )
        async with session.get(url, allow_redirects=False) as response:
            if response.status != 200:
                return _http_failure("ZeroBounce", response)

            data = await response.json()
            result_status = data.get("status", "unknown")
            if result_status in {"valid", "catch-all"}:
                return {
                    "category": "technical",
                    "status": result_status,
                    "source": "Email Verification",
                    "icon": "✅",
                    "description": f"ZeroBounce returned: {result_status}.",
                    "type": "verification",
                    "priority": 70,
                    "confidence": "high",
                }

            return {
                "category": "technical",
                "source": "ZeroBounce",
                "status": result_status,
                "description": f"ZeroBounce returned: {result_status}.",
            }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        return _provider_exception("ZeroBounce", exc)


async def _check_domain_mx(
    session: aiohttp.ClientSession,
    domain: str,
) -> Optional[Dict]:
    """Check whether the email domain publishes MX records via public DNS-over-HTTPS resolvers."""
    last_error = "DNS lookup could not be completed."

    for resolver in DNS_RESOLVERS:
        try:
            if "cloudflare" in resolver:
                url = f"{resolver}?name={quote(domain)}&type=MX"
                headers = {
                    "Accept": "application/dns-json",
                    "User-Agent": "TraceNova/1.0",
                }
            else:
                url = f"{resolver}?name={quote(domain)}&type=MX"
                headers = {"User-Agent": "TraceNova/1.0"}

            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    last_error = f"DNS resolver returned HTTP {response.status}."
                    continue

                return _interpret_mx_response(await response.json(), domain, resolver)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            last_error = f"DNS resolver unavailable: {type(exc).__name__}."
            continue

    return {
        "category": "technical",
        "source": "DNS / MX",
        "status": "unavailable",
        "description": last_error,
        "details": {"domain": domain},
    }


def _interpret_mx_response(data: object, domain: str, resolver: str) -> Dict:
    if not isinstance(data, dict) or type(data.get("Status")) is not int or data.get("TC"):
        raise ValueError("Invalid or truncated DNS response")

    result = {
        "category": "technical",
        "source": "DNS / MX",
        "details": {"domain": domain, "resolver": resolver},
    }
    status_code = data["Status"]
    if status_code == 3:
        return {
            **result,
            "status": "nxdomain",
            "description": "The DNS resolver reported that the queried name does not exist (NXDOMAIN).",
        }
    if status_code != 0:
        raise ValueError(f"DNS response code {status_code}")

    answers = data.get("Answer", [])
    if not isinstance(answers, list):
        raise ValueError("Invalid DNS answer list")

    mx_records = set()
    for answer in answers:
        if not isinstance(answer, dict) or type(answer.get("type")) is not int:
            raise ValueError("Invalid DNS answer")
        if answer["type"] != 15:
            continue
        record = answer.get("data")
        fields = record.split() if isinstance(record, str) else []
        if len(fields) != 2 or not re.fullmatch(r"[0-9]{1,5}", fields[0]):
            raise ValueError("Invalid MX record")
        preference = int(fields[0])
        exchange = fields[1]
        if preference > 65535 or (exchange == "." and preference != 0):
            raise ValueError("Invalid MX preference")
        mx_records.add(f"{preference} {exchange}")

    if not mx_records:
        return {
            **result,
            "status": "no_mx",
            "description": "No explicit MX record was returned. SMTP may fall back to address records.",
        }

    result["details"]["mx_records"] = sorted(mx_records)
    if "0 ." in mx_records:
        if len(mx_records) != 1:
            raise ValueError("Null MX is mixed with other MX records")
        return {
            **result,
            "status": "null_mx",
            "description": "The domain publishes a null MX, which declares that it does not accept email.",
        }
    return {
        **result,
        "status": "checked",
        "description": "The domain publishes MX records. This does not establish mailbox existence.",
    }


async def _check_gravatar(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """Check for a public Gravatar associated with the email hash."""
    try:
        digest = hashlib.md5(email.encode("utf-8")).hexdigest()
        url = f"https://www.gravatar.com/avatar/{digest}?d=404"

        async with session.get(url, allow_redirects=True) as response:
            if response.status == 200:
                return {
                    "found": True,
                    "source": "Gravatar",
                    "source_url": f"https://gravatar.com/{digest}",
                    "icon": "🖼️",
                    "description": "A public Gravatar image was found for this email hash.",
                    "type": "public_profile",
                    "priority": 60,
                    "confidence": "medium",
                    "note": "This is evidence of a public avatar association, not proof of identity.",
                }
            if response.status == 404:
                return _source_check("Gravatar", "checked_no_match", "No public avatar was returned.")
            return _http_failure("Gravatar", response)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return _provider_exception("Gravatar", exc)


async def _search_public_web(
    session: aiohttp.ClientSession,
    email: str,
) -> Optional[Dict]:
    """Search indexed public web pages for an exact email mention."""
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if not api_key:
        return None

    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
        "User-Agent": "TraceNova/1.0",
    }
    params = {
        "q": f'"{email}"',
        "count": 20,
        "safesearch": "strict",
    }

    try:
        async with session.get(url, headers=headers, params=params, allow_redirects=False) as response:
            if response.status != 200:
                return _http_failure("Brave Search", response)

            data = await response.json()
            results = data.get("web", {}).get("results", [])
            matches = []
            normalized_email = email.casefold()

            for item in results:
                title = item.get("title") or ""
                result_url = item.get("url") or ""
                description = item.get("description") or ""
                combined = f"{title} {result_url} {description}".casefold()

                if normalized_email not in combined:
                    continue

                matches.append({
                    "title": title,
                    "url": result_url,
                    "snippet": description,
                    "domain": _extract_domain(result_url),
                })

            if not matches:
                return {
                    "category": "technical",
                    "source": "Brave Search",
                    "status": "checked_no_match",
                    "description": (
                        "No indexed search result contained the exact email "
                        "in its returned title, URL, or snippet."
                    ),
                }

            return {
                "found": True,
                "source": "Public Web Search",
                "source_url": "https://search.brave.com",
                "icon": "🌐",
                "description": (
                    f"Found {len(matches)} indexed public result(s) whose returned "
                    "metadata contains the exact email. This is public-web evidence, "
                    "not proof of identity."
                ),
                "results": matches,
                "type": "web_search",
                "priority": 55,
                "confidence": "low",
            }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        return _provider_exception("Brave Search", exc)


def _extract_domain(url: str) -> str:
    """Return the hostname from a public result URL."""
    match = re.match(r"^https?://([^/]+)", url, flags=re.IGNORECASE)
    return match.group(1).lower() if match else ""


def _deduplicate_sources(sources: List[Dict]) -> List[Dict]:
    """Remove duplicate source records while preserving the first result."""
    seen = set()
    unique = []

    for source in sources:
        key = (
            source.get("source"),
            source.get("source_url"),
            source.get("type"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)

    return unique


def _manual_web_searches(email: str) -> List[Dict]:
    query = quote(f'"{email}"', safe="")
    return [
        {"status": "manual", "source": source, "source_url": base_url + query,
         "type": "web_search", "description": "Search indexed pages for the exact address."}
        for source, base_url in (
            ("Google Search", "https://www.google.com/search?q="),
            ("Bing", "https://www.bing.com/search?q="),
            ("DuckDuckGo", "https://duckduckgo.com/?q="),
        )
    ]
