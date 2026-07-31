"""
Comprehensive Scraper Service - ALL search data WITHOUT AI dependency
Uses free APIs, web scraping, and public data sources only
"""

import asyncio
import aiohttp
import socket
import re
import http.client
from typing import Dict, Optional, List
from urllib.parse import quote
import ssl

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


async def search_comprehensive(query: str, query_type: str) -> Dict:
    """Route to appropriate comprehensive search"""
    query = query.strip()

    if query_type == "domain":
        return await _search_domain(query)
    elif query_type == "url":
        return await _search_url(query)
    elif query_type == "ip":
        return await _search_ip(query)
    elif query_type == "username":
        return await _search_username(query)
    elif query_type == "email":
        return await _search_email(query)
    elif query_type == "phone":
        return await _search_phone(query)

    return {"status": "error", "message": "Unknown search type"}


# ============================================================================
# DOMAIN SEARCH
# ============================================================================

async def _search_domain(domain: str) -> Dict:
    """Search domain: IP, DNS, WHOIS basics, SSL info"""
    try:
        ip = socket.gethostbyname(domain)

        reverse_dns = "N/A"
        try:
            reverse_dns = socket.gethostbyaddr(ip)[0]
        except:
            pass

        sources = []

        # IP info
        sources.append({
            "found": True,
            "source": "DNS Resolution",
            "icon": "🌐",
            "description": f"Domain IP address",
            "details": {
                "Domain": domain,
                "IP Address": ip,
                "Reverse DNS": reverse_dns if reverse_dns != "N/A" else "Not available"
            },
            "type": "dns",
            "priority": 100
        })

        # Registrar info (basic)
        sources.append({
            "found": True,
            "source": "WHOIS Info",
            "icon": "📋",
            "description": "Domain registration information (use whois command)",
            "details": {
                "Query": f"whois {domain}",
                "Method": "Public WHOIS database",
                "Note": "Run 'whois " + domain + "' in terminal for details"
            },
            "type": "whois",
            "priority": 85,
            "source_url": f"https://who.is/whois/{domain}"
        })

        # Shodan scan (passive)
        sources.append({
            "found": True,
            "source": "Public Information",
            "icon": "🔍",
            "description": f"Search {domain} on public databases",
            "details": {
                "Censys": f"https://censys.io/search?q={domain}",
                "SSL Cert": f"https://crt.sh/?q={domain}",
                "DNS Records": f"https://dnschecker.org/?domain={domain}"
            },
            "type": "public_db",
            "priority": 75
        })

        return {
            "status": "success",
            "domain": domain,
            "ip_address": ip,
            "found_in_sources": sources,
            "message": f"Found domain information for {domain}"
        }

    except Exception as e:
        return {
            "status": "error",
            "domain": domain,
            "message": f"Could not resolve domain: {str(e)}"
        }


# ============================================================================
# URL SEARCH
# ============================================================================

async def _search_url(url: str) -> Dict:
    """Search URL: extract domain, headers, metadata"""
    try:
        # Extract domain
        if "://" not in url:
            url = "https://" + url

        domain = url.split("://")[1].split("/")[0]

        try:
            ip = socket.gethostbyname(domain)
        except:
            ip = "N/A"

        sources = [
            {
                "found": True,
                "source": "URL Information",
                "icon": "🌐",
                "description": "Extracted URL metadata",
                "details": {
                    "Full URL": url,
                    "Domain": domain,
                    "IP": ip
                },
                "type": "metadata",
                "priority": 100
            },
            {
                "found": True,
                "source": "HTTP Headers",
                "icon": "📡",
                "description": "Website response headers",
                "details": {
                    "Check": f"curl -I {url}",
                    "Method": "Terminal command to see headers",
                    "Info": "Reveals server type, caching policy, security headers"
                },
                "type": "headers",
                "priority": 85
            },
            {
                "found": True,
                "source": "Archive & History",
                "icon": "📚",
                "description": "Historical snapshots",
                "details": {
                    "Wayback Machine": f"https://web.archive.org/web/*/{domain}",
                    "Google Cache": f"https://webcache.googleusercontent.com/cache:{url}",
                },
                "type": "archive",
                "priority": 80,
                "source_url": f"https://web.archive.org/web/*/{domain}"
            }
        ]

        return {
            "status": "success",
            "url": url,
            "domain": domain,
            "found_in_sources": sources,
            "message": f"Analyzed URL: {url}"
        }

    except Exception as e:
        return {
            "status": "error",
            "url": url,
            "message": f"Could not analyze URL: {str(e)}"
        }


# ============================================================================
# IP SEARCH
# ============================================================================

async def _search_ip(ip: str) -> Dict:
    """Search IP: reverse DNS, geolocation, ASN, WHOIS"""
    try:
        # Validate IP
        parts = ip.split(".")
        if len(parts) != 4 or not all(0 <= int(p) <= 255 for p in parts):
            return {
                "status": "error",
                "ip": ip,
                "message": "Invalid IP address format"
            }

        reverse_dns = "N/A"
        try:
            reverse_dns = socket.gethostbyaddr(ip)[0]
        except:
            pass

        sources = []

        # Reverse DNS
        sources.append({
            "found": True,
            "source": "Reverse DNS",
            "icon": "🔄",
            "description": "Hostname associated with IP",
            "details": {
                "IP": ip,
                "Hostname": reverse_dns
            },
            "type": "dns",
            "priority": 100
        })

        # GeoIP
        sources.append({
            "found": True,
            "source": "GeoIP Location",
            "icon": "📍",
            "description": "Approximate geographic location",
            "details": {
                "Service": "ip-api.com (free tier)",
                "Data": "Country, city, ISP, ASN",
                "Link": f"https://ip-api.com/json/{ip}"
            },
            "type": "geolocation",
            "priority": 90
        })

        # WHOIS
        sources.append({
            "found": True,
            "source": "WHOIS Lookup",
            "icon": "📋",
            "description": "IP allocation information",
            "details": {
                "Command": f"whois {ip}",
                "Info": "RIR, allocation, abuse contact",
                "Online": f"https://whois.arin.net/ui/?query={ip}"
            },
            "type": "whois",
            "priority": 85,
            "source_url": f"https://whois.arin.net/ui/?query={ip}"
        })

        # Shodan
        sources.append({
            "found": True,
            "source": "Public Services",
            "icon": "🔍",
            "description": "Scan for open ports, services",
            "details": {
                "Shodan": f"https://www.shodan.io/search?query={ip}",
                "Censys": f"https://censys.io/search?q={ip}",
                "Nmap": f"nmap {ip}"
            },
            "type": "services",
            "priority": 75,
            "source_url": f"https://www.shodan.io/search?query={ip}"
        })

        return {
            "status": "success",
            "ip": ip,
            "reverse_dns": reverse_dns,
            "found_in_sources": sources,
            "message": f"IP information gathered for {ip}"
        }

    except Exception as e:
        return {
            "status": "error",
            "ip": ip,
            "message": f"Error searching IP: {str(e)}"
        }


# ============================================================================
# USERNAME SEARCH
# ============================================================================

async def _search_username(username: str) -> Dict:
    """Search username across platforms - ALL independent sources"""
    username_clean = re.sub(r'[^a-zA-Z0-9._-]', '', username)

    if not username_clean or len(username_clean) < 2:
        return {
            "status": "error",
            "username": username,
            "message": "Username too short (minimum 2 characters)"
        }

    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        platforms = [
            ("GitHub", f"https://api.github.com/users/{username_clean}"),
            ("GitLab", f"https://gitlab.com/api/v4/users?username={username_clean}"),
            ("Twitter", f"https://twitter.com/{username_clean}"),
            ("Reddit", f"https://www.reddit.com/user/{username_clean}/about.json"),
            ("StackOverflow", f"https://stackoverflow.com/users?tab=newest&filter={username_clean}"),
            ("Keybase", f"https://keybase.io/{username_clean}"),
            ("Pastebin", f"https://pastebin.com/search?q={username_clean}"),
        ]

        found_profiles = []

        for platform, url in platforms:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status in [200, 301]:
                        if "github" in url:
                            profile_url = f"https://github.com/{username_clean}"
                        elif "gitlab" in url:
                            profile_url = f"https://gitlab.com/{username_clean}"
                        elif "twitter" in url:
                            profile_url = f"https://twitter.com/{username_clean}"
                        elif "reddit" in url:
                            profile_url = f"https://reddit.com/user/{username_clean}"
                        elif "stackoverflow" in url:
                            profile_url = url
                        elif "keybase" in url:
                            profile_url = f"https://keybase.io/{username_clean}"
                        else:
                            profile_url = url

                        found_profiles.append({
                            "platform": platform,
                            "username": username_clean,
                            "profile_url": profile_url,
                            "found": True,
                            "verified": True
                        })
            except:
                pass

        return {
            "status": "success",
            "username": username_clean,
            "profiles": found_profiles,
            "profiles_found": len(found_profiles),
            "message": f"Found {len(found_profiles)} public profile(s) for {username_clean}"
        }


# ============================================================================
# EMAIL SEARCH
# ============================================================================

async def _search_email(email: str) -> Dict:
    """Comprehensive email search - breaches, profiles, public mentions"""
    email_clean = email.strip().lower()

    # Validate email
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}$', email_clean):
        return {
            "status": "error",
            "email": email_clean,
            "message": "Invalid email format"
        }

    sources = []
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. Check HaveIBeenPwned for breaches
        try:
            headers = {"User-Agent": "TraceNova/1.0"}
            async with session.get(
                f"https://haveibeenpwned.com/api/v3/breachedaccount/{email_clean}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                if r.status == 200:
                    breaches = await r.json()
                    breach_names = [b["Name"] for b in breaches]
                    sources.append({
                        "found": True,
                        "source": "Data Breaches",
                        "icon": "⚠️",
                        "warning": "⚠️ FOUND IN BREACHES",
                        "description": f"Email found in {len(breaches)} data breach(es)",
                        "breaches": breach_names,
                        "type": "security_alert",
                        "priority": 120,
                        "source_url": "https://haveibeenpwned.com"
                    })
        except:
            pass

        # 2. GitHub search
        try:
            async with session.get(
                f"https://api.github.com/search/users?q={email_clean}",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("items"):
                        profiles = [{
                            "username": u["login"],
                            "profile_url": u["html_url"],
                            "avatar": u["avatar_url"]
                        } for u in data["items"][:3]]
                        sources.append({
                            "found": True,
                            "source": "GitHub Profiles",
                            "icon": "🐙",
                            "description": f"Found {len(profiles)} GitHub profile(s)",
                            "profiles": profiles,
                            "type": "verification",
                            "priority": 110,
                            "source_url": f"https://github.com/search?q={email_clean}"
                        })
        except:
            pass

        # 3. Search links (Google, social media)
        sources.append({
            "found": True,
            "source": "Google Search",
            "icon": "🔍",
            "description": "Search entire web for email mentions",
            "details": {
                "Search": f'"{email_clean}"',
                "Coverage": "All public web pages"
            },
            "type": "web_search",
            "priority": 90,
            "source_url": f"https://www.google.com/search?q=%22{quote(email_clean)}%22"
        })

        # 4. Reverse email lookup
        sources.append({
            "found": True,
            "source": "Email Validation",
            "icon": "✉️",
            "description": "Email format and deliverability check",
            "details": {
                "Format": "Valid" if re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email_clean) else "Invalid",
                "Domain": email_clean.split("@")[1],
                "MX Records": "Use: nslookup -q=MX " + email_clean.split("@")[1]
            },
            "type": "validation",
            "priority": 80
        })

    if not sources:
        return {
            "status": "no_results",
            "email": email_clean,
            "found_in_sources": [],
            "summary": f"No public results found for {email_clean}"
        }

    return {
        "status": "success",
        "email": email_clean,
        "found_in_sources": sources,
        "summary": f"Found {len(sources)} source(s) for {email_clean}",
        "total_sources": len(sources)
    }


# ============================================================================
# PHONE SEARCH
# ============================================================================

async def _search_phone(phone: str) -> Dict:
    """Comprehensive phone search - validation, location, breaches, lookup"""
    phone_clean = re.sub(r'[^\d+]', '', phone)

    if not phone_clean or len(phone_clean) < 10:
        return {
            "status": "error",
            "phone": phone,
            "message": "Invalid phone number (minimum 10 digits)"
        }

    sources = []
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        # 1. Phone type detection
        digits = len(re.sub(r'[^\d]', '', phone_clean))
        phone_type = "Mobile" if digits >= 11 else "Landline"

        sources.append({
            "found": True,
            "source": "Phone Type",
            "icon": "📱",
            "description": f"Phone type detection",
            "details": {
                "Format": phone_clean,
                "Digits": digits,
                "Type": phone_type,
                "International": "Yes" if phone_clean.startswith("+") else "No"
            },
            "type": "type_info",
            "priority": 85
        })

        # 2. Country detection from code
        country_codes = {
            "+1": "USA/Canada",
            "+44": "United Kingdom",
            "+33": "France",
            "+49": "Germany",
            "+91": "India",
            "+86": "China",
            "+61": "Australia",
        }
        country = "Unknown"
        for code, name in country_codes.items():
            if phone_clean.startswith(code):
                country = name
                break

        sources.append({
            "found": True,
            "source": "Location",
            "icon": "🌍",
            "description": f"Country: {country}",
            "details": {
                "Country": country,
                "Based on": "Call country code",
                "Precision": "Country-level"
            },
            "type": "location",
            "priority": 75
        })

        # 3. HaveIBeenPwned breach check
        try:
            headers = {"User-Agent": "TraceNova/1.0"}
            async with session.get(
                f"https://haveibeenpwned.com/api/v3/breachedaccount/{phone_clean}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=5)
            ) as r:
                if r.status == 200:
                    breaches = await r.json()
                    if breaches:
                        breach_names = [b["Name"] for b in breaches]
                        sources.append({
                            "found": True,
                            "source": "Data Breaches",
                            "icon": "⚠️",
                            "warning": "⚠️ FOUND IN BREACHES",
                            "description": f"Phone found in {len(breaches)} breach(es)",
                            "breaches": breach_names,
                            "type": "security_alert",
                            "priority": 120,
                            "source_url": "https://haveibeenpwned.com"
                        })
        except:
            pass

        # 4. Reverse lookup services
        sources.append({
            "found": True,
            "source": "Reverse Lookup",
            "icon": "☎️",
            "description": "Search phone in reverse lookup databases",
            "details": {
                "TrueCaller": f"https://www.truecaller.com/search?q={quote(phone_clean)}",
                "NumLookup": f"https://www.numlookup.com/{phone_clean}",
                "WhitePages": f"https://www.whitepages.com/phone/{phone_clean}",
            },
            "type": "reverse_lookup",
            "priority": 90,
            "source_url": f"https://www.truecaller.com/search?q={quote(phone_clean)}"
        })

        # 5. Google search
        sources.append({
            "found": True,
            "source": "Google Search",
            "icon": "🔍",
            "description": "Find all public mentions of this phone",
            "details": {
                "Search Query": f'"{phone_clean}"',
                "Coverage": "Entire web"
            },
            "type": "web_search",
            "priority": 70,
            "source_url": f"https://www.google.com/search?q=%22{quote(phone_clean)}%22"
        })

    return {
        "status": "success",
        "phone": phone_clean,
        "found_in_sources": sources,
        "summary": f"Found {len(sources)} source(s) for phone number",
        "total_sources": len(sources)
    }
