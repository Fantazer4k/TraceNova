"""Public username discovery with evidence-backed statuses.

Only structured API data can yield a verified public match. A profile link or an
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


def _x(data: Any, name: str) -> bool:
    user = data.get("data") if isinstance(data, dict) else None
    return isinstance(user, dict) and bool(user.get("id")) and _same(user.get("username"), name)


def _youtube(data: Any, name: str) -> bool:
    # channels.list filters by the exact requested handle before returning IDs.
    items = data.get("items") if isinstance(data, dict) else None
    return (isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict)
            and isinstance(items[0].get("id"), str) and bool(items[0]["id"]))


def _vk(data: Any, name: str) -> bool:
    profile = data.get("response") if isinstance(data, dict) else None
    return (isinstance(profile, dict) and profile.get("type") == "user"
            and type(profile.get("object_id")) is int and profile["object_id"] > 0)


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
    "x": {"url": "https://api.x.com/2/users/by/username/{name}", "profile": "https://x.com/{name}",
          "valid": _x, "credential": "X_BEARER_TOKEN"},
    "youtube": {"url": "https://www.googleapis.com/youtube/v3/channels?part=id&forHandle=%40{name}",
                "profile": "https://www.youtube.com/@{name}", "valid": _youtube,
                "credential": "YOUTUBE_API_KEY"},
    "vk": {"url": "https://api.vk.com/method/utils.resolveScreenName?v=5.199&screen_name={name}",
           "profile": "https://vk.com/{name}", "valid": _vk, "credential": "VK_SERVICE_TOKEN"},
}

# No reliable exact-username integration is configured for these platforms.
UNSUPPORTED_PLATFORMS = (
    "instagram", "tiktok", "facebook",
    "snapchat", "pinterest", "tumblr", "stackoverflow", "pastebin",
)


def _lookup_options(platform: str, config: Dict) -> Dict | None:
    headers = {"User-Agent": "TraceNova/1.0 (public profile lookup)", "Accept": "application/json"}
    options: Dict = {"headers": headers, "allow_redirects": False}
    credential = config.get("credential")
    token = os.getenv(credential, "").strip() if credential else ""
    if credential and not token:
        return None
    if platform == "youtube":
        headers["X-Goog-Api-Key"] = token
    elif platform == "x":
        headers["Authorization"] = "Bearer " + token
    elif platform == "vk":
        options["params"] = {"access_token": token}
    elif platform == "github" and os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    return options


async def _check_platform(session: aiohttp.ClientSession, sem: asyncio.Semaphore,
                          platform: str, config: Dict, name: str) -> Dict:
    encoded = quote(name, safe="")
    base = {"platform": platform, "username": name, "found": False}
    options = _lookup_options(platform, config)
    if options is None:
        return {**base, "status": "unavailable", "reason": "not_configured",
                "error": "Provider credentials are not configured"}
    try:
        async with sem:
            async with session.get(config["url"].format(name=encoded), **options) as response:
                if response.status == 404:
                    return {**base, "status": "not_found"}
                if response.status == 429 or (
                    response.status == 403 and response.headers.get("X-RateLimit-Remaining") == "0"
                ):
                    return {**base, "status": "rate_limited", "error": "Provider rate limit reached"}
                if response.status in (401, 403):
                    return {**base, "status": "unavailable", "error": "Access denied (HTTP %s)" % response.status}
                if response.status == 400 and platform == "bluesky":
                    return {**base, "status": "unavailable",
                            "error": "Bluesky did not resolve this default .bsky.social handle (HTTP 400). Not a confirmed match."}
                if response.status != 200:
                    return {**base, "status": "error", "error": "HTTP %s" % response.status}
                try:
                    payload = await response.json(content_type=None)
                except (ValueError, aiohttp.ClientError):
                    return {**base, "status": "error", "error": "Invalid API response"}
        if config["valid"](payload, name):
            return {**base, "status": "found", "found": True,
                    "profile_url": config["profile"].format(name=encoded)}
        # Some APIs return a JSON object for nonexistent users. Only a clearly
        # documented 'not found' payload can establish absence; otherwise unknown.
        if platform == "hackernews" and payload is None:
            return {**base, "status": "not_found"}
        if platform == "gitlab" and isinstance(payload, list) and not payload:
            return {**base, "status": "not_found"}
        if platform == "youtube" and isinstance(payload, dict) and payload.get("items") == []:
            return {**base, "status": "not_found"}
        if platform == "vk" and isinstance(payload, dict):
            profile = payload.get("response")
            if profile == [] or (isinstance(profile, dict) and profile.get("type") in
                                 {"group", "page", "event", "application"}):
                return {**base, "status": "not_found"}
        return {**base, "status": "unavailable", "error": "API did not confirm an exact handle"}
    except asyncio.TimeoutError:
        return {**base, "status": "timeout", "error": "Request timed out"}
    except aiohttp.ClientError as exc:
        return {**base, "status": "error", "error": type(exc).__name__}
    except Exception as exc:
        return {**base, "status": "error", "error": type(exc).__name__}


async def _resolve_telegram(name: str, api_id: int, api_hash: str, token: str) -> str:
    from telethon import TelegramClient, errors, functions, types
    from telethon.sessions import MemorySession

    client = TelegramClient(MemorySession(), api_id, api_hash, connection_retries=0,
                            request_retries=0, flood_sleep_threshold=0, receive_updates=False)
    try:
        await client.start(bot_token=token)
        try:
            result = await client(functions.contacts.ResolveUsernameRequest(name))
        except errors.UsernameNotOccupiedError:
            return "not_found"
        except errors.UsernameInvalidError:
            return "not_found"
        if isinstance(result.peer, types.PeerUser):
            return "found" if any(
                isinstance(user, types.User) and user.id == result.peer.user_id and not user.deleted
                for user in result.users
            ) else "unavailable"
        return "not_found" if isinstance(result.peer, (types.PeerChat, types.PeerChannel)) else "unavailable"
    except errors.FloodWaitError:
        return "rate_limited"
    except errors.RPCError:
        return "unavailable"
    finally:
        await client.disconnect()


async def _check_telegram(sem: asyncio.Semaphore, name: str) -> Dict:
    base = {"platform": "telegram", "username": name, "found": False}
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not (api_id.isascii() and api_id.isdecimal() and api_hash and token):
        return {**base, "status": "unavailable", "reason": "not_configured",
                "error": "Provider credentials are not configured"}
    try:
        async with sem:
            status = await asyncio.wait_for(
                _resolve_telegram(name, int(api_id), api_hash, token), REQUEST_TIMEOUT)
    except ImportError:
        return {**base, "status": "unavailable", "reason": "not_configured",
                "error": "Optional Telethon dependency is not installed"}
    except asyncio.TimeoutError:
        return {**base, "status": "timeout", "error": "Request timed out"}
    except (OSError, ValueError):
        return {**base, "status": "unavailable", "error": "Telegram lookup failed"}
    if status == "found":
        return {**base, "status": status, "found": True, "profile_url": "https://t.me/" + quote(name, safe="")}
    return {**base, "status": status}


async def search_username(username: str) -> Dict:
    username = (username or "").strip()
    if not USERNAME_RE.fullmatch(username):
        return {"query_type": "username", "status": "error", "username": username,
                "message": "Username must contain 2–39 letters, digits, underscores, dots or hyphens."}
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        lookups = [
            _check_platform(session, sem, platform, cfg, username)
            for platform, cfg in PLATFORMS.items()
        ]
        results: List[Dict] = await asyncio.gather(*lookups, _check_telegram(sem, username))
    found = [item for item in results if item["status"] == "found"]
    failed = [item for item in results if item["status"] in ("error", "timeout", "unavailable", "rate_limited")]
    unsupported = [
        {"platform": platform, "username": username, "status": "unavailable",
         "reason": "unsupported", "found": False}
        for platform in UNSUPPORTED_PLATFORMS
    ]
    message = "Verified %d public profile(s)." % len(found)
    return {
        "query_type": "username",
        "status": "success" if found else ("partial_failure" if failed else "no_profiles_found"),
        "username": username,
        "profiles_found": len(found),
        "profiles": found,
        "sources": results + unsupported,
        "manual_sources": [],
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
    options = _lookup_options(platform, cfg)
    if options is None:
        return {"status": "unavailable"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(cfg["url"].format(name=quote(username, safe="")), **options) as response:
                if response.status == 404:
                    return {"status": "not_found"}
                if response.status != 200:
                    return {"status": "unavailable", "http_status": response.status}
                return await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return {"status": "error", "error": "Lookup failed"}
