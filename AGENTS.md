# Karpathy Behavioral Guidelines

Estas reglas aplican a todo agente que trabaje en Artenisa. Son obligatorias, no opcionales.

## 1. Think Before Coding
No asumas. No escondas confusion. Muestra tradeoffs.
- Si algo no está claro, PARA. Nombra qué no entiendes. Pregunta.
- Si hay múltiples interpretaciones, PRESÉNTALAS. No elijas en silencio.
- Si existe una aproximación más simple, DILO.

## 2. Simplicity First
Código mínimo que resuelve el problema. Nada especulativo.
- Sin features más allá de lo pedido.
- Sin abstracciones para código de un solo uso.
- Sin "flexibilidad" o "configurabilidad" que no se solicitó.
- Si escribiste 200 líneas y podían ser 50, REESCRÍBELAS.

## 3. Surgical Changes
Toca solo lo necesario. Limpia solo tu propio desorden.
- No "mejores" código, comentarios o formato adyacente.
- No refactorices lo que no está roto.
- Cada línea cambiada debe rastrearse directamente al pedido del usuario.
- Si tu cambio deja huérfanos (imports, variables), elimínalos. No elimines dead code preexistente.

## 4. Goal-Driven Execution
Define criterios de éxito. Itera hasta verificar.
- "Agrega validación" → "Escribe tests para inputs inválidos, luego hazlos pasar"
- "Arregla el bug" → "Escribe un test que lo reproduzca, luego hazlo pasar"
- Tareas multi-paso: muestra plan breve con verify points.

---

## Session 2026-07-14

### Committed Baseline
- The final commit is at `71a9023` (`feat: six real-tool Telegram wizards + Karpathy guidelines + remediation`).
- Generic Kali tool execution was committed in `f84cad2`; the earlier Phase 2
  Kali/Nmap and Telegram UX baseline is `a65ec1b`.

### Implemented Work (Tasks 1-13)
Six real-tool Telegram wizards (Recon Nmap, Web recon/audit, Crack Hash, Payload Reverse/Webshell, Red Nmap, OSINT Email/Domain) with:
- Karpathy behavioral guidelines integrated as project rules and OpenCode skill.
- Scoped wizard sessions (8-hex session ID, 30-min TTL, owner/chat binding).
- Stale/foreign callback rejection with show_alert without shared-message mutation.
- Web target validation (parser-differential safe, private/del/C1/rejected).
- Safe Telegram delivery (Markdown fallback, unrelated BadRequest propagation).
- Supported hash validation (MD5/SHA*, integrated+custom dictionaries).
- Consume-before-I/O terminal transitions with one-shot state.
- Document/media registration and audited failure paths.
- Task ownership isolation (optional user_id filter in TaskQueue, pass from commands).
- Voice handler offloaded to asyncio.to_thread.
- Transactional wizard transitions (state commit only after successful delivery).
- Honest OSINT failures (structured errors, partial results with warnings).
- Web playbook contracts fixed (canonical URL routing per step signature).
- Aggregate all-failed playbook outcomes with preserved partial step details.
- Corrected 9 payload generators (Bash/Python/PHP/PowerShell reverse, nc, PHP/ASP/ASPX/JSP/Python CGI webshells) with dual-stack IPv4/IPv6, valid syntax.
- Uppercase/mixed-case hash cracking (casefold comparison, original input preserved).
- Fail-closed IPv6 CIDR policy (reject non-/128 and non-global networks).
- DNS/subdomain transport error contracts with legitimate empty-result distinction.
- Comprehensive test suite: 190 tests across Telegram, playbooks, TaskQueue, ToolsEngine, payloads/hash, CIDR.

### Final Test Evidence
```powershell
python -X utf8 -m unittest discover -s tests -p "test_telegram_wizards.py" -v   # 150 passed
python -X utf8 -m unittest tests.test_playbooks -v                                  # 15 passed
python -X utf8 -m unittest tests.test_task_queue_tools -v                           # 10 passed
python -X utf8 -m unittest tests.test_tools_engine -v                               # 5 passed
python -X utf8 -m unittest tests.test_hacking_full -v                               # 10 passed (1 skip)
python -X utf8 -m py_compile backend/telegram_bot.py ...                            # exit 0
git diff --check                                                                     # no whitespace errors
```
- Total: 190 passed, 0 failed, 0 errors (1 skip: PHP parser unavailable).
- The Telegram suite intentionally emits simulated operation-failure tracebacks
  and Markdown fallback warnings from passing negative-path tests.

### Final Telegram Deployment
- `docker compose build artenisa-telegram-bot` exited 0 and produced image
  `sha256:8cafbfe778d1310dc14083c478cbf5943424cd8dce45d8497266edf604d33efe`.
- `docker compose up -d --no-deps --force-recreate artenisa-telegram-bot` recreated
  the container. Logs contain `[OK] Bot de Artenisa sincronizado y escuchando en Telegram...`
  with no tracebacks, conflicts, or import errors.
- Backend (`asistente-ia-artenisa-backend`) and Kali (`asistente-ia-artenisa-kali-tools`)
  containers remained healthy with the same IDs; neither was rebuilt.
- Interactive smoke testing was not performed.

### Out-of-Scope / Residual Risks
- DNS-resolution and redirect-based SSRF protection remains outside scope
  per approved design (`docs/superpowers/specs/2026-07-14-telegram-wizard-stabilization-design.md:20-27`).
- Cancelling a running TaskQueue entry does not stop the underlying tool execution.
- The voice handler offloads blocking work to a thread but the test suite does not
  include live FFmpeg/transcription integration tests.
- No VPN/proxy support for offensive tool traffic; all operations use direct connections.
- Interactive Telegram smoke tests were not performed.
- `tests/test_api.py` remains outside the gate (10 pre-existing failures from token/contract churn).
- Root-level prompt files (`PLAN_CORRECTO_OPENCODE.md`, `PROMPT_OPENCODE_EXPLÍCITO.md`,
  `PROMPT_OPENCODE_FINAL.md`) describe earlier superseded tool scopes and are excluded
  from the committed tree to avoid documenting unsupported capabilities.

### Git State (pre-commit)
- Tracked modifications and new files staged for the single final commit.
