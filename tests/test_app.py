"""API checks with real reference data and mocked external providers."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import anthropic
import httpx
from fastapi.testclient import TestClient

from backend.app import app
from backend.passages import Passage, PassageError


class APITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.original_source = app.state.source
        self.original_claude = app.state.claude
        self.addCleanup(self.restore_resources)
        self.source = SimpleNamespace(
            translation="ESV",
            fetch=AsyncMock(return_value=Passage("John 3", "[16] Test chapter text")),
        )
        self.create = AsyncMock(return_value=SimpleNamespace(
            content=[SimpleNamespace(type="text", text="A sourced answer.")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        ))
        app.state.source = self.source
        app.state.claude = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def restore_resources(self):
        app.state.source = self.original_source
        app.state.claude = self.original_claude

    def test_summary_and_chat_use_real_commentary_and_chapter_context(self):
        for endpoint, body in (
            ("/summary", {"reference": "John.3"}),
            ("/chat", {"reference": "John.3.16", "question": "Who is the world?"}),
        ):
            with self.subTest(endpoint=endpoint):
                # Arrange
                self.create.reset_mock()
                self.source.fetch.reset_mock()

                # Act
                response = self.client.post(endpoint, json=body)

                # Assert
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertEqual(payload["text"], "A sourced answer.")
                self.assertEqual(payload["translation"], "ESV")
                self.assertTrue(any("Jamieson" in s for s in payload["sources"]))
                self.assertEqual(payload["usage"]["input_tokens"], 100)
                chapter_ref = self.source.fetch.call_args.args[0]
                self.assertEqual(chapter_ref.display(), "John 3")
                call = self.create.call_args.kwargs
                self.assertIn("Test chapter text", call["system"][1]["text"])
                self.assertEqual(call["system"][0]["cache_control"]["ttl"], "1h")
                if endpoint == "/chat":
                    self.assertIn("MHCC", payload["omitted_modules"])

    def test_chat_preserves_completed_turns(self):
        # Arrange
        history = [
            {"role": "user", "content": "What does world mean?"},
            {"role": "assistant", "content": "The supplied commentators differ."},
        ]

        # Act
        response = self.client.post("/chat", json={
            "reference": "John.3.16", "question": "How do they differ?", "history": history,
        })

        # Assert
        self.assertEqual(response.status_code, 200)
        messages = self.create.call_args.kwargs["messages"]
        self.assertEqual(messages[:2], history)
        self.assertIn("How do they differ?", messages[-1]["content"])

    def test_invalid_input_does_not_call_providers(self):
        for endpoint, body in (
            ("/summary", {"reference": ""}),
            ("/summary", {"reference": "NoBook.3"}),
            ("/summary", {"reference": "John.nope"}),
            ("/summary", {"reference": "John.0"}),
            ("/summary", {"reference": "John.3.0"}),
            ("/summary", {"reference": "John.3.19-John.3.14"}),
            ("/summary", {"reference": "John.3.30-John.4.2"}),
            ("/summary", {"reference": "John.3", "tradition": "unknown"}),
            ("/summary", {"reference": "John.3", "reading_level": "unknown"}),
            ("/chat", {"reference": "John.3.16", "question": "   "}),
            ("/chat", {"reference": "John.3.16", "question": "Why?", "history": [
                {"role": "assistant", "content": "Unpaired answer"},
            ]}),
        ):
            with self.subTest(endpoint=endpoint, body=body):
                # Arrange
                self.source.fetch.reset_mock()
                self.create.reset_mock()

                # Act
                response = self.client.post(endpoint, json=body)

                # Assert
                self.assertEqual(response.status_code, 422, response.text)
                self.source.fetch.assert_not_called()
                self.create.assert_not_called()

    def test_missing_configuration(self):
        for attribute, key in (
            ("source", "ESV_API_KEY"), ("claude", "ANTHROPIC_API_KEY")
        ):
            with self.subTest(key=key):
                # Arrange
                with patch.object(app.state, attribute, None):
                    # Act
                    health = self.client.get("/health")
                    response = self.client.post("/summary", json={"reference": "John.3"})

                # Assert
                self.assertEqual(health.status_code, 200)
                self.assertIn(key, health.json()["missing"])
                self.assertEqual(response.status_code, 503)
                self.assertIn(key, response.json()["detail"])

    def test_esv_failure(self):
        # Arrange
        self.source.fetch.side_effect = PassageError("private provider detail")

        # Act
        response = self.client.post("/summary", json={"reference": "John.3"})

        # Assert
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private provider detail", response.text)
        self.create.assert_not_called()

    def test_anthropic_failures(self):
        provider_response = httpx.Response(
            400, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        )
        for error_type, status in (
            (anthropic.AuthenticationError, 502),
            (anthropic.RateLimitError, 429),
            (anthropic.BadRequestError, 502),
        ):
            with self.subTest(error=error_type):
                # Arrange
                self.create.side_effect = error_type(
                    "private provider detail", response=provider_response, body=None,
                )

                # Act
                response = self.client.post("/summary", json={"reference": "John.3"})

                # Assert
                self.assertEqual(response.status_code, status)
                self.assertNotIn("private provider detail", response.text)

    def test_empty_and_truncated_answers(self):
        for content, stop_reason in (([], "end_turn"), (
            [SimpleNamespace(type="text", text="Partial answer")], "max_tokens"
        )):
            with self.subTest(stop_reason=stop_reason):
                # Arrange
                self.create.return_value.content = content
                self.create.return_value.stop_reason = stop_reason

                # Act
                response = self.client.post("/summary", json={"reference": "John.3"})

                # Assert
                self.assertEqual(response.status_code, 502)


if __name__ == "__main__":
    unittest.main()
