import asyncio
import os
from pathlib import Path

from .models import LogSource


class LogMonitor:
    def __init__(self):
        self._sources: list[LogSource] = []
        self._running = False
        self._positions: dict[str, int] = {}
        self._callbacks: list = []

    def add_source(self, source: LogSource):
        if source not in self._sources:
            self._sources.append(source)

    def remove_source(self, source_id: str):
        self._sources = [s for s in self._sources if s.id != source_id]

    def list_sources(self) -> list[LogSource]:
        return list(self._sources)

    def on_line(self, callback):
        self._callbacks.append(callback)

    async def start(self):
        self._running = True
        for src in self._sources:
            path = Path(src.path)
            if path.exists():
                self._positions[src.path] = path.stat().st_size
        asyncio.create_task(self._poll_loop())

    def stop(self):
        self._running = False

    async def _poll_loop(self):
        while self._running:
            for src in self._sources:
                if not src.enabled:
                    continue
                path = Path(src.path)
                if not path.exists():
                    continue
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        pos = self._positions.get(src.path, 0)
                        if pos > path.stat().st_size:
                            pos = 0
                        f.seek(pos)
                        for line in f:
                            line = line.rstrip("\n\r")
                            if line:
                                for cb in self._callbacks:
                                    try:
                                        cb(src, line)
                                    except Exception:
                                        pass
                        self._positions[src.path] = f.tell()
                except Exception:
                    pass
            await asyncio.sleep(1)
