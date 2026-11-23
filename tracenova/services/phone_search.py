"""Offline phone-number metadata; never mistake validation for public discovery.

No phone-number breach lookups: the HIBP breachedaccount API is for emails.
External search links are explicitly manual and are not evidence of a match.
"""
import re
from typing import Dict
from urllib.parse import quote

try:
    import phonenumbers
    from phonenumbers import PhoneNumberFormat, PhoneNumberType, carrier, geocoder
except ImportError:
    phonenumbers = None

_TYPE_NAMES = {
    "MOBILE": "Mobile", "FIXED_LINE": "Fixed line",
    "FIXED_LINE_OR_MOBILE": "Fixed line or mobile",
    "TOLL_FREE": "Toll free", "PREMIUM_RATE": "Premium rate",
    "VOIP": "VoIP", "PERSONAL_NUMBER": "Personal number",
    "UNKNOWN": "Unknown",
}


def _validation(parsed) -> Dict:
    valid = phonenumbers.is_valid_number(parsed)
    ntype = _TYPE_NAMES.get(PhoneNumberType.to_string(phonenumbers.number_type(parsed)), "Unknown")
    details = {
        "Valid numbering-plan assignment": "Yes" if valid else "No",
        "Plausible number length": "Yes" if phonenumbers.is_possible_number(parsed) else "No",
        "International": phonenumbers.format_number(parsed, PhoneNumberFormat.INTERNATIONAL),
        "Numbering-plan region": geocoder.description_for_number(parsed, "en") or "Unknown",
        "Line type": ntype,
        "Original carrier (prefix metadata)": carrier.name_for_number(parsed, "en") or "Unknown",
    }
    return {
        "found": False, "status": "info", "source": "Phone Validation",
        "icon": "✓" if valid else "!", "type": "validation",
        "description": ("Number matches an assigned numbering plan; this does NOT verify "
                        "an active subscriber or public occurrence."
                        if valid else "Number does not match an assigned numbering plan."),
        "details": details,
    }


async def search_phone(phone: str) -> Dict:
    """Return technical metadata and clearly identified manual search links."""
    original = (phone or "").strip()
    clean = re.sub(r"[^\d+]", "", original)
    digits = re.sub(r"\D", "", clean)
    if not clean.startswith("+") or not 7 <= len(digits) <= 15:
        return {"query_type": "phone", "status": "error", "phone": original,
                "message": "Enter a plus sign followed by the country calling code and phone number (7–15 digits total)."}
    if phonenumbers is None:
        return {"query_type": "phone", "status": "error", "phone": original,
                "message": "Phone metadata is unavailable: install the phonenumbers dependency."}
    try:
        parsed = phonenumbers.parse(clean, None)
    except phonenumbers.NumberParseException:
        return {"query_type": "phone", "status": "error", "phone": original,
                "message": "The phone number could not be parsed."}
    international = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    info_sources = [
        _validation(parsed),
        {
            "status": "info", "source": "Number Format", "icon": "📱",
            "type": "format_info",
            "description": "Technical metadata inferred from the supplied number.",
            "details": {
                "E.164 format": international,
                "Country calling code": "+" + str(parsed.country_code),
                "Region code": phonenumbers.region_code_for_number(parsed) or "Unknown",
            },
        },
    ]
    manual_sources = [
        {
            "status": "manual", "source": "Google Search",
            "source_url": "https://www.google.com/search?q=%22" + quote(international, safe="") + "%22",
            "icon": "🔎", "type": "web_search",
            "description": "Open public-web mentions manually; no match has been verified.",
        },
        {
            "status": "manual", "source": "Truecaller",
            "source_url": "https://www.truecaller.com/",
            "icon": "☎", "type": "caller_id",
            "description": "Manual lookup only, subject to Truecaller's terms and access requirements.",
        },
    ]
    return {
        "query_type": "phone",
        "status": "info",
        "phone": original,
        "found_in_sources": [],
        "info_sources": info_sources,
        "manual_sources": manual_sources,
        "total_sources": 0,
        "summary": "TraceNova checked the numbering plan. Public searches are available as external links.",
    }
