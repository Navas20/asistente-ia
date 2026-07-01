# Artenisa v5.0 — De Bot de Comandos a Copiloto de Operaciones

## Resumen

Evolución de Artenisa de un bot que ejecuta herramientas a un copiloto
de operaciones con flujos guiados, contexto persistente, playbooks,
memoria estructurada, dashboard en vivo, tareas asíncronas y reportes
profesionales.

---

## 1. Motor de Objetivos (Target Context Engine)

### 1.1 Objetivo activo de sesión

El bot recuerda el objetivo actual de la sesión automáticamente:

```
Usuario: /objetivo ejemplo.com
Artenisa: ✅ Objetivo activo: ejemplo.com

Usuario: /recon
→ usa ejemplo.com automáticamente

Usuario: /webscan
→ usa ejemplo.com automáticamente
```

### 1.2 Display en menú

Encabezado del menú principal:

```
🎯 Objetivo: ejemplo.com
📁 Operación: Reconocimiento inicial
⏱️ Tiempo activo: 12 min
```

### 1.3 Almacenamiento

- Se guarda en `memories` con key `session_target`, `session_operation`, `session_started_at`
- Persiste entre mensajes y reinicios
- Comando `/objetivo <target>` para establecer
- Comando `/olvidar_objetivo` para limpiar

---

## 2. Flujos Guiados (Wizard System)

En lugar de comandos crudos, menús paso a paso:

### Flujo de Recon

```
Usuario pulsa: [🔍 Recon]

Artenisa:
¿Qué tipo de objetivo deseas analizar?
[🌐 Dominio] [🖥️ IP] [📱 Local] [📡 Red]

Usuario selecciona: 🌐 Dominio

Artenisa:
Ingresa el dominio o IP:

Usuario: ejemplo.com

Artenisa:
¿Qué profundidad de análisis deseas?
[⚡ Rápido (2-5 min)] [🔎 Normal (5-15 min)] [🧠 Profundo (15-60 min)]
```

### Implementación

Cada flujo es una máquina de estados simple:

```python
WIZARD_STATES = {
    "recon": {
        "type": Step("Tipo de objetivo", options=["dominio", "ip", "local", "red"]),
        "target": Step("Ingresa el objetivo"),
        "depth": Step("Profundidad", options=["rapido", "normal", "profundo"]),
    },
    ...
}
```

El estado del wizard se guarda en memoria por usuario (diccionario en `user_wizards`).
Cada step valida la entrada antes de avanzar.

---

## 3. Playbooks (Reemplaza "Ataque completo")

### Playbooks disponibles

```
📚 Playbooks

[🔍 Reconocimiento Web]
[🛡️ Auditoría de Superficie]
[🌐 Enumeración de Servicios]
[📧 OSINT de Dominio]
[🔐 Credenciales Expuestas]
[📄 Informe Ejecutivo]
```

### Estructura de un Playbook

```python
PLAYBOOK_RECON_WEB = {
    "name": "Reconocimiento Web",
    "description": "Escanea un objetivo web paso a paso",
    "steps": [
        {"tool": "dns_resolve", "label": "Resolución DNS"},
        {"tool": "subdomain_scan", "label": "Subdominios"},
        {"tool": "port_scan", "label": "Puertos comunes"},
        {"tool": "fingerprint", "label": "Fingerprinting"},
        {"tool": "dir_bruteforce", "label": "Directorios"},
        {"tool": "summary", "label": "Resumen de hallazgos"},
    ],
    "target_type": "domain",
}
```

### Ejecución

- Cada paso se ejecuta secuencialmente
- El bot reporta progreso después de cada paso
- Se puede cancelar en cualquier momento
- Al final, genera resumen de hallazgos

---

## 4. Memoria de 3 Capas

### Capa 1 — Memoria Reciente (últimos 20-50 mensajes)

- Historial completo de conversación
- Se inyecta directo en el prompt

### Capa 2 — Memoria Operativa (JSON estructurado)

Se guarda por conversación como JSON:

```json
{
  "target": "ejemplo.com",
  "target_type": "domain",
  "ip": "93.184.216.34",
  "ports": [{"port": 80, "service": "HTTP", "banner": "nginx/1.24.0"},
            {"port": 443, "service": "HTTPS", "banner": "nginx/1.24.0"}],
  "technologies": ["nginx", "WordPress", "PHP 8.1"],
  "subdomains": ["www", "mail", "admin"],
  "vulnerabilities": [{"type": "SQLi", "param": "id", "url": "/page.php?id=1"}]
}
```

Ventajas:
- El modelo responde preguntas factuales sin depender de resúmenes NL
- Se puede consultar: "¿Qué puertos estaban abiertos?"
- Persiste en tabla `operation_context`

### Capa 3 — Memoria Histórica (operaciones anteriores)

```json
{
  "operation_id": 15,
  "target": "ejemplo.com",
  "date": "2026-07-01",
  "critical_findings": 2,
  "services": ["nginx", "ssh", "mysql"],
  "summary": "Se detectaron 3 puertos abiertos..."
}
```

Permite:
- "Este dominio ya se analizó hace 3 días"
- "Comparado con el scan anterior, hay 2 puertos nuevos"

---

## 5. Dashboard en Vivo (Telegram)

### Mensaje editable con estado de operación

```
🎯 Operación: ejemplo.com
🔄 EN EJECUCIÓN (45%)

Puertos:    3  [22, 80, 443]
Subdominios: 12 [www, mail, ...]
Tecnologías: 4  [nginx, WP, PHP, MySQL]
Riesgos:    2  [Por revisar]

[📊 Actualizar] [📄 Reporte] [⏹ Detener]
```

### Implementación

- Se usa `bot.edit_message_text()` para actualizar el mismo mensaje
- Un thread worker envía actualizaciones periódicas
- El mensaje contiene el message_id para editarlo
- Al terminar, se marca como `✅ COMPLETADO` o `❌ DETENIDO`

---

## 6. Cola de Tareas y Ejecución Asíncrona

### Arquitectura

```
Telegram Bot → Task Queue (threading + cola interna) → Workers → Result → Notificación
```

### Comportamiento

- Las tareas largas se ejecutan en segundo plano
- El usuario recibe un ID de tarea:
  ```
  🔄 Tarea #A7F2 iniciada
  Objetivo: ejemplo.com
  Playbook: Reconocimiento Web
  Estado: Ejecutando (15%)
  Usa /tarea A7F2 para ver progreso.
  ```
- `/tareas` lista todas las tareas activas
- `/tarea A7F2` muestra estado detallado
- Al completarse, Artenisa envía notificación automática

### Implementación

- `TaskQueue` clase con cola FIFO + workers
- Cada tarea tiene: id, type, target, status, progress, result
- Se guardan en `data/tasks.json` para persistencia
- Máximo N tareas concurrentes (configurable)

---

## 7. Reportes Profesionales

### Formato

```
📄 INFORME DE AUDITORÍA
━━━━━━━━━━━━━━━━━━━━━━
Objetivo: ejemplo.com
Fecha: 2026-07-01
Duración: 34 min
Metodología: OWASP Top 10 + PTES

RESUMEN EJECUTIVO
─────────────────
Se identificaron 12 subdominios, 3 puertos abiertos,
4 tecnologías y 2 vulnerabilidades críticas.

SERVICIOS DETECTADOS
────────────────────
22/tcp  → SSH        → OpenSSH 8.9p1
80/tcp  → HTTP       → nginx 1.24.0
443/tcp → HTTPS      → nginx 1.24.0

HALLAZGOS CRÍTICOS
──────────────────
1. SQL Injection en /page.php?id= (CVSS 9.8)
2. XSS Reflejado en /search.php?q= (CVSS 6.1)

RECOMENDACIONES
───────────────
1. Actualizar nginx a última versión
2. Implementar WAF (ModSecurity)
3. Sanitizar inputs en /page.php
```

### Exportación

- Markdown (nativo)
- HTML con CSS embebido
- JSON estructurado
- PDF (via weasyprint o markdown-pdf)

Comando: `/reporte [format=md|html|json|pdf]`

---

## 8. Seguridad

### Controles

| Control | Implementación |
|---------|----------------|
| Whitelist de usuarios | `ALLOWED_USER_ID` (existente) + `ALLOWED_USER_IDS` (lista) |
| Roles | `admin` (todo), `operator` (herramientas), `viewer` (solo reportes) |
| Confirmación | Inline keyboard `[✅ Confirmar] [❌ Cancelar]` en acciones destructivas |
| Rate limiting | `@rate_limit(5, 60)` decorator: max 5 llamadas cada 60s |
| Auditoría | Tabla `audit_log`: quién, qué, cuándo, target, resultado |
| Sandbox | Ejecución en Docker container aislado (futuro) |
| Validación estricta | Regex whitelist para IPs, dominios, URLs |
| Límite concurrencia | Máximo 3 tareas simultáneas por usuario |

### Tabla `audit_log`

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    command TEXT,
    target TEXT,
    timestamp TEXT,
    status TEXT,
    output_truncated TEXT
);
```

---

## 9. Plugins (Arquitectura desde el inicio)

### Estructura de un plugin

```
backend/plugins/
  __init__.py
  shodan/
    __init__.py
    plugin.py        # ShodanPlugin(PluginBase)
    manifest.json    # name, version, description, commands, dependencies
    requirements.txt # requests
```

### PluginBase

```python
class PluginBase:
    name: str
    version: str
    description: str
    commands: list[str]  # comandos que registra
    playbooks: list[dict]  # playbooks que aporta

    def on_load(self): ...
    def on_unload(self): ...
    def handle_command(self, command, args, context): ...
    def get_manifest(self) -> dict: ...
```

### Ciclo de vida

1. Al iniciar, Artenisa escanea `backend/plugins/`
2. Carga cada plugin que tenga `manifest.json` válido
3. Registra comandos y playbooks del plugin
4. Si un plugin falla, no bloquea la carga de los demás

---

## 10. Telegram Bot (Implementación)

### Menú principal con ReplyKeyboardMarkup

```python
main_keyboard = ReplyKeyboardMarkup([
    ["🔍 Recon", "🌐 Web", "🔑 Crack"],
    ["💣 Payloads", "📡 Red", "🔎 OSINT"],
    ["📚 Playbooks", "📄 Reporte", "⚙️ Sistema"],
], resize_keyboard=True)
```

### Handlers nuevos

| Handler | Disparador |
|---------|------------|
| `handle_photo` | `filters.PHOTO` |
| `handle_voice` | `filters.VOICE` |
| `handle_document` | `filters.Document.ALL` (existente) |
| `handle_text` | `filters.TEXT & ~filters.COMMAND` |
| `handle_callback` | `filters.CallbackQuery` |
| `handle_command` | `filters.COMMAND` |

### Callback data pattern

```python
callback_data = f"{action}:{param1}:{param2}"
# Ejemplo: "recon:domain:normal"
# Ejemplo: "playbook:recon_web:start"
# Ejemplo: "confirm:yes:task_A7F2"
```

---

## 11. Archivos a modificar/crear

| Archivo | Acción |
|---------|--------|
| `backend/telegram_bot.py` | Reescribir completo con flujos, keyboards, voz, imagen, dashboard |
| `backend/main.py` | Sistema de contexto 3 capas + target engine + audit log |
| `backend/ataque.py` | Renombrar -> `backend/playbooks.py` con motor de playbooks |
| `backend/task_queue.py` | **Nuevo** — cola de tareas asíncronas |
| `backend/plugins/__init__.py` | **Nuevo** — cargador de plugins |
| `backend/plugins/plugin_base.py` | **Nuevo** — PluginBase clase abstracta |
| `backend/plugins/shodan/` | **Nuevo** — plugin ejemplo |
| `backend/report.py` | **Nuevo** — generador de reportes (MD, HTML, JSON, PDF) |
| `backend/dashboard.py` | **Nuevo** — lógica de dashboard en vivo |
| `backend/requirements.txt` | Añadir: pillow, pytesseract, pydub, weasyprint, jinja2 |
| `cli/asistente.py` | Flujos guiados + target engine (si aplica) |

---

## 12. Prioridad de Implementación (Top 3 del usuario)

1. **🎯 Motor de Objetivos** — target persistente + display en menú
2. **📚 Playbooks** — reemplazar sistema de ataques por playbooks estructurados
3. **🧠 Memoria estructurada** — capa 2 operativa + capa 3 histórica

Siguiente: flujos guiados → task queue → dashboard → reportes → plugins

---

## 13. No incluido en esta iteración

- Web UI (descartado por usuario)
- RAG / vector DB (futuro)
- Modo autónomo (futuro)
- Sandbox Docker (futuro)
- Multi-modelo (OpenAI, Anthropic) — se hará vía plugins
