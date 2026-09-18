"""
Email search services.

Only confirmed results are reported as found. Manual search links are returned
separately so the UI does not mistake a generated search URL for a match.
"""

import asyncio
import aiohttp
import re
import os
from typing import Dict, List, Optional
from urllib.parse import quote

EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"


async def search_email(email: str) -> Dict:
    """Search public sources for an email address."""
    if not email or "@" not in email:
        return {"status": "error", "email": email, "message": "Please enter a valid email"}

    email = email.lower().strip()
    if not re.match(EMAIL_REGEX, email):
        return {"status": "error", "email": email, "message": "Invalid email format"}

    found_sources = []
    manual_sources = []

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [
                _search_github(session, email),
                _check_breach_hibp(session, email),
                _verify_email_zerobounce(session, email),
                _search_github_gists(session, email),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, dict):
                    if result.get("found"):
                        found_sources.append(result)
                    elif result.get("status") == "manual":
                        manual_sources.append(result)

    except Exception:
        return {
            "status": "error",
            "email": email,
            "message": "Unable to complete the email search.",
        }

    # Manual links are useful, but they are not evidence of a match.
    manual_sources.extend([
        _manual_google_search(email),
        _manual_social_search(email),
    ])

    found_sources.sort(key=lambda x: x.get("priority", 0), reverse=True)

    if not found_sources:
        status = "manual" if manual_sources else "no_results"
        return {
            "status": status,
            "email": email,
            "found_in_sources": [],
            "manual_sources": manual_sources,
            "total_sources": 0,
            "summary": (
                "No confirmed matches found. Manual search links are available."
                if manual_sources
                else f"No results found for {email}"
            ),
        }

    return {
        "status": "success",
        "email": email,
        "found_in_sources": found_sources,
        "manual_sources": manual_sources,
        "total_sources": len(found_sources),
        "summary": f"Found {len(found_sources)} confirmed source(s)",
    }


async def _search_github(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    try:
        url = f"https://api.github.com/search/users?q={quote(email)}+in:email&per_page=10"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "TraceNova/1.0"}

        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("total_count", 0) > 0:
                    users = data.get("items", [])[:10]
                    return {
                        "found": True,
                        "source": "GitHub",
                        "source_url": "https://github.com",
                        "icon": "🐙",
                        "description": f"Found {data.get('total_count')} GitHub profile(s) matching this query",
                        "profiles": [
                            {
                                "username": u.get("login"),
                                "profile_url": u.get("html_url"),
                                "avatar": u.get("avatar_url"),
                            }
                            for u in users
                        ],
                        "type": "real_search",
                        "priority": 100,
                    }
    except Exception:
        return None
    return None


async def _check_breach_hibp(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    try:
        url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote(email, safe='')}"
        headers = {"User-Agent": "TraceNova/1.0"}

        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                breaches = await response.json()
                if breaches:
                    return {
                        "found": True,
                        "source": "Data Breaches (HIBP)",
                        "source_url": "https://haveibeenpwned.com",
                        "icon": "⚠️",
                        "warning": "FOUND IN BREACHES",
                        "description": f"Found in {len(breaches)} breach(es)",
                        "breaches": [b.get("Name") for b in breaches],
                        "type": "security_alert",
                        "priority": 95,
                    }
            elif response.status == 404:
                return None
    except Exception:
        return None
    return None


async def _verify_email_zerobounce(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    try:
        url = f"https://api.zerobounce.net/v2/validate?email={quote(email)}&api_key=free_api"

        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                status = data.get("status")
                if status in {"valid", "catch-all"}:
                    return {
                        "found": True,
                        "source": "Email Verification",
                        "icon": "✅",
                        "description": f"Email verification returned: {status}",
                        "type": "verification",
                        "priority": 70,
                    }
    except Exception:
        return None
    return None


async def _search_github_gists(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    try:
        url = f"https://api.github.com/search/code?q={quote(email)}+in:file&per_page=5"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "TraceNova/1.0"}

        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("total_count", 0) > 0:
                    return {
                        "found": True,
                        "source": "GitHub Code",
                        "source_url": f"https://github.com/search?q={quote(email)}",
                        "icon": "📄",
                        "description": f"Found {data.get('total_count')} code result(s) containing the query",
                        "type": "code_search",
                        "priority": 85,
                    }
    except Exception:
        return None
    return None


def _manual_google_search(email: str) -> Dict:
    return {
        "status": "manual",
        "source": "Google Search",
        "source_url": f"https://www.google.com/search?q=%22{quote(email)}%22",
        "icon": "🔍",
        "description": "Open a manual web search for public mentions.",
        "type": "web_search",
        "priority": 50,
    }


def _manual_social_search(email: str) -> Dict:
    return {
        "status": "manual",
        "source": "Social Media Search",
        "source_url": (
            "https://www.google.com/search?q="
            f"%22{quote(email)}%22+site%3Atwitter.com+OR+site%3Areddit.com+OR+site%3Alinkedin.com"
        ),
        "icon": "📱",
        "description": "Open a manual search for public social-media mentions.",
        "type": "social_search",
        "priority": 45,
    }
