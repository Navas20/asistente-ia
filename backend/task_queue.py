import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"


class TaskQueue:
    def __init__(self, max_concurrent=3):
        self.max_concurrent = max_concurrent
        self._tasks = {}
        self._queue = []
        self._active = 0
        self._lock = threading.Lock()
        self._load_tasks()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def submit(self, task_type, target, params=None):
        now = _now()
        task_id = uuid.uuid4().hex[:6].upper()
        task = {
            "id": task_id,
            "type": task_type,
            "target": target,
            "params": params or {},
            "status": "queued",
            "progress": 0,
            "current_step": "",
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }
        with self._lock:
            self._tasks[task_id] = task
            self._queue.append(task_id)
            self._save()
        logger.info("Tarea %s encolada: %s %s", task_id, task_type, target)
        return task_id

    def get_status(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
        if task is None:
            return {"error": "Tarea no encontrada"}
        return dict(task)

    def list_tasks(self, limit=10):
        with self._lock:
            sorted_tasks = sorted(
                self._tasks.values(),
                key=lambda t: t["created_at"],
                reverse=True,
            )
        return sorted_tasks[:limit]

    def cancel(self, task_id):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task["status"] in ("queued", "running"):
                task["status"] = "cancelled"
                if task_id in self._queue:
                    self._queue.remove(task_id)
                self._save()
                logger.info("Tarea %s cancelada", task_id)
                return True
            return False

    def update_progress(self, task_id, progress, step=""):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["progress"] = progress
            if step:
                task["current_step"] = step
            self._save()

    def complete(self, task_id, result):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["status"] = "completed"
            task["progress"] = 100
            task["completed_at"] = _now()
            task["result"] = result
            self._save()
        logger.info("Tarea %s completada", task_id)

    def fail(self, task_id, error):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task["status"] = "failed"
            task["error"] = error
            task["completed_at"] = _now()
            self._save()
        logger.error("Tarea %s fallida: %s", task_id, error)

    # ------------------------------------------------------------------ #
    # Worker loop
    # ------------------------------------------------------------------ #

    def _worker_loop(self):
        while True:
            time.sleep(0.5)
            with self._lock:
                if self._active >= self.max_concurrent or not self._queue:
                    continue
                task_id = self._queue.pop(0)
                task = self._tasks.get(task_id)
                if task is None:
                    continue
                task["status"] = "running"
                task["started_at"] = _now()
                self._active += 1
                self._save()
            logger.info("Tarea %s iniciada", task_id)
            t = threading.Thread(
                target=self._run_task,
                args=(task_id, dict(task)),
                daemon=True,
            )
            t.start()

    def _run_task(self, task_id, task):
        try:
            try:
                from playbooks import run_playbook
                import hacking
            except ImportError:
                from backend.playbooks import run_playbook
                from backend import hacking

            def progress_callback(step, pct):
                self.update_progress(task_id, pct, step)

            params = task.get("params", {})
            target = task["target"]
            pb_name = params.get("playbook", "")
            depth = params.get("depth", "rapido")

            result = run_playbook(
                name=pb_name,
                target=target,
                depth=depth,
                hacking_module=hacking,
                progress_callback=progress_callback,
            )

            self.complete(task_id, result)
        except Exception as e:
            logger.exception("Error ejecutando tarea %s", task_id)
            self.fail(task_id, str(e))
        finally:
            with self._lock:
                self._active -= 1

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load_tasks(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not TASKS_FILE.exists():
            self._tasks = {}
            self._queue = []
            return
        try:
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._tasks = data.get("tasks", {})
            self._queue = data.get("queue", [])
            self._queue = [tid for tid in self._queue if tid in self._tasks]
            logger.info(
                "Tareas cargadas: %d activas, %d en cola",
                len(self._tasks),
                len(self._queue),
            )
        except Exception as e:
            logger.warning("No se pudieron cargar tareas: %s", e)
            self._tasks = {}
            self._queue = []

    def _save(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            data = {
                "tasks": self._tasks,
                "queue": self._queue,
            }
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Error guardando tareas: %s", e)


def _now():
    return datetime.now(timezone.utc).isoformat()
