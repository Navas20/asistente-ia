import os
import json
import httpx
import logging
from pathlib import Path
from typing import Generator

log = logging.getLogger("artenisa.llama")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "personal")

_httpx_client = None

def get_client():
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.Client(timeout=300)
    return _httpx_client

def check_model() -> bool:
    try:
        r = get_client().get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return r.status_code == 200
    except:
        return False

OLLAMA_OPTIONS = {
    "num_predict": 1024,
    "temperature": 0.85,
    "stop": ["<|im_end|>", "<|im_start|>"]
}

def generate(prompt: str, temperature: float = 0.85) -> str:
    client = get_client()
    try:
        options = {**OLLAMA_OPTIONS, "temperature": temperature}
        resp = client.post(f"{OLLAMA_URL}/api/generate", json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": options
        }, timeout=300)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except httpx.TimeoutException:
        raise TimeoutError("Timeout del modelo")
    except httpx.RequestError as e:
        raise RuntimeError(f"Error conectando con Ollama: {e}")
    except Exception as e:
        raise RuntimeError(f"Error: {e}")

def generate_stream(prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
    """Genera tokens uno por uno usando streaming SSE de Ollama."""
    client = get_client()
    try:
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
            timeout=300
        ) as resp:
            resp.raise_for_status()
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
                        yield token
                    if obj.get("done"):
                        break
                except json.JSONDecodeError:
                    continue
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
    except:
        pass
    return ["personal"]
