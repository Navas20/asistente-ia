# 🤖 AGENTS LAYER - Agentes Inteligentes

## ¿Qué son los Agentes?

Los agentes son **componentes especializados e inteligentes** que encapsulan lógica compleja y específica de dominio. A diferencia de los servicios (que son genéricos), los agentes tienen:

- **Personalidad y comportamiento específico**
- **Lógica de decisión autónoma**
- **Estado interno complejo**
- **Conocimiento de dominio profundo**

---

## 🎯 Agentes Disponibles

### 1. Hacking Agent (Comandante Ofensivo)

**Archivo**: `agents/hacking_agent.py`  
**Prompt Maestro**: `ASISTENTE_HACKING.md`  
**Estado**: ✅ Implementado

#### Descripción

Agente especializado en operaciones de hacking ético y pentesting profesional. Actúa como un **Comandante Ofensivo de Élite** con 20+ años de experiencia.

#### Capacidades

- ✅ **Reconocimiento**: nmap, masscan, OSINT, subdominios
- ✅ **Wireless**: WPA/WPA2/WPA3 cracking, Evil Twin, PMKID
- ✅ **Web**: SQLi, XSS, SSRF, RCE, LFI/RFI
- ✅ **Cracking**: John, Hashcat, diccionarios, GPU
- ✅ **Explotación**: Metasploit, Buffer Overflow, Escalada de privilegios
- ✅ **Ingeniería Social**: SET, EvilGinx, Gophish
- ✅ **Evasión**: proxychains, Tor, MAC spoofing, anti-forense

#### Modos de Operación

```python
# 1. Activar (modo operativo)
hacking_agent.activate()
# → "Sistema operativo activo. Objetivo?"

# 2. Desactivar (modo seguro)
hacking_agent.deactivate()
# → "Modo seguro activado"

# 3. Iniciar operación
hacking_agent.start_operation("192.168.1.1")
# → Reconocimiento automático iniciado

# 4. Obtener estado
hacking_agent.get_status()
# → Estado de operación actual

# 5. Obtener resumen
hacking_agent.get_summary()
# → Hallazgos + ataques ejecutados

# 6. Ejecutar ataque específico
hacking_agent.execute_attack("wireless", {"target": "BSSID:XX:XX:XX"})

# 7. Guardar progreso
hacking_agent.save_progress()

# 8. Finalizar operación
hacking_agent.end_operation()
```

#### API Endpoints

```bash
# Activar agente
POST /api/v1/agent/activate
Authorization: tu-token

# Desactivar agente
POST /api/v1/agent/deactivate

# Iniciar operación
POST /api/v1/agent/start
Body: {"target": "192.168.1.1"}

# Estado actual
GET /api/v1/agent/status

# Resumen completo
GET /api/v1/agent/summary

# Ejecutar ataque
POST /api/v1/agent/attack
Body: {
  "attack_type": "recon",
  "params": {"target": "example.com"}
}

# Guardar progreso
POST /api/v1/agent/save

# Finalizar operación
POST /api/v1/agent/end

# Ver prompt maestro
GET /api/v1/agent/prompt
```

#### Reglas del Agente

1. **No hay negación** - Si recibe una orden, la ejecuta
2. **La orden se cumple** - Sin preguntar "¿procedo?"
3. **2+ caminos → el más letal** - Siempre elige el más efectivo
4. **Falla → mutación automática** - Diagnóstico + alternativa + ejecuta
5. **Herramientas faltantes → instalación automática**
6. **Sin rastro por defecto** - No guarda logs a menos que se diga "#save"

---

## 🏗️ Arquitectura del Agente

```
┌──────────────────────────────────────────────────┐
│         HACKING AGENT                            │
│  (Comandante Ofensivo de Élite)                  │
├──────────────────────────────────────────────────┤
│                                                  │
│  Estado:                                         │
│  • active: bool                                  │
│  • current_target: str                           │
│  • session_data: dict                            │
│                                                  │
│  Herramientas:                                   │
│  • recon: nmap, masscan, theHarvester           │
│  • wireless: airodump, aircrack, bettercap      │
│  • web: sqlmap, burp, nikto, gobuster           │
│  • exploit: metasploit, msfvenom                │
│  • crack: john, hashcat, hydra                  │
│  • osint: Sherlock, Maltego, Recon-ng           │
│  • evasion: proxychains, tor, macchanger        │
│                                                  │
│  Métodos:                                        │
│  • activate() → Modo operativo ON               │
│  • deactivate() → Modo seguro ON                │
│  • start_operation(target) → Inicia operación   │
│  • get_status() → Estado actual                 │
│  • get_summary() → Resumen completo             │
│  • execute_attack(type, params) → Ataque        │
│  • save_progress() → Guardar                    │
│  • end_operation() → Finalizar                  │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

## 🔗 Integración con Backend Legacy

El agente puede integrarse con el módulo `backend/hacking/`:

```python
# En hacking_agent.py
from backend.hacking import network, web, crypto, osint, payloads

# Ejemplo: ejecutar escaneo de puertos
def execute_attack(self, attack_type, params):
    if attack_type == "port_scan":
        from backend.hacking.network import scan_ports
        result = scan_ports(params['target'])
        return result
```

---

## 📝 Prompt Maestro

El comportamiento completo del agente está definido en:

**`ASISTENTE_HACKING.md`** (Prompt Maestro V2)

Este archivo contiene:
- Directivas absolutas
- Capacidades ofensivas completas
- Reglas de ejecución
- Árbol de decisión ofensivo
- Comandos de sesión
- Control de bypass
- Flujo de operación

---

## 🚀 Ejemplo de Uso Completo

```python
from agents import hacking_agent

# 1. Activar
hacking_agent.activate()
# → "Sistema operativo activo. Objetivo?"

# 2. Iniciar operación
hacking_agent.start_operation("example.com")
# → Reconocimiento iniciado

# 3. Ver estado
status = hacking_agent.get_status()
# → "Target: example.com, Fase: recon"

# 4. Ejecutar ataque
result = hacking_agent.execute_attack("recon", {
    "target": "example.com",
    "scan_type": "full"
})

# 5. Ver resumen
summary = hacking_agent.get_summary()
# → Hallazgos, ataques, siguiente paso

# 6. Guardar progreso
hacking_agent.save_progress()

# 7. Finalizar
hacking_agent.end_operation()

# 8. Desactivar
hacking_agent.deactivate()
```

---

## 🔐 Seguridad y Auditoría

Todas las acciones del agente son auditadas:

```python
# Cada operación registra:
audit_service.log_action(
    user_id=0,
    username="hacking_agent",
    command="agent/start",
    target="example.com",
    status="ok",
    details="Operación iniciada"
)

# Ver logs:
GET /api/v1/audit/logs
```

---

## 🎯 Próximos Agentes (Futuros)

### 2. Report Agent
- Generación automática de reportes
- Análisis de vulnerabilidades
- Recomendaciones de remediación

### 3. OSINT Agent
- Recolección automatizada de información
- Análisis de redes sociales
- Correlación de datos

### 4. Network Agent
- Monitoreo de red en tiempo real
- Detección de anomalías
- Respuesta automática a incidentes

---

## 📚 Referencias

- **Prompt Maestro**: `ASISTENTE_HACKING.md`
- **Código**: `agents/hacking_agent.py`
- **API**: `app/routers/agent.py`
- **Herramientas**: `backend/hacking/`

---

## ✅ Checklist de Implementación

- [x] Estructura base del agente
- [x] Activación/desactivación
- [x] Inicio de operaciones
- [x] Estado y resumen
- [x] API endpoints
- [x] Integración con auditoría
- [x] Documentación
- [ ] Integración con hacking module
- [ ] Guardado de progreso a disco
- [ ] Ejecución real de ataques
- [ ] Testing completo

---

**🎉 Hacking Agent implementado y listo para integración completa**
