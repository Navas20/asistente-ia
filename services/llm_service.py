"""
SERVICES LAYER - Servicio de LLM (OpenRouter)
"""
import time
import json
import logging
import httpx
from typing import Generator, Optional

from app.config import (
    OPENROUTER_URL, OPENROUTER_API_KEY, OPENROUTER_MODEL,
    OPENROUTER_TIMEOUT, OPENROUTER_MAX_RETRIES, OPENROUTER_NUM_PREDICT,
    OPENROUTER_MIN_INTERVAL
)

log = logging.getLogger("artenisa.llm")


class LLMService:
    """Servicio centralizado de LLM con OpenRouter"""
    
    def __init__(self):
        self._client = None
        self._last_request_time = 0.0
    
    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=OPENROUTER_TIMEOUT)
        return self._client
    
    def _throttle(self):
        """Throttling entre requests"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < OPENROUTER_MIN_INTERVAL:
            wait = OPENROUTER_MIN_INTERVAL - elapsed
            log.debug(f"Throttling {wait:.1f}s entre requests")
            time.sleep(wait)
        self._last_request_time = time.time()
    
    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if OPENROUTER_API_KEY:
            headers["Authorization"] = f"Bearer {OPENROUTER_API_KEY}"
        return headers
    
    def _payload(self, prompt: str, temperature: float, stream: bool = False) -> dict:
        return {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": OPENROUTER_NUM_PREDICT,
            "stream": stream,
        }
    
    def _retry(self, fn, max_retries: Optional[int] = None):
        """Retry con backoff exponencial"""
        max_retries = max_retries or OPENROUTER_MAX_RETRIES
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
        """Genera texto sin streaming"""
        def _do_generate():
            client = self._get_client()
            resp = client.post(
                OPENROUTER_URL,
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
                OPENROUTER_URL,
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
