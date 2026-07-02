# Task 1: Target Context Engine + Memory System

## Files to Create
- `backend/target_engine.py`
- `backend/memory_engine.py`

## target_engine.py

`TargetEngine` class with:
- `set_target(user_id: int, target: str, target_type: str = "domain")` — save target to `data/target_state.json`
- `get_target(user_id: int) -> dict` — return {target, target_type, set_at, operation, elapsed_minutes}
- `clear_target(user_id: int)` — remove user's target
- `set_operation(user_id: int, operation: str)` — update current operation name
- `get_context_summary(user_id: int) -> str` — return formatted string like `"🎯 Objetivo: x | 📁 Recon | ⏱️ 12 min"` or empty string if no target

Persistence: JSON file at `data/target_state.json` (relative to `backend/`). Load on init, save on every mutation.

## memory_engine.py

`MemoryEngine` class with 3 layers.

**Layer 2 — Operational Context:**
- Uses DB at `DB_PATH` env var (default `data/conversations.db`)
- Table `operation_context` with columns: `id`, `conversation_id`, `context_json`, `updated_at`
- `store_operational(conv_id, context: dict)` — insert or replace
- `get_operational(conv_id) -> dict` — fetch and parse JSON
- `merge_operational(conv_id, updates: dict)` — get current, update, store

**Layer 3 — Historical Operations:**
- Table `operation_history` with columns: `id`, `target`, `operation`, `date`, `summary`, `findings_count`
- `store_historical(target, operation, summary, findings_count=0)` — insert
- `get_history(target) -> list` — return all rows for target ordered by date DESC

**Layer 1 — Smart Summary:**
- `needs_summary(conv_id, threshold=50) -> bool` — checks if message count in `messages` table is >0 and divisible by threshold
- `generate_summary(messages_text: str, llama_generate_fn) -> str` — calls llama_generate_fn with a summarization prompt

## Global Constraints
- Must work on Windows 10/11 without WSL
- Python 3.10+ compatible only
- All user-facing text in Spanish
- No external paid services required
- Minimum new dependencies
- Every new file must be importable without side effects at module level
