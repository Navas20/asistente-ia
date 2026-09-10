import os
import logging
from typing import Generator, Optional

log = logging.getLogger("artenisa.providers")

PROVIDER_REGISTRY = {}

def register_provider(name: str, cls: type):
    PROVIDER_REGISTRY[name] = cls

def get_provider(name: str = None):
    name = name or os.getenv("ACTIVE_PROVIDER", "openrouter")
    cls = PROVIDER_REGISTRY.get(name)
    if not cls:
        raise ValueError(f"Provider '{name}' no encontrado. Disponibles: {list(PROVIDER_REGISTRY.keys())}")
    return cls()

def list_providers() -> list:
    return list(PROVIDER_REGISTRY.keys())

class BaseProvider:
    name = ""
    env_key = ""
    env_model = ""
    default_model = ""
    default_url = ""
    supports_tools = False

    def __init__(self):
        self.api_key = os.getenv(self.env_key, "")
        self.model = os.getenv(self.env_model, self.default_model)
        self.base_url = os.getenv(f"{self.env_key.replace('_KEY', '_URL')}", self.default_url)
        self.timeout = int(os.getenv(f"{self.env_key.replace('_KEY', '_TIMEOUT')}", "180"))

    def generate(self, prompt: str, temperature: float = 0.85) -> str:
        raise NotImplementedError

    def generate_stream(self, prompt: str, temperature: float = 0.85) -> Generator[str, None, None]:
        raise NotImplementedError

    def chat(self, messages: list, tools: list | None = None, temperature: float = 0.7) -> dict:
        """Chat con Tool Calling nativo (formato OpenAI-compat).

        messages: lista de diccionarios {role, content, tool_calls, tool_call_id}.
        Retorna normalize: {"content": str, "tool_calls": [{id, name, arguments: dict}]}."""
        raise NotImplementedError(f"Provider '{self.name}' no implementa chat() con tools")

    def list_models(self) -> list:
        return [self.model]

    def switch_model(self, model: str):
        self.model = model

    def switch_key(self, key: str):
        self.api_key = key
