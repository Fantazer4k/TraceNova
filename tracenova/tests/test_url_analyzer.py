"""Unit tests for safe URL analysis."""

import unittest
from unittest.mock import patch

from services.url_analyzer import _analyze_url, _resolve_public_addresses


class URLAnalyzerTests(unittest.TestCase):
    @patch("services.url_analyzer._resolve_public_addresses", return_value=["93.184.216.34"])
    def test_http_url_returns_parsed_metadata(self, _resolve):
        result = _analyze_url("http://example.com/docs?q=1")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["hostname"], "example.com")
        self.assertEqual(result["scheme"], "http")
        self.assertEqual(result["path"], "/docs")
        self.assertEqual(result["resolved_ips"], ["93.184.216.34"])
        self.assertEqual(result["tls"]["status"], "not_applicable")

    @patch("services.url_analyzer._inspect_tls", return_value={
        "status": "success",
        "version": "TLSv1.3",
        "cipher": "TEST-CIPHER",
        "subject": (),
        "issuer": (),
        "expires": "Jan 01 00:00:00 2030 GMT",
    })
    @patch("services.url_analyzer._resolve_public_addresses", return_value=["93.184.216.34"])
    def test_https_url_checks_tls(self, _resolve, _tls):
        result = _analyze_url("https://example.com")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tls"]["status"], "success")
        self.assertEqual(result["tls"]["version"], "TLSv1.3")

    def test_unsupported_scheme_is_rejected(self):
        result = _analyze_url("ftp://example.com/file")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "invalid_url_or_target")

    def test_embedded_credentials_are_rejected(self):
        result = _analyze_url("https://user:password@example.com")

        self.assertEqual(result["status"], "error")
        self.assertIn("credentials", result["message"])

    @patch("services.url_analyzer.socket.getaddrinfo")
    def test_private_dns_destination_is_blocked(self, getaddrinfo):
        getaddrinfo.return_value = [
            (2, 1, 6, "", ("127.0.0.1", 80))
        ]

        with self.assertRaises(ValueError):
            _resolve_public_addresses("internal.example", 80)

    @patch("services.url_analyzer._resolve_with_doh", return_value=["93.184.216.34"])
    @patch("services.url_analyzer.socket.getaddrinfo", side_effect=__import__("socket").gaierror("DNS unavailable"))
    def test_doh_fallback_is_used_when_system_dns_fails(self, _getaddrinfo, doh):
        addresses = _resolve_public_addresses("example.com", 443)

        self.assertEqual(addresses, ["93.184.216.34"])
        doh.assert_called_once_with("example.com")

    @patch("services.url_analyzer._resolve_with_doh", return_value=["10.0.0.5"])
    @patch("services.url_analyzer.socket.getaddrinfo", side_effect=__import__("socket").gaierror("DNS unavailable"))
    def test_doh_private_destination_is_still_blocked(self, _getaddrinfo, _doh):
        with self.assertRaises(ValueError):
            _resolve_public_addresses("internal.example", 443)


if __name__ == "__main__":
    unittest.main()
