# JARVIS v4.0 — Guía de instalación

**Asistente personal con**: Voz, Memoria persistente, Pentesting automatizado, Web UI, Telegram, CLI
**Modelo**: WhiteRabbitNeo 2.5 7B (ciberseguridad ofensiva, sin censura)
**Servidor**: Oracle Cloud Free Tier (24GB RAM, 4 CPUs ARM, $0 para siempre)

---

## 1. Crear cuenta Oracle Cloud

1. Ve a https://www.oracle.com/cloud/free/
2. Regístrate (tarjeta requerida, no cobran si usas solo Free Tier)
3. Inicia sesión en la consola

## 2. Crear instancia ARM

1. Compute > Instances > Create Instance
2. Nombre: `jarvis`
3. Image: **Ubuntu 24.04 (ARM)**
4. Shape: `VM.Standard.A1.Flex` — OCPUs: 4, Memory: 24 GB
5. Add SSH keys (sube tu clave pública)
6. Create

## 3. Conectar por SSH

```powershell
ssh -i tu-clave.pem ubuntu@<IP-de-tu-instancia>
```

## 4. Subir proyecto

```bash
# Desde tu PC, en la carpeta asistente-ia
scp -i tu-clave.pem -r * ubuntu@<IP>:/home/ubuntu/jarvis/
```

## 5. Instalar todo

```bash
ssh -i tu-clave.pem ubuntu@<IP>
cd ~/jarvis/scripts
chmod +x setup_oracle.sh
./setup_oracle.sh
```

## 6. Configurar tokens

Editar `~/jarvis/backend/.env`:
```
AUTH_TOKEN=token-super-seguro
MODEL_NAME=personal
OLLAMA_URL=http://localhost:11434
```

Editar `~/jarvis/backend/.env.telegram`:
```
API_URL=http://localhost:8000
AUTH_TOKEN=token-super-seguro
TELEGRAM_TOKEN=token-de-botfather
ALLOWED_USER_ID=tu-id-de-telegram
```

## 7. Iniciar servicios

### Backend API + Web UI:
```bash
cd ~/jarvis/backend
export AUTH_TOKEN=token-super-seguro
python3 main.py &
```

### Telegram Bot:
```bash
export TELEGRAM_TOKEN=...
export ALLOWED_USER_ID=...
python3 telegram_bot.py &
```

## 8. Acceder

- **Web UI**: `http://<IP>:8000/web`
- **API**: `http://<IP>:8000`
- **Telegram**: Chat con tu bot
- **CLI**: `python3 cli/asistente.py`

## 9. Endpoints principales

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/chat` | POST | Chat con JARVIS |
| `/execute` | POST | Ejecutar comandos |
| `/search` | GET | Buscar en internet |
| `/upload` | POST | Subir archivos |
| `/files` | GET | Listar archivos |
| `/memories` | GET | Ver memoria |
| `/workflows` | GET | Listar workflows |
| `/workflows/{name}` | POST | Ejecutar workflow |
| `/speak` | POST | Texto a voz |
| `/web` | GET | Web UI |

## 10. Comandos en Telegram

- `/memoria` — lo que JARVIS sabe de ti
- `/buscar <q>` — buscar en internet
- `/ejecutar <cmd>` — ejecutar comando
- `/archivos` — listar archivos subidos
- `/nueva` — nueva conversación
- `/olvidar` — borrar memoria

## 11. Comandos en CLI

- `/voz` — activar/desactivar modo voz
- `/hablar` — grabar y enviar voz
- `/wf <nombre>` — ejecutar workflow
- `/workflows` — listar workflows
- `/buscar <q>` — buscar
- `/run <cmd>` — ejecutar comando
