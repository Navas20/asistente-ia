"""
SERVICES LAYER - Servicio de LLM (Ollama, 100% local)
"""
import time
import json
import logging
import httpx
from typing import Generator, Optional

from app.config import (
    OLLAMA_HOST, OLLAMA_MODEL,
    OLLAMA_TIMEOUT, OLLAMA_MAX_RETRIES, OLLAMA_NUM_PREDICT
)

log = logging.getLogger("artenisa.llm")

_OLLAMA_URL = f"{OLLAMA_HOST.rstrip('/')}/v1/chat/completions"


class LLMService:
    """Servicio centralizado de LLM con Ollama"""

    def __init__(self):
        self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=OLLAMA_TIMEOUT)
        return self._client

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def _payload(self, prompt: str, temperature: float, stream: bool = False) -> dict:
        return {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": OLLAMA_NUM_PREDICT,
            "stream": stream,
        }

    def _retry(self, fn, max_retries: Optional[int] = None):
        """Retry con backoff (errores transitorios del server local)"""
        max_retries = max_retries or OLLAMA_MAX_RETRIES
        last_err = RuntimeError("Max retries agotados")

        for attempt in range(max_retries + 1):
            try:
                return fn()
            except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as e:
                last_err = e
                if attempt < max_retries:
                    wait = min(2 ** (attempt + 1), 10)
                    log.warning(f"Reintento {attempt + 1}/{max_retries} en {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise

        raise last_err

    def generate(self, prompt: str, temperature: float = 0.85) -> str:
        """Genera texto sin streaming"""
        def _do_generate():
            client = self._get_client()
            resp = client.post(
                _OLLAMA_URL,
                json=self._payload(prompt, temperature, stream=False),
                headers=self._headers()
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
            return ""

        return self._retry(_do_generate)

    def stream(self, prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
        """Genera texto con streaming"""
        def _do_stream():
            client = self._get_client()
            with client.stream(
                "POST",
                _OLLAMA_URL,
                json=self._payload(prompt, temperature, stream=True),
                headers=self._headers()
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        line = line[6:]
                        if line == "[DONE]":
                            break
                        try:
                            data = json.loads(line)
                            choice = data.get("choices", [{}])[0]
                            delta = choice.get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

        return self._retry(_do_stream)


# Instancia global
llm_service = LLMService()