# Task 3: Playbook Engine

## Files
- Create: `backend/playbooks.py`
- Modify: `backend/workflows.py` — delegate to playbooks

## playbooks.py

### PLAYBOOKS dict — 5 playbooks

Each playbook has: `name`, `description`, `target_type`, `depth_estimate`, `steps`.

Steps are arrays of `{id, label, tool}` objects. Each `tool` is a function name in the `hacking` module.

**playbook 1 — recon_web:**
- name: "Reconocimiento Web"
- target_type: "domain"
- steps: dns, subdomains, ports, tech, dirs

**playbook 2 — web_audit:**
- name: "Auditoría Web"
- target_type: "url"
- steps: tech, headers(note: no tool yet, skip), ssl, sqli, xss, lfi, dirs

**playbook 3 — osint_domain:**
- name: "OSINT de Dominio"
- target_type: "domain"
- steps: dns, subdomains, certs, geo

**playbook 4 — password_audit:**
- name: "Auditoría de Credenciales"
- target_type: "any"
- steps: hash_id, hash_crack

**playbook 5 — full_scan:**
- name: "Escaneo Completo"
- target_type: "domain"
- steps: dns, subdomains, ports, tech, dirs, sqli, xss, ssl, certs, report(note: skip, no tool)

### Functions

`list_playbooks() -> dict` — return name, description, target_type, depth_estimate for all

`run_playbook(name, target, depth="rapido", hacking_module=None, target_engine=None, memory_engine=None, conv_id=None, progress_callback=None) -> dict`

Execution logic:
1. Look up playbook by name, return error if not found
2. Iterate steps, for each:
   - Call progress_callback(step.label, progress_pct) if provided
   - Get tool function from hacking_module via getattr
   - If tool exists, call tool(target), else skip with note
   - Append result to results list
   - If memory_engine and conv_id, store step result in memory_engine.merge_operational
3. On completion, store historical in memory_engine if available
4. Return {playbook, target, depth, steps_completed, results, summary}

### Headers check note
For `check_headers` step in web_audit, since there's no dedicated function, use `detect_tech` result's headers as a fallback.

### Report step note
For `generate_report` in full_scan, since there's no tool yet, simply append a placeholder step result noting "report generation available via /reporte".

## workflows.py modification
Add at the top:
```python
# DEPRECATED — Use playbooks.py instead
from playbooks import list_playbooks, run_playbook
```
Replace existing WORKFLOWS dict with empty dict `{}`.
Keep `ejecutar_workflow` and `listar_workflows` as thin wrappers that call playbook functions for backward compatibility.

## Global Constraints
- Must work on Windows
- Python 3.10+
- All user-facing text in Spanish
- Importable without side effects
