"""Offline checks for the analysis HTTP boundary."""

import asyncio
import json
import unittest
from unittest.mock import patch

from backend.app import create_app
from main import main


async def request(app, path, method="GET", payload=None):
    messages = []
    body_read = False

    async def receive():
        nonlocal body_read
        if body_read:
            await asyncio.Future()
        body_read = True
        return {"type": "http.request", "body": json.dumps(payload).encode(), "more_body": False}

    async def send(message):
        messages.append(message)

    await app({
        "type": "http", "asgi": {"spec_version": "2.4"}, "method": method,
        "path": path, "headers": [(b"content-type", b"application/json")],
        "query_string": b"",
    }, receive, send)
    return messages[0]["status"], dict(messages[0]["headers"]), b"".join(
        message.get("body", b"") for message in messages[1:]
    )


class AnalysisSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_422_omits_submitted_text_and_sets_no_store(self):
        status, headers, body = await request(
            create_app(), "/api/analyze", "POST",
            {"query_type": "private@example.com", "query": "a" * 2049},
        )
        self.assertEqual(status, 422)
        self.assertEqual(headers[b"cache-control"], b"no-store")
        self.assertNotIn(b"private@example.com", body)

    @patch("backend.app.search_email", side_effect=RuntimeError("private@example.com"))
    async def test_analysis_error_sanitizes_log_and_sets_no_store(self, _search):
        with self.assertLogs("backend.app", level="ERROR") as logged:
            status, headers, body = await request(
                create_app(), "/api/analyze", "POST",
                {"query_type": "email", "query": "private@example.com"},
            )
        self.assertEqual(status, 500)
        self.assertEqual(headers[b"cache-control"], b"no-store")
        self.assertNotIn(b"private@example.com", body)
        self.assertNotIn("private@example.com", str(logged.output))

    async def test_html_has_security_headers(self):
        status, headers, _ = await request(create_app(), "/")
        self.assertEqual(status, 200)
        self.assertIn(b"frame-ancestors 'none'", headers[b"content-security-policy"])
        self.assertEqual(headers[b"x-content-type-options"], b"nosniff")

    async def test_capacity_is_recovered_after_analysis(self):
        started = asyncio.Event()
        finish = asyncio.Event()

        async def slow_search(_query):
            started.set()
            await finish.wait()
            return {"status": "success"}

        with patch("backend.app.settings.max_concurrent_analyses", 1), patch(
            "backend.app.search_email", side_effect=slow_search,
        ):
            app = create_app()
            params = {"query_type": "email", "query": "test@example.com"}
            first = asyncio.create_task(request(app, "/api/analyze", "POST", params))
            try:
                await asyncio.wait_for(started.wait(), 2)
                status, headers, _ = await request(app, "/api/analyze", "POST", params)
                self.assertEqual(status, 503)
                self.assertEqual(headers[b"retry-after"], b"1")
            finally:
                finish.set()
                await first
            status, _, _ = await request(app, "/api/analyze", "POST", params)
            self.assertEqual(status, 200)


class StartupTests(unittest.TestCase):
    @patch("main.uvicorn.run")
    @patch("main.create_app")
    @patch("main.get_settings")
    def test_uses_configured_address(self, settings, create_app, run):
        settings.return_value.host = "::1"
        settings.return_value.port = 9000
        main()
        run.assert_called_once_with(create_app.return_value, host="::1", port=9000, access_log=False)
