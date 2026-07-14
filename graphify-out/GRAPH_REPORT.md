# Graph Report - asistente-ia  (2026-07-14)

## Corpus Check
- 124 files · ~49,750 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1189 nodes · 1923 edges · 118 communities (69 shown, 49 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 91 edges (avg confidence: 0.58)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `10dea44d`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- router.py
- Finding
- main.py
- __init__.py
- artenisa.ps1
- router.py
- BaseProvider
- Screen
- telegram_bot.py
- HackingAgent
- TaskQueue
- SubagentManager
- ProjectManager
- agent.py
- auth.py
- ChatService
- TestJARVIS
- chat
- .get_conn
- MemoryService
- repositories.py
- MCPServer
- LLMService
- audit.py
- models.py
- PluginBase
- execute
- MemoryEngine
- OASTManager
- call_ollama
- AuditService
- AuditLog
- TargetEngine
- chat.py
- llama_backend.py
- generate_report
- TaskRepository
- watchdog.sh
- memory.py
- execute_command
- security.py
- AuditRepository
- tools.py
- voice.py
- RateLimiter
- playbooks.py
- build_prompt
- _extract_memories_worker
- export_import.py
- opencode.json
- run_tests.sh
- PromptLimitsTests
- _handle_tareas
- graphify.js
- stop.sh
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- backup.sh
- entrypoint.sh
- setup_oracle.sh
- start.sh
- __init__.py
- Artenisa v5.0 — De Bot de Comandos a Copiloto de Operaciones
- 10. Defense / Blue Team Module (`backend/defense/`)
- CAPACIDADES OFENSIVAS TOTALES
- 🤖 AGENTS LAYER - Agentes Inteligentes
- JARVIS v4.0 — Guía de instalación
- File Structure
- Global Constraints
- Artenisa
- Skill: Artenisa Programming Excellence
- Artenisa Backend
- artenisa-programming.prompt.md
- Artenisa CLI
- Security Bypass Layers (6 capas)
- CVSS v3.1 Base Score Calculator
- Daniel Navas (Owner)
- Defense / Blue Team Module
- FastAPI Framework
- Hacking Agent (Comandante Ofensivo de Elite)
- Hacking Tools Module
- Kali Linux Environment
- Kill Chain Phases (Recon/Enum/Vuln/Exploit/Post-Exploit/Report)
- Live Dashboard (editable messages)
- Offensive Capabilities (15 categories)
- Offensive Decision Tree
- Ollama Setup (VC++ Redist Fix)
- OpenRouter LLM Client (Gemma 4 26B)
- Oracle Cloud Free Tier Deployment
- Pentest Engine (orchestrator)
- Playbook Engine
- Plugin System (PluginBase + PluginManager)
- Scope Validator (CIDR/domain/wildcard)
- Security Layer (AuditLog, RateLimiter, Roles)
- Sistema Operativo Mode (Activation)
- SQLite Database
- Target Context Engine
- Async Task Queue
- 3-Layer Memory Engine
- Wizard System (State Machine)

## God Nodes (most connected - your core abstractions)
1. `verify_token()` - 59 edges
2. `Finding` - 28 edges
3. `Incident` - 25 edges
4. `FindingsManager` - 25 edges
5. `extract_findings()` - 21 edges
6. `Screen` - 20 edges
7. `_make_finding()` - 19 edges
8. `_check_role()` - 18 edges
9. `execute()` - 16 edges
10. `SubagentManager` - 16 edges

## Surprising Connections (you probably didn't know these)
- `ChatService` --uses--> `ConversationRepository`  [INFERRED]
  services/chat_service.py → data_layer/repositories.py
- `MemoryService` --uses--> `ConversationRepository`  [INFERRED]
  services/memory_service.py → data_layer/repositories.py
- `MemoryService` --uses--> `MemoryRepository`  [INFERRED]
  services/memory_service.py → data_layer/repositories.py
- `AuditService` --uses--> `AuditRepository`  [INFERRED]
  security/audit.py → data_layer/repositories.py
- `_check_role()` --calls--> `get_role()`  [INFERRED]
  backend/telegram_bot.py → backend/security.py

## Import Cycles
- None detected.

## Communities (118 total, 49 thin omitted)

### Community 0 - "router.py"
Cohesion: 0.06
Nodes (25): AlertManager, AttackDetector, EvidenceCollector, ForensicPackage, Incident, LogSource, BaseModel, ResponseRule (+17 more)

### Community 1 - "Finding"
Cohesion: 0.09
Nodes (28): _extract_cert(), _extract_crack(), extract_credentials(), _extract_dirs(), _extract_dns(), _extract_email(), extract_findings(), _extract_geo() (+20 more)

### Community 2 - "main.py"
Cohesion: 0.08
Nodes (37): get_workflows(), list_providers_endpoint(), _run_browser(), run_workflow_endpoint(), set_system_prompt_endpoint(), tool_browse(), tool_copy(), tool_delete() (+29 more)

### Community 3 - "__init__.py"
Cohesion: 0.09
Nodes (35): decode_b64(), encode_b64(), generate_wordlist(), hash_crack(), hash_id(), banner_grab(), dns_enum(), get_local_ip() (+27 more)

### Community 5 - "router.py"
Cohesion: 0.09
Nodes (10): PentestEngine, generate_html(), generate_mermaid(), get_ordered_phases(), get_phase(), attack_graph(), attack_graph_html(), list_phases() (+2 more)

### Community 6 - "BaseProvider"
Cohesion: 0.08
Nodes (9): AnthropicProvider, Client, GroqProvider, Client, BaseProvider, list_providers(), register_provider(), OpenRouterProvider (+1 more)

### Community 7 - "Screen"
Cohesion: 0.09
Nodes (15): api_delete(), api_get(), api_post(), copy_to_clipboard(), elapsed_str(), fetch_system_prompt(), main(), save_code_block() (+7 more)

### Community 8 - "telegram_bot.py"
Cohesion: 0.18
Nodes (35): analizar(), _chat_api(), _check_role(), crack_shortcut(), _depth_keyboard(), _execute_immediate(), _execute_wizard(), _format_crack() (+27 more)

### Community 9 - "HackingAgent"
Cohesion: 0.08
Nodes (15): HackingAgent, AGENTS LAYER - Hacking Agent (Comandante Ofensivo)  Agente especializado en op, Obtiene el estado actual de la operación, Obtiene el resumen completo de la operación, Comandante Ofensivo de Élite          Agente especializado en:     - Reconoci, Guarda el progreso actual, # TODO: Implementar guardado a disco, Finaliza la operación actual (+7 more)

### Community 10 - "TaskQueue"
Cohesion: 0.14
Nodes (11): _build_summary(), list_playbooks(), Return name, description, target_type, depth_estimate for all playbooks., run_playbook(), _now(), TaskQueue, ejecutar_workflow(), listar_workflows() (+3 more)

### Community 11 - "SubagentManager"
Cohesion: 0.14
Nodes (5): get_provider(), SubagentManager, BaseModel, SubagentTask, launch_subagent()

### Community 13 - "agent.py"
Cohesion: 0.08
Nodes (23): Done, Files Modified This Session, Next Steps, Session 2026-07-14, activate_agent(), deactivate_agent(), end_operation(), execute_attack() (+15 more)

### Community 14 - "auth.py"
Cohesion: 0.12
Nodes (13): UploadFile, API Router - File management endpoints, upload_file(), get_task_endpoint(), API Router - Task queue endpoints, Obtiene el estado de una tarea, get_role(), SECURITY LAYER - Autenticación y autorización (+5 more)

### Community 15 - "ChatService"
Cohesion: 0.15
Nodes (7): ChatService, Servicio centralizado de chat, Crea una nueva conversación, Agrega un mensaje del usuario, Genera una respuesta del asistente, Genera una respuesta con streaming, Obtiene el historial de conversación

### Community 16 - "TestJARVIS"
Cohesion: 0.18
Nodes (3): api(), Tests de integración para JARVIS API.  Ejecutar: python tests/test_api.py Requis, TestJARVIS

### Community 17 - "chat"
Cohesion: 0.15
Nodes (14): chat(), chat_stream(), ChatRequest, ChatResponse, get_history(), get_history_endpoint(), get_memories(), load_all_memories() (+6 more)

### Community 18 - ".get_conn"
Cohesion: 0.22
Nodes (4): ConversationRepository, MemoryRepository, Repositorio de conversaciones, Repositorio de memoria (3 capas)

### Community 19 - "MemoryService"
Cohesion: 0.15
Nodes (9): MemoryService, Servicio de memoria con 3 capas: reciente, operacional, histórica, Obtiene contexto reciente de la conversación, Almacena contexto operacional (objetivo, progreso, etc), Obtiene contexto operacional, Actualiza el contexto operacional, Almacena operación histórica, Obtiene historial de operaciones por target (+1 more)

### Community 20 - "repositories.py"
Cohesion: 0.17
Nodes (9): load_env(), Configuración centralizada del proyecto, Carga variables de entorno desde backend/.env, DATA LAYER - Repositorios y acceso a datos, SECURITY LAYER - Rate Limiting, SERVICES LAYER - Servicio de Chat, SERVICES LAYER - Lógica de negocio central  Exporta las instancias de servicio, SERVICES LAYER - Servicio de LLM (OpenRouter) (+1 more)

### Community 21 - "MCPServer"
Cohesion: 0.19
Nodes (8): mcp_jsonrpc(), mcp_tools(), call_tool(), _describe_function(), list_tools(), MCPServer, callable, Request

### Community 22 - "LLMService"
Cohesion: 0.16
Nodes (7): LLMService, Client, Genera texto con streaming, Servicio centralizado de LLM con OpenRouter, Throttling entre requests, Retry con backoff exponencial, Genera texto sin streaming

### Community 23 - "audit.py"
Cohesion: 0.15
Nodes (8): FastAPI Entry Point - Punto de entrada de la aplicación, get_audit_logs_endpoint(), API Router - Audit endpoints, Obtiene los logs de auditoría recientes, get_target_endpoint(), API Router - Target management endpoints, Obtiene información de un target, SECURITY LAYER - Auditoría

### Community 24 - "models.py"
Cohesion: 0.27
Nodes (12): AuditEntry, ChatRequest, FileUploadResponse, MemoryItem, Message, PlaybookRequest, PlaybookStep, BaseModel (+4 more)

### Community 26 - "execute"
Cohesion: 0.29
Nodes (12): add_memory(), db(), delete_memory(), download_file(), execute(), get_conn(), init_db(), list_conversations() (+4 more)

### Community 29 - "call_ollama"
Cohesion: 0.22
Nodes (11): call_ollama(), call_ollama_safe(), _get_provider(), list_models(), Versión segura que no lanza excepciones., set_provider(), set_provider_model(), switch_model() (+3 more)

### Community 30 - "AuditService"
Cohesion: 0.29
Nodes (4): AuditService, Servicio de auditoría centralizado, Registra una acción en el log de auditoría, Obtiene los logs recientes

### Community 33 - "chat.py"
Cohesion: 0.24
Nodes (9): ChatResponse, chat_endpoint(), chat_stream_endpoint(), get_history_endpoint(), API Router - Chat endpoints, Endpoint de chat sin streaming, Endpoint de chat con streaming, Obtiene el historial de una conversación (+1 more)

### Community 34 - "llama_backend.py"
Cohesion: 0.36
Nodes (5): generate(), generate_stream(), get_client(), _retry(), _throttle()

### Community 35 - "generate_report"
Cohesion: 0.47
Nodes (8): generate_html(), generate_json(), generate_markdown(), generate_pdf(), generate_report(), _html_to_pdf(), _sanitize(), _ts()

### Community 37 - "watchdog.sh"
Cohesion: 0.53
Nodes (8): check_disk(), check_ollama(), is_running(), log(), run_backup(), watchdog.sh script, start_backend(), start_telegram()

### Community 38 - "memory.py"
Cohesion: 0.25
Nodes (7): get_history_endpoint(), get_memory_endpoint(), API Router - Memory endpoints, Obtiene el contexto completo de memoria, Almacena contexto operacional, Obtiene el historial de operaciones por target, store_memory_endpoint()

### Community 39 - "execute_command"
Cohesion: 0.25
Nodes (8): _auto_install(), execute_body(), execute_command(), _get_tool_name(), process_tool_commands(), Convierte un comando string en lista de argumentos segura., _safe_args(), search_web()

### Community 40 - "security.py"
Cohesion: 0.43
Nodes (6): decrypt(), _derive_key(), encrypt(), _get_machine_id(), load_key(), save_key()

### Community 41 - "AuditRepository"
Cohesion: 0.14
Nodes (8): AuditRepository, DatabaseConnection, FileRepository, Repositorio de archivos, Gestor de conexiones SQLite con WAL mode, Repositorio de auditoría, init_database(), Inicializa todas las tablas y directorios

### Community 42 - "tools.py"
Cohesion: 0.29
Nodes (5): file_write_endpoint(), API Router - Tool execution endpoints, Ejecuta una búsqueda web, Escribe en un archivo, web_search_endpoint()

### Community 43 - "voice.py"
Cohesion: 0.43
Nodes (4): init_stt(), record_from_mic(), transcribe(), transcribe_google()

### Community 44 - "RateLimiter"
Cohesion: 0.29
Nodes (4): RateLimiter, Rate limiter en memoria con buckets por clave, Verifica si se puede hacer la llamada, Decorator para rate limiting

### Community 45 - "playbooks.py"
Cohesion: 0.33
Nodes (4): list_playbooks_endpoint(), API Router - Playbook endpoints, Lista todos los playbooks disponibles, # TODO: Implementar lógica de ejecución

### Community 46 - "build_prompt"
Cohesion: 0.47
Nodes (6): build_prompt(), format_memories(), get_system_prompt(), get_system_prompt_endpoint(), _prepare_history_for_prompt(), _truncate_text()

### Community 47 - "_extract_memories_worker"
Cohesion: 0.33
Nodes (6): _extract_memories_worker(), Corre en segundo plano para no bloquear la respuesta, save_memories_batch(), search(), tool_grep(), trigger_memory_extraction()

### Community 48 - "export_import.py"
Cohesion: 0.40
Nodes (4): export_data(), import_data(), Exporta toda la base de datos a un JSON., Importa datos desde un JSON exportado.

### Community 49 - "opencode.json"
Cohesion: 0.50
Nodes (3): plugin, $schema, .opencode/plugins/graphify.js

### Community 50 - "run_tests.sh"
Cohesion: 0.50
Nodes (3): API_URL, AUTH_TOKEN, run_tests.sh script

### Community 52 - "_handle_tareas"
Cohesion: 0.67
Nodes (3): _handle_tareas(), _load_tareas(), _save_tareas()

### Community 79 - "Artenisa v5.0 — De Bot de Comandos a Copiloto de Operaciones"
Cohesion: 0.05
Nodes (41): 10. Telegram Bot (Implementación), 11. Archivos a modificar/crear, 12. Prioridad de Implementación (Top 3 del usuario), 13. No incluido en esta iteración, 1.1 Objetivo activo de sesión, 1.2 Display en menú, 1.3 Almacenamiento, 1. Motor de Objetivos (Target Context Engine) (+33 more)

### Community 80 - "10. Defense / Blue Team Module (`backend/defense/`)"
Cohesion: 0.05
Nodes (40): 10.10 Telegram Integration, 10.11 Forensics Report (for authorities), 10.12 Implementation Order (Defense), 10.13 Safety & Legal Design, 10.1 Log Monitor (`monitor.py`), 10.2 Attack Detector (`detector.py`), 10.3 Auto-Responder (`responder.py`), 10.4 Forensics (`forensics.py`) (+32 more)

### Community 81 - "CAPACIDADES OFENSIVAS TOTALES"
Cohesion: 0.06
Nodes (34): 10. Móvil, 11. Cloud, 12. SCADA / ICS, 13. IoT, 14. Físico, 15. Ataques Avanzados / Zero-Day, 1. Reconocimiento y OSINT, 2. Redes y Wireless (+26 more)

### Community 82 - "🤖 AGENTS LAYER - Agentes Inteligentes"
Cohesion: 0.10
Nodes (20): 1. Hacking Agent (Comandante Ofensivo), 2. Report Agent, 3. OSINT Agent, 4. Network Agent, 🎯 Agentes Disponibles, 🤖 AGENTS LAYER - Agentes Inteligentes, API Endpoints, 🏗️ Arquitectura del Agente (+12 more)

### Community 83 - "JARVIS v4.0 — Guía de instalación"
Cohesion: 0.13
Nodes (14): 10. Comandos en Telegram, 11. Comandos en CLI, 1. Crear cuenta Oracle Cloud, 2. Crear instancia ARM, 3. Conectar por SSH, 4. Subir proyecto, 5. Instalar todo, 6. Configurar tokens (+6 more)

### Community 84 - "File Structure"
Cohesion: 0.15
Nodes (12): Artenisa v5.0 Implementation Plan, File Structure, Self-Review (passed), Task 1: Target Context Engine + Memory System, Task 2: Hacking Tools Module, Task 3: Playbook Engine, Task 4: Async Task Queue, Task 5: Security Controls (+4 more)

### Community 85 - "Global Constraints"
Cohesion: 0.20
Nodes (9): Global Constraints, Pentest Engine Implementation Plan, Task 1: Findings Models + Engine, Task 2: CVSS v3.1 Calculator, Task 3: Auto-Extraction + Router, Task 4: Pentest Scope + Phases, Task 5: Pentest Engine + Router, Task 6: Defense Module (+1 more)

### Community 86 - "Artenisa"
Cohesion: 0.22
Nodes (8): Artenisa, Características, Estructura, Instalación rápida, Licencia, Requisitos, Stack, Uso

### Community 87 - "Skill: Artenisa Programming Excellence"
Cohesion: 0.25
Nodes (7): Comportamiento esperado, Estilo de respuesta, Flujo de trabajo recomendado, Principios, Propósito, Skill: Artenisa Programming Excellence, Áreas de dominio

### Community 88 - "Artenisa Backend"
Cohesion: 0.40
Nodes (5): Artenisa Backend, Artenisa Telegram Bot, CI/CD Pentest Workflow (GitHub Actions), Docker Compose Deployment, SARIF Report Format

## Knowledge Gaps
- **186 isolated node(s):** `$schema`, `.opencode/plugins/graphify.js`, `backup.sh script`, `entrypoint.sh script`, `setup_oracle.sh script` (+181 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **49 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_playbook()` connect `TaskQueue` to `__init__.py`?**
  _High betweenness centrality (0.033) - this node is a cross-community bridge._
- **Why does `detect_tech()` connect `__init__.py` to `TaskQueue`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Are the 4 inferred relationships involving `Incident` (e.g. with `AlertManager` and `AttackDetector`) actually correct?**
  _`Incident` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `FindingsManager` (e.g. with `Finding` and `FindingSummary`) actually correct?**
  _`FindingsManager` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `extract_findings()` (e.g. with `_extract_cert()` and `_extract_crack()`) actually correct?**
  _`extract_findings()` has 18 INFERRED edges - model-reasoned connections that need verification._
- **What connects `$schema`, `.opencode/plugins/graphify.js`, `backup.sh script` to the rest of the system?**
  _186 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `router.py` be split into smaller, more focused modules?**
  _Cohesion score 0.057942057942057944 - nodes in this community are weakly interconnected._