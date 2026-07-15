# Telegram Final Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the release-blocking defects found by the whole-change review while preserving the approved six real-tool Telegram wizards.

**Architecture:** Fix defects at their source contracts rather than adding Telegram-only disguises. Playbooks receive the right argument shape, generators return usable text, TaskQueue gains optional owner filtering, nonterminal wizard state commits only after successful delivery, and OSINT preserves upstream failures.

**Tech Stack:** Python 3, `unittest`, python-telegram-bot, TaskQueue, existing hacking helpers, Docker Compose.

## Global Constraints

- Expose only these Telegram operations: Recon Nmap Quick/Normal/Full; Web `recon_web`/`web_audit`; Crack Hash integrated/custom; Payload Reverse Shell/Webshell; Red Nmap Quick/Normal/Full; OSINT Email/Domain.
- Do not expose or simulate Nikto, SQLMap, Meterpreter, WiFi attacks, Person search, fake passwords, or fake scan results.
- Preserve eight-hex wizard session IDs, 30-minute TTL, owner/chat binding, stale/foreign callback rejection, consume-before-I/O terminal transitions, strict endpoint grammar, safe Telegram fallback, and audit logging.
- Preserve API callers by making TaskQueue owner filters optional.
- DNS-resolution, DNS-rebinding, subresource, and redirect SSRF defenses beyond the current literal-target policy remain explicitly outside this change, as specified in `docs/superpowers/specs/2026-07-14-telegram-wizard-stabilization-design.md:20-27`.
- Reject non-global IPv6 CIDRs under the existing literal-target policy.
- Do not commit per task. The user requested one final commit after all verification and deployment.

---

### Task 9: Web Playbook Contracts And Outcomes

**Files:**
- Modify: `backend/playbooks.py`
- Modify: `backend/task_queue.py`
- Modify: `backend/hacking/web.py`
- Modify: `backend/telegram_bot.py`
- Test: `tests/test_playbooks.py`
- Test: `tests/test_telegram_wizards.py`

**Interfaces:**
- Consumes: normalized absolute HTTP(S) URL from the Telegram Web wizard.
- Produces: step-specific calls using hostname for DNS/subdomain/port steps, URL for HTTP steps, `(hostname, port)` for SSL, and `(url, query_parameter)` for SQLi/XSS/LFI probes.
- Produces: explicit failed transport results and an aggregate task failure when every playbook step fails.

- [ ] **Step 1: Write failing routing tests**

Add tests that run each playbook with `https://example.com:8443/search?q=1` and assert the exact step arguments described above. Add transport-failure tests proving `status == 0`, all failed directory requests, and all failed steps are not reported as successful.

- [ ] **Step 2: Verify RED**

Run: `python -X utf8 -m unittest tests.test_playbooks -v`

Expected: failures showing bare-host URL calls, wrong SSL/probe arity, or false-success outcomes.

- [ ] **Step 3: Implement minimal adapters**

Keep one canonical absolute URL as the playbook target. In `run_playbook`, parse it once and route each known Web step to the argument shape its existing function declares. Use the first query key, with `q` as the deterministic fallback. Preserve explicit per-step errors and return an aggregate error only when no step succeeds.

- [ ] **Step 4: Verify GREEN**

Run: `python -X utf8 -m unittest tests.test_playbooks -v`

Run: `python -X utf8 -m unittest discover -s tests -p "test_telegram_wizards.py" -v`

Expected: all tests pass.

### Task 10: Real Payloads, Hash Case, And IPv6 CIDRs

**Files:**
- Modify: `backend/hacking/payloads.py`
- Modify: `backend/hacking/crypto.py`
- Modify: `backend/tools_engine.py`
- Test: `tests/test_hacking_full.py`
- Test: `tests/test_tools_engine.py`
- Test: `tests/test_telegram_wizards.py`

**Interfaces:**
- Consumes: the existing Reverse Shell and Webshell callback values.
- Produces: syntactically valid Bash, Python, PHP, and PowerShell reverse-shell templates plus PHP, ASP, ASPX, JSP, and Python CGI webshell templates.
- Produces: case-insensitive digest comparison while retaining the original hash in returned data.

- [ ] **Step 1: Write failing generator, hash, and CIDR tests**

Add table-driven tests for every Telegram-exposed payload choice. Parse generated Python with `ast`, assert corrected language-specific syntax markers for templates without local compilers, verify Python uses dual-stack connection setup, verify uppercase integrated/custom hashes crack, and reject `::1/128`, `fc00::/7`, `fe80::/10`, `ff00::/8`, and IPv4-mapped private IPv6 CIDRs.

- [ ] **Step 2: Verify RED**

Run: `python -X utf8 -m unittest tests.test_hacking_full tests.test_tools_engine -v`

Expected: failures for damaged templates, uppercase comparison, and private IPv6 CIDRs.

- [ ] **Step 3: Implement minimal source fixes**

Replace damaged constants with standalone valid templates; use `socket.create_connection()` for Python reverse shells and bracket numeric IPv6 in PHP socket URIs. Normalize only the comparison hash with `casefold()`. Make CIDR validation version-aware and fail closed for non-global IPv6 networks.

- [ ] **Step 4: Verify GREEN**

Run: `python -X utf8 -m unittest tests.test_hacking_full tests.test_tools_engine -v`

Run: `python -X utf8 -m unittest discover -s tests -p "test_telegram_wizards.py" -v`

Expected: all tests pass.

### Task 11: Telegram Task Ownership And Voice Concurrency

**Files:**
- Modify: `backend/task_queue.py`
- Modify: `backend/telegram_bot.py`
- Test: `tests/test_task_queue_tools.py`
- Test: `tests/test_telegram_wizards.py`

**Interfaces:**
- Produces: `TaskQueue.get_status(task_id, user_id=None)` and `TaskQueue.list_tasks(limit=20, user_id=None)`; omitted owner retains service-level global behavior.
- Requires: every Telegram Nmap/Web/OSINT submission stores `params["user_id"] = uid`.
- Produces: the existing voice conversion/transcription behavior without blocking the async event loop.

- [ ] **Step 1: Write failing isolation and concurrency tests**

Add two-user queue and Telegram command tests proving a foreign task is indistinguishable from a missing task and is absent from lists. Add submission tests for owner metadata. Add an async voice test that patches `asyncio.to_thread` and proves the blocking pipeline is delegated.

- [ ] **Step 2: Verify RED**

Run: `python -X utf8 -m unittest tests.test_task_queue_tools -v`

Run the named ownership/voice tests from `tests.test_telegram_wizards`.

Expected: global task leakage, ownerless playbook submissions, and direct blocking calls.

- [ ] **Step 3: Implement minimal ownership and thread delegation**

Filter under the TaskQueue lock before applying list limits. Pass the Telegram caller UID from `/tarea` and `/tareas`; keep API/internal calls unchanged. Move file conversion, FFmpeg, transcription, and cleanup into one synchronous helper invoked with `await asyncio.to_thread(...)`.

- [ ] **Step 4: Verify GREEN**

Run: `python -X utf8 -m unittest tests.test_task_queue_tools -v`

Run: `python -X utf8 -m unittest discover -s tests -p "test_telegram_wizards.py" -v`

Expected: all tests pass.

### Task 12: Transactional Wizard Transitions And Honest OSINT

**Files:**
- Modify: `backend/hacking/osint.py`
- Modify: `backend/telegram_bot.py`
- Test: `tests/test_telegram_wizards.py`

**Interfaces:**
- Produces: nonterminal wizard state mutation only after the corresponding Telegram edit/reply succeeds.
- Produces: Email OSINT result data with source-specific warnings and aggregate `ok`, `partial`, or `error` status.
- Preserves: unrelated Telegram errors still propagate; terminal one-shot states remain consumed before I/O.

- [ ] **Step 1: Write failing transition and OSINT tests**

For all six type transitions plus reverse language, hash-to-dictionary, and custom dictionary selection, inject a non-Markdown delivery failure and assert state is unchanged. Patch Email DNS/HTTP sources to produce complete and partial failure, asserting warnings, user copy, and non-`ok` audit status.

- [ ] **Step 2: Verify RED**

Run the named new tests from `tests.test_telegram_wizards`.

Expected: state advances before delivery and real Email failures appear successful.

- [ ] **Step 3: Implement minimal transactional transitions and OSINT status**

Build the next state without mutating the stored dictionary, deliver the next UI, then commit state. For a newly created wizard, remove only that same session if initial delivery fails. Preserve DNS `NoAnswer` as a valid empty result while representing resolver/dependency/HTTP failures explicitly; render partial data with warnings and audit `partial`/`failed` accordingly.

- [ ] **Step 4: Verify GREEN**

Run: `python -X utf8 -m unittest discover -s tests -p "test_telegram_wizards.py" -v`

Expected: all tests pass.

### Task 13: Final Review, Deployment, Documentation, And Commit

**Files:**
- Modify: `AGENTS.md`
- Create or update: `OPENCODE_ENTREGA.md`

- [ ] **Step 1: Run all related suites**

Run the Telegram, playbook, Kali server, ToolsEngine, TaskQueue, router, Dockerfile, and prompt-limit suites. Run `py_compile` and `git diff --check`.

- [ ] **Step 2: Complete whole-change review**

Review the complete diff against the approved design and this remediation plan. Resolve all in-scope findings before proceeding.

- [ ] **Step 3: Rebuild and recreate only Telegram**

Run `docker compose build artenisa-telegram-bot` followed by `docker compose up -d --no-deps --force-recreate artenisa-telegram-bot`. Verify stable container identity, running state, restart count, startup log, and absence of conflicts/tracebacks/import errors. Verify backend and Kali container identities did not change.

- [ ] **Step 4: Update durable documentation**

Record exact tests, image/container evidence, residual out-of-scope risks, and the lack of interactive Telegram smoke testing in `AGENTS.md` and `OPENCODE_ENTREGA.md`.

- [ ] **Step 5: Create the single final commit**

Inspect status, diff, and recent log. Stage only implementation, tests, approved plans, and delivery documentation. Exclude stale root prompts that describe unsupported tools. Commit once with a concise repository-style message.
