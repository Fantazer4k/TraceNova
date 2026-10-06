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
            _search_github(session, email),
            _search_github_code(session, email),
            _check_hibp(session, email),
            _check_domain_mx(session, domain),
            _check_gravatar(session, email),
        ]

        # These integrations are useful when configured, but never pretend
        # that a placeholder/free key is a real verification service.
        if os.getenv("ZEROBOUNCE_API_KEY"):
            tasks.append(_verify_email_zerobounce(session, email))
        else:
            technical_checks.append({
                "source": "ZeroBounce",
                "status": "not_configured",
                "description": "Optional email verification API key is not configured.",
            })

        results = await asyncio.gather(*tasks, return_exceptions=True)

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
            web_result = await _search_public_web(web_session, email)
        if web_result:
            if web_result.get("found") is True:
                found_sources.append(web_result)
            elif web_result.get("category") == "technical":
                technical_checks.append(web_result)
    else:
        manual_sources.extend([
            _manual_google_search(email),
            _manual_social_search(email),
        ])

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
            "No confirmed public-source matches found. "
            "This does not prove that the email is unused or invalid."
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

        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                return None

            data = await response.json()
            total_count = data.get("total_count", 0)
            if total_count <= 0:
                return None

            return {
                "found": True,
                "source": "GitHub",
                "source_url": "https://github.com",
                "icon": "🐙",
                "description": (
                    f"GitHub returned {total_count} public profile match(es) "
                    "for this search query. A search match is not proof of identity."
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
                "confidence": "medium",
            }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None
    return None


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

        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                return None

            data = await response.json()
            total_count = data.get("total_count", 0)
            if total_count <= 0:
                return None

            return {
                "found": True,
                "source": "GitHub Code",
                "source_url": f"https://github.com/search?q={quote(chr(34) + email + chr(34))}&type=code",
                "icon": "📄",
                "description": (
                    f"Found {total_count} public code result(s) containing the exact email."
                ),
                "type": "code_search",
                "priority": 85,
                "confidence": "medium",
            }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None
    return None


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

        async with session.get(url, headers=headers) as response:
            if response.status == 404:
                return {
                    "category": "technical",
                    "source": "Have I Been Pwned",
                    "status": "checked_no_match",
                    "description": "No breach match was returned for this email.",
                }

            if response.status == 200:
                breaches = await response.json()
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
                    "confidence": "high",
                }

            return {
                "category": "technical",
                "source": "Have I Been Pwned",
                "status": "unavailable",
                "description": f"HIBP returned HTTP {response.status}.",
            }
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return {
            "category": "technical",
            "source": "Have I Been Pwned",
            "status": "unavailable",
            "description": "HIBP could not be reached.",
        }


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
        async with session.get(url) as response:
            if response.status != 200:
                return {
                    "category": "technical",
                    "source": "ZeroBounce",
                    "status": "unavailable",
                    "description": f"ZeroBounce returned HTTP {response.status}.",
                }

            data = await response.json()
            result_status = data.get("status", "unknown")
            if result_status in {"valid", "catch-all"}:
                return {
                    "found": True,
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
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return {
            "category": "technical",
            "source": "ZeroBounce",
            "status": "unavailable",
            "description": "ZeroBounce could not be reached.",
        }


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

                data = await response.json()
                status_code = data.get("Status")
                if status_code not in (None, 0):
                    last_error = f"DNS resolver returned status {status_code}."
                    continue

                answers = data.get("Answer", [])
                mx_records = sorted(
                    {
                        answer.get("data")
                        for answer in answers
                        if answer.get("type") == 15 and answer.get("data")
                    }
                )

                if mx_records:
                    return {
                        "category": "technical",
                        "source": "DNS / MX",
                        "status": "checked",
                        "description": "The email domain publishes MX records.",
                        "details": {
                            "domain": domain,
                            "mx_records": mx_records,
                            "resolver": resolver,
                        },
                    }

                return {
                    "category": "technical",
                    "source": "DNS / MX",
                    "status": "no_mx",
                    "description": "No MX record was returned for this domain.",
                    "details": {"domain": domain, "resolver": resolver},
                }
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
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None
    return None


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
        async with session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                return {
                    "category": "technical",
                    "source": "Brave Search",
                    "status": "unavailable",
                    "description": f"Public web search returned HTTP {response.status}.",
                }

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
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return {
            "category": "technical",
            "source": "Brave Search",
            "status": "unavailable",
            "description": "Public web search could not be completed.",
        }


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


def _manual_google_search(email: str) -> Dict:
    return {
        "status": "manual",
        "source": "Google Search",
        "source_url": f"https://www.google.com/search?q=%22{quote(email)}%22",
        "icon": "🔍",
        "description": "Manual web search for public mentions not covered by an API.",
        "type": "web_search",
        "priority": 50,
    }


def _manual_social_search(email: str) -> Dict:
    query = (
        f'%22{quote(email)}%22+site%3Atwitter.com+OR+site%3Areddit.com+'
        f'site%3Alinkedin.com+OR+site%3Agithub.com'
    )
    return {
        "status": "manual",
        "source": "Public Web Search",
        "source_url": f"https://www.google.com/search?q={query}",
        "icon": "🌐",
        "description": "Fallback search for public mentions on indexed websites.",
        "type": "web_search",
        "priority": 45,
    }
