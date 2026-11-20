"""Public username discovery with evidence-backed statuses.

Only public, structured APIs can yield a verified match. A profile link or an
HTTP 200 response from a social site is not enough to claim an account exists.
No login, scraping around access controls, or private data collection.
"""
import asyncio
import os
import re
from typing import Any, Dict, List
from urllib.parse import quote

import aiohttp

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{2,39}$")
REQUEST_TIMEOUT = 7
MAX_CONCURRENCY = 5


def _same(actual: Any, wanted: str) -> bool:
    return isinstance(actual, str) and actual.casefold() == wanted.casefold()


def _github(data: Any, name: str) -> bool:
    return isinstance(data, dict) and isinstance(data.get("id"), int) and _same(data.get("login"), name)


def _gitlab(data: Any, name: str) -> bool:
    return isinstance(data, list) and any(
        isinstance(user, dict) and _same(user.get("username"), name) for user in data
    )


def _reddit(data: Any, name: str) -> bool:
    return (isinstance(data, dict) and isinstance(data.get("data"), dict)
            and _same(data["data"].get("name"), name))


def _keybase(data: Any, name: str) -> bool:
    if not isinstance(data, dict) or (data.get("status") or {}).get("code") != 0:
        return False
    users = data.get("them")
    if isinstance(users, dict):
        users = [users]
    if not isinstance(users, list):
        return False
    return any(isinstance(u, dict) and _same(
        (u.get("basics") or {}).get("username"), name) for u in users)


def _hackernews(data: Any, name: str) -> bool:
    return isinstance(data, dict) and _same(data.get("id"), name)


def _devto(data: Any, name: str) -> bool:
    return isinstance(data, dict) and _same(data.get("username"), name)


def _codeberg(data: Any, name: str) -> bool:
    return isinstance(data, dict) and _same(data.get("login"), name)


def _bluesky(data: Any, name: str) -> bool:
    return isinstance(data, dict) and _same(data.get("handle"), name + ".bsky.social") and bool(data.get("did"))


PLATFORMS = {
    "github": {"url": "https://api.github.com/users/{name}", "profile": "https://github.com/{name}", "valid": _github},
    "gitlab": {"url": "https://gitlab.com/api/v4/users?username={name}", "profile": "https://gitlab.com/{name}", "valid": _gitlab},
    "reddit": {"url": "https://www.reddit.com/user/{name}/about.json", "profile": "https://www.reddit.com/user/{name}", "valid": _reddit},
    "keybase": {"url": "https://keybase.io/_/api/1.0/user/lookup.json?username={name}", "profile": "https://keybase.io/{name}", "valid": _keybase},
    "hackernews": {"url": "https://hacker-news.firebaseio.com/v0/user/{name}.json", "profile": "https://news.ycombinator.com/user?id={name}", "valid": _hackernews},
    "devto": {"url": "https://dev.to/api/users/by_username?url={name}", "profile": "https://dev.to/{name}", "valid": _devto},
    "codeberg": {"url": "https://codeberg.org/api/v1/users/{name}", "profile": "https://codeberg.org/{name}", "valid": _codeberg},
    # Public Bluesky AppView: confirms only the default username.bsky.social handle.
    "bluesky": {"url": "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={name}.bsky.social",
                "profile": "https://bsky.app/profile/{name}.bsky.social", "valid": _bluesky},
}

# No dependable anonymous API for arbitrary profile existence on these services.
# A candidate URL is offered for the user to inspect; it is NEVER a confirmed hit.
MANUAL_PLATFORMS = {
    "instagram": "https://www.instagram.com/{name}/",
    "tiktok": "https://www.tiktok.com/@{name}",
    "x": "https://x.com/{name}",
    "telegram": "https://t.me/{name}",
    "snapchat": "https://www.snapchat.com/add/{name}",
    "youtube": "https://www.youtube.com/@{name}",
    "pinterest": "https://www.pinterest.com/{name}/",
    "tumblr": "https://{name}.tumblr.com/",
    "stackoverflow": "https://stackoverflow.com/users/?tab=users&search={name}",
    "pastebin": "https://pastebin.com/u/{name}",
}


async def _check_platform(session: aiohttp.ClientSession, sem: asyncio.Semaphore,
                          platform: str, config: Dict, name: str) -> Dict:
    encoded = quote(name, safe="")
    base = {"platform": platform, "username": name,
            "profile_url": config["profile"].format(name=encoded), "found": False}
    headers = {"User-Agent": "TraceNova/1.0 (public profile lookup)", "Accept": "application/json"}
    if platform == "github" and os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    try:
        async with sem:
            async with session.get(config["url"].format(name=encoded), headers=headers,
                                   allow_redirects=False) as response:
                if response.status == 404:
                    return {**base, "status": "not_found"}
                if response.status in (401, 403, 429):
                    return {**base, "status": "unavailable", "error": "Blocked or rate limited (HTTP %s)" % response.status}
                if response.status != 200:
                    return {**base, "status": "error", "error": "HTTP %s" % response.status}
                try:
                    payload = await response.json(content_type=None)
                except (ValueError, aiohttp.ClientError):
                    return {**base, "status": "error", "error": "Invalid API response"}
        if config["valid"](payload, name):
            return {**base, "status": "found", "found": True}
        # Some APIs return a JSON object for nonexistent users. Only a clearly
        # documented 'not found' payload can establish absence; otherwise unknown.
        if platform == "hackernews" and payload is None:
            return {**base, "status": "not_found"}
        if platform == "gitlab" and isinstance(payload, list) and not payload:
            return {**base, "status": "not_found"}
        return {**base, "status": "unavailable", "error": "API did not confirm an exact handle"}
    except asyncio.TimeoutError:
        return {**base, "status": "timeout", "error": "Request timed out"}
    except aiohttp.ClientError as exc:
        return {**base, "status": "error", "error": type(exc).__name__}
    except Exception as exc:
        return {**base, "status": "error", "error": type(exc).__name__}


async def search_username(username: str) -> Dict:
    username = (username or "").strip()
    if not USERNAME_RE.fullmatch(username):
        return {"query_type": "username", "status": "error", "username": username,
                "message": "Username must contain 2–39 letters, digits, underscores, dots or hyphens."}
    encoded = quote(username, safe="")
    manual = [
        {"platform": platform, "username": username, "status": "manual",
         "profile_url": template.format(name=encoded),
         "message": "Candidate link only — account existence not verified."}
        for platform, template in MANUAL_PLATFORMS.items()
    ]
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        results: List[Dict] = await asyncio.gather(*(
            _check_platform(session, sem, platform, cfg, username)
            for platform, cfg in PLATFORMS.items()
        ))
    found = [item for item in results if item["status"] == "found"]
    failed = [item for item in results if item["status"] in ("error", "timeout", "unavailable")]
    message = ("Verified %d public profile(s) on %d API-backed platforms. "
               "%d platform(s) could not be confirmed; %d additional candidate links "
               "require manual verification." % (len(found), len(results), len(failed), len(manual)))
    return {
        "query_type": "username",
        "status": "success" if found else ("partial_failure" if failed else "no_profiles_found"),
        "username": username,
        "profiles_found": len(found),
        "profiles": found,
        "sources": results,
        "manual_sources": manual,
        "message": message,
    }


async def get_username_info(username: str, platform: str) -> Dict:
    """Fetch public structured API data for a supported platform."""
    if not USERNAME_RE.fullmatch(username or ""):
        return {"error": "Invalid username"}
    cfg = PLATFORMS.get(platform)
    if not cfg:
        return {"error": "Unsupported platform"}
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    headers = {"User-Agent": "TraceNova/1.0"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(cfg["url"].format(name=quote(username, safe="")),
                                   headers=headers, allow_redirects=False) as response:
                if response.status == 404:
                    return {"status": "not_found"}
                if response.status != 200:
                    return {"status": "unavailable", "http_status": response.status}
                return await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return {"status": "error", "error": "Lookup failed"}
