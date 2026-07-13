import os
import json
import time
import httpx
import logging
from typing import Generator
from . import BaseProvider, register_provider

log = logging.getLogger("artenisa.providers.openrouter")

class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    env_key = "OPENROUTER_API_KEY"
    env_model = "OPENROUTER_MODEL"
    default_model = "google/gemma-4-26b-a4b-it:free"
    default_url = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self):
        super().__init__()
        self.max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "5"))
        self.num_predict = int(os.getenv("OPENROUTER_NUM_PREDICT", "8192"))
        self.min_interval = float(os.getenv("OPENROUTER_MIN_INTERVAL", "6"))
        self._client = None
        self._last_request_time = 0.0

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _throttle(self):
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_time = time.time()

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _payload(self, prompt: str, temperature: float, stream: bool = False) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": self.num_predict,
            "stream": stream,
        }

    def _retry(self, fn, max_retries=None):
        max_retries = max_retries or self.max_retries
        last_err = RuntimeError("Max retries agotados")
        for attempt in range(max_retries + 1):
            try:
                self._throttle()
                return fn()
            except httpx.HTTPStatusError as e:
                last_err = e
                if e.response.status_code == 429 and attempt < max_retries:
                    retry_after = e.response.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after else min(2 ** (attempt + 3), 120)
                    log.warning(f"Rate limit (429), esperando {wait}s (intento {attempt + 1}/{max_retries})")
                    time.sleep(wait)
                else:
                    raise
            except (httpx.TimeoutException, httpx.RequestError) as e:
                last_err = e
                if attempt < max_retries:
                    wait = min(2 ** (attempt + 1), 30)
                    log.warning(f"Reintento {attempt + 1}/{max_retries} en {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise
        raise last_err

    def generate(self, prompt: str, temperature: float = 0.85) -> str:
        client = self._get_client()
        def _do():
            resp = client.post(self.base_url, json=self._payload(prompt, temperature), headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            return choices[0].get("message", {}).get("content", "").strip() if choices else ""
        try:
            return self._retry(_do)
        except httpx.TimeoutException:
            raise TimeoutError("Timeout del modelo OpenRouter")
        except httpx.RequestError as e:
            raise RuntimeError(f"Error conectando con OpenRouter: {e}")
        except Exception as e:
            raise RuntimeError(f"Error: {e}")

    def generate_stream(self, prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
        client = self._get_client()
        def _do():
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
                        delta = obj.get("choices", [{}])[0].get("delta", {})
                        token = delta.get("content", "")
                        if token: yield token
                    except json.JSONDecodeError: continue
        try:
            yield from self._retry(_do)
        except httpx.TimeoutException:
            raise TimeoutError("Timeout del modelo OpenRouter (streaming)")
        except httpx.RequestError:
            raise RuntimeError("Error conectando con OpenRouter (streaming)")
        except Exception as e:
            raise RuntimeError(f"Error streaming: {e}")

register_provider("openrouter", OpenRouterProvider)
