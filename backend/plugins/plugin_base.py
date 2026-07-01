import importlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PluginBase:
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    commands: list = None
    playbooks: list = None

    def __init__(self):
        self.commands = self.commands or []
        self.playbooks = self.playbooks or []

    def on_load(self):
        pass

    def on_unload(self):
        pass

    def handle_command(self, command: str, args: str, context: dict) -> dict:
        raise NotImplementedError

    def get_manifest(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "commands": self.commands,
            "playbooks": self.playbooks,
        }


class PluginManager:
    def __init__(self, plugins_dir: str = None):
        if plugins_dir is None:
            plugins_dir = Path(__file__).parent
        self.plugins_dir = Path(plugins_dir)
        self._plugins: dict[str, PluginBase] = {}

    def discover(self):
        for entry in self.plugins_dir.iterdir():
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                module_name = f"{entry.name}.plugin"
                spec = importlib.util.spec_from_file_location(
                    module_name, entry / "plugin.py"
                )
                if spec is None or spec.loader is None:
                    logger.warning("No hay plugin.py en %s", entry.name)
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type) and issubclass(attr, PluginBase) and attr is not PluginBase:
                        instance = attr()
                        instance.on_load()
                        self._plugins[instance.name] = instance
                        logger.info("Plugin cargado: %s v%s", instance.name, instance.version)
            except Exception as exc:
                logger.error("Error al cargar plugin desde %s: %s", entry.name, exc)

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        return self._plugins.get(name)

    def list_plugins(self) -> list:
        return [p.get_manifest() for p in self._plugins.values()]

    def handle_command(self, command: str, args: str, context: dict) -> dict:
        for plugin in self._plugins.values():
            if command in plugin.commands:
                return plugin.handle_command(command, args, context)
        return {"error": f"Ningún plugin maneja el comando '{command}'"}
