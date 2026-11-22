"""Offline regression tests for validated requests and public-source statuses."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from backend.app import AnalysisRequest, create_app
from services import username_search
from services.ip_resolver import analyze_ip
from services.phone_search import search_phone


class UsernameTests(unittest.TestCase):
    def test_exact_match_validation(self):
        self.assertTrue(username_search._github({"login": "Ab", "id": 1}, "ab"))
        self.assertFalse(username_search._github({"login": "ab-other", "id": 1}, "ab"))
        self.assertTrue(username_search._gitlab([{"username": "ab"}], "ab"))
        self.assertFalse(username_search._gitlab([{"username": "abc"}], "ab"))
        self.assertTrue(username_search._bluesky({"handle": "ab.bsky.social", "did": "did:plc:abc"}, "ab"))
        self.assertFalse(username_search._bluesky({"handle": "ab-other.bsky.social", "did": "did:plc:abc"}, "ab"))

    def test_two_character_username_and_manual_not_found(self):
        async def fake_check(*args):
            name = args[2]
            return {"platform": name, "status": "not_found", "found": False}
        with patch.object(username_search, "_check_platform", side_effect=fake_check):
            result = asyncio.run(username_search.search_username("ab"))
        self.assertEqual(result["query_type"], "username")
        self.assertEqual(result["profiles_found"], 0)
        self.assertEqual(result["status"], "no_profiles_found")
        self.assertTrue(any(s["platform"] == "telegram" for s in result["manual_sources"]))
        self.assertTrue(all(s["status"] == "manual" for s in result["manual_sources"]))

    def test_unknown_platforms_are_not_false_absence(self):
        async def fake_check(*args):
            return {"platform": args[2], "status": "timeout", "found": False}
        with patch.object(username_search, "_check_platform", side_effect=fake_check):
            result = asyncio.run(username_search.search_username("ab"))
        self.assertEqual(result["status"], "partial_failure")
        self.assertEqual(result["profiles_found"], 0)


class PhoneTests(unittest.TestCase):
    def test_no_phone_breach_endpoint_and_validation_is_info(self):
        result = asyncio.run(search_phone("+353851234567"))
        self.assertEqual(result["query_type"], "phone")
        if result["status"] == "error":
            self.fail(result["message"])
        self.assertEqual(result["found_in_sources"], [])
        self.assertEqual(result["total_sources"], 0)
        self.assertTrue(any(s["type"] == "validation" for s in result["info_sources"]))
        self.assertTrue(all(s["status"] == "manual" for s in result["manual_sources"]))

    def test_reject_missing_country_code(self):
        result = asyncio.run(search_phone("0851234567"))
        self.assertEqual(result["status"], "error")


class IPTests(unittest.TestCase):
    def test_special_addresses_do_not_contact_public_sources(self):
        with patch("services.ip_resolver.get_additional_ip_info", return_value={}), \
             patch("services.ip_resolver._rdap_ip") as rdap, \
             patch("services.ip_resolver._geo_ip") as geo:
            for address in ("224.0.0.1", "ff02::1", "::ffff:192.168.0.1"):
                with self.subTest(address=address):
                    result = asyncio.run(analyze_ip(address))
                    self.assertEqual(result["ip_info"]["address_type"], "private_or_reserved")
        rdap.assert_not_awaited()
        geo.assert_not_awaited()

    def test_private_ip_does_not_contact_public_sources(self):
        with patch("services.ip_resolver.get_additional_ip_info",
                   new_callable=AsyncMock, return_value={"reverse_dns": "N/A"}) as reverse, \
             patch("services.ip_resolver._rdap_ip", new_callable=AsyncMock) as rdap, \
             patch("services.ip_resolver._geo_ip", new_callable=AsyncMock) as geo:
            result = asyncio.run(analyze_ip("192.168.0.1"))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["ip_info"]["address_type"], "private_or_reserved")
        reverse.assert_awaited_once()
        rdap.assert_not_awaited()
        geo.assert_not_awaited()

    def test_public_ip_sources_are_separate(self):
        with patch("services.ip_resolver.get_additional_ip_info",
                   new_callable=AsyncMock, return_value={}), \
             patch("services.ip_resolver._rdap_ip", new_callable=AsyncMock,
                   return_value={"network_name": "Example Network"}), \
             patch("services.ip_resolver._geo_ip", new_callable=AsyncMock,
                   return_value={"asn": 15169, "geolocation_source": "test"}):
            result = asyncio.run(analyze_ip("8.8.8.8"))
        self.assertEqual(result["ip_info"]["asn"], 15169)
        self.assertEqual(result["ip_info"]["network_name"], "Example Network")

    def test_reject_malformed_ip(self):
        result = asyncio.run(analyze_ip("not-an-ip"))
        self.assertEqual(result["status"], "error")


class APITests(unittest.TestCase):
    def test_post_route_and_no_get_analysis(self):
        app = create_app()
        route = next(r for r in app.routes if getattr(r, "path", "") == "/api/analyze")
        self.assertEqual(route.methods, {"POST"})

    def test_two_character_username_accepted(self):
        request = AnalysisRequest(query_type="username", query="ab")
        app = create_app()
        route = next(r for r in app.routes if getattr(r, "path", "") == "/api/analyze")
        with patch("backend.app.search_username", new_callable=AsyncMock,
                   return_value={"status": "success", "profiles": []}) as checker:
            result = asyncio.run(route.endpoint(request))
        self.assertEqual(result["query_type"], "username")
        checker.assert_awaited_once_with("ab")

    def test_bad_type_and_excessive_length_rejected(self):
        with self.assertRaises(ValidationError):
            AnalysisRequest(query_type="wrong", query="test")
        with self.assertRaises(ValidationError):
            AnalysisRequest(query_type="email", query="a" * 2049)


if __name__ == "__main__":
    unittest.main()
