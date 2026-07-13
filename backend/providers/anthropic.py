import json
import httpx
import logging
from typing import Generator
from . import BaseProvider, register_provider

log = logging.getLogger("artenisa.providers.anthropic")

ANTHROPIC_MODELS = [
    "claude-sonnet-4-20250514", "claude-4-5-sonnet-20250702",
    "claude-sonnet-4-20250514", "claude-3-5-haiku-20241022",
]

class AnthropicProvider(BaseProvider):
    name = "anthropic"
    env_key = "ANTHROPIC_API_KEY"
    env_model = "ANTHROPIC_MODEL"
    default_model = "claude-sonnet-4-20250514"
    default_url = "https://api.anthropic.com/v1/messages"

    def __init__(self):
        super().__init__()
        self.max_tokens = int(self.timeout * 10)
        self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

    def _payload(self, prompt: str, temperature: float, stream: bool = False) -> dict:
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }

    def generate(self, prompt: str, temperature: float = 0.85) -> str:
        client = self._get_client()
        resp = client.post(self.base_url, json=self._payload(prompt, temperature), headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", [])
        if content:
            return "".join(block.get("text", "") for block in content if block.get("type") == "text")
        return ""

    def generate_stream(self, prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
        client = self._get_client()
        with client.stream("POST", self.base_url, json=self._payload(prompt, temperature, stream=True), headers=self._headers()) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line: continue
                line = line.strip()
                if not line.startswith("data: "): continue
                data_str = line[6:]
                if data_str == "[DONE]": break
                try:
                    obj = json.loads(data_str)
                    if obj.get("type") == "content_block_delta":
                        delta = obj.get("delta", {})
                        text = delta.get("text", "")
                        if text: yield text
                except json.JSONDecodeError: continue

    def list_models(self) -> list:
        return ANTHROPIC_MODELS

register_provider("anthropic", AnthropicProvider)
