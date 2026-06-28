import os
import json
import httpx
import logging
from pathlib import Path
from typing import Generator

log = logging.getLogger("artenisa.llama")

LLAMA_SERVER_URL = os.getenv("LLAMA_SERVER_URL", "http://localhost:8080")

_httpx_client = None

def get_client():
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.Client(timeout=300)
    return _httpx_client

def check_model() -> bool:
    try:
        r = get_client().get(f"{LLAMA_SERVER_URL}/health", timeout=5)
        return r.status_code == 200
    except:
        return False

def generate(prompt: str, temperature: float = 0.85) -> str:
    client = get_client()
    try:
        resp = client.post(f"{LLAMA_SERVER_URL}/completion", json={
            "prompt": prompt,
            "temperature": temperature,
            "n_predict": 1024,
            "stop": ["<|im_end|>", "<|im_start|>"]
        }, timeout=300)
        resp.raise_for_status()
        return resp.json()["content"].strip()
    except httpx.TimeoutException:
        raise TimeoutError("Timeout del modelo")
    except httpx.RequestError as e:
        raise RuntimeError(f"Error conectando con llama-server: {e}")
    except Exception as e:
        raise RuntimeError(f"Error: {e}")

def generate_stream(prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
    """Genera tokens uno por uno usando streaming SSE de llama-server."""
    client = get_client()
    try:
        with client.stream(
            "POST",
            f"{LLAMA_SERVER_URL}/completion",
            json={
                "prompt": prompt,
                "temperature": temperature,
                "n_predict": 1024,
                "stream": True,
                "stop": ["<|im_end|>", "<|im_start|>"]
            },
            timeout=300
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    token = obj.get("content", "")
                    if token:
                        yield token
                    if obj.get("stop"):
                        break
                except json.JSONDecodeError:
                    continue
    except httpx.TimeoutException:
        raise TimeoutError("Timeout del modelo (streaming)")
    except httpx.RequestError as e:
        raise RuntimeError(f"Error conectando con llama-server: {e}")
    except Exception as e:
        raise RuntimeError(f"Error streaming: {e}")

def list_models() -> list:
    """Lista modelos disponibles en Ollama."""
    try:
        with httpx.Client(timeout=10) as c:
            r = c.get("http://localhost:11434/api/tags")
            if r.status_code == 200:
                data = r.json()
                return [m["name"] for m in data.get("models", [])]
    except:
        pass
    return ["personal"]
