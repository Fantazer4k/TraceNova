"""
Comprehensive Email Search - ALL METHODS
Uses every available free API and search method
"""

import asyncio
import aiohttp
import re
import os
from typing import Dict, List, Optional
from urllib.parse import quote

EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'


async def search_email(email: str) -> Dict:
    """Comprehensive email search using ALL available methods"""
    if not email or '@' not in email:
        return {"status": "error", "email": email, "message": "Please enter a valid email"}

    if not re.match(EMAIL_REGEX, email.lower().strip()):
        return {"status": "error", "email": email, "message": "Invalid email format"}

    email = email.lower().strip()
    found_sources = []

    try:
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        async with aiohttp.ClientSession(connector=connector) as session:
            # Run all searches in parallel
            tasks = [
                _search_github(session, email),
                _check_breach_hibp(session, email),
                _verify_email_zerobounce(session, email),
                _search_google(email),
                _search_social_media(email),
                _search_shodan(session, email),
                _search_rapid7(session, email),
                _search_pastebin_real(session, email),
                _search_github_gists(session, email),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                try:
                    if result and isinstance(result, dict) and result.get("found"):
                        found_sources.append(result)
                except Exception as e:
                    print(f"Result processing error: {e}")
                    continue

    except Exception as e:
        print(f"Email search error: {e}")
        return {"status": "error", "email": email, "message": f"Search error: {str(e)}"}

    # Sort by priority
    try:
        found_sources.sort(key=lambda x: x.get("priority", 0), reverse=True)
    except Exception as e:
        print(f"Sort error: {e}")

    if len(found_sources) == 0:
        return {
            "status": "no_results",
            "email": email,
            "found_in_sources": [],
            "total_sources": 0,
            "summary": f"No results found for {email}"
        }

    return {
        "status": "success",
        "email": email,
        "found_in_sources": found_sources,
        "total_sources": len(found_sources),
        "summary": f"Found in {len(found_sources)} source(s)"
    }


async def _search_github(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """GitHub: Search user profiles"""
    try:
        url = f"https://api.github.com/search/users?q={email}+in:email&per_page=10"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "TraceNova/1.0"}

        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("total_count", 0) > 0:
                    users = data.get("items", [])[:10]
                    profiles = [{"username": u.get("login"), "profile_url": u.get("html_url"), "avatar": u.get("avatar_url")} for u in users]

                    return {
                        "found": True,
                        "source": "GitHub",
                        "source_url": "https://github.com",
                        "icon": "🐙",
                        "description": f"Found {data.get('total_count')} GitHub profile(s) with this email",
                        "profiles": profiles,
                        "type": "real_search",
                        "priority": 100
                    }
    except Exception as e:
        print(f"GitHub error: {e}")

    return None


async def _check_breach_hibp(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """HaveIBeenPwned: Check data breaches"""
    try:
        url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
        headers = {"User-Agent": "TraceNova/1.0"}

        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as response:
            if response.status == 200:
                breaches = await response.json()
                if breaches and len(breaches) > 0:
                    breach_names = [b.get("Name") for b in breaches]
                    return {
                        "found": True,
                        "source": "Data Breaches (HIBP)",
                        "source_url": "https://haveibeenpwned.com",
                        "icon": "⚠️",
                        "warning": "⚠️ FOUND IN BREACHES",
                        "description": f"Found in {len(breaches)} breach(es)",
                        "breaches": breach_names,
                        "type": "security_alert",
                        "priority": 95
                    }
            elif response.status == 404:
                return None

    except Exception as e:
        print(f"HIBP error: {e}")

    return None


async def _verify_email_zerobounce(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """Email verification via ZeroBounce"""
    try:
        url = f"https://api.zerobounce.net/v2/validate?email={email}&api_key=free_api"

        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as response:
            if response.status == 200:
                data = await response.json()
                status = data.get("status")

                if status in ["valid", "catch-all"]:
                    return {
                        "found": True,
                        "source": "Email Verification",
                        "icon": "✅",
                        "description": f"Email is valid ({status})",
                        "type": "verification",
                        "priority": 70
                    }

    except Exception as e:
        print(f"ZeroBounce error: {e}")

    return None


async def _search_pastebin_real(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """Search Pastebin for email mentions"""
    try:
        url = f"https://www.google.com/search?q=site%3Apastebin.com+{quote(email)}"

        return {
            "found": True,
            "source": "Pastebin/Leaks",
            "source_url": url,
            "icon": "📝",
            "description": f"Search Pastebin for '{email}' leaks",
            "note": "Often contains exposed credentials",
            "type": "alternative_search",
            "priority": 60
        }

    except Exception as e:
        print(f"Pastebin search error: {e}")
        return None


async def _search_github_gists(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """Search GitHub Gists for email"""
    try:
        url = f"https://api.github.com/search/code?q={email}+in:file&per_page=5"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "TraceNova/1.0"}

        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("total_count", 0) > 0:
                    return {
                        "found": True,
                        "source": "GitHub Gists/Code",
                        "source_url": f"https://github.com/search?q={quote(email)}",
                        "icon": "📄",
                        "description": f"Found {data.get('total_count')} code snippets with this email",
                        "type": "code_leak",
                        "priority": 85
                    }

    except Exception as e:
        print(f"GitHub gists error: {e}")

    return None


async def _search_shodan(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """Shodan: Search internet devices/services"""
    try:
        api_key = os.getenv("SHODAN_API_KEY")
        if not api_key:
            return None

        url = f"https://api.shodan.io/shodan/host/search?query={quote(email)}&key={api_key}"

        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("total", 0) > 0:
                    return {
                        "found": True,
                        "source": "Shodan",
                        "source_url": f"https://www.shodan.io",
                        "icon": "🔍",
                        "description": f"Found {data.get('total')} results on Shodan",
                        "type": "iot_search",
                        "priority": 80
                    }

    except Exception as e:
        print(f"Shodan error: {e}")

    return None


async def _search_rapid7(session: aiohttp.ClientSession, email: str) -> Optional[Dict]:
    """Rapid7: Search for email in public exploits"""
    try:
        url = f"https://api.rapid7.com/exposures/search?query={quote(email)}"
        headers = {"User-Agent": "TraceNova/1.0"}

        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("results", []):
                    return {
                        "found": True,
                        "source": "Rapid7/Project Sonar",
                        "source_url": "https://www.rapid7.com",
                        "icon": "🛡️",
                        "description": f"Found in Rapid7 exposure database",
                        "type": "exposure_db",
                        "priority": 90
                    }

    except Exception as e:
        print(f"Rapid7 error: {e}")

    return None


async def _search_google(email: str) -> Optional[Dict]:
    """Generate comprehensive Google search"""
    try:
        return {
            "found": True,
            "source": "Google Search",
            "source_url": f"https://www.google.com/search?q=%22{quote(email)}%22",
            "icon": "🔍",
            "description": f"Comprehensive web search for '{email}'",
            "note": "Find all public mentions across the web",
            "type": "web_search",
            "priority": 50
        }
    except Exception as e:
        print(f"Google search error: {e}")
        return None


async def _search_social_media(email: str) -> Optional[Dict]:
    """Search social media for email"""
    try:
        return {
            "found": True,
            "source": "Social Media Search",
            "source_url": f"https://www.google.com/search?q=%22{quote(email)}%22+site%3Atwitter.com+OR+site%3Areddit.com+OR+site%3Alinkedin.com",
            "icon": "📱",
            "description": f"Search Twitter, Reddit, LinkedIn for '{email}'",
            "note": "Often reveals real identities and connections",
            "type": "social_search",
            "priority": 55
        }
    except Exception as e:
        print(f"Social media search error: {e}")
        return None
