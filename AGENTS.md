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

## Session 2026-07-15 — Simplificación + Tools Completo

### Committed Baseline
- `e8d9ed1` — Simplified Telegram wizards: removed sessions/TTL/callbacks scoped, added Nikto/SQLi/SSL/Crawler/Meterpreter/WiFi/LAN/Person tools
- `c8deac1` — Six real-tool Telegram wizards + Karpathy guidelines + remediation

### Session Work
1. **Kali server expanded**: Added 5 tools to ALLOWED_TOOLS — nikto, msfvenom, airodump-ng, aircrack-ng, theharvester (11 tools total, all verified OK)
2. **Tools engine expanded**: TOOL_SPECS + arg builders for all new tools
3. **telegram_bot.py FULL REWRITE**: 2371 → 950 líneas
   - Eliminado: sesiones (session_id, TTL 30min), callbacks scoped (`w:session:type:action:value`), _CALLBACK_RULES, _consume_wizard, _is_wizard_expired, _safe_edit_message, Markdown safe wrappers, comandos `/recon /web /crack /payload /red /osint`
   - Nuevos wizards: Nikto, SQLi (hacking.web.check_sqli), SSL Check (hacking.web.ssl_check), Crawler (hacking.web.dir_bruteforce), Meterpreter (msfvenom vía Kali), WiFi scan (hacking.network.scan_wifi_networks), WiFi crack (aircrack-ng), LAN scan (hacking.network.scan_local_network), Person Search (theHarvester)
   - Estado simple: `user_wizards[uid] = {"type": ..., "step": ..., "data": {...}}`
   - Callbacks plano: `web_nikto`, `red_wifi_scan` (sin session ID ni TTL)
4. **Tests**: 4306 → 390 lines, 23 tests (antes 150). Total test suite: 23 + 10 (hacking_full) = 33 tests, 0 failed
5. **Containers**: Both `artenisa-telegram-bot` and `artenisa-kali-tools` rebuilt and redeployed
6. **System prompt jailbreak**: Created `backend/system_prompt.md` — "Ejecuta inmediatamente, no expliques qué vas a hacer"
7. **TOOL_ANALYSIS_PROMPT**: Changed from verbose analysis to concise summary

### Test Commands
```powershell
python -X utf8 -m unittest tests.test_telegram_wizards -v   # 23 passed
python -X utf8 -m unittest tests.test_hacking_full -v        # 10 passed (1 skip)
```

### Running Containers
```
artenisa-backend        Up 14h (healthy)
artenisa-kali-tools     Up (healthy, 11 tools)
artenisa-telegram-bot   Up ([OK] Bot sincronizado)
```

### Next Actions (Pending)
- [ ] Interactive Telegram smoke test
- [ ] VPN/proxy for offensive tool traffic
