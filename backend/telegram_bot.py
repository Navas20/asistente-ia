import os
import asyncio
import ipaddress
import logging
import re
import secrets
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from target_engine import TargetEngine
from memory_engine import MemoryEngine
from task_queue import TaskQueue
from security import AuditLog, RateLimiter, get_role
from playbooks import list_playbooks
from report_generator import generate_report
import hacking
import tools_engine

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

WIZARD_TTL_SECONDS = 30 * 60


def _new_wizard(uid, wizard_type, chat_id, step="select_type", **state):
    wizard = {
        "session_id": secrets.token_hex(4),
        "type": wizard_type,
        "step": step,
        "chat_id": chat_id,
        "created_at": time.time(),
        "target": None,
        "data": {},
    }
    wizard.update(state)
    user_wizards[uid] = wizard
    log.info(
        "Wizard session created: user=%s type=%s session=%s",
        uid,
        wizard_type,
        wizard["session_id"],
    )
    return wizard


def _is_wizard_expired(uid, now=None):
    wizard = user_wizards.get(uid)
    if not wizard:
        return False
    current_time = time.time() if now is None else now
    if current_time - wizard.get("created_at", 0) <= WIZARD_TTL_SECONDS:
        return False
    user_wizards.pop(uid, None)
    log.info("Wizard session expired: user=%s", uid)
    return True


def _consume_wizard(uid, session_id):
    wizard = user_wizards.get(uid)
    if not wizard or wizard.get("session_id") != session_id:
        return None
    return user_wizards.pop(uid)


def _wizard_callback(wizard, action, value):
    callback = (
        f"w:{wizard['session_id']}:{wizard['type']}:{action}:{value}"
    )
    if len(callback.encode("utf-8")) > 64:
        raise ValueError("Telegram callback_data exceeds 64 bytes")
    return callback


user_depths = {}
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("\U0001f50d Recon"), KeyboardButton("\U0001f310 Web"), KeyboardButton("\U0001f511 Crack")],
        [KeyboardButton("\U0001f4a3 Payloads"), KeyboardButton("\U0001f4e1 Red"), KeyboardButton("\U0001f50e OSINT")],
        [KeyboardButton("\U0001f4cb Mis Tareas"), KeyboardButton("\u2753 Ayuda"), KeyboardButton("\u2699\ufe0f Objetivo")],
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


def _is_markdown_parse_error(exc):
    message = str(exc).casefold()
    return any(
        marker in message
        for marker in (
            "can't parse entities",
            "cannot parse entities",
            "can not parse entities",
        )
    )


def _is_message_not_modified(exc):
    return "message is not modified" in str(exc).casefold()


async def _safe_telegram_call(method, text, **kwargs):
    try:
        return await method(text, **kwargs)
    except BadRequest as exc:
        if "parse_mode" not in kwargs or not _is_markdown_parse_error(exc):
            log.error("Telegram BadRequest: %s", exc)
            raise
        fallback = dict(kwargs)
        fallback.pop("parse_mode", None)
        log.warning("Telegram Markdown parse failed; retrying as plain text")
        try:
            return await method(text, **fallback)
        except BadRequest as fallback_exc:
            log.error(
                "Telegram plain-text fallback failed: %s", fallback_exc
            )
            raise


async def _safe_reply_text(message, text, **kwargs):
    return await _safe_telegram_call(message.reply_text, text, **kwargs)


async def _safe_edit_text(message, text, **kwargs):
    return await _safe_telegram_call(message.edit_text, text, **kwargs)


async def _safe_edit_message(query, text, **kwargs):
    return await _safe_telegram_call(query.edit_message_text, text, **kwargs)


# ─── Command Handlers ───


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    user_wizards.pop(uid, None)
    summary = target_engine.get_context_summary(uid)
    msg = "\U0001f3af *Artenisa v5.0 en l\u00ednea*\n\nSelecciona una operaci\u00f3n del men\u00fa:"
    if summary:
        msg += f"\n\n{summary}"
    await _safe_reply_text(
        update.message,
        msg,
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


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
    await _safe_reply_text(
        update.message,
        f"\u2705 Objetivo establecido: `{target}`",
        parse_mode="Markdown",
    )


async def olvidar_objetivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    target_engine.clear_target(uid)
    audit_log.log(uid, _username(update), "/olvidar_objetivo")
    await update.message.reply_text("\U0001f5d1\ufe0f Objetivo olvidado.")


async def tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    if not context.args:
        await update.message.reply_text("Uso: /tarea <id>")
        return
    tid = context.args[0]
    status = task_queue.get_status(tid, user_id=uid)
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

    await _safe_reply_text(update.message, msg, parse_mode="Markdown")


async def tareas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    tasks = task_queue.list_tasks(user_id=uid)
    if not tasks:
        await update.message.reply_text("\U0001f4ed No hay tareas.")
        return
    icons = {"queued": "\u23f3", "running": "\u25b6\ufe0f", "completed": "\u2705", "failed": "\u274c", "cancelled": "\U0001f6ab"}
    lines = ["\U0001f4cb *Tareas recientes:*"]
    for t in tasks:
        icon = icons.get(t["status"], "\u2753")
        lines.append(f"{icon} `{t['id']}` {t['type']} \u2192 {t['target']} ({t['status']})")
    await _safe_reply_text(
        update.message, "\n".join(lines), parse_mode="Markdown"
    )


async def nmap_shortcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    log.info("[nmap] Handler called by %s, args=%s", uid, context.args)
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    rl = _rate_limit_msg(uid)
    if rl:
        await update.message.reply_text(rl)
        return

    valid_types = {"quick", "normal", "full", "vuln"}
    target = None
    scan_type = "normal"

    args = context.args or []
    if len(args) == 0:
        target_info = target_engine.get_target(uid)
        if not target_info:
            await update.message.reply_text("\u274c No hay objetivo. Usa /objetivo <target> primero.")
            return
        target = target_info["target"]

    elif len(args) == 1:
        if args[0] in valid_types:
            scan_type = args[0]
            target_info = target_engine.get_target(uid)
            if not target_info:
                await update.message.reply_text("\u274c No hay objetivo. Usa /objetivo <target> primero o /nmap <scan_type> <target>")
                return
            target = target_info["target"]
        else:
            target = args[0]

    else:
        scan_type = args[0]
        if scan_type not in valid_types:
            await update.message.reply_text(f"scan_type debe ser uno de: {', '.join(sorted(valid_types))}")
            return
        target = args[1]

    from tools_engine import validate_target
    error = validate_target(target)
    if error:
        await update.message.reply_text(f"\u274c {error}")
        return

    task_error = None
    try:
        log.info("[nmap] Submitting: %s (%s)", target, scan_type)
        task_id = task_queue.submit("nmap", target, {"scan_type": scan_type, "user_id": uid})
        log.info("[nmap] Task ID: %s", task_id)
        if not task_id:
            task_error = "\u274c Error al encolar tarea"
        else:
            audit_log.log(
                uid,
                _username(update),
                "/nmap",
                target,
                "ok",
                f"task:{task_id}",
            )
    except Exception as exc:
        log.error("[nmap] Exception: %s", exc, exc_info=True)
        task_error = f"\u274c Error: {str(exc)}"

    if task_error:
        await update.message.reply_text(task_error)
        return

    msg = await _safe_reply_text(
        update.message,
        f"\u2705 `{task_id}` \u2014 Escaneando {target} ({scan_type})",
        parse_mode="Markdown",
    )
    asyncio.create_task(_poll_nmap_task(msg, task_id))


async def _poll_nmap_task(
    msg, task_id, timeout=300, return_to_menu=False
):
    await asyncio.sleep(2)
    deadline = asyncio.get_event_loop().time() + timeout
    last_progress_text = None
    while True:
        status = task_queue.get_status(task_id)
        s = status.get("status")
        if not s:
            error = status.get("error") or "Tarea no encontrada"
            await _safe_edit_text(msg, f"\u274c Nmap: {error}")
            if return_to_menu:
                await _safe_reply_text(
                    msg,
                    "Menú principal:",
                    reply_markup=MAIN_KEYBOARD,
                )
            return

        if s == "cancelled":
            await _safe_edit_text(msg, "\u274c Nmap: tarea cancelada")
            if return_to_menu:
                await _safe_reply_text(
                    msg,
                    "Menú principal:",
                    reply_markup=MAIN_KEYBOARD,
                )
            return

        if s == "completed":
            result = status.get("result") or {}
            target = status.get("target", "")
            scan_type = (status.get("params") or {}).get("scan_type", "normal")
            elapsed = result.get("elapsed", 0)
            parsed = result.get("parsed")
            stdout = result.get("stdout", "")

            lines = [f"\u2705 *Nmap* `{target}` ({scan_type}) \u2014 {elapsed:.1f}s"]
            if parsed:
                hosts = parsed.get("summary", {}).get("hosts_up", 0)
                ports = parsed.get("summary", {}).get("total_ports_found", 0)
                if hosts:
                    lines.append(f"Hosts: {hosts} | Puertos: {ports}")
                for host in parsed.get("hosts", [])[:3]:
                    ip = host.get("ip", "")
                    hn = host.get("hostname", "")
                    name = f" ({hn})" if hn else ""
                    lines.append(f"\n`{ip}`{name}")
                    for p in host.get("ports", [])[:10]:
                        svc = f" - {p['service']}" if p.get("service") else ""
                        lines.append(f"  \U0001f4e1 {p['port']}/{p['protocol']} {p['state']}{svc}")
            else:
                out = stdout[:1500] if stdout else "(sin salida)"
                lines.append(f"\n```\n{out}\n```")
            await _safe_edit_text(
                msg, "\n".join(lines), parse_mode="Markdown"
            )
            if return_to_menu:
                await _safe_reply_text(
                    msg,
                    "Men\u00fa principal:",
                    reply_markup=MAIN_KEYBOARD,
                )
            return

        elif s == "failed":
            error = status.get("error", "Error desconocido")
            await _safe_edit_text(msg, f"\u274c Nmap fall\u00f3: {error}")
            if return_to_menu:
                await _safe_reply_text(
                    msg,
                    "Men\u00fa principal:",
                    reply_markup=MAIN_KEYBOARD,
                )
            return

        elif s == "running":
            pct = status.get("progress", 0)
            filled = max(0, min(10, int(pct) // 10))
            bar = "\u2588" * filled + "\u2591" * (10 - filled)
            step = status.get("current_step") or "Procesando..."
            progress_text = (
                f"\u23f3 `{task_id}` \u2014 [{bar}] {pct}%\n"
                f"\U0001f527 {step}"
            )
            if progress_text != last_progress_text:
                try:
                    await _safe_edit_text(
                        msg,
                        progress_text,
                        parse_mode="Markdown",
                    )
                except BadRequest as exc:
                    if not _is_message_not_modified(exc):
                        raise
                    log.debug(
                        "Nmap progress was already current: task=%s",
                        task_id,
                    )
                last_progress_text = progress_text

        if asyncio.get_event_loop().time() > deadline:
            await _safe_edit_text(
                msg,
                f"\u23f0 `{task_id}` \u2014 Tiempo agotado ({timeout}s)",
            )
            if return_to_menu:
                await _safe_reply_text(
                    msg,
                    "Men\u00fa principal:",
                    reply_markup=MAIN_KEYBOARD,
                )
            return

        await asyncio.sleep(2)


async def _poll_playbook_task(
    msg, task_id, label, timeout=600, return_to_menu=False, uid=None
):
    await asyncio.sleep(2)
    deadline = asyncio.get_event_loop().time() + timeout
    last_progress_text = None

    async def finish(text):
        await _safe_edit_text(msg, text)
        if return_to_menu:
            await _safe_reply_text(
                msg,
                "Menú principal:",
                reply_markup=MAIN_KEYBOARD,
            )

    while True:
        status = task_queue.get_status(task_id)
        state = status.get("status")

        if not state:
            error = status.get("error") or "Tarea no encontrada"
            await finish(f"{label}: {error}")
            return

        if state == "cancelled":
            await finish(f"{label}: tarea cancelada")
            return

        if state == "completed":
            result = status.get("result") or {}
            target = status.get("target") or result.get("target") or ""

            def clip(value, limit):
                text = str(value)
                if len(text) <= limit:
                    return text
                return text[:limit - 3] + "..."

            lines = [
                f"{clip(label, 120)} completado",
                f"Objetivo: {clip(target, 500)}",
            ]
            summary = result.get("summary")
            if summary:
                lines.extend(("", clip(summary, 500)))
            results = result.get("results") or []
            if results:
                lines.extend(("", "Resultados:"))
                for step_result in results:
                    step_status = (
                        "OK" if step_result.get("success") else "SKIP"
                    )
                    step_label = clip(
                        step_result.get("label") or "", 120
                    )
                    step_line = f"[{step_status}] {step_label}"
                    note = step_result.get("note")
                    if note:
                        step_line += f" - {clip(note, 80)}"
                    lines.append(step_line)
            completion = "\n".join(lines)
            if len(completion) > 3500:
                completion = completion[:3497] + "..."
            if uid:
                ok_count = sum(1 for r in results if r.get("success"))
                audit_status = "ok" if ok_count == len(results) else "partial"
                params = status.get("params") or {}
                task_target = status.get("target") or ""
                audit_log.log(
                    uid,
                    str(uid),
                    "wizard:osint",
                    task_target,
                    audit_status,
                    f"task:{task_id} ok:{ok_count}/{len(results)}",
                )
            await finish(completion)
            return

        if state == "failed":
            error = status.get("error") or "Error desconocido"
            if uid:
                task_target = status.get("target") or ""
                audit_log.log(
                    uid,
                    str(uid),
                    "wizard:osint",
                    task_target,
                    "error",
                    f"task:{task_id} error:{error}",
                )
            await finish(f"{label} falló: {error}")
            return

        if state in {"queued", "running"}:
            pct = status.get("progress", 0)
            filled = max(0, min(10, int(pct) // 10))
            bar = "\u2588" * filled + "\u2591" * (10 - filled)
            step = status.get("current_step") or "Sin paso reportado"
            progress_text = (
                f"\u23f3 `{task_id}` \u2014 [{bar}] {pct}%\n"
                f"\U0001f527 {step}"
            )
            if progress_text != last_progress_text:
                try:
                    await _safe_edit_text(
                        msg,
                        progress_text,
                        parse_mode="Markdown",
                    )
                except BadRequest as exc:
                    if not _is_message_not_modified(exc):
                        raise
                    log.debug(
                        "Playbook progress was already current: task=%s",
                        task_id,
                    )
                last_progress_text = progress_text

        if asyncio.get_event_loop().time() > deadline:
            await finish(
                f"\u23f0 `{task_id}` \u2014 Tiempo agotado ({timeout}s)"
            )
            return

        await asyncio.sleep(2)


# ─── Wizard Keyboards ───


def _wizard_keyboard(
    wizard: dict, options: list[tuple[str, str, str]]
):
    buttons = [
        InlineKeyboardButton(
            label,
            callback_data=_wizard_callback(wizard, action, value),
        )
        for label, action, value in options
    ]
    rows = [
        buttons[index:index + 2]
        for index in range(0, len(buttons), 2)
    ]
    rows.append(
        [
            InlineKeyboardButton(
                "\U0001f519 Atr\u00e1s",
                callback_data=_wizard_callback(wizard, "back", "main"),
            ),
            InlineKeyboardButton(
                "\u274c Cancelar",
                callback_data=_wizard_callback(wizard, "cancel", "now"),
            ),
        ]
    )
    return InlineKeyboardMarkup(rows)


_CALLBACK_RULES = {
    ("recon", "select_type", "type"): {"quick", "normal", "full"},
    ("web", "select_type", "type"): {"recon", "vuln"},
    ("crack", "select_type", "type"): {"hash"},
    ("crack", "select_dict", "method"): {"integrated", "custom"},
    ("payload", "select_type", "type"): {"reverse", "webshell"},
    ("payload", "select_lang", "lang"): {"bash", "php"},
    ("red", "select_type", "type"): {"quick", "normal", "full"},
    ("osint", "select_type", "type"): {"email", "domain"},
}


_EXPIRED_CALLBACK_ALERT = (
    "Este boton ya expiro. Abre un nuevo wizard desde el menu."
)


def _validate_wizard_callback(
    uid: int, chat_id: int, data: str
) -> tuple[
    dict | None,
    str | None,
    str | None,
    tuple[str, str] | None,
]:
    if not _check_role(uid):
        return None, None, None, ("unauthorized", "No autorizado")
    rate_limit_error = _rate_limit_msg(uid)
    if rate_limit_error:
        return None, None, None, ("rate_limited", rate_limit_error)
    if not isinstance(data, str) or len(data.encode("utf-8")) > 64:
        return None, None, None, ("malformed_data", _EXPIRED_CALLBACK_ALERT)
    parts = data.split(":")
    if (
        len(parts) != 5
        or parts[0] != "w"
        or not re.fullmatch(r"[0-9a-f]{8}", parts[1])
    ):
        return None, None, None, ("malformed_data", _EXPIRED_CALLBACK_ALERT)
    _, session_id, wizard_type, action, value = parts
    if _is_wizard_expired(uid):
        return None, None, None, ("expired_session", _EXPIRED_CALLBACK_ALERT)
    wizard = user_wizards.get(uid)
    if not wizard:
        return None, None, None, ("no_session", _EXPIRED_CALLBACK_ALERT)
    if wizard.get("session_id") != session_id:
        return None, None, None, ("session_mismatch", _EXPIRED_CALLBACK_ALERT)
    if wizard.get("type") != wizard_type:
        return None, None, None, (
            "wizard_type_mismatch",
            _EXPIRED_CALLBACK_ALERT,
        )
    if wizard.get("chat_id") != chat_id:
        return None, None, None, ("chat_mismatch", _EXPIRED_CALLBACK_ALERT)
    if action == "back" and value == "main":
        return wizard, action, value, None
    if action == "cancel" and value == "now":
        return wizard, action, value, None
    allowed = _CALLBACK_RULES.get(
        (wizard_type, wizard.get("step"), action)
    )
    if not allowed or value not in allowed:
        return None, None, None, ("invalid_selection", _EXPIRED_CALLBACK_ALERT)
    if wizard_type == "payload" and action == "lang":
        language_sets = {
            "reverse": {"bash", "python", "php", "powershell"},
            "webshell": {"php", "asp", "aspx", "jsp", "py"},
        }
        if value not in language_sets.get(
            wizard.get("payload_type"), set()
        ):
            return None, None, None, (
                "invalid_payload_language",
                _EXPIRED_CALLBACK_ALERT,
            )
    return wizard, action, value, None


async def _reject_callback(
    query, reason, message, uid=None, chat_id=None
):
    log.warning(
        "Telegram callback rejected: reason=%s user=%s chat=%s data=%r",
        reason,
        uid,
        chat_id,
        getattr(query, "data", None),
    )
    try:
        await query.answer(message, show_alert=True)
    except Exception:
        log.warning(
            "Could not answer rejected Telegram callback", exc_info=True
        )


async def _send_expired_callback(query):
    await _reject_callback(
        query, "session_unavailable", _EXPIRED_CALLBACK_ALERT
    )


# ─── Recon Wizard ───


async def _start_recon_wizard(update, uid):
    wizard = _new_wizard(uid, "recon", update.effective_chat.id)
    keyboard = _wizard_keyboard(wizard, [
        ("\u26a1 Quick", "type", "quick"),
        ("\U0001f50e Normal", "type", "normal"),
        ("\U0001f9e0 Full", "type", "full"),
    ])
    await update.message.reply_text("\U0001f50d *Recon* \u2014 \u00bfTipo de escaneo?", parse_mode="Markdown", reply_markup=keyboard)


async def _handle_recon_type(query, uid, wizard, subtype):
    if subtype not in {"quick", "normal", "full"}:
        await query.edit_message_text("Tipo de escaneo no permitido.")
        return
    updates = dict(
        step="awaiting_target",
        scan_type=subtype,
        target=None,
    )
    await query.edit_message_text("Introduce la IP, dominio o rango:")
    wizard.update(updates)


# ─── Web Wizard ───


_EXPLICIT_SCHEME_RE = re.compile(
    r"^([A-Za-z][A-Za-z0-9+.-]*):(?![0-9]+(?:[/?#]|$))"
)


def _normalize_web_input(value: str) -> tuple[str | None, str | None, str | None]:
    raw = value.strip()
    if not raw:
        return None, None, "La URL no puede estar vacia."
    if len(raw) > 2048:
        return None, None, "La URL supera el limite de 2048 caracteres."
    if "\\" in raw:
        return None, None, "La URL no puede contener barras invertidas."
    if any(
        char.isspace() or ord(char) < 32 or 0x7F <= ord(char) <= 0x9F
        for char in raw
    ):
        return None, None, "La URL no puede contener espacios o controles."

    scheme_match = _EXPLICIT_SCHEME_RE.match(raw)
    if scheme_match:
        supplied_scheme = scheme_match.group(1).lower()
        if supplied_scheme not in ("http", "https"):
            return None, None, "Solo se permiten URLs HTTP o HTTPS."
    else:
        raw = "https://" + raw

    try:
        parsed = urlparse(raw)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return None, None, "La URL esta malformada."

    if scheme not in ("http", "https") or not hostname:
        return None, None, "La URL debe incluir un hostname valido."
    if parsed.username is not None or parsed.password is not None:
        return None, None, "La URL no puede incluir credenciales."

    normalized = parsed._replace(scheme=scheme).geturl()
    from tools_engine import validate_target, validate_url_target

    error = validate_url_target(normalized)
    if error:
        return None, None, error
    error = validate_target(hostname)
    if error:
        return None, None, error
    return normalized, hostname, None


async def _start_web_wizard(update, uid):
    wizard = _new_wizard(uid, "web", update.effective_chat.id)
    keyboard = _wizard_keyboard(wizard, [
        ("\U0001f50e Reconocimiento Web", "type", "recon"),
        ("\U0001f6e1\ufe0f Auditoría de Vulnerabilidades", "type", "vuln"),
    ])
    await update.message.reply_text("\U0001f310 *Web* \u2014 \u00bfTipo de auditor\u00eda?", parse_mode="Markdown", reply_markup=keyboard)


async def _handle_web_type(query, uid, wizard, subtype):
    if subtype not in {"recon", "vuln"}:
        await query.edit_message_text("Tipo de auditoria no permitido.")
        return
    updates = dict(
        step="awaiting_target",
        audit_type=subtype,
        target=None,
    )
    await query.edit_message_text("Introduce una URL HTTP(S) del sitio web:")
    wizard.update(updates)


# ─── Crack Wizard ───


SUPPORTED_HASH_ALGORITHMS = frozenset(
    {"MD5", "SHA1", "SHA224", "SHA256", "SHA384", "SHA512"}
)


def _validate_hash_algorithm(value: str) -> tuple[str | None, str | None]:
    candidates = hacking.crypto.hash_id(value.strip())
    for candidate in candidates:
        algorithm = candidate.get("type", "")
        if algorithm in SUPPORTED_HASH_ALGORITHMS:
            return algorithm, None
    detected = ", ".join(
        candidate.get("type", "desconocido") for candidate in candidates
    )
    return None, (
        f"Algoritmo no soportado: {detected}. "
        "Usa MD5 o SHA1/224/256/384/512."
    )


async def _start_crack_wizard(update, uid):
    wizard = _new_wizard(uid, "crack", update.effective_chat.id)
    keyboard = _wizard_keyboard(wizard, [
        ("\U0001f511 Hash", "type", "hash"),
    ])
    await update.message.reply_text("\U0001f511 *Crack* \u2014 \u00bfTipo?", parse_mode="Markdown", reply_markup=keyboard)


async def _handle_crack_type(query, uid, wizard, subtype):
    if subtype != "hash":
        await query.edit_message_text("Tipo de crack no permitido.")
        return
    if (
        user_wizards.get(uid) is not wizard
        or wizard.get("type") != "crack"
        or wizard.get("step") != "select_type"
    ):
        await query.edit_message_text("Este wizard expiro. Vuelve al menu.")
        return
    updates = dict(
        step="awaiting_value",
        crack_type="hash",
        target=None,
    )
    await query.edit_message_text("Pega el hash:")
    wizard.update(updates)


async def _handle_crack_value(query, uid, value):
    wizard = user_wizards.get(uid)
    if (
        not wizard
        or wizard.get("type") != "crack"
        or wizard.get("step") != "awaiting_value"
        or wizard.get("crack_type") != "hash"
    ):
        await query.edit_message_text("Metodo de crack no permitido.")
        return
    algorithm, error = _validate_hash_algorithm(value)
    if error:
        await _safe_edit_message(query, error)
        return
    updates = dict(
        target=value.strip(),
        algorithm=algorithm,
        step="select_dict",
    )
    keyboard = _wizard_keyboard(wizard, [
        ("\U0001f4da Integrado", "method", "integrated"),
        ("\U0001f3b2 Custom", "method", "custom"),
    ])
    await query.edit_message_text("\U0001f511 \u00bfDiccionario?", reply_markup=keyboard)
    wizard.update(updates)


async def _execute_crack(
    query,
    uid,
    wizard,
    method,
    wordlist=None,
    consumed_wizard=None,
):
    if wizard.get("crack_type") != "hash" or method not in (
        "integrated",
        "custom",
    ):
        await query.edit_message_text("Metodo de crack no permitido.")
        return
    algorithm, error = _validate_hash_algorithm(wizard.get("target", ""))
    if error:
        await _safe_edit_message(query, error)
        return
    consumed = consumed_wizard or _consume_wizard(
        uid, wizard.get("session_id", "")
    )
    if not consumed:
        await _send_expired_callback(query)
        return

    hash_value = consumed["target"]
    await _safe_edit_message(query, "\u23f3 Analizando hash...")
    try:
        if wordlist is None:
            result = hacking.crypto.hash_crack(hash_value)
        else:
            result = hacking.crypto.hash_crack(hash_value, wordlist)
    except Exception as exc:
        log.exception("Crack wizard failed")
        audit_log.log(
            uid,
            str(uid),
            "wizard:crack",
            hash_value,
            "error",
            str(exc),
        )
        await _safe_edit_message(
            query,
            "No se pudo completar Crack. Abre un nuevo wizard desde el menu.",
        )
        await _safe_reply_text(
            query.message,
            "Menú principal:",
            reply_markup=MAIN_KEYBOARD,
        )
        return
    status = "ok" if result.get("cracked") else "fail"
    audit_log.log(
        uid, str(uid), "wizard:crack", hash_value, status, method
    )
    message = _format_crack(result, method)
    await _safe_edit_message(query, message, parse_mode="Markdown")
    await _safe_reply_text(
        query.message,
        "Menú principal:",
        reply_markup=MAIN_KEYBOARD,
    )


# ─── Payload Wizard ───


def _parse_payload_endpoint(
    value: str,
) -> tuple[str | None, int | None, str | None]:
    raw = value
    if raw.startswith("["):
        match = re.fullmatch(r"\[([^\[\]\s]+)\]:([0-9]+)", raw)
        if not match:
            return None, None, "Endpoint inválido. Usa [IPv6]:Puerto."
        host, port_text = match.groups()
        expected_version = 6
    else:
        match = re.fullmatch(r"([^:\s]+):([0-9]+)", raw)
        if not match:
            return None, None, "Endpoint inválido. Usa IP:Puerto."
        host, port_text = match.groups()
        expected_version = 4

    try:
        address = ipaddress.ip_address(host)
        port = int(port_text)
    except ValueError:
        return None, None, "Endpoint inválido. Usa una IP y puerto válidos."

    if address.version != expected_version:
        form = "[IPv6]:Puerto" if expected_version == 6 else "IPv4:Puerto"
        return None, None, f"Endpoint inválido. Usa {form}."
    if not 1 <= port <= 65535:
        return None, None, "Endpoint inválido. El puerto debe ser 1-65535."
    if address.is_unspecified or address.is_multicast:
        return None, None, "Endpoint inválido. La IP no puede ser multicast ni no especificada."
    return str(address), port, None


async def _start_payload_wizard(update, uid):
    wizard = _new_wizard(uid, "payload", update.effective_chat.id)
    keyboard = _wizard_keyboard(wizard, [
        ("\U0001f41a Reverse Shell", "type", "reverse"),
        ("\U0001f4bb Webshell", "type", "webshell"),
    ])
    await update.message.reply_text("\U0001f4a3 *Payload* \u2014 \u00bfTipo?", parse_mode="Markdown", reply_markup=keyboard)


async def _handle_payload_type(query, uid, wizard, subtype):
    if subtype not in {"reverse", "webshell"}:
        await query.edit_message_text("Tipo de payload no permitido.")
        return
    if subtype == "webshell":
        options = [
            ("\U0001f7e8 PHP", "lang", "php"),
        ]
    else:
        options = [
            ("\U0001f539 Bash", "lang", "bash"),
        ]
    keyboard = _wizard_keyboard(wizard, options)
    await query.edit_message_text("\U0001f4a3 \u00bfLenguaje?", reply_markup=keyboard)
    wizard.update(step="select_lang", payload_type=subtype)


async def _handle_payload_lang(
    query, uid, wizard, lang, consumed_wizard=None
):
    active_wizard = user_wizards.get(uid)
    if consumed_wizard is None:
        valid_session = active_wizard is wizard
    else:
        valid_session = consumed_wizard is wizard
    if (
        not valid_session
        or wizard.get("type") != "payload"
        or wizard.get("step") != "select_lang"
    ):
        await query.edit_message_text("\u23f0 Este wizard expir\u00f3. Vuelve al men\u00fa.")
        return

    payload_type = wizard.get("payload_type")
    if payload_type == "webshell":
        consumed = consumed_wizard or _consume_wizard(
            uid, wizard.get("session_id", "")
        )
        if not consumed:
            await _send_expired_callback(query)
            return
        try:
            result = hacking.payloads.webshell(lang)
        except Exception as exc:
            log.exception("Webshell wizard failed")
            audit_log.log(
                uid,
                str(uid),
                "wizard:payload",
                lang,
                "error",
                str(exc),
            )
            await _safe_edit_message(
                query,
                "No se pudo generar el payload. Abre un nuevo wizard desde el menu.",
            )
            await _safe_reply_text(
                query.message,
                "Menú principal:",
                reply_markup=MAIN_KEYBOARD,
            )
            return
        status = "error" if result.get("error") else "ok"
        audit_log.log(
            uid,
            str(uid),
            "wizard:payload",
            lang,
            status,
            "webshell",
        )
        message = _format_webshell(result)
        await _safe_edit_message(query, message, parse_mode="Markdown")
        await _safe_reply_text(
            query.message,
            "Menú principal:",
            reply_markup=MAIN_KEYBOARD,
        )
        return
    if payload_type != "reverse":
        await query.edit_message_text("Tipo de payload no permitido.")
        return

    await query.edit_message_text(
        "Introduce tu listener como IP:Puerto (IPv6: [IP]:Puerto):"
    )
    wizard.update(lang=lang, step="awaiting_endpoint")


# ─── Red Wizard ───


async def _start_red_wizard(update, uid):
    wizard = _new_wizard(uid, "red", update.effective_chat.id)
    keyboard = _wizard_keyboard(wizard, [
        ("\u26a1 Quick", "type", "quick"),
        ("\U0001f50e Normal", "type", "normal"),
        ("\U0001f9e0 Full", "type", "full"),
    ])
    await update.message.reply_text(
        "\U0001f4e1 *RED* — ¿Perfil Nmap?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def _handle_red_type(query, uid, wizard, subtype):
    if subtype not in {"quick", "normal", "full"}:
        await query.edit_message_text("Tipo de RED no permitido.")
        return
    updates = dict(
        step="awaiting_target",
        scan_type=subtype,
        target=None,
    )
    await query.edit_message_text(
        "Introduce una IP, dominio o rango autorizado:"
    )
    wizard.update(updates)


# ─── OSINT Wizard ───


async def _start_osint_wizard(update, uid):
    wizard = _new_wizard(uid, "osint", update.effective_chat.id)
    keyboard = _wizard_keyboard(wizard, [
        ("\U0001f4e7 Email", "type", "email"),
        ("\U0001f310 Dominio", "type", "domain"),
    ])
    await update.message.reply_text("\U0001f50e *OSINT* \u2014 \u00bfTipo?", parse_mode="Markdown", reply_markup=keyboard)


async def _handle_osint_type(query, uid, wizard, subtype):
    prompts = {
        "email": "Introduce el email:",
        "domain": "Introduce el dominio:",
    }
    if subtype not in prompts:
        await query.edit_message_text("Tipo de OSINT no permitido.")
        return
    updates = dict(
        step="awaiting_target",
        osint_type=subtype,
        target=None,
    )
    await query.edit_message_text(prompts[subtype])
    wizard.update(updates)


def _validate_osint_email(value: str) -> str | None:
    if not re.fullmatch(
        r"[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+", value
    ):
        return "Email inválido. Usa una dirección con dominio completo."
    domain = value.rsplit("@", 1)[1]
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        return "Email inválido. Debe usar un dominio, no una IP."
    if tools_engine.validate_target(domain):
        return "Email inválido. Usa una dirección con dominio válido."
    return None


def _validate_osint_domain(value: str) -> str | None:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError:
            pass
        else:
            return "Introduce un dominio, no un rango CIDR."
    else:
        return "Introduce un dominio, no una dirección IP."

    private_suffixes = (
        ".home",
        ".home.arpa",
        ".internal",
        ".lan",
        ".local",
        ".localdomain",
        ".localhost",
    )
    if value.casefold().endswith(private_suffixes):
        return "El dominio privado no está permitido."
    return tools_engine.validate_target(value)


def _format_email_osint(result: dict, target: str) -> str:
    if result.get("error"):
        return f"\u274c {result['error']}"

    lines = ["\U0001f50e OSINT Email", f"Email: {result.get('email', target)}"]
    domain = result.get("domain")
    if domain:
        lines.append(f"Dominio: {domain}")

    mx_records = result.get("mx_records") or []
    if mx_records:
        lines.append("MX:")
        lines.extend(f"- {record}" for record in mx_records[:10])
    else:
        lines.append("MX: sin registros reportados")

    domain_info = result.get("dominio_info") or {}
    total_certs = domain_info.get("total_certs")
    if total_certs is not None:
        lines.append(f"Certificados reportados: {total_certs}")
    cert_domains = domain_info.get("subdominios_cert") or []
    if cert_domains:
        lines.append("Dominios en certificados:")
        lines.extend(f"- {domain}" for domain in cert_domains[:20])

    warnings = result.get("warnings") or []
    if warnings:
        for w in warnings:
            lines.append(f"\u26a0\ufe0f {w}")

    status = result.get("status", "ok")
    if status == "error":
        lines.append("\u274c OSINT fall\u00f3: todas las fuentes reportaron error")
    elif status == "partial":
        lines.append("\u26a0\ufe0f Resultado parcial: algunas fuentes no respondieron")

    return "\n".join(lines)


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

    if uid in user_wizards and _is_wizard_expired(uid):
        await update.message.reply_text(
            "Este wizard expiro. Abre uno nuevo desde el menu."
        )
        return

    wizard = user_wizards.get(uid)
    if wizard and wizard.get("chat_id") != update.effective_chat.id:
        await update.message.reply_text(
            "Este wizard pertenece a otro chat. Continua en el chat original."
        )
        return

    menu = {
        "\U0001f50d Recon": lambda: _start_recon_wizard(update, uid),
        "\U0001f310 Web": lambda: _start_web_wizard(update, uid),
        "\U0001f511 Crack": lambda: _start_crack_wizard(update, uid),
        "\U0001f4a3 Payloads": lambda: _start_payload_wizard(update, uid),
        "\U0001f4e1 Red": lambda: _start_red_wizard(update, uid),
        "\U0001f50e OSINT": lambda: _start_osint_wizard(update, uid),
        "\U0001f4cb Mis Tareas": lambda: tareas(update, context),
        "\u2753 Ayuda": lambda: ayuda(update, context),
        "\u2699\ufe0f Objetivo": lambda: _objetivo_wizard(update, uid),
    }
    handler = menu.get(text)
    if handler:
        user_wizards.pop(uid, None)
        await handler()
        return

    if uid in user_wizards:
        wizard = user_wizards[uid]
        wtype = wizard["type"]
        step = wizard["step"]

        if step == "awaiting_target":
            if wtype == "objetivo":
                state = dict(wizard)
                consumed = _consume_wizard(
                    uid, state.get("session_id", "")
                )
                if not consumed:
                    await update.message.reply_text(
                        "Este wizard expiro. Vuelve al menu."
                    )
                    return
                try:
                    target_engine.set_target(uid, text, "domain")
                except Exception as exc:
                    log.exception("Objetivo wizard failed")
                    audit_log.log(
                        uid,
                        _username(update),
                        "wizard:objetivo",
                        text,
                        "error",
                        str(exc),
                    )
                    await _safe_reply_text(
                        update.message,
                        "No se pudo guardar el objetivo. Abre un nuevo wizard desde el menu.",
                    )
                    return
                audit_log.log(
                    uid,
                    _username(update),
                    "wizard:objetivo",
                    text,
                    "ok",
                    "",
                )
                await _safe_reply_text(
                    update.message,
                    f"\u2705 Objetivo establecido: `{text}`",
                    parse_mode="Markdown",
                )
                return

            elif wtype == "red":
                error = tools_engine.validate_target(text)
                if error:
                    await _safe_reply_text(
                        update.message, f"\u274c {error}"
                    )
                    return

                if "/" in text:
                    target_type = "network"
                else:
                    try:
                        ipaddress.ip_address(text)
                    except ValueError:
                        target_type = "domain"
                    else:
                        target_type = "ip"

                consumed = _consume_wizard(
                    uid, wizard.get("session_id", "")
                )
                if not consumed:
                    await update.message.reply_text(
                        "Este wizard expiro. Vuelve al menu."
                    )
                    return

                scan_type = consumed.get("scan_type", "normal")
                try:
                    target_engine.set_target(uid, text, target_type)
                    task_id = task_queue.submit(
                        "nmap",
                        text,
                        {"scan_type": scan_type, "user_id": uid},
                    )
                    if not task_id:
                        raise RuntimeError(
                            "Task queue returned no task ID"
                        )
                except Exception as exc:
                    log.exception("Red wizard failed")
                    audit_log.log(
                        uid,
                        _username(update),
                        "wizard:red",
                        text,
                        "error",
                        str(exc),
                    )
                    await _safe_reply_text(
                        update.message,
                        "No se pudo iniciar Red. Abre un nuevo wizard desde el menu.",
                    )
                    await _safe_reply_text(
                        update.message,
                        "Menú principal:",
                        reply_markup=MAIN_KEYBOARD,
                    )
                    return

                audit_log.log(
                    uid,
                    _username(update),
                    "wizard:red",
                    text,
                    "ok",
                    f"task:{task_id} scan_type:{scan_type}",
                )
                msg = await _safe_reply_text(
                    update.message,
                    f"\u2705 `{task_id}` — Escaneando {text} ({scan_type})",
                    parse_mode="Markdown",
                )
                asyncio.create_task(
                    _poll_nmap_task(
                        msg, task_id, return_to_menu=True
                    )
                )
                return

            target_type = wizard.get("target_type", "domain")
            if wtype == "web":
                normalized, hostname, error = _normalize_web_input(text)
                if error:
                    await _safe_reply_text(
                        update.message,
                        f"Error: {error}\n"
                        "Introduce una URL HTTP(S) e intenta de nuevo."
                    )
                    return

                operations = {
                    "recon": (
                        "recon_web",
                        normalized,
                        "normal",
                        "Reconocimiento Web",
                    ),
                    "vuln": (
                        "web_audit",
                        normalized,
                        "profundo",
                        "Auditoría de Vulnerabilidades",
                    ),
                }
                operation = operations.get(wizard.get("audit_type"))
                if not operation:
                    await _safe_reply_text(
                        update.message,
                        "Tipo de auditoria Web no permitido.",
                    )
                    return

                playbook, playbook_target, depth, label = operation
                state = dict(wizard)
                consumed = _consume_wizard(
                    uid, state.get("session_id", "")
                )
                if not consumed:
                    await _safe_reply_text(
                        update.message,
                        "Este wizard expiro. Vuelve al menu.",
                    )
                    return

                try:
                    target_engine.set_target(uid, normalized, "url")
                    task_id = task_queue.submit(
                        "playbook",
                        playbook_target,
                        {"playbook": playbook, "depth": depth, "user_id": uid},
                    )
                    if not task_id:
                        raise RuntimeError(
                            "Task queue returned no task ID"
                        )
                except Exception as exc:
                    log.exception("Web wizard failed")
                    audit_log.log(
                        uid,
                        _username(update),
                        "wizard:web",
                        normalized,
                        "error",
                        str(exc),
                    )
                    await _safe_reply_text(
                        update.message,
                        "No se pudo iniciar Web. Abre un nuevo wizard desde el menu.",
                    )
                    return

                audit_log.log(
                    uid,
                    _username(update),
                    "wizard:web",
                    normalized,
                    "ok",
                    f"task:{task_id} playbook:{playbook} depth:{depth}",
                )
                msg = await _safe_reply_text(
                    update.message,
                    f"Web iniciado: `{task_id}`\n{label}\n{normalized}",
                    parse_mode="Markdown",
                )
                asyncio.create_task(
                    _poll_playbook_task(
                        msg,
                        task_id,
                        label,
                        return_to_menu=True,
                    )
                )
                return
            elif wtype == "recon":
                error = tools_engine.validate_target(text)
                if error:
                    await _safe_reply_text(
                        update.message, f"\u274c {error}"
                    )
                    return

                state = dict(wizard)
                consumed = _consume_wizard(
                    uid, state.get("session_id", "")
                )
                if not consumed:
                    await _safe_reply_text(
                        update.message,
                        "Este wizard expiro. Vuelve al menu.",
                    )
                    return

                target = text
                scan_type = consumed.get("scan_type", "normal")
                if "/" in target:
                    target_type = "network"
                else:
                    try:
                        ipaddress.ip_address(target)
                    except ValueError:
                        target_type = "domain"
                    else:
                        target_type = "ip"

                try:
                    target_engine.set_target(uid, target, target_type)
                    task_id = task_queue.submit(
                        "nmap",
                        target,
                        {"scan_type": scan_type, "user_id": uid},
                    )
                    if not task_id:
                        raise RuntimeError("Task queue returned no task ID")
                except Exception as exc:
                    log.exception("Recon wizard failed")
                    audit_log.log(
                        uid,
                        _username(update),
                        "wizard:recon",
                        target,
                        "error",
                        str(exc),
                    )
                    await _safe_reply_text(
                        update.message,
                        "No se pudo iniciar Recon. Abre un nuevo wizard desde el menu.",
                    )
                    return

                audit_log.log(
                    uid,
                    _username(update),
                    "wizard:recon",
                    target,
                    "ok",
                    f"task:{task_id} scan_type:{scan_type}",
                )
                msg = await _safe_reply_text(
                    update.message,
                    f"\u2705 `{task_id}` \u2014 Escaneando {target} ({scan_type})",
                    parse_mode="Markdown",
                )
                asyncio.create_task(
                    _poll_nmap_task(msg, task_id, return_to_menu=True)
                )
            elif wtype == "osint":
                osint_type = wizard.get("osint_type")
                if osint_type == "email":
                    error = _validate_osint_email(text)
                    if error:
                        await _safe_reply_text(
                            update.message, f"\u274c {error}"
                        )
                        return

                    consumed = _consume_wizard(
                        uid, wizard.get("session_id", "")
                    )
                    if not consumed:
                        await update.message.reply_text(
                            "Este wizard expiro. Vuelve al menu."
                        )
                        return

                    status_message = await _safe_reply_text(
                        update.message,
                        f"\U0001f50e Consultando OSINT para {text}...",
                    )
                    try:
                        target_engine.set_target(uid, text, "email")
                        result = await asyncio.to_thread(
                            hacking.osint.email_osint, text
                        )
                    except Exception as exc:
                        log.exception("OSINT email wizard failed")
                        audit_log.log(
                            uid,
                            _username(update),
                            "wizard:osint:email",
                            text,
                            "error",
                            str(exc),
                        )
                        await _safe_edit_text(
                            status_message,
                            "No se pudo completar OSINT. Abre un nuevo wizard desde el menu.",
                        )
                        await _safe_reply_text(
                            update.message,
                            "Menú principal:",
                            reply_markup=MAIN_KEYBOARD,
                        )
                        return

                    result_status = result.get("status", "error" if result.get("error") else "ok")
                    audit_log.log(
                        uid,
                        _username(update),
                        "wizard:osint:email",
                        text,
                        result_status,
                        "email_osint",
                    )
                    await _safe_edit_text(
                        status_message,
                        _format_email_osint(result, text),
                    )
                    await _safe_reply_text(
                        update.message,
                        "Menú principal:",
                        reply_markup=MAIN_KEYBOARD,
                    )
                    return

                if osint_type != "domain":
                    await update.message.reply_text(
                        "Tipo de OSINT no permitido."
                    )
                    return

                error = _validate_osint_domain(text)
                if error:
                    await _safe_reply_text(
                        update.message, f"\u274c {error}"
                    )
                    return

                consumed = _consume_wizard(
                    uid, wizard.get("session_id", "")
                )
                if not consumed:
                    await update.message.reply_text(
                        "Este wizard expiro. Vuelve al menu."
                    )
                    return

                try:
                    target_engine.set_target(uid, text, "domain")
                    task_id = task_queue.submit(
                        "playbook",
                        text,
                        {
                            "playbook": "osint_domain",
                            "depth": "normal",
                            "user_id": uid,
                        },
                    )
                    if not task_id:
                        raise RuntimeError(
                            "Task queue returned no task ID"
                        )
                except Exception as exc:
                    log.exception("OSINT domain wizard failed")
                    audit_log.log(
                        uid,
                        _username(update),
                        "wizard:osint",
                        text,
                        "error",
                        str(exc),
                    )
                    await _safe_reply_text(
                        update.message,
                        "No se pudo iniciar OSINT. Abre un nuevo wizard desde el menu.",
                    )
                    await _safe_reply_text(
                        update.message,
                        "Menú principal:",
                        reply_markup=MAIN_KEYBOARD,
                    )
                    return

                msg = await _safe_reply_text(
                    update.message,
                    f"\u2705 *OSINT* — `{task_id}`\n{text}",
                    parse_mode="Markdown",
                )
                asyncio.create_task(
                    _poll_playbook_task(
                        msg,
                        task_id,
                        "OSINT de Dominio",
                        return_to_menu=True,
                        uid=uid,
                    )
                )
            return

        elif step == "awaiting_value":
            if wtype == "crack":
                if wizard.get("crack_type") != "hash":
                    await update.message.reply_text(
                        "Tipo de crack no permitido."
                    )
                    return
                algorithm, error = _validate_hash_algorithm(text)
                if error:
                    await _safe_reply_text(update.message, error)
                    return
                wizard.update(
                    target=text,
                    algorithm=algorithm,
                    step="select_dict",
                )
                keyboard = _wizard_keyboard(wizard, [
                    ("\U0001f4da Integrado", "method", "integrated"),
                    ("\U0001f3b2 Custom", "method", "custom"),
                ])
                await update.message.reply_text("\U0001f511 \u00bfDiccionario?", reply_markup=keyboard)
                return

        elif step == "awaiting_dictionary" and wtype == "crack":
            if wizard.get("crack_type") != "hash":
                await update.message.reply_text(
                    "Metodo de crack no permitido."
                )
                return
            words = [
                word.strip()
                for word in text.replace("\n", ",").split(",")
                if word.strip()
            ]
            if not words:
                await update.message.reply_text("\u274c Introduce al menos una palabra.")
                return
            algorithm, error = _validate_hash_algorithm(
                wizard.get("target", "")
            )
            if error:
                await _safe_reply_text(update.message, error)
                return
            state = dict(wizard)
            consumed = _consume_wizard(
                uid, state.get("session_id", "")
            )
            if not consumed:
                await update.message.reply_text(
                    "Este wizard expiro. Vuelve al menu."
                )
                return

            hash_value = consumed["target"]
            await _safe_reply_text(
                update.message, "\u23f3 Analizando hash..."
            )
            try:
                result = hacking.crypto.hash_crack(hash_value, words)
            except Exception as exc:
                log.exception("Custom Crack wizard failed")
                audit_log.log(
                    uid,
                    _username(update),
                    "wizard:crack",
                    hash_value,
                    "error",
                    str(exc),
                )
                await _safe_reply_text(
                    update.message,
                    "No se pudo completar Crack. Abre un nuevo wizard desde el menu.",
                )
                await _safe_reply_text(
                    update.message,
                    "Menú principal:",
                    reply_markup=MAIN_KEYBOARD,
                )
                return
            status = "ok" if result.get("cracked") else "fail"
            audit_log.log(
                uid,
                _username(update),
                "wizard:crack",
                hash_value,
                status,
                "custom",
            )
            message = _format_crack(result, "custom")
            await _safe_reply_text(
                update.message, message, parse_mode="Markdown"
            )
            await _safe_reply_text(
                update.message,
                "Menú principal:",
                reply_markup=MAIN_KEYBOARD,
            )
            return

        elif step == "awaiting_endpoint" and wtype == "payload":
            ip, port, error = _parse_payload_endpoint(
                update.message.text
            )
            if error:
                await update.message.reply_text(f"\u274c {error}")
                return

            if (
                wizard.get("payload_type") != "reverse"
                or wizard.get("lang") != "bash"
            ):
                await update.message.reply_text(
                    "Tipo de payload no permitido."
                )
                return

            consumed = _consume_wizard(
                uid, wizard.get("session_id", "")
            )
            if not consumed:
                await update.message.reply_text(
                    "Este wizard expiro. Vuelve al menu."
                )
                return
            lang = consumed["lang"]
            audit_target = (
                f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"
            )
            try:
                result = hacking.payloads.reverse_shell(
                    ip, port, lang
                )
            except Exception as exc:
                log.exception("Payload wizard failed")
                audit_log.log(
                    uid,
                    _username(update),
                    "wizard:payload",
                    audit_target,
                    "error",
                    str(exc),
                )
                await _safe_reply_text(
                    update.message,
                    "No se pudo generar el payload. Abre un nuevo wizard desde el menu.",
                )
                await _safe_reply_text(
                    update.message,
                    "Menú principal:",
                    reply_markup=MAIN_KEYBOARD,
                )
                return
            status = "error" if result.get("error") else "ok"
            audit_log.log(
                uid,
                _username(update),
                "wizard:payload",
                audit_target,
                status,
                lang,
            )
            msg = _format_payload(result)
            await _safe_reply_text(
                update.message, msg, parse_mode="Markdown"
            )
            await _safe_reply_text(
                update.message,
                "Menú principal:",
                reply_markup=MAIN_KEYBOARD,
            )
            return

    await _chat_api(update, text)


async def _objetivo_wizard(update, uid):
    _new_wizard(
        uid,
        "objetivo",
        update.effective_chat.id,
        step="awaiting_target",
    )
    await update.message.reply_text("Introduce el target (IP, dominio o rango):")


def _format_crack(result: dict, method: str = "integrated") -> str:
    lines = ["\U0001f511 *Hash Crack*"]
    lines.append(f"Hash: `{result['hash']}`")
    lines.append(f"Algoritmo: {result['algorithm']}")
    if result.get("identified"):
        types = [t["type"] for t in result["identified"]]
        lines.append(f"Identificado: {', '.join(types)}")
    if result.get("cracked"):
        lines.append(f"\u2705 *Crackeado:* `{result['plaintext']}`")
    else:
        dictionary = "custom" if method == "custom" else "integrado"
        lines.append(
            f"\u274c No se pudo crackear con el diccionario {dictionary}."
        )
    return "\n".join(lines)


def _format_payload(result: dict) -> str:
    if "error" in result:
        return f"\u274c {result['error']}"
    payload_type = result.get("type", "reverse")
    payload = result.get("decoded", result.get("payload", ""))
    encoded = result.get("encoded", result.get("encoded_b64", ""))
    lines = ["\U0001f4a3 *Payload ({})*".format(payload_type)]
    lines.append(f"```\n{payload}\n```")
    if result.get("listener"):
        lines.append(f"\U0001f4e1 Listener: `{result['listener']}`")
    if encoded:
        lines.append(f"\U0001f510 Base64: `{encoded}`")
    return "\n".join(lines)


def _format_webshell(result: dict) -> str:
    if "error" in result:
        return f"\u274c {result['error']}"
    language = result.get("language", "webshell")
    return (
        f"\U0001f4bb *Webshell ({language})*\n"
        f"```\n{result.get('decoded', '')}\n```\n"
        f"\U0001f510 Base64: `{result.get('encoded', '')}`"
    )


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
    await _safe_reply_text(
        update.message, "\n".join(lines), parse_mode="Markdown"
    )


async def _send_report(update, uid):
    target_info = target_engine.get_target(uid)
    if not target_info:
        await update.message.reply_text("\u274c No hay objetivo establecido. Usa /objetivo <target> primero.")
        return
    target = target_info["target"]
    try:
        report = generate_report(target, {}, fmt="md")
        content = report.get("content", "")[:3000]
        await _safe_reply_text(
            update.message,
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
    await _safe_reply_text(
        update.message, "\n".join(lines), parse_mode="Markdown"
    )


async def _chat_api(update, text):
    delivery_kwargs = {}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{API_URL}/chat",
                json={"message": text},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if not isinstance(data, dict):
                        raise ValueError("response JSON is not an object")
                except ValueError as exc:
                    log.warning("Chat API returned invalid JSON: %s", exc)
                    msg = "\u274c Respuesta invalida de la API."
                else:
                    msg = data.get("response", "Sin respuesta")
                    delivery_kwargs["parse_mode"] = "Markdown"
            else:
                msg = f"\u274c Error de API: {resp.status_code}"
    except httpx.HTTPError as exc:
        msg = f"\u274c Error de conexi\u00f3n: {str(exc)}"

    await _safe_reply_text(update.message, msg, **delivery_kwargs)


# ─── Callback Query Handler ───


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    wizard, action, value, rejection = _validate_wizard_callback(
        uid, chat_id, query.data
    )
    if rejection:
        reason, message = rejection
        await _reject_callback(query, reason, message, uid, chat_id)
        return

    if action == "back":
        if not _consume_wizard(uid, wizard["session_id"]):
            await _send_expired_callback(query)
            return
        await query.answer()
        await _safe_edit_message(query, "Operaci\u00f3n cerrada.")
        await _safe_reply_text(
            query.message,
            "Men\u00fa principal:",
            reply_markup=MAIN_KEYBOARD,
        )
        return
    if action == "cancel":
        if not _consume_wizard(uid, wizard["session_id"]):
            await _send_expired_callback(query)
            return
        await query.answer()
        await _safe_edit_message(query, "\u274c Operaci\u00f3n cancelada.")
        return

    wizard_type = wizard["type"]
    if action == "type":
        await query.answer()
        handlers = {
            "recon": _handle_recon_type,
            "web": _handle_web_type,
            "crack": _handle_crack_type,
            "payload": _handle_payload_type,
            "red": _handle_red_type,
            "osint": _handle_osint_type,
        }
        await handlers[wizard_type](query, uid, wizard, value)
        return
    if wizard_type == "crack" and action == "method":
        if value == "custom":
            await query.answer()
            await query.edit_message_text(
                "Introduce palabras separadas por comas:"
            )
            wizard.update(step="awaiting_dictionary")
        else:
            consumed = _consume_wizard(uid, wizard["session_id"])
            if not consumed:
                await _send_expired_callback(query)
                return
            await query.answer()
            await _execute_crack(
                query,
                uid,
                wizard,
                value,
                consumed_wizard=consumed,
            )
        return
    if wizard_type == "payload" and action == "lang":
        if wizard.get("payload_type") == "webshell":
            consumed = _consume_wizard(uid, wizard["session_id"])
            if not consumed:
                await _send_expired_callback(query)
                return
            await query.answer()
            await _handle_payload_lang(
                query,
                uid,
                wizard,
                value,
                consumed_wizard=consumed,
            )
        else:
            await query.answer()
            await _handle_payload_lang(query, uid, wizard, value)
        return

    log.warning(
        "Telegram callback rejected: reason=%s user=%s chat=%s data=%r",
        "unroutable_callback",
        uid,
        chat_id,
        query.data,
    )


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
                    f"ID: `{file_id}`"
                )
            else:
                await update.message.reply_text(f"\u274c Error al subir: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"\u274c Error: {str(e)}")


# ─── Voice Handler ───


def _process_voice_blocking(ogg_bytes: bytes, uid: int) -> str:
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

    return text


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

    text = await asyncio.to_thread(_process_voice_blocking, ogg_bytes, uid)

    if text and not text.startswith("["):
        await _safe_reply_text(
            update.message,
            f"\U0001f3a4 *Transcripci\u00f3n:*\n{text}",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(text)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        return
    rl = _rate_limit_msg(uid)
    if rl:
        await update.message.reply_text(rl)
        return

    await update.message.reply_text(
        "El cracking de archivos no esta disponible. Usa el flujo Hash."
    )


async def _open_wizard_command(update, starter):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("No autorizado")
        return
    rate_limit_error = _rate_limit_msg(uid)
    if rate_limit_error:
        await update.message.reply_text(rate_limit_error)
        return
    user_wizards.pop(uid, None)
    await starter(update, uid)


async def recon_command(update, context):
    await _open_wizard_command(update, _start_recon_wizard)


async def web_command(update, context):
    await _open_wizard_command(update, _start_web_wizard)


async def crack_command(update, context):
    await _open_wizard_command(update, _start_crack_wizard)


async def payload_command(update, context):
    await _open_wizard_command(update, _start_payload_wizard)


async def osint_command(update, context):
    await _open_wizard_command(update, _start_osint_wizard)


# ─── Ayuda ───


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    msg = (
        "*Comandos:*\n"
        "`/objetivo <target>` \u2014 Establecer target global\n"
        "`/nmap [tipo] [target]` \u2014 Escanear con Nmap\n"
        "`/tarea <id>` \u2014 Ver estado de tarea\n"
        "`/tareas` \u2014 Listar tareas\n"
        "`/ayuda` \u2014 Esta ayuda\n\n"
        "*Tipos de escaneo:* `quick`, `normal` (default), `full`, `vuln`\n\n"
        "*Ejemplos:*\n"
        "`/objetivo scanme.nmap.org`\n"
        "`/nmap` \u2014 escanea objetivo guardado\n"
        "`/nmap full` \u2014 escanea objetivo con full\n"
        "`/nmap quick 8.8.8.8` \u2014 escanea otra IP"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


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
    application.add_handler(CommandHandler("tarea", tarea))
    application.add_handler(CommandHandler("tareas", tareas))
    application.add_handler(CommandHandler("nmap", nmap_shortcut))
    application.add_handler(CommandHandler("recon", recon_command))
    application.add_handler(CommandHandler(["webscan", "web"], web_command))
    application.add_handler(CommandHandler("crack", crack_command))
    application.add_handler(CommandHandler("payload", payload_command))
    application.add_handler(CommandHandler("osint", osint_command))
    application.add_handler(CommandHandler("ayuda", ayuda))
    application.add_handler(CommandHandler("help", ayuda))

    # Manejador global de texto e interacción de menús
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))

    print("[OK] Bot de Artenisa sincronizado y escuchando en Telegram...")
    log.info("Bot de Telegram iniciado con éxito.")
    
    # Arrancar el polling de forma síncrona pura (rompe el congelamiento del contenedor)
    application.run_polling()

if __name__ == "__main__":
    main()
