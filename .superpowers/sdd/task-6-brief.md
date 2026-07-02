# Task 6: Plugin Architecture

## Files
Create:
- `backend/plugins/__init__.py`
- `backend/plugins/plugin_base.py`

## plugin_base.py

### PluginBase (abstract class)
```python
class PluginBase:
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    commands: list = []
    playbooks: list = []

    def on_load(self): pass
    def on_unload(self): pass
    def handle_command(self, command: str, args: str, context: dict) -> dict:
        raise NotImplementedError
    def get_manifest(self) -> dict:
        return {"name": self.name, "version": self.version, ...}
```

### PluginManager
- `__init__(self, plugins_dir: str = None)` — default to `Path(__file__).parent`
- `discover(self)` — scan subdirectories for `manifest.json`, import `{dir}.plugin`, find PluginBase subclasses, instantiate, call on_load(), register
- `get_plugin(name) -> PluginBase | None`
- `list_plugins() -> list` — return manifests
- `handle_command(command, args, context) -> dict` — find plugin that handles command, call it

## __init__.py
```python
from .plugin_base import PluginBase, PluginManager
__all__ = ["PluginBase", "PluginManager"]
```

## Global Constraints
- Windows compatible
- Python 3.10+
- Spanish text
- Importable without side effects
- stdlib only (importlib, json, pathlib, logging)
