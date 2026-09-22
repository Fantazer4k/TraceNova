"""
Username search service
Find public profiles across multiple platforms
"""

import asyncio
import os
from typing import Dict, Optional

import aiohttp


PLATFORMS = {
    "github": {
        "url": "https://api.github.com/users/{username}",
        "profile_url": "https://github.com/{username}",
    },
    "twitter": {
        "url": "https://twitter.com/{username}",
        "profile_url": "https://twitter.com/{username}",
        "method": "web",
    },
    "reddit": {
        "url": "https://www.reddit.com/user/{username}/about.json",
        "profile_url": "https://reddit.com/u/{username}",
    },
    "gitlab": {
        "url": "https://gitlab.com/api/v4/users?username={username}",
        "profile_url": "https://gitlab.com/{username}",
    },
    "stackoverflow": {
        "url": "https://stackoverflow.com/users/{username}",
        "profile_url": "https://stackoverflow.com/users/{username}",
        "method": "web",
    },
    "keybase": {
        "url": "https://keybase.io/api/1.0/user/lookup?username={username}",
        "profile_url": "https://keybase.io/{username}",
    },
    "pastebin": {
        "url": "https://pastebin.com/u/{username}",
        "profile_url": "https://pastebin.com/u/{username}",
        "method": "web",
    },
    "instagram": {
        "url": "https://www.instagram.com/{username}/?__a=1",
        "profile_url": "https://www.instagram.com/{username}",
        "method": "web",
    },
    "tiktok": {
        "url": "https://www.tiktok.com/@{username}",
        "profile_url": "https://www.tiktok.com/@{username}",
        "method": "web",
    },
    "telegram": {
        "url": "https://t.me/{username}",
        "profile_url": "https://t.me/{username}",
        "method": "web",
    },
}

MANUAL_PLATFORMS = {
    "instagram",
    "tiktok",
    "telegram",
    "twitter",
    "stackoverflow",
    "pastebin",
}


async def search_username(username: str) -> Dict:
    """Search for a username across supported platforms."""

    username = username.strip() if username else ""

    if len(username) < 2:
        return {
            "status": "error",
            "message": "Username too short (minimum 2 characters)",
            "username": username,
        }

    found_profiles = []
    manual_sources = []

    async with aiohttp.ClientSession() as session:
        tasks = []

        for platform, config in PLATFORMS.items():
            if platform in MANUAL_PLATFORMS:
                manual_sources.append(
                    {
                        "platform": platform,
                        "username": username,
                        "profile_url": config["profile_url"].format(
                            username=username
                        ),
                        "status": "manual",
                        "message": (
                            "Manual verification required; "
                            "HTTP status alone is not treated as proof."
                        ),
                    }
                )
                continue

            tasks.append(
                _search_platform(session, platform, username, config)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, dict) and result.get("found") is True:
                found_profiles.append(result)

    total_verified = len(found_profiles)

    return {
        "status": "success" if total_verified else "no_profiles_found",
        "username": username,
        "profiles_found": total_verified,
        "profiles": found_profiles,
        "manual_sources": manual_sources,
        "message": (
            f"Found {total_verified} verified profile(s) "
            f"with username '{username}'"
        ),
    }


async def _search_platform(
    session: aiohttp.ClientSession,
    platform: str,
    username: str,
    config: Dict,
) -> Optional[Dict]:
    """Search for a username on an API-backed platform."""

    try:
        url = config["url"].format(username=username)
        profile_url = config["profile_url"].format(username=username)

        headers = {"User-Agent": "TraceNova/1.0"}

        if platform == "github":
            headers["Accept"] = "application/vnd.github+json"
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                headers["Authorization"] = f"Bearer {github_token}"

        timeout = aiohttp.ClientTimeout(total=5)

        async with session.get(
            url,
            headers=headers,
            timeout=timeout,
        ) as response:
            if response.status == 404:
                return None

            if response.status != 200:
                return None

            try:
                data = await response.json()
            except (aiohttp.ContentTypeError, ValueError):
                return None

            if _is_valid_profile(platform, data):
                return {
                    "platform": platform,
                    "username": username,
                    "profile_url": profile_url,
                    "found": True,
                    "status": "verified",
                }

            return None

    except (asyncio.TimeoutError, aiohttp.ClientError):
        return None
    except Exception:
        return None


def _is_valid_profile(platform: str, data: Dict) -> bool:
    """Check whether an API response indicates a valid profile."""

    if not data:
        return False

    if platform == "github":
        return (
            isinstance(data, dict)
            and "login" in data
            and "id" in data
        )

    if platform == "reddit":
        return (
            isinstance(data, dict)
            and isinstance(data.get("data"), dict)
            and "name" in data["data"]
        )

    if platform == "gitlab":
        return isinstance(data, list) and len(data) > 0

    if platform == "keybase":
        return (
            isinstance(data, dict)
            and data.get("them") is not None
        )

    return False


async def get_username_info(username: str, platform: str) -> Dict:
    """Get detailed information about a username on a supported platform."""

    if platform not in PLATFORMS:
        return {"error": "Platform not supported"}

    config = PLATFORMS[platform]

    if platform in MANUAL_PLATFORMS:
        return {
            "error": "Manual verification required",
            "profile_url": config["profile_url"].format(username=username),
        }

    url = config["url"].format(username=username)
    headers = {"User-Agent": "TraceNova/1.0"}

    if platform == "github":
        headers["Accept"] = "application/vnd.github+json"
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

    try:
        timeout = aiohttp.ClientTimeout(total=5)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    return {
                        "error": "Profile not found",
                        "status_code": response.status,
                    }

                try:
                    return await response.json()
                except (aiohttp.ContentTypeError, ValueError):
                    return {"error": "Invalid response from platform"}

    except asyncio.TimeoutError:
        return {"error": "request_timeout"}
    except aiohttp.ClientError:
        return {"error": "request_failed"}
    except Exception:
        return {"error": "request_failed"}
