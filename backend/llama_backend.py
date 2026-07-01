import os
import json
import time
import httpx
import logging
from pathlib import Path
from typing import Generator

log = logging.getLogger("artenisa.llama")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "personal")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "60"))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "2"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "1536"))
OLLAMA_STOP_TOKENS = [token.strip() for token in os.getenv("OLLAMA_STOP_TOKENS", "").split(",") if token.strip()]

_httpx_client = None

def get_client():
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.Client(timeout=OLLAMA_TIMEOUT)
    return _httpx_client

def _retry(fn, max_retries=None):
    max_retries = max_retries or OLLAMA_MAX_RETRIES
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except (httpx.TimeoutException, httpx.RequestError) as e:
            last_err = e
            if attempt < max_retries:
                wait = 2 ** attempt
                log.warning(f"Reintento {attempt + 1}/{max_retries} en {wait}s: {e}")
                time.sleep(wait)
            else:
                raise
    raise last_err

def check_model() -> bool:
    try:
        r = get_client().get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return r.status_code == 200
    except httpx.HTTPError:
        return False

OLLAMA_OPTIONS = {
    "num_predict": OLLAMA_NUM_PREDICT,
    "temperature": 0.85,
}
if OLLAMA_STOP_TOKENS:
    OLLAMA_OPTIONS["stop"] = OLLAMA_STOP_TOKENS

def generate(prompt: str, temperature: float = 0.85) -> str:
    client = get_client()
    def _do_generate():
        options = {**OLLAMA_OPTIONS, "temperature": temperature}
        resp = client.post(f"{OLLAMA_URL}/api/generate", json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": options
        }, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    try:
        return _retry(_do_generate)
    except httpx.TimeoutException:
        raise TimeoutError("Timeout del modelo")
    except httpx.RequestError as e:
        raise RuntimeError(f"Error conectando con Ollama: {e}")
    except Exception as e:
        raise RuntimeError(f"Error: {e}")

def generate_stream(prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
    """Genera tokens uno por uno usando streaming SSE de Ollama."""
    client = get_client()
    def _do_stream():
        options = {**OLLAMA_OPTIONS, "temperature": temperature}
        with client.stream(
            "POST",
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": True,
                "options": options
            },
            timeout=OLLAMA_TIMEOUT
        ) as resp:
            resp.raise_for_status()
            tokens = []
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    token = obj.get("response", "")
                    if token:
                        tokens.append(token)
                        yield token
                    if obj.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
    try:
        yield from _retry(_do_stream)
    except httpx.TimeoutException:
        raise TimeoutError("Timeout del modelo (streaming)")
    except httpx.RequestError as e:
        raise RuntimeError(f"Error conectando con Ollama: {e}")
    except Exception as e:
        raise RuntimeError(f"Error streaming: {e}")

def list_models() -> list:
    """Lista modelos disponibles en Ollama."""
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get(f"{OLLAMA_URL}/api/tags")
            if r.status_code == 200:
                data = r.json()
                return [m["name"] for m in data.get("models", [])]
    except httpx.HTTPError:
        pass
    return ["personal"]
