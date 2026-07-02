import os
import json
import time
import httpx
import logging
from typing import Generator

log = logging.getLogger("artenisa.llama")

OPENROUTER_URL = os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")
OPENROUTER_TIMEOUT = int(os.getenv("OPENROUTER_TIMEOUT", "180"))
OPENROUTER_MAX_RETRIES = int(os.getenv("OPENROUTER_MAX_RETRIES", "5"))
OPENROUTER_NUM_PREDICT = int(os.getenv("OPENROUTER_NUM_PREDICT", "8192"))

_httpx_client = None

def get_client():
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.Client(timeout=OPENROUTER_TIMEOUT)
    return _httpx_client

def _retry(fn, max_retries=None):
    max_retries = max_retries or OPENROUTER_MAX_RETRIES
    last_err = RuntimeError("Max retries agotados")
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except httpx.HTTPStatusError as e:
            last_err = e
            if e.response.status_code == 429 and attempt < max_retries:
                wait = min(2 ** (attempt + 2), 60)
                log.warning(f"Rate limit (429), esperando {wait}s (intento {attempt + 1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
        except (httpx.TimeoutException, httpx.RequestError) as e:
            last_err = e
            if attempt < max_retries:
                wait = 2 ** attempt
                log.warning(f"Reintento {attempt + 1}/{max_retries} en {wait}s: {e}")
                time.sleep(wait)
            else:
                raise
    raise last_err

def _headers():
    headers = {
        "Content-Type": "application/json",
    }
    if OPENROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {OPENROUTER_API_KEY}"
    return headers

def _payload(prompt: str, temperature: float, stream: bool = False) -> dict:
    return {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": OPENROUTER_NUM_PREDICT,
        "stream": stream,
    }

def generate(prompt: str, temperature: float = 0.85) -> str:
    client = get_client()
    def _do_generate():
        resp = client.post(
            OPENROUTER_URL,
            json=_payload(prompt, temperature, stream=False),
            headers=_headers(),
            timeout=OPENROUTER_TIMEOUT
        )
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            return content.strip()
        return ""
    try:
        return _retry(_do_generate)
    except httpx.TimeoutException:
        raise TimeoutError("Timeout del modelo OpenRouter")
    except httpx.RequestError as e:
        raise RuntimeError(f"Error conectando con OpenRouter: {e}")
    except Exception as e:
        raise RuntimeError(f"Error: {e}")

def generate_stream(prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
    client = get_client()
    def _do_stream():
        with client.stream(
            "POST",
            OPENROUTER_URL,
            json=_payload(prompt, temperature, stream=True),
            headers=_headers(),
            timeout=OPENROUTER_TIMEOUT
        ) as resp:
            resp.raise_for_status()
            tokens = []
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    obj = json.loads(data_str)
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        tokens.append(token)
                        yield token
                except json.JSONDecodeError:
                    continue
    try:
        yield from _retry(_do_stream)
    except httpx.TimeoutException:
        raise TimeoutError("Timeout del modelo OpenRouter (streaming)")
    except httpx.RequestError as e:
        raise RuntimeError(f"Error conectando con OpenRouter: {e}")
    except Exception as e:
        raise RuntimeError(f"Error streaming: {e}")

def list_models() -> list:
    return [OPENROUTER_MODEL]
