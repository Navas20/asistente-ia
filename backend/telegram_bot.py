import os
import logging
import subprocess
from datetime import datetime
from pathlib import Path

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from target_engine import TargetEngine
from memory_engine import MemoryEngine
from task_queue import TaskQueue
from security import AuditLog, RateLimiter, get_role
from playbooks import list_playbooks
from report_generator import generate_report
import hacking

log = logging.getLogger("artenisa.telegram")

API_URL = os.getenv("API_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

target_engine = TargetEngine()
memory_engine = MemoryEngine()
task_queue = TaskQueue()
audit_log = AuditLog()
rate_limiter = RateLimiter()
user_wizards = {}
user_depths = {}
voice_mode_users = set()

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("\U0001f50d Recon"), KeyboardButton("\U0001f310 Web"), KeyboardButton("\U0001f511 Crack")],
        [KeyboardButton("\U0001f4a3 Payloads"), KeyboardButton("\U0001f4e1 Red"), KeyboardButton("\U0001f50e OSINT")],
        [KeyboardButton("\U0001f4da Playbooks"), KeyboardButton("\U0001f4c4 Reporte"), KeyboardButton("\u2699\ufe0f Sistema")],
    ],
    resize_keyboard=True,
)


def _check_role(uid: int) -> bool:
    return get_role(uid) != "denied"


def _rate_limit_msg(uid: int):
    ok, _, reset_after = rate_limiter.check(f"user:{uid}")
    if not ok:
        return f"\u23f3 L\u00edmite de llamadas. Espera {reset_after}s."
    return None


def _username(update: Update) -> str:
    u = update.effective_user
    return u.username or u.full_name or str(u.id)


def _recon_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f310 Dominio", callback_data="wizard:recon:dominio"),
         InlineKeyboardButton("\U0001f5a5\ufe0f IP", callback_data="wizard:recon:ip")],
        [InlineKeyboardButton("\U0001f4e1 Rango de Red", callback_data="wizard:recon:red"),
         InlineKeyboardButton("\U0001f519 Atr\u00e1s", callback_data="menu:main")],
    ])


def _depth_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u26a1 R\u00e1pido", callback_data="depth:rapido"),
         InlineKeyboardButton("\U0001f50e Normal", callback_data="depth:normal"),
         InlineKeyboardButton("\U0001f9e0 Profundo", callback_data="depth:profundo")],
        [InlineKeyboardButton("\U0001f519 Atr\u00e1s", callback_data="menu:main"),
         InlineKeyboardButton("\u274c Cancelar", callback_data="action:cancel")],
    ])


# ─── Command Handlers ───


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    summary = target_engine.get_context_summary(uid)
    msg = "\U0001f3af *Artenisa v5.0 en l\u00ednea*\n\nSelecciona una operaci\u00f3n del men\u00fa:"
    if summary:
        msg += f"\n\n{summary}"
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    rl = _rate_limit_msg(uid)
    if rl:
        await update.message.reply_text(rl)
        return
    target = " ".join(context.args)
    if not target:
        await update.message.reply_text("Uso: /objetivo <target>\nEj: /objetivo example.com")
        return
    target_engine.set_target(uid, target, "manual")
    audit_log.log(uid, _username(update), "/objetivo", target)
    await update.message.reply_text(f"\u2705 Objetivo establecido: `{target}`", parse_mode="Markdown")


async def olvidar_objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    target_engine.clear_target(uid)
    audit_log.log(uid, _username(update), "/olvidar_objetivo")
    await update.message.reply_text("\U0001f5d1\ufe0f Objetivo olvidado.")


async def voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    if uid in voice_mode_users:
        voice_mode_users.discard(uid)
        await update.message.reply_text("\U0001f507 Modo voz desactivado.")
    else:
        voice_mode_users.add(uid)
        await update.message.reply_text("\U0001f50a Modo voz activado. Las respuestas se enviar\u00e1n como audio.")


async def tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    if not context.args:
        await update.message.reply_text("Uso: /tarea <id>")
        return
    tid = context.args[0]
    status = task_queue.get_status(tid)
    if "error" in status:
        await update.message.reply_text(f"\u274c {status['error']}")
        return

    msg = (
        f"\U0001f4cb *Tarea:* `{status['id']}`\n"
        f"\U0001f4cc Estado: `{status['status']}`\n"
        f"\U0001f3af Objetivo: {status['target']}\n"
        f"\U0001f4c8 Progreso: {status['progress']}%\n"
        f"\U0001f527 Paso: {status['current_step'] or 'N/A'}"
    )

    result = status.get("result")
    if result and status["status"] == "completed":
        summary = result.get("summary", "")
        if summary:
            msg += f"\n\n{summary}"
        for step in result.get("results", []):
            if step.get("step_id") == "screenshot":
                data = step.get("data") or {}
                if data.get("success"):
                    import base64
                    img_bytes = base64.b64decode(data["screenshot_base64"])
                    await update.message.reply_photo(
                        photo=img_bytes,
                        caption=f"\U0001f4f7 Screenshot: {data.get('title', status['target'])}",
                    )
                elif data.get("error"):
                    msg += f"\n\u26a0\ufe0f Screenshot: {data['error']}"

    await update.message.reply_text(msg, parse_mode="Markdown")


async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    tasks = task_queue.list_tasks()
    if not tasks:
        await update.message.reply_text("\U0001f4ed No hay tareas.")
        return
    icons = {"queued": "\u23f3", "running": "\u25b6\ufe0f", "completed": "\u2705", "failed": "\u274c", "cancelled": "\U0001f6ab"}
    lines = ["\U0001f4cb *Tareas recientes:*"]
    for t in tasks:
        icon = icons.get(t["status"], "\u2753")
        lines.append(f"{icon} `{t['id']}` {t['type']} \u2192 {t['target']} ({t['status']})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def analizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    rl = _rate_limit_msg(uid)
    if rl:
        await update.message.reply_text(rl)
        return
    if not context.args:
        await update.message.reply_text("Uso: /analizar <file_id>\nEnv\u00eda una foto primero para obtener su file_id.")
        return
    file_id = context.args[0]
    try:
        file = await context.bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        api = os.getenv("API_URL", "http://localhost:8000")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{api}/upload",
                files={"file": ("image.jpg", file_bytes, "image/jpeg")},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                fid = data.get("file_id", "")
                await update.message.reply_text(
                    f"\U0001f4f8 Imagen subida.\n"
                    f"ID: `{fid}`\n"
                    f"El an\u00e1lisis por IA a\u00fan no est\u00e1 disponible.",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(f"\u274c Error al subir: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"\u274c Error: {str(e)}")


async def recon_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    target = " ".join(context.args)
    if not target:
        await update.message.reply_text("Uso: /recon <dominio>")
        return
    user_wizards[uid] = {"type": "recon", "target": target, "step": "awaiting_depth"}
    await update.message.reply_text("Selecciona profundidad:", reply_markup=_depth_keyboard())


async def webscan_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    target = " ".join(context.args)
    if not target:
        await update.message.reply_text("Uso: /webscan <url>")
        return
    user_wizards[uid] = {"type": "web", "target": target, "step": "awaiting_depth"}
    await update.message.reply_text("Selecciona profundidad:", reply_markup=_depth_keyboard())


async def crack_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    target = " ".join(context.args)
    if not target:
        await update.message.reply_text("Uso: /crack <hash>")
        return
    result = hacking.crypto.hash_crack(target)
    await update.message.reply_text(_format_crack(result), parse_mode="Markdown")


async def payload_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    target = " ".join(context.args)
    if not target:
        await update.message.reply_text("Uso: /payload <ip:puerto>\nEj: /payload 10.0.0.1:4444")
        return
    parts = target.split(":")
    if len(parts) != 2:
        await update.message.reply_text("\u274c Formato: ip:puerto (ej: 10.0.0.1:4444)")
        return
    ip, port = parts[0], parts[1]
    result = hacking.payloads.reverse_shell(ip, int(port))
    await update.message.reply_text(_format_payload(result), parse_mode="Markdown")


async def osint_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    target = " ".join(context.args)
    if not target:
        await update.message.reply_text("Uso: /osint <dominio|email>")
        return
    user_wizards[uid] = {"type": "osint", "target": target, "step": "awaiting_depth"}
    await update.message.reply_text("Selecciona profundidad:", reply_markup=_depth_keyboard())


# ─── Text Message Handler ───


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        return
    rl = _rate_limit_msg(uid)
    if rl:
        await update.message.reply_text(rl)
        return

    text = update.message.text.strip()

    if uid in user_wizards:
        wizard = user_wizards[uid]
        if wizard["step"] == "awaiting_target":
            wizard["target"] = text
            wizard["step"] = "awaiting_depth"
            await update.message.reply_text("Selecciona profundidad:", reply_markup=_depth_keyboard())
            return
        elif wizard["step"] == "awaiting_value":
            await _execute_immediate(update, wizard, text)
            return

    menu = {
        "\U0001f50d Recon": lambda: _start_wizard(update, uid, "recon", _recon_keyboard(), "Selecciona tipo de reconocimiento:"),
        "\U0001f310 Web": lambda: _start_wizard(update, uid, "web", None, "Introduce la URL del sitio web a auditar:"),
        "\U0001f511 Crack": lambda: _start_wizard(update, uid, "crack", None, "Introduce el hash a crackear:"),
        "\U0001f4a3 Payloads": lambda: _start_wizard(update, uid, "payload", None, "Introduce IP:puerto (ej: 10.0.0.1:4444):"),
        "\U0001f4e1 Red": lambda: _start_wizard(update, uid, "red", None, "Introduce IP o rango de red:"),
        "\U0001f50e OSINT": lambda: _start_wizard(update, uid, "osint", None, "Introduce dominio o email para OSINT:"),
        "\U0001f4da Playbooks": lambda: _show_playbooks(update),
        "\U0001f4c4 Reporte": lambda: _send_report(update, uid),
        "\u2699\ufe0f Sistema": lambda: _system_status(update, uid),
    }

    handler = menu.get(text)
    if handler:
        await handler()
    else:
        await _chat_api(update, text)


async def _start_wizard(update, uid, wtype, keyboard, prompt):
    if wtype in ("crack", "payload"):
        user_wizards[uid] = {"type": wtype, "step": "awaiting_value", "target": None}
    else:
        user_wizards[uid] = {"type": wtype, "step": "awaiting_target", "target": None}
    await update.message.reply_text(prompt, reply_markup=keyboard)


async def _execute_immediate(update, wizard, value):
    uid = update.effective_user.id
    wtype = wizard["type"]
    try:
        if wtype == "crack":
            result = hacking.crypto.hash_crack(value)
            msg = _format_crack(result)
        elif wtype == "payload":
            parts = value.split(":")
            if len(parts) != 2:
                await update.message.reply_text("\u274c Formato: ip:puerto (ej: 10.0.0.1:4444)")
                return
            ip, port = parts[0], parts[1]
            result = hacking.payloads.reverse_shell(ip, int(port))
            msg = _format_payload(result)
        else:
            msg = "\u274c Comando no reconocido."
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"\u274c Error: {str(e)}")
    finally:
        user_wizards.pop(uid, None)


def _format_crack(result: dict) -> str:
    lines = ["\U0001f511 *Hash Crack*"]
    lines.append(f"Hash: `{result['hash']}`")
    lines.append(f"Algoritmo: {result['algorithm']}")
    if result.get("identified"):
        types = [t["type"] for t in result["identified"]]
        lines.append(f"Identificado: {', '.join(types)}")
    if result.get("cracked"):
        lines.append(f"\u2705 *Crackeado:* `{result['plaintext']}`")
    else:
        lines.append("\u274c No se pudo crackear con el diccionario integrado.")
    return "\n".join(lines)


def _format_payload(result: dict) -> str:
    if "error" in result:
        return f"\u274c {result['error']}"
    lines = ["\U0001f4a3 *Payload ({})*".format(result["type"])]
    lines.append(f"```\n{result['payload']}\n```")
    lines.append(f"\U0001f4e1 Listener: `{result['listener']}`")
    lines.append(f"\U0001f510 Base64: `{result['encoded_b64']}`")
    return "\n".join(lines)


async def _show_playbooks(update):
    pbs = list_playbooks()
    if not pbs:
        await update.message.reply_text("\U0001f4da No hay playbooks disponibles.")
        return
    lines = ["\U0001f4da *Playbooks Disponibles*\n"]
    for name, info in pbs.items():
        lines.append(f"\u2022 *{info['name']}* (`{name}`)")
        lines.append(f"  _{info['description']}_")
        lines.append(f"  Tipo: {info['target_type']} | Profundidad: {info['depth_estimate']}\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _send_report(update, uid):
    target_info = target_engine.get_target(uid)
    if not target_info:
        await update.message.reply_text("\u274c No hay objetivo establecido. Usa /objetivo <target> primero.")
        return
    target = target_info["target"]
    try:
        report = generate_report(target, {}, fmt="md")
        content = report.get("content", "")[:3000]
        await update.message.reply_text(
            f"\U0001f4c4 *Reporte generado:* `{report['filename']}`\n{content}",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(f"\u274c Error al generar reporte: {str(e)}")


async def _system_status(update, uid):
    target_info = target_engine.get_target(uid)
    tasks = task_queue.list_tasks(limit=5)
    lines = ["\u2699\ufe0f *Estado del Sistema*\n"]
    if target_info:
        lines.append(f"\U0001f3af Objetivo: `{target_info['target']}` ({target_info['target_type']})")
        lines.append(f"\u23f1\ufe0f Tiempo: {target_info.get('elapsed_minutes', 0)} min")
    else:
        lines.append("\U0001f3af Objetivo: *No establecido*")
    active = [t for t in tasks if t["status"] in ("running", "queued")]
    lines.append(f"\n\U0001f4cb Tareas activas: {len(active)}")
    for t in active:
        lines.append(f"  \u2022 `{t['id']}` \u2192 {t['target']} ({t['status']})")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def _chat_api(update, text):
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{API_URL}/chat",
                json={"message": text},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                msg = data.get("response", "Sin respuesta")
                try:
                    await update.message.reply_text(msg, parse_mode="Markdown")
                except Exception:
                    await update.message.reply_text(msg)
            else:
                await update.message.reply_text(f"\u274c Error de API: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"\u274c Error de conexi\u00f3n: {str(e)}")


# ─── Callback Query Handler ───


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not _check_role(uid):
        await query.edit_message_text("\u274c No autorizado")
        return
    rl = _rate_limit_msg(uid)
    if rl:
        await query.edit_message_text(rl)
        return

    data = query.data

    if data == "menu:main":
        user_wizards.pop(uid, None)
        await query.edit_message_text("Men\u00fa principal:", reply_markup=MAIN_KEYBOARD)
        return

    if data == "action:cancel":
        user_wizards.pop(uid, None)
        await query.edit_message_text("\u274c Operaci\u00f3n cancelada.")
        return

    if data.startswith("wizard:"):
        parts = data.split(":")
        wtype = parts[1]
        subtype = parts[2]
        prompts = {"dominio": "Introduce el dominio para reconocimiento:",
                   "ip": "Introduce la IP para reconocimiento:",
                   "red": "Introduce el rango de red para reconocimiento:"}
        user_wizards[uid] = {"type": wtype, "target_type": subtype, "step": "awaiting_target", "target": None}
        await query.edit_message_text(prompts.get(subtype, "Introduce el objetivo:"))
        return

    if data.startswith("depth:"):
        depth = data.split(":")[1]
        wizard = user_wizards.get(uid)
        if not wizard or wizard["step"] != "awaiting_depth" or not wizard.get("target"):
            await query.edit_message_text("\u274c No hay wizard activo o falta el objetivo.")
            return
        await _execute_wizard(query, uid, wizard, depth)


async def _execute_wizard(query, uid, wizard, depth):
    wtype = wizard["type"]
    target = wizard["target"]
    target_type = wizard.get("target_type", "domain")

    target_engine.set_target(uid, target, target_type)
    target_engine.set_operation(uid, wtype)

    pb_map = {"recon": "recon_web", "web": "web_audit", "red": "full_scan", "osint": "osint_domain"}
    pb_name = pb_map.get(wtype, "recon_web")
    task_id = task_queue.submit("playbook", target, {"playbook": pb_name, "depth": depth})
    audit_log.log(uid, str(uid), f"wizard:{wtype}", target, "ok", f"task:{task_id} depth:{depth}")

    user_wizards.pop(uid, None)

    depth_names = {"rapido": "\u26a1 R\u00e1pido", "normal": "\U0001f50e Normal", "profundo": "\U0001f9e0 Profundo"}
    msg = (
        f"\u2705 *Wizard iniciado*\n\n"
        f"\U0001f4cc Operaci\u00f3n: `{wtype}`\n"
        f"\U0001f3af Objetivo: `{target}`\n"
        f"\U0001f4ca Profundidad: {depth_names.get(depth, depth)}\n"
        f"\U0001f4cb Tarea: `{task_id}`\n\n"
        f"Usa /tarea `{task_id}` para ver el progreso."
    )
    await query.edit_message_text(msg, parse_mode="Markdown")


# ─── Photo Handler ───


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        return
    rl = _rate_limit_msg(uid)
    if rl:
        await update.message.reply_text(rl)
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_bytes = await file.download_as_bytearray()
    file_id = photo.file_id

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API_URL}/upload",
                files={"file": ("photo.jpg", file_bytes, "image/jpeg")},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            )
            if resp.status_code == 200:
                await update.message.reply_text(
                    f"\U0001f4f8 Foto recibida.\n"
                    f"ID: `{file_id}`\n"
                    f"Usa /analizar `{file_id}` para analizarla con OCR."
                )
            else:
                await update.message.reply_text(f"\u274c Error al subir: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"\u274c Error: {str(e)}")


# ─── Voice Handler ───


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        return
    rl = _rate_limit_msg(uid)
    if rl:
        await update.message.reply_text(rl)
        return

    voice = update.message.voice
    file = await voice.get_file()
    ogg_bytes = await file.download_as_bytearray()

    audio_dir = Path("data/audio")
    audio_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().timestamp()
    ogg_path = audio_dir / f"voice_{uid}_{ts}.ogg"
    wav_path = ogg_path.with_suffix(".wav")
    ogg_path.write_bytes(ogg_bytes)

    wav_available = False
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(ogg_path), "-ar", "16000", "-ac", "1", str(wav_path)],
            capture_output=True, timeout=30, check=True,
        )
        wav_available = True
    except (subprocess.SubprocessError, FileNotFoundError):
        wav_available = False

    text = ""
    if wav_available and wav_path.exists():
        try:
            from voice import transcribe
            text = transcribe(str(wav_path))
        except ImportError:
            text = "[voz: transcripci\u00f3n no disponible]"
        except Exception as e:
            text = f"[Error de transcripci\u00f3n: {e}]"
    else:
        text = "[voz: ffmpeg no disponible]"

    try:
        ogg_path.unlink(missing_ok=True)
        if wav_available:
            wav_path.unlink(missing_ok=True)
    except Exception:
        pass

    if text and not text.startswith("["):
        await update.message.reply_text(f"\U0001f3a4 *Transcripci\u00f3n:*\n{text}", parse_mode="Markdown")
    else:
        await update.message.reply_text(text)


# ─── Main ───


def main():
    """Función principal corregida para arrancar el bot de forma nativa sin congelar Docker"""
    import os
    token = os.getenv("TELEGRAM_TOKEN")
    
    if not token:
        log.error("No se encontró la variable TELEGRAM_TOKEN")
        return

    # Construir la aplicación nativa de python-telegram-bot
    application = Application.builder().token(token).build()

    # Registrar tus manejadores de comandos tradicionales
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("objetivo", objetivo))
    application.add_handler(CommandHandler("olvidar_objetivo", olvidar_objetivo))
    application.add_handler(CommandHandler("voz", voz))
    application.add_handler(CommandHandler("tarea", tarea))
    application.add_handler(CommandHandler("tareas", tareas))
    application.add_handler(CommandHandler("analizar", analizar))

    # Manejador global de texto e interacción de menús
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))

    print("[OK] Bot de Artenisa sincronizado y escuchando en Telegram...")
    log.info("Bot de Telegram iniciado con éxito.")
    
    # Arrancar el polling de forma síncrona pura (rompe el congelamiento del contenedor)
    application.run_polling()

if __name__ == "__main__":
    main()

