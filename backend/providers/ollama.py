import os
import json
import httpx
import logging
from typing import Generator
from . import BaseProvider, register_provider

log = logging.getLogger("artenisa.providers.ollama")

class OllamaProvider(BaseProvider):
    name = "ollama"
    env_key = "OLLAMA_API_KEY"
    env_model = "OLLAMA_MODEL"
    default_model = "artenisa"
    default_url = "http://artenisa-ollama:11434/v1/chat/completions"
    supports_tools = True

    def __init__(self):
        self.api_key = os.getenv("OLLAMA_API_KEY", "")
        self.model = os.getenv("OLLAMA_MODEL", self.default_model)
        host = os.getenv("OLLAMA_HOST", "http://artenisa-ollama:11434").rstrip("/")
        self.chat_url = f"{host}/v1/chat/completions"
        self.gen_url = f"{host}/api/generate"
        self.base_url = self.chat_url
        self.timeout = int(os.getenv("OLLAMA_TIMEOUT", "600"))
        self.num_predict = int(os.getenv("OLLAMA_NUM_PREDICT", "400"))
        self.max_retries = int(os.getenv("OLLAMA_MAX_RETRIES", "1"))
        self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _payload(self, prompt: str, temperature: float, stream: bool = False) -> dict:
        return {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {"temperature": temperature, "num_predict": self.num_predict},
        }

    def _retry(self, fn, max_retries=None):
        max_retries = max_retries if max_retries is not None else self.max_retries
        last_err = RuntimeError("Max retries agotados")
        for attempt in range(max_retries + 1):
            try:
                return fn()
            except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as e:
                last_err = e
                if attempt < max_retries:
                    wait = min(2 ** (attempt + 1), 10)
                    log.warning(f"Reintento {attempt + 1}/{max_retries} en {wait}s: {e}")
                    import time
                    time.sleep(wait)
                else:
                    raise
        raise last_err

    def chat(self, messages: list, tools: list | None = None, temperature: float = 0.7) -> dict:
        client = self._get_client()
        def _do():
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": self.num_predict,
                "stream": False,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            resp = client.post(self.chat_url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            message = (data.get("choices") or [{}])[0].get("message", {})
            tool_calls = []
            for tc in message.get("tool_calls") or []:
                fn = tc.get("function", {})
                raw_args = fn.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": tc.get("id", f"call_{len(tool_calls)}"),
                    "name": fn.get("name", ""),
                    "arguments": args,
                })
            return {"content": (message.get("content") or "").strip(), "tool_calls": tool_calls}
        try:
            return self._retry(_do)
        except httpx.TimeoutException:
            raise TimeoutError("Timeout del modelo Ollama (chat con tools)")
        except httpx.RequestError as e:
            raise RuntimeError(f"Error conectando con Ollama: {e}")
        except Exception as e:
            raise RuntimeError(f"Error: {e}")

    def generate(self, prompt: str, temperature: float = 0.85) -> str:
        client = self._get_client()
        def _do():
            resp = client.post(self.gen_url, json=self._payload(prompt, temperature), headers=self._headers())
            resp.raise_for_status()
            return (resp.json().get("response") or "").strip()
        try:
            return self._retry(_do)
        except httpx.TimeoutException:
            raise TimeoutError("Timeout del modelo Ollama")
        except httpx.RequestError as e:
            raise RuntimeError(f"Error conectando con Ollama: {e}")
        except Exception as e:
            raise RuntimeError(f"Error: {e}")

    def generate_stream(self, prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
        client = self._get_client()
        def _do():
            with client.stream("POST", self.gen_url, json=self._payload(prompt, temperature, stream=True), headers=self._headers()) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = obj.get("response", "")
                    if token:
                        yield token
        try:
            yield from self._retry(_do)
        except httpx.TimeoutException:
            raise TimeoutError("Timeout del modelo Ollama (streaming)")
        except httpx.RequestError:
            raise RuntimeError("Error conectando con Ollama (streaming)")
        except Exception as e:
            raise RuntimeError(f"Error streaming: {e}")

register_provider("ollama", OllamaProvider)