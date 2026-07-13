import json
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .models import SubagentTask

TASKS_FILE = Path("data/subagents.json")
MAX_CONCURRENT = int(os.getenv("MAX_SUBAGENTS", "10"))
MAX_QUEUED = int(os.getenv("MAX_QUEUED_SUBAGENTS", "50"))


class SubagentManager:
    def __init__(self):
        self._tasks: list[SubagentTask] = []
        self._lock = threading.Lock()
        self._running: dict[str, threading.Thread] = {}
        self._pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT, thread_name_prefix="subagent")
        self._pending_queue = queue.Queue(maxsize=MAX_QUEUED)
        self._queue_worker_running = False
        self._load()
        self._start_queue_worker()

    def _start_queue_worker(self):
        if self._queue_worker_running:
            return
        self._queue_worker_running = True
        def _worker():
            while self._queue_worker_running:
                try:
                    task_id, task = self._pending_queue.get(timeout=2)
                    with self._lock:
                        active = sum(1 for t in self._tasks if t.status == "running")
                        if active < MAX_CONCURRENT:
                            task.status = "running"
                            self._save()
                            future = self._pool.submit(self._run_task, task_id)
                            future.add_done_callback(lambda f: self._pending_queue.task_done())
                        else:
                            self._pending_queue.put((task_id, task))
                except queue.Empty:
                    continue
                except Exception:
                    pass
        t = threading.Thread(target=_worker, daemon=True, name="subagent-queue")
        t.start()

    def _load(self):
        if TASKS_FILE.exists():
            try:
                data = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
                self._tasks = [SubagentTask(**d) for d in data]
            except Exception:
                pass

    def _save(self):
        TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = [t.model_dump() for t in self._tasks]
        TASKS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def launch(self, name: str, target: str, task: str, model: str = "",
               provider: str = "openrouter", parent_id: str = "") -> SubagentTask:
        with self._lock:
            active = sum(1 for t in self._tasks if t.status == "running")
            t = SubagentTask(
                name=name, target=target, task=task,
                model=model, provider=provider, parent_id=parent_id,
                status="running" if active < MAX_CONCURRENT else "pending",
                progress=0
            )
            self._tasks.append(t)
            self._save()

        if t.status == "running":
            future = self._pool.submit(self._run_task, t.id)
        else:
            try:
                self._pending_queue.put_nowait((t.id, t))
            except queue.Full:
                t.status = "failed"
                t.error = "Queue full (max queued reached)"
                self._save()
        return t

    def _run_task(self, task_id: str):
        task = self._get(task_id)
        if not task:
            return
        try:
            from providers import get_provider
            provider = get_provider(task.provider)
            if not provider:
                task.status = "failed"
                task.error = f"Provider '{task.provider}' not available"
                self._save()
                return
            prompt = f"Target: {task.target}\nTask: {task.task}\nExecute tools and analyze. Return findings."
            result = provider.generate(prompt)
            if isinstance(result, dict):
                text = result.get("response", result.get("text", str(result)))
            else:
                text = str(result)
            task.result = text[:2000]
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.progress = 100
            from findings.auto_extract import extract_findings
            from findings.engine import FindingsManager
            fm = FindingsManager()
            findings = extract_findings("subagent", text, host=task.target, phase="recon")
            for f in findings:
                if not fm.exists(f.title, f.host):
                    fm.save(f)
            task.findings_count = len(findings)
        except Exception as e:
            task.status = "failed"
            task.error = str(e)[:500]
        self._save()
        self._running.pop(task_id, None)

    def list(self, status: str | None = None) -> list[SubagentTask]:
        with self._lock:
            tasks = list(self._tasks)
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks[-50:]

    def _get(self, task_id: str) -> SubagentTask | None:
        for t in self._tasks:
            if t.id == task_id:
                return t
        return None

    def get(self, task_id: str) -> dict | None:
        t = self._get(task_id)
        return t.model_dump() if t else None

    def cancel(self, task_id: str) -> bool:
        t = self._get(task_id)
        if t and t.status in ("running", "pending"):
            t.status = "cancelled"
            self._save()
            return True
        return False

    def running_count(self) -> int:
        return sum(1 for t in self._tasks if t.status == "running")

    def stats(self) -> dict:
        all_t = self._tasks
        return {
            "total": len(all_t),
            "running": sum(1 for t in all_t if t.status == "running"),
            "pending": sum(1 for t in all_t if t.status == "pending"),
            "completed": sum(1 for t in all_t if t.status == "completed"),
            "failed": sum(1 for t in all_t if t.status == "failed"),
            "cancelled": sum(1 for t in all_t if t.status == "cancelled"),
            "max_concurrent": MAX_CONCURRENT,
            "pool_size": self._pool._max_workers,
            "queue_size": self._pending_queue.qsize(),
        }

    def stop(self):
        self._queue_worker_running = False
        self._pool.shutdown(wait=False)
