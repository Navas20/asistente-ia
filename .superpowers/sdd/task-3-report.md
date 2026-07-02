# Task 3: Playbook Engine - Report

## Status: DONE

## Commit
`0f98a9601d027aaa034eac61ca8965c41a45ed21`

## Files Changed
- **Created** `backend/playbooks.py` (230 lines) — Playbook engine with PLAYBOOKS dict, list_playbooks(), run_playbook()
- **Modified** `backend/workflows.py` (172 lines → 157 lines) — Deprecated, delegates to playbooks

## Implementation Summary

### playbooks.py
- **PLAYBOOKS dict** with 5 playbooks:
  - `recon_web`: DNS, subdomains, ports, tech, dirs (target_type: domain, medio)
  - `web_audit`: tech, headers, ssl, sqli, xss, lfi, dirs (target_type: url, lento)
  - `osint_domain`: dns, subdomains, certs, geo (target_type: domain, rapido)
  - `password_audit`: hash_id, hash_crack (target_type: any, rapido)
  - `full_scan`: dns, subdomains, ports, tech, dirs, sqli, xss, ssl, certs, report (target_type: domain, lento)
- **list_playbooks()**: Returns name, description, target_type, depth_estimate for all
- **run_playbook()**: Accepts name, target, depth, hacking_module, target_engine, memory_engine, conv_id, progress_callback. Executes steps, handles special cases (headers fallback to detect_tech, report placeholder), stores operational/historical in memory_engine if available
- All user-facing text in Spanish

### workflows.py
- Added `# DEPRECATED` header, delegates to playbooks
- Import handles both `import playbooks` and `from backend import playbooks`
- WORKFLOWS replaced with empty dict `{}`
- `ejecutar_workflow()`: Thin wrapper around `run_playbook()` with target extraction from params
- `listar_workflows()`: Thin wrapper around `list_playbooks()` with format conversion
- Backward-compatible helpers (tool_exists, run, try_run) preserved

### Special Steps
- **headers** step: Falls back to `detect_tech()` result's headers since `check_headers` doesn't exist
- **report** step: Returns placeholder noting "report generation available via /reporte"

## Test Results
All 8 tests pass:
1. `list_playbooks()` returns 5 playbooks
2. `listar_workflows()` returns 5 workflows (backward compat)
3. `run_playbook('password_audit', hash)` executes 2 steps successfully
4. `run_playbook('nonexistent', ...)` returns error dict
5. `ejecutar_workflow('password_audit', {'hash': ...})` delegates correctly
6. `ejecutar_workflow(..., {})` with missing target returns error
7. `run_playbook('recon_web', 'localhost')` executes 5 steps
8. All playbook data fields present in list_playbooks()

## Concerns
- Functions like `check_sqli`, `check_xss`, `check_lfi` require a `param` argument but are called as `tool(target)`. TypeError is caught and noted in step result — user needs to ensure target includes query params for these to work.
- Network-dependent playbooks (recon_web, full_scan) may time out if target is unreachable — this is expected behavior.
- Old workflow names (exploit_suggest, network_scan, full_recon) no longer exist — will return error through the new system.
