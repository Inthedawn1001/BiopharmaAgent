import unittest

from biopharma_agent.config import LLMSettings
from biopharma_agent.llm.factory import create_llm_provider
from biopharma_agent.llm.errors import LLMHTTPError
from biopharma_agent.llm.providers.openai_compatible import OpenAICompatibleProvider
from biopharma_agent.llm.providers.smoke import SmokeProvider
from biopharma_agent.llm.types import ChatMessage, EmbeddingRequest, LLMRequest, StructuredOutputRequest


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post_json(self, url, payload, headers=None, timeout=60.0):
        self.calls.append(
            {
                "url": url,
                "payload": payload,
                "headers": headers or {},
                "timeout": timeout,
            }
        )
        return self.response


class SequenceTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post_json(self, url, payload, headers=None, timeout=60.0):
        self.calls.append({"url": url, "payload": payload, "headers": headers or {}})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class OpenAICompatibleProviderTest(unittest.TestCase):
    def settings(self):
        return LLMSettings(
            provider="openai",
            base_url="https://example.test/v1",
            api_key="test-key",
            model="test-model",
        )

    def test_chat_payload_and_response(self):
        transport = FakeTransport(
            {
                "model": "test-model",
                "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        )
        provider = OpenAICompatibleProvider(self.settings(), transport=transport)

        response = provider.chat(
            LLMRequest(messages=[ChatMessage(role="user", content="hi")], temperature=0)
        )

        self.assertEqual(response.text, "hello")
        self.assertEqual(transport.calls[0]["url"], "https://example.test/v1/chat/completions")
        self.assertEqual(transport.calls[0]["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(transport.calls[0]["payload"]["messages"][0]["content"], "hi")

    def test_structured_adds_json_schema_response_format(self):
        transport = FakeTransport(
            {
                "model": "test-model",
                "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
            }
        )
        provider = OpenAICompatibleProvider(self.settings(), transport=transport)

        provider.structured(
            StructuredOutputRequest(
                messages=[ChatMessage(role="user", content="hi")],
                json_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
                schema_name="check",
            )
        )

        response_format = transport.calls[0]["payload"]["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertEqual(response_format["json_schema"]["name"], "check")

    def test_structured_falls_back_to_json_object(self):
        transport = SequenceTransport(
            [
                LLMHTTPError("response_format type is unavailable now"),
                {
                    "model": "test-model",
                    "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
                },
            ]
        )
        provider = OpenAICompatibleProvider(self.settings(), transport=transport)

        response = provider.structured(
            StructuredOutputRequest(
                messages=[ChatMessage(role="user", content="hi")],
                json_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
                schema_name="check",
            )
        )

        self.assertEqual(response.text, '{"ok": true}')
        self.assertEqual(transport.calls[0]["payload"]["response_format"]["type"], "json_schema")
        self.assertEqual(transport.calls[1]["payload"]["response_format"]["type"], "json_object")

    def test_embed_response(self):
        transport = FakeTransport(
            {
                "model": "embedding-model",
                "data": [{"embedding": [0.1, 0.2]}],
                "usage": {"total_tokens": 3},
            }
        )
        provider = OpenAICompatibleProvider(self.settings(), transport=transport)

        response = provider.embed(EmbeddingRequest(inputs=["abc"], model="embedding-model"))

        self.assertEqual(response.vectors, [[0.1, 0.2]])
        self.assertEqual(transport.calls[0]["url"], "https://example.test/v1/embeddings")


class SmokeProviderTest(unittest.TestCase):
    def test_factory_creates_smoke_provider(self):
        provider = create_llm_provider(
            LLMSettings(
                provider="smoke",
                base_url="local://smoke",
                api_key=None,
                model="smoke-model",
            )
        )

        self.assertIsInstance(provider, SmokeProvider)

    def test_smoke_provider_returns_schema_compatible_json(self):
        provider = SmokeProvider()

        response = provider.structured(
            StructuredOutputRequest(
                messages=[ChatMessage(role="user", content="FDA issued a regulatory update.")],
                json_schema={"type": "object"},
            )
        )

        self.assertIn('"summary"', response.text)
        self.assertEqual(response.provider, "smoke")
        self.assertEqual(provider.embed(EmbeddingRequest(inputs=["a", "b"])).vectors, [[0.0], [0.0]])


if __name__ == "__main__":
    unittest.main()
