import unittest
from unittest.mock import AsyncMock, MagicMock

from services.email_search import DNS_RESOLVERS, _check_domain_mx


def dns_response(payload, status=200):
    response = MagicMock()
    response.status = status
    response.json = AsyncMock(return_value=payload)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


class EmailMXTests(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_responses_have_distinct_technical_statuses(self):
        for payload, expected_status, expected_records in (
            ({"Status": 3}, "nxdomain", None),
            ({"Status": 0}, "no_mx", None),
            ({"Status": 0, "Answer": [{"type": 5, "data": "alias.example."}]}, "no_mx", None),
            ({"Status": 0, "Answer": [{"type": 15, "data": "0 ."}]}, "null_mx", ["0 ."]),
            (
                {"Status": 0, "Answer": [{"type": 15, "data": "10 mail.example."}]},
                "checked",
                ["10 mail.example."],
            ),
        ):
            with self.subTest(expected_status=expected_status):
                session = MagicMock()
                session.get.return_value = dns_response(payload)

                result = await _check_domain_mx(session, "example.test")

                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result["category"], "technical")
                self.assertEqual(result["details"].get("mx_records"), expected_records)
                session.get.assert_called_once()

    async def test_invalid_or_failed_response_uses_the_next_resolver(self):
        for payload in (
            {"Status": 2},
            {"Status": 0, "TC": True},
            {},
            {"Status": 0, "Answer": [{"type": 15, "data": None}]},
            {"Status": 0, "Answer": [{"type": 15, "data": "5 ."}]},
            {"Status": 0, "Answer": [
                {"type": 15, "data": "0 ."},
                {"type": 15, "data": "10 mail.example."},
            ]},
        ):
            with self.subTest(payload=payload):
                session = MagicMock()
                session.get.side_effect = [dns_response(payload), dns_response({"Status": 3})]

                result = await _check_domain_mx(session, "example.test")

                self.assertEqual(result["status"], "nxdomain")
                self.assertEqual(result["details"]["resolver"], DNS_RESOLVERS[1])
                self.assertEqual(session.get.call_count, 2)

    async def test_exhausted_resolvers_are_unavailable(self):
        session = MagicMock()
        session.get.side_effect = [
            dns_response({}, status=503),
            dns_response({"Status": 2}),
        ]

        result = await _check_domain_mx(session, "example.test")

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["details"], {"domain": "example.test"})
