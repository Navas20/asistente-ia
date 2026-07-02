# Task 4: Async Task Queue

## File
Create: `backend/task_queue.py`

## TaskQueue class

`TaskQueue(max_concurrent=3)`

### Constructor
- Accept `max_concurrent` (default 3)
- Initialize `_tasks: dict`, `_queue: list`, `_active: int = 0`, `_lock: threading.Lock()`
- Load existing tasks from `data/tasks.json` (relative to backend/)
- Start a daemon worker thread that runs `_worker_loop`

### Methods

`submit(task_type: str, target: str, params: dict = None) -> str`
- Generate task ID: 6-char uppercase hex (uuid4 hex[:6])
- Task dict: `{id, type, target, params, status: "queued", progress: 0, current_step: "", created_at, started_at: None, completed_at: None, result: None, error: None}`
- Store, append to queue, save, return task_id

`get_status(task_id: str) -> dict`
- Return task dict or `{"error": "Task not found"}`

`list_tasks(limit=10) -> list`
- Return sorted by created_at desc, limited

`cancel(task_id: str) -> bool`
- Set status to "cancelled" if queued or running, save

`update_progress(task_id, progress: int, step: str = "")`
- Update task progress and current_step, save

`complete(task_id, result: dict)`
- Set status="completed", progress=100, completed_at, result, save

`fail(task_id, error: str)`
- Set status="failed", error, completed_at, save

### _worker_loop
- Run in a daemon thread, loop with time.sleep(0.5)
- Check if active < max_concurrent and queue has items
- Pop from queue, set status="running", started_at
- Increment active, spawn `_run_task` in a daemon thread

### _run_task(task_id, task)
- In a try/except:
  - Import playbooks and hacking modules
  - Define a `progress_callback` closure that calls `self.update_progress`
  - Extract target, pb_name, depth from task params
  - Call `run_playbook(pb_name, target, depth, hacking_module=hacking, progress_callback=progress_callback)`
  - Call `self.complete(task_id, result)`
- On exception: call `self.fail(task_id, str(e))`
- Finally: decrement `_active` with lock

### Persistence
- `data/tasks.json` relative to backend/
- Load on init, save after every mutation
- Thread-safe via `_lock`

## Global Constraints
- Windows compatible
- Python 3.10+
- All text in Spanish
- Importable without side effects
- Use only stdlib (threading, json, uuid, time, logging, pathlib)
