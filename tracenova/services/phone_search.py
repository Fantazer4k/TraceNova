"""
Phone-number search services.

Only confirmed API/database results are reported as found. Inferred metadata
and manual lookup links are labelled separately.
"""

import asyncio
import aiohttp
import re
from typing import Dict, Optional
from urllib.parse import quote


async def search_phone(phone: str) -> Dict:
    """Search public sources for a phone number."""
    phone_clean = re.sub(r"[^\d+]", "", phone or "")

    if not phone_clean or len(re.sub(r"\D", "", phone_clean)) < 10:
        return {
            "status": "error",
            "phone": phone,
            "message": "Please enter a valid phone number (10+ digits)",
        }

    found_sources = []
    info_sources = []

    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks = [
                _get_phone_validation(session, phone_clean),
                _get_carrier_info(session, phone_clean),
                _check_breach_phone(session, phone_clean),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, dict):
                    if result.get("found"):
                        found_sources.append(result)
                    elif result.get("status") == "info":
                        info_sources.append(result)

    except Exception:
        return {
            "status": "error",
            "phone": phone,
            "message": "Unable to complete the phone search.",
        }

    info_sources.extend([
        _get_format_info(phone_clean),
        _get_location_info(phone_clean),
    ])

    manual_sources = [
        _manual_google_search(phone_clean),
        _manual_truecaller_search(phone_clean),
    ]

    found_sources.sort(key=lambda x: x.get("priority", 0), reverse=True)

    if not found_sources:
        return {
            "status": "info",
            "phone": phone,
            "found_in_sources": [],
            "info_sources": info_sources,
            "manual_sources": manual_sources,
            "total_sources": 0,
            "summary": "No confirmed matches found. Inferred information and manual searches are available.",
        }

    return {
        "status": "success",
        "phone": phone,
        "found_in_sources": found_sources,
        "info_sources": info_sources,
        "manual_sources": manual_sources,
        "total_sources": len(found_sources),
        "summary": f"Found {len(found_sources)} confirmed source(s)",
    }


async def _get_phone_validation(session: aiohttp.ClientSession, phone: str) -> Optional[Dict]:
    try:
        url = f"https://api.numverify.com/validate?number={quote(phone)}&access_key=free"

        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("valid") or data.get("is_valid"):
                    return {
                        "found": True,
                        "source": "Phone Validation",
                        "icon": "✅",
                        "description": "Phone number was validated by the configured service.",
                        "details": {
                            "Number": phone,
                            "Valid": "Yes",
                            "Country": data.get("country_name", "Unknown"),
                            "Country Code": data.get("country_code", "N/A"),
                            "Type": data.get("number_type", "Unknown"),
                            "Carrier": data.get("carrier", "Unknown"),
                        },
                        "type": "validation",
                        "priority": 100,
                    }
    except Exception:
        return None
    return None


async def _get_carrier_info(session: aiohttp.ClientSession, phone: str) -> Optional[Dict]:
    try:
        url = f"https://api.abstract-api.com/v1/phone-validation/?api_key=free&phone={quote(phone)}"

        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                if data.get("valid"):
                    return {
                        "found": True,
                        "source": "Carrier Information",
                        "icon": "📞",
                        "description": "Carrier information was returned by the configured service.",
                        "details": {
                            "Carrier": data.get("carrier", "Unknown"),
                            "Type": data.get("type", "Unknown"),
                            "Country": data.get("country", "Unknown"),
                            "Timezone": data.get("timezone", "Unknown"),
                        },
                        "type": "carrier",
                        "priority": 95,
                    }
    except Exception:
        return None
    return None


async def _check_breach_phone(session: aiohttp.ClientSession, phone: str) -> Optional[Dict]:
    try:
        url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{quote(phone, safe='')}"
        headers = {"User-Agent": "TraceNova/1.0"}

        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                breaches = await response.json()
                if breaches:
                    return {
                        "found": True,
                        "source": "Data Breaches",
                        "source_url": "https://haveibeenpwned.com",
                        "icon": "⚠️",
                        "warning": "FOUND IN BREACHES",
                        "description": f"Found in {len(breaches)} data breach(es)",
                        "breaches": [b.get("Name") for b in breaches],
                        "type": "security_alert",
                        "priority": 120,
                    }
            elif response.status == 404:
                return None
    except Exception:
        return None
    return None


def _get_format_info(phone: str) -> Dict:
    digits = re.sub(r"\D", "", phone)
    return {
        "status": "info",
        "source": "Number Format",
        "icon": "📱",
        "description": "Format information inferred from the supplied number.",
        "details": {
            "Format": phone,
            "Digits": len(digits),
            "International": "Yes" if phone.startswith("+") else "No",
        },
        "type": "format_info",
        "priority": 20,
    }


def _get_location_info(phone: str) -> Dict:
    country_codes = {
        "+1": "USA/Canada",
        "+44": "United Kingdom",
        "+33": "France",
        "+49": "Germany",
        "+39": "Italy",
        "+34": "Spain",
        "+31": "Netherlands",
        "+38": "Europe",
        "+86": "China",
        "+91": "India",
        "+61": "Australia",
    }

    country = "Unknown"
    for code, name in sorted(country_codes.items(), key=lambda item: len(item[0]), reverse=True):
        if phone.startswith(code):
            country = name
            break

    return {
        "status": "info",
        "source": "Country Code",
        "icon": "🌍",
        "description": f"Country-level information inferred from the country calling code: {country}.",
        "details": {
            "Country": country,
            "Precision": "Country-level only",
        },
        "type": "inferred_location",
        "priority": 15,
    }


def _manual_google_search(phone: str) -> Dict:
    return {
        "status": "manual",
        "source": "Google Search",
        "source_url": f"https://www.google.com/search?q=%22{quote(phone)}%22",
        "icon": "🔍",
        "description": "Open a manual web search for public mentions.",
        "type": "web_search",
        "priority": 50,
    }


def _manual_truecaller_search(phone: str) -> Dict:
    return {
        "status": "manual",
        "source": "Truecaller",
        "source_url": f"https://www.truecaller.com/search?q={quote(phone)}",
        "icon": "☎️",
        "description": "Open a manual Truecaller search. TraceNova has not confirmed a match.",
        "type": "caller_id",
        "priority": 45,
    }
