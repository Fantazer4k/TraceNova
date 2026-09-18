"""
Username search service
Find public profiles across multiple platforms
"""

import asyncio
import aiohttp
import os
from typing import Dict, List, Optional

# List of platforms to search with their API endpoints
PLATFORMS = {
    "github": {
        "url": "https://api.github.com/users/{username}",
        "profile_url": "https://github.com/{username}",
        "field": "login"
    },
    "twitter": {
        "url": "https://twitter.com/{username}",
        "profile_url": "https://twitter.com/{username}",
        "method": "web"  # Twitter requires scraping or paid API
    },
    "reddit": {
        "url": "https://www.reddit.com/user/{username}/about.json",
        "profile_url": "https://reddit.com/u/{username}",
        "field": "name"
    },
    "gitlab": {
        "url": "https://gitlab.com/api/v4/users?username={username}",
        "profile_url": "https://gitlab.com/{username}",
        "field": "username"
    },
    "stackoverflow": {
        "url": "https://stackoverflow.com/users/{username}",
        "profile_url": "https://stackoverflow.com/users/{username}",
        "method": "web"
    },
    "keybase": {
        "url": "https://keybase.io/api/1.0/user/lookup?username={username}",
        "profile_url": "https://keybase.io/{username}",
        "field": "them"
    },
    "pastebin": {
        "url": "https://pastebin.com/u/{username}",
        "profile_url": "https://pastebin.com/u/{username}",
        "method": "web"
    },
    "instagram": {
        "url": "https://www.instagram.com/{username}/?__a=1",
        "profile_url": "https://www.instagram.com/{username}",
        "field": "user"
    },
    "tiktok": {
        "url": "https://api.tiktok.com/v1/user/info/?unique_id={username}",
        "profile_url": "https://www.tiktok.com/@{username}",
        "method": "api"
    },
    "telegram": {
        "url": "https://t.me/{username}",
        "profile_url": "https://t.me/{username}",
        "method": "web"
    }
}


async def search_username(username: str) -> Dict:
    """
    Search for username across multiple platforms

    Args:
        username: Username to search for

    Returns:
        Dict with found profiles
    """

    if not username or len(username) < 2:
        return {
            "status": "error",
            "message": "Username too short (minimum 2 characters)",
            "username": username
        }

    found_profiles = []

    async with aiohttp.ClientSession() as session:
        tasks = []

        for platform, config in PLATFORMS.items():
            task = _search_platform(session, platform, username, config)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if result and isinstance(result, dict):
                found_profiles.append(result)

    return {
        "status": "success" if found_profiles else "no_profiles_found",
        "username": username,
        "profiles_found": len(found_profiles),
        "profiles": found_profiles,
        "message": f"Found {len(found_profiles)} profile(s) with username '{username}'"
    }


async def _search_platform(session: aiohttp.ClientSession, platform: str, username: str, config: Dict) -> Optional[Dict]:
    """
    Search for username on a specific platform
    """
    try:
        url = config["url"].format(username=username)
        profile_url = config["profile_url"].format(username=username)

        headers = {
            "User-Agent": "TraceNova/1.0"
        }

        # Add GitHub token if available (for higher rate limits)
        # You can set GITHUB_TOKEN env var for better rate limiting
        if platform == "github":
            headers["Accept"] = "application/vnd.github.v3+json"
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                headers["Authorization"] = f"Bearer {github_token}"

        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
            # Some platforms do not expose a stable public endpoint here.
        # A successful HTTP response is not enough to prove that a profile exists.
        if platform in ["instagram", "tiktok", "telegram", "twitter", "stackoverflow", "pastebin"]:
            return {
                "platform": platform,
                "username": username,
                "profile_url": profile_url,
                "found": False,
                "status": "manual",
                "message": "Manual verification required; HTTP status alone is not treated as proof."
            }

        # For API-based platforms
            if response.status == 200:
                try:
                    data = await response.json()

                    # Check if user exists based on platform
                    if _is_valid_profile(platform, data):
                        return {
                            "platform": platform,
                            "username": username,
                            "profile_url": profile_url,
                            "found": True,
                            "status": "verified"
                        }
                except Exception:
                    return None
            elif response.status == 404:
                return None
            else:
                return None

    except asyncio.TimeoutError:
        return {
            "platform": platform,
            "username": username,
            "found": False,
            "error": "timeout"
        }
    except Exception:
        return {
            "platform": platform,
            "username": username,
            "found": False,
            "error": "request_failed"
        }


def _is_valid_profile(platform: str, data: Dict) -> bool:
    """
    Check if the API response indicates a valid profile
    """
    if not data:
        return False

    if platform == "github":
        return "login" in data and "id" in data
    elif platform == "reddit":
        return "data" in data and "name" in data.get("data", {})
    elif platform == "gitlab":
        return isinstance(data, list) and len(data) > 0
    elif platform == "keybase":
        return "them" in data and data["them"] is not None
    elif platform == "instagram":
        return "user" in data and "id" in data.get("user", {})
    elif platform == "tiktok":
        return "data" in data and "user" in data.get("data", {})
    elif platform == "telegram":
        return isinstance(data, dict) and len(data) > 0

    return True


async def get_username_info(username: str, platform: str) -> Dict:
    """
    Get detailed info about username on specific platform
    """
    if platform not in PLATFORMS:
        return {"error": "Platform not supported"}

    config = PLATFORMS[platform]
    url = config["url"].format(username=username)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Profile not found (status {response.status})"}
    except Exception:
        return {"error": "request_failed"}
