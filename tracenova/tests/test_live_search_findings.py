"""Offline regressions for findings from end-to-end user testing."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from services import email_search, ip_resolver, url_analyzer, username_search


class _FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self, *args, **kwargs):
        return self.payload


class _FakeSession:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    def get(self, *args, **kwargs):
        return _FakeResponse(self.status, self.payload)


class EmailConfidenceTests(unittest.TestCase):
    def test_empty_rate_limited_and_invalid_responses_are_distinct(self):
        for status, body, expected in (
            (200, {"total_count": 0}, "checked_no_match"),
            (429, {}, "rate_limited"),
            (503, {}, "unavailable"),
            (200, [], "error"),
        ):
            with self.subTest(status=status, expected=expected):
                session = _FakeSession(status, body)
                result = asyncio.run(email_search._search_github(session, "example@example.com"))
                self.assertEqual(result["status"], expected)

    def test_timeout_is_not_reported_as_absence(self):
        session = _FakeSession(200, {})
        with patch.object(session, "get", side_effect=asyncio.TimeoutError):
            result = asyncio.run(email_search._check_gravatar(session, "example@example.com"))
        self.assertEqual(result["status"], "timeout")

    def test_github_profile_search_is_unverified(self):
        session = _FakeSession(200, {
            "total_count": 8,
            "items": [{"login": "candidate", "html_url": "https://github.com/candidate"}],
        })
        result = asyncio.run(email_search._search_github(session, "example@example.com"))
        self.assertNotEqual(result.get("found"), True)
        self.assertEqual(result["status"], "candidates_unverified")
        self.assertEqual(result["category"], "technical")

    def test_github_code_count_is_not_proof_of_exact_occurrence(self):
        session = _FakeSession(200, {"total_count": 12, "items": []})
        result = asyncio.run(email_search._search_github_code(session, "example@example.com"))
        self.assertNotEqual(result.get("found"), True)
        self.assertEqual(result["status"], "candidates_unverified")

    def test_email_verification_is_technical_not_public_mention(self):
        session = _FakeSession(200, {"status": "valid"})
        with patch.dict("os.environ", {"ZEROBOUNCE_API_KEY": "test-only-placeholder"}):
            result = asyncio.run(email_search._verify_email_zerobounce(session, "example@example.com"))
        self.assertEqual(result["category"], "technical")
        self.assertNotEqual(result.get("found"), True)


class DomainDNSConsistencyTests(unittest.TestCase):
    def test_domain_uses_shared_dns_fallback_and_returns_all_addresses(self):
        answers = ["104.20.23.154", "172.66.147.243", "2606:4700:10::6814:179a"]
        with patch.object(url_analyzer, "_resolve_public_addresses", return_value=answers) as dns:
            result = asyncio.run(ip_resolver.resolve_domain_to_ip("example.com"))
        dns.assert_called_once_with("example.com", 443)
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["ip_addresses"]), 2)
        self.assertEqual(len(result["ipv6_addresses"]), 1)

    def test_private_domain_answer_is_rejected(self):
        with patch.object(url_analyzer, "_resolve_public_addresses",
                          side_effect=ValueError("Private IP is blocked")):
            result = asyncio.run(ip_resolver.resolve_domain_to_ip("local.example"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "invalid_domain_or_target")

    def test_invalid_domain_path_is_rejected(self):
        result = asyncio.run(ip_resolver.resolve_domain_to_ip("example.com/secret"))
        self.assertEqual(result["status"], "error")


class TLSEndpointTests(unittest.TestCase):
    def test_first_certificate_fails_second_succeeds(self):
        import ssl
        def handshake(host, address, port):
            if address == "104.20.23.154":
                raise ssl.SSLCertVerificationError("invalid certificate")
            return {"status": "success", "version": "TLSv1.3", "expires": "future"}
        with patch.object(url_analyzer, "_resolve_public_addresses",
                          return_value=["104.20.23.154", "172.66.147.243"]), \
             patch.object(url_analyzer, "_inspect_tls", side_effect=handshake):
            result = url_analyzer._analyze_url("https://example.com")
        self.assertEqual(result["tls"]["status"], "success")
        self.assertEqual(result["tls"]["connected_ip"], "172.66.147.243")

    def test_all_certificate_errors_report_without_disabling_tls_verification(self):
        import ssl
        with patch.object(url_analyzer, "_resolve_public_addresses", return_value=["104.20.23.154"]), \
             patch.object(url_analyzer, "_inspect_tls",
                          side_effect=ssl.SSLCertVerificationError("invalid certificate")):
            result = url_analyzer._analyze_url("https://example.com")
        self.assertEqual(result["tls"]["status"], "verification_failed")
        self.assertIn("local trust", result["tls"]["message"])


class UsernameAvailabilityTests(unittest.TestCase):
    def test_bluesky_bad_request_does_not_claim_found(self):
        async def run():
            sem = asyncio.Semaphore(1)
            return await username_search._check_platform(
                _FakeSession(400, {}), sem, "bluesky",
                username_search.PLATFORMS["bluesky"], "example")
        result = asyncio.run(run())
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["found"])


if __name__ == "__main__":
    unittest.main()
