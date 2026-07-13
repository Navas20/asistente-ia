import json
import httpx
import logging
from typing import Generator
from . import BaseProvider, register_provider

log = logging.getLogger("artenisa.providers.groq")

GROQ_MODELS = [
    "kimi-k2-instruct-0905", "qwen3-32b", "qwen3-16b",
    "llama-4-scout-17b-16e-instruct", "llama-4-maverick-17b-128e-instruct",
    "deepseek-r1-distill-llama-70b", "mixtral-8x7b-32768", "gemma2-9b-it",
]

class GroqProvider(BaseProvider):
    name = "groq"
    env_key = "GROQ_API_KEY"
    env_model = "GROQ_MODEL"
    default_model = "kimi-k2-instruct-0905"
    default_url = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        super().__init__()
        self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _headers(self) -> dict:
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

    def _payload(self, prompt: str, temperature: float, stream: bool = False) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": stream,
        }

    def generate(self, prompt: str, temperature: float = 0.85) -> str:
        client = self._get_client()
        resp = client.post(self.base_url, json=self._payload(prompt, temperature), headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        return choices[0].get("message", {}).get("content", "").strip() if choices else ""

    def generate_stream(self, prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
        client = self._get_client()
        with client.stream("POST", self.base_url, json=self._payload(prompt, temperature, stream=True), headers=self._headers()) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line: continue
                line = line.strip()
                if not line or not line.startswith("data: "): continue
                data_str = line[6:]
                if data_str == "[DONE]": break
                try:
                    obj = json.loads(data_str)
                    choices = obj.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content: yield content
                except json.JSONDecodeError: continue

    def list_models(self) -> list:
        return GROQ_MODELS

register_provider("groq", GroqProvider)
