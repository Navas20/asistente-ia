import os
import asyncio
import ipaddress
import logging
import re
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


async def _safe_reply_text(message, text, **kwargs):
    try:
        return await message.reply_text(text, **kwargs)
    except BadRequest as exc:
        if "parse_mode" not in kwargs:
            raise
        log.warning("Markdown parse failed, retrying as plain text")
        fallback = dict(kwargs)
        fallback.pop("parse_mode", None)
        return await message.reply_text(text, **fallback)


def _back_cancel_keyboard(wizard_type: str):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f519 Atr\u00e1s", callback_data=f"back_{wizard_type}"),
            InlineKeyboardButton("\u274c Cancelar", callback_data="cancel"),
        ]
    ])


def _menu_keyboard(options: list[tuple[str, str]], wizard_type: str):
    buttons = []
    for label, cb in options:
        buttons.append(InlineKeyboardButton(label, callback_data=cb))
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([
        InlineKeyboardButton("\U0001f519 Atr\u00e1s", callback_data=f"back_{wizard_type}"),
        InlineKeyboardButton("\u274c Cancelar", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(rows)


async def _back_to_menu(message):
    await _safe_reply_text(message, "Men\u00fa principal:", reply_markup=MAIN_KEYBOARD)


async def _return_to_menu_with_result(message, text):
    await _safe_reply_text(message, text)
    await _back_to_menu(message)


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
    await _safe_reply_text(update.message, msg, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


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
    await _safe_reply_text(update.message, f"\u2705 Objetivo establecido: `{target}`", parse_mode="Markdown")


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
    await _safe_reply_text(update.message, "\n".join(lines), parse_mode="Markdown")


# ─── Helper: execute a direct hacking function ───

def _run_blocking(fn, *args, **kwargs):
    return fn(*args, **kwargs)


async def _run_crack(hash_value: str, wordlist=None) -> dict:
    if wordlist:
        return hacking.crypto.hash_crack(hash_value, wordlist)
    return hacking.crypto.hash_crack(hash_value)


# ─── Wizard Starters ───

async def _start_recon_wizard(update, uid):
    user_wizards[uid] = {"type": "recon", "step": "select_type", "data": {}}
    keyboard = _menu_keyboard([
        ("\u26a1 Quick", "recon_quick"),
        ("\U0001f50e Normal", "recon_normal"),
        ("\U0001f9e0 Full", "recon_full"),
    ], "recon")
    await update.message.reply_text("\U0001f50d *Recon* \u2014 \u00bfTipo de escaneo?", parse_mode="Markdown", reply_markup=keyboard)


async def _start_web_wizard(update, uid):
    user_wizards[uid] = {"type": "web", "step": "select_type", "data": {}}
    keyboard = _menu_keyboard([
        ("\U0001f9f0 Nikto", "web_nikto"),
        ("\U0001f50d SQLi", "web_sqli"),
        ("\U0001f512 SSL Check", "web_ssl"),
        ("\U0001f577\ufe0f Crawler", "web_crawler"),
    ], "web")
    await update.message.reply_text("\U0001f310 *Web* \u2014 \u00bfTipo de auditor\u00eda?", parse_mode="Markdown", reply_markup=keyboard)


async def _start_crack_wizard(update, uid):
    user_wizards[uid] = {"type": "crack", "step": "select_type", "data": {}}
    keyboard = _menu_keyboard([
        ("\U0001f511 Hash", "crack_hash"),
    ], "crack")
    await update.message.reply_text("\U0001f511 *Crack* \u2014 \u00bfTipo?", parse_mode="Markdown", reply_markup=keyboard)


async def _start_payload_wizard(update, uid):
    user_wizards[uid] = {"type": "payload", "step": "select_type", "data": {}}
    keyboard = _menu_keyboard([
        ("\U0001f41a Reverse Shell", "payload_reverse"),
        ("\U0001f916 Meterpreter", "payload_meterpreter"),
        ("\U0001f4bb Webshell", "payload_webshell"),
    ], "payload")
    await update.message.reply_text("\U0001f4a3 *Payload* \u2014 \u00bfTipo?", parse_mode="Markdown", reply_markup=keyboard)


async def _start_red_wizard(update, uid):
    user_wizards[uid] = {"type": "red", "step": "select_type", "data": {}}
    keyboard = _menu_keyboard([
        ("\U0001f4f6 Escanear WiFi", "red_wifi_scan"),
        ("\U0001f511 Crackear WiFi", "red_wifi_crack"),
        ("\U0001f4e1 Escanear LAN", "red_lan_scan"),
    ], "red")
    await update.message.reply_text("\U0001f4e1 *Red* \u2014 \u00bfTipo de operaci\u00f3n?", parse_mode="Markdown", reply_markup=keyboard)


async def _start_osint_wizard(update, uid):
    user_wizards[uid] = {"type": "osint", "step": "select_type", "data": {}}
    keyboard = _menu_keyboard([
        ("\U0001f4e7 Email", "osint_email"),
        ("\U0001f310 Dominio", "osint_domain"),
        ("\U0001f9d1 Persona", "osint_person"),
    ], "osint")
    await update.message.reply_text("\U0001f50e *OSINT* \u2014 \u00bfTipo?", parse_mode="Markdown", reply_markup=keyboard)


# ─── Inline Keyboard Selection Handling ───
# After user clicks an option in the menu, handle_callback routes here.
# These functions ask for target data or execute directly.

SUPPORTED_HASH_ALGORITHMS = frozenset({"MD5", "SHA1", "SHA224", "SHA256", "SHA384", "SHA512"})


def _validate_hash_algorithm(value: str) -> tuple[str | None, str | None]:
    candidates = hacking.crypto.hash_id(value.strip())
    for candidate in candidates:
        algorithm = candidate.get("type", "")
        if algorithm in SUPPORTED_HASH_ALGORITHMS:
            return algorithm, None
    detected = ", ".join(candidate.get("type", "desconocido") for candidate in candidates)
    return None, f"Algoritmo no soportado: {detected}. Usa MD5 o SHA1/224/256/384/512."


async def _handle_crack_hash(query, uid):
    user_wizards[uid].update(step="awaiting_hash", data={})
    await query.edit_message_text("Pega el hash:")


async def _execute_crack_now(query, uid, hash_value, method="integrated", wordlist=None):
    algorithm, error = _validate_hash_algorithm(hash_value)
    if error:
        await _safe_reply_text(query.message, error)
        return
    await query.edit_message_text("\u23f3 Analizando hash...")
    try:
        result = await asyncio.to_thread(hacking.crypto.hash_crack, hash_value, wordlist)
    except Exception as exc:
        log.exception("Crack wizard failed")
        audit_log.log(uid, str(uid), "wizard:crack", hash_value, "error", str(exc))
        await query.edit_message_text("No se pudo completar Crack.")
        await _back_to_menu(query.message)
        return
    status = "ok" if result.get("cracked") else "fail"
    audit_log.log(uid, str(uid), "wizard:crack", hash_value, status, method)
    lines = ["\U0001f511 *Hash Crack*"]
    lines.append(f"Hash: `{result['hash']}`")
    lines.append(f"Algoritmo: {result['algorithm']}")
    if result.get("identified"):
        types = [t["type"] for t in result["identified"]]
        lines.append(f"Identificado: {', '.join(types)}")
    if result.get("cracked"):
        lines.append(f"\u2705 *Crackeado:* `{result['plaintext']}`")
    else:
        lines.append(f"\u274c No se pudo crackear con el diccionario {method}.")
    msg = "\n".join(lines)
    await query.edit_message_text(msg, parse_mode="Markdown")
    await _back_to_menu(query.message)


async def _handle_payload_type(query, uid, payload_type):
    wiz = user_wizards.get(uid)
    if not wiz:
        return
    wiz["step"] = "select_subtype"
    wiz["data"]["payload_type"] = payload_type

    if payload_type == "reverse":
        langs = [
            ("\U0001f539 Bash", "payload_lang_bash"),
            ("\U0001f7e8 Python", "payload_lang_python"),
            ("\U0001f7e9 PHP", "payload_lang_php"),
            ("\U0001f7ea PowerShell", "payload_lang_powershell"),
        ]
        keyboard = _menu_keyboard(langs, "payload")
        await query.edit_message_text("\U0001f4a3 \u00bfLenguaje?", reply_markup=keyboard)
    elif payload_type == "meterpreter":
        await query.edit_message_text("Introduce IP:Puerto para el listener:")
    elif payload_type == "webshell":
        langs = [
            ("\U0001f7e8 PHP", "payload_lang_php"),
            ("\U0001f7ea ASP", "payload_lang_asp"),
            ("\U0001f7e7 ASPX", "payload_lang_aspx"),
            ("\U0001f7e6 JSP", "payload_lang_jsp"),
            ("\U0001f7e5 Python CGI", "payload_lang_py"),
        ]
        keyboard = _menu_keyboard(langs, "payload")
        await query.edit_message_text("\U0001f4bb \u00bfLenguaje?", reply_markup=keyboard)


def _parse_endpoint(value: str) -> tuple[str | None, int | None, str | None]:
    raw = value.strip()
    if raw.startswith("["):
        m = re.fullmatch(r"\[([^\[\]\s]+)\]:([0-9]+)", raw)
        if not m:
            return None, None, "Formato inv\u00e1lido. Usa [IPv6]:Puerto."
        host, port_text = m.groups()
    else:
        m = re.fullmatch(r"([^:\s]+):([0-9]+)", raw)
        if not m:
            return None, None, "Formato inv\u00e1lido. Usa IP:Puerto."
        host, port_text = m.groups()
    try:
        address = ipaddress.ip_address(host)
        port = int(port_text)
    except ValueError:
        return None, None, "IP o puerto inv\u00e1lido."
    if not 1 <= port <= 65535:
        return None, None, "Puerto inv\u00e1lido (1-65535)."
    return str(address), port, None


def _format_payload(payload: dict) -> str:
    if "error" in payload:
        return f"\u274c {payload['error']}"
    ptype = payload.get("type", "payload")
    decoded = payload.get("decoded", payload.get("payload", ""))
    encoded = payload.get("encoded", payload.get("encoded_b64", ""))
    lines = [f"\U0001f4a3 *Payload ({ptype})*"]
    lines.append(f"```\n{decoded}\n```")
    if encoded:
        lines.append(f"\U0001f510 Base64: `{encoded}`")
    return "\n".join(lines)


async def _handle_red_wifi_scan(query, uid):
    await query.edit_message_text("\U0001f4f6 Escaneando redes WiFi...")
    try:
        result = await asyncio.to_thread(hacking.network.scan_wifi_networks)
    except Exception as e:
        log.exception("WiFi scan failed")
        result = {"error": str(e)}
    if "error" in result:
        await query.edit_message_text(f"\u274c WiFi: {result['error']}")
    else:
        lines = [f"\U0001f4f6 *Redes WiFi ({result.get('total', 0)})*"]
        for net in result.get("networks", []):
            ssid = net.get("ssid", "?")
            signal = net.get("signal", "?")
            auth = net.get("auth", "?")
            bssid = net.get("bssid", "?")
            lines.append(f"\n*{ssid}*")
            lines.append(f"  \U0001f4f6 Se\u00f1al: {signal}")
            lines.append(f"  \U0001f512 Auth: {auth}")
            if bssid:
                lines.append(f"  \U0001f4cb BSSID: {bssid}")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
    await _back_to_menu(query.message)


async def _handle_red_lan_scan(query, uid):
    await query.edit_message_text("\U0001f4e1 Escaneando red local...")
    try:
        result = await asyncio.to_thread(hacking.network.scan_local_network)
    except Exception as e:
        log.exception("LAN scan failed")
        result = {"error": str(e)}
    if "error" in result:
        await query.edit_message_text(f"\u274c LAN: {result['error']}")
    else:
        devices = result.get("devices", [])
        lines = [f"\U0001f4e1 *Red Local* - {result.get('total', 0)} dispositivos"]
        for d in devices[:30]:
            ip = d.get("ip", "?")
            mac = d.get("mac", d.get("hostname", ""))
            source = d.get("source", d.get("interface", ""))
            lines.append(f"\n\U0001f4bb {ip}")
            if mac:
                lines.append(f"  \U0001f4cb {mac}")
            if source:
                lines.append(f"  \U0001f4cc {source}")
        if len(devices) > 30:
            lines.append(f"\n... y {len(devices) - 30} m\u00e1s")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
    await _back_to_menu(query.message)


async def _handle_red_wifi_crack(query, uid):
    await query.edit_message_text(
        "Introduce BSSID:WordlistPath\n"
        "Ejemplo: AA:BB:CC:DD:EE:FF:rockyou.txt"
    )
    wiz = user_wizards.get(uid)
    if wiz:
        wiz["step"] = "awaiting_wifi_crack"


async def _handle_osint_email(query, uid):
    user_wizards[uid].update(step="awaiting_email_target")
    await query.edit_message_text("Introduce el email:")


async def _handle_osint_domain(query, uid):
    user_wizards[uid].update(step="awaiting_domain_target")
    await query.edit_message_text("Introduce el dominio:")


async def _handle_osint_person(query, uid):
    user_wizards[uid].update(step="awaiting_person_target")
    await query.edit_message_text("Introduce el nombre o dominio para buscar:")


async def _execute_web_nikto(query, uid, url):
    await query.edit_message_text(f"\U0001f9f0 Ejecutando Nikto sobre {url}...")
    try:
        result = tools_engine.tools_engine.run_tool("nikto", url, timeout=300)
        if result.success:
            await query.edit_message_text(f"\u2705 Nikto completado en {result.elapsed:.0f}s\n```\n{result.stdout[:3000]}\n```", parse_mode="Markdown")
        else:
            await query.edit_message_text(f"\u274c Nikto fall\u00f3: {result.error or result.stderr[:500]}")
    except Exception as e:
        await query.edit_message_text(f"\u274c Error en Nikto: {str(e)}")
    await _back_to_menu(query.message)


async def _execute_web_sqli(query, uid, url):
    await query.edit_message_text(f"\U0001f50d Probando SQLi en {url}...\n\u26a0\ufe0f Usa par\u00e1metros como ?id=1 o ?q=test")
    user_wizards[uid].update(step="awaiting_sqli_url", data={"url": url})


async def _execute_web_ssl(query, uid, host_port):
    host_port = host_port.strip()
    if ":" in host_port:
        host, port_str = host_port.rsplit(":", 1)
        try:
            port = int(port_str)
        except ValueError:
            await query.edit_message_text("\u274c Puerto inv\u00e1lido. Usa host:puerto (ej: example.com:443)")
            return
    else:
        host = host_port
        port = 443
    await query.edit_message_text(f"\U0001f512 Verificando SSL en {host}:{port}...")
    try:
        result = await asyncio.to_thread(hacking.web.ssl_check, host, port)
        if result.get("valid"):
            lines = [f"\u2705 *SSL en {host}:{port}*"]
            lines.append(f"Versi\u00f3n: {result.get('version', '?')}")
            cipher = result.get("cipher", {})
            if cipher:
                lines.append(f"Cifrado: {cipher.get('name', '?')} ({cipher.get('bits', '?')} bits)")
            lines.append(f"Subject: {result.get('subject', '?')}")
            lines.append(f"Organizaci\u00f3n: {result.get('organization', '?')}")
            lines.append(f"Issuer: {result.get('issuer', '?')}")
            san = result.get("san", [])
            if san:
                lines.append(f"SAN: {', '.join(s[1] for s in san[:5])}")
            await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
        else:
            await query.edit_message_text(f"\u274c SSL inv\u00e1lido: {result.get('error', 'desconocido')}")
    except Exception as e:
        await query.edit_message_text(f"\u274c Error SSL: {str(e)}")
    await _back_to_menu(query.message)


async def _execute_web_crawler(query, uid, url):
    await query.edit_message_text(f"\U0001f577\ufe0f Escaneando directorios en {url}...")
    try:
        result = await asyncio.to_thread(hacking.web.dir_bruteforce, url)
        found = result.get("found", [])
        if found:
            lines = [f"\U0001f577\ufe0f *Directorios encontrados* ({len(found)})"]
            for d in found[:30]:
                lines.append(f"- `{d['path']}` ({d['status']})")
            if len(found) > 30:
                lines.append(f"... y {len(found) - 30} m\u00e1s")
            await query.edit_message_text("\n".join(lines), parse_mode="Markdown")
        else:
            await query.edit_message_text(f"\U0001f50d No se encontraron directorios.")
    except Exception as e:
        await query.edit_message_text(f"\u274c Error en Crawler: {str(e)}")
    await _back_to_menu(query.message)


# ─── Callback Query Handler ───

_CALLBACK_HANDLERS = {
    "recon_quick": lambda q, u, w: _prompt_target(q, u, "recon", "quick"),
    "recon_normal": lambda q, u, w: _prompt_target(q, u, "recon", "normal"),
    "recon_full": lambda q, u, w: _prompt_target(q, u, "recon", "full"),
    "web_nikto": lambda q, u, w: _prompt_web_target(q, u, "nikto"),
    "web_sqli": lambda q, u, w: _prompt_web_target(q, u, "sqli"),
    "web_ssl": lambda q, u, w: _prompt_text(q, u, "ssl_host", "Introduce el host:puerto (ej: example.com:443):"),
    "web_crawler": lambda q, u, w: _prompt_web_target(q, u, "crawler"),
    "crack_hash": lambda q, u, w: _handle_crack_hash(q, u),
    "crack_dict_integrated": lambda q, u, w: _execute_crack_now(q, u, w.get("data", {}).get("hash", ""), "integrated"),
    "crack_dict_custom": lambda q, u, w: _prompt_text(q, u, "crack_words", "Introduce palabras separadas por comas:"),
    "payload_reverse": lambda q, u, w: _handle_payload_type(q, u, "reverse"),
    "payload_meterpreter": lambda q, u, w: _handle_payload_type(q, u, "meterpreter"),
    "payload_webshell": lambda q, u, w: _handle_payload_type(q, u, "webshell"),
    "payload_lang_bash": lambda q, u, w: _prompt_text(q, u, "payload_endpoint", "Introduce IP:Puerto para el listener:"),
    "payload_lang_python": lambda q, u, w: _prompt_text(q, u, "payload_endpoint", "Introduce IP:Puerto para el listener:"),
    "payload_lang_php": lambda q, u, w: _prompt_payload_lang(q, u, "php"),
    "payload_lang_powershell": lambda q, u, w: _prompt_text(q, u, "payload_endpoint", "Introduce IP:Puerto para el listener:"),
    "payload_lang_asp": lambda q, u, w: _prompt_payload_lang(q, u, "asp"),
    "payload_lang_aspx": lambda q, u, w: _prompt_payload_lang(q, u, "aspx"),
    "payload_lang_jsp": lambda q, u, w: _prompt_payload_lang(q, u, "jsp"),
    "payload_lang_py": lambda q, u, w: _prompt_payload_lang(q, u, "py"),
    "red_wifi_scan": lambda q, u, w: _handle_red_wifi_scan(q, u),
    "red_wifi_crack": lambda q, u, w: _handle_red_wifi_crack(q, u),
    "red_lan_scan": lambda q, u, w: _handle_red_lan_scan(q, u),
    "osint_email": lambda q, u, w: _handle_osint_email(q, u),
    "osint_domain": lambda q, u, w: _handle_osint_domain(q, u),
    "osint_person": lambda q, u, w: _handle_osint_person(q, u),
}


def _prompt_target(query, uid, wizard_type, scan_type):
    user_wizards[uid] = {"type": wizard_type, "step": "awaiting_target", "data": {"scan_type": scan_type}}
    prompt = {"recon": "Introduce la IP, dominio o rango:", "red": "Introduce la IP, dominio o rango:"}.get(wizard_type, "Introduce el target:")
    query.edit_message_text(prompt)


def _prompt_web_target(query, uid, web_type):
    user_wizards[uid] = {"type": "web", "step": "awaiting_target", "data": {"web_type": web_type}}
    query.edit_message_text("Introduce la URL (http://...):")


def _prompt_text(query, uid, step, prompt):
    wiz = user_wizards.get(uid)
    if wiz:
        wiz["step"] = f"awaiting_{step}"
    query.edit_message_text(prompt)


def _prompt_payload_lang(query, uid, lang):
    wiz = user_wizards.get(uid)
    if not wiz or wiz.get("type") != "payload":
        return
    ptype = wiz.get("data", {}).get("payload_type", "webshell")
    if ptype == "webshell":
        result = hacking.payloads.webshell(lang)
        if "error" in result:
            query.edit_message_text(f"\u274c {result['error']}")
        else:
            msg = _format_payload(result)
            query.edit_message_text(msg, parse_mode="Markdown")
        _back_to_menu(query.message)
    else:
        wiz["step"] = "awaiting_payload_endpoint"
        wiz["data"]["payload_lang"] = lang
        query.edit_message_text("Introduce IP:Puerto para el listener:")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    data = query.data

    if not _check_role(uid):
        await query.answer("No autorizado", show_alert=True)
        return

    rl = _rate_limit_msg(uid)
    if rl:
        await query.answer(rl, show_alert=True)
        return

    await query.answer()

    if data == "cancel":
        user_wizards.pop(uid, None)
        await query.edit_message_text("\u274c Operaci\u00f3n cancelada.")
        await _back_to_menu(query.message)
        return

    if data.startswith("back_"):
        user_wizards.pop(uid, None)
        await query.edit_message_text("\U0001f519 Volviendo al men\u00fa...")
        await _back_to_menu(query.message)
        return

    handler = _CALLBACK_HANDLERS.get(data)
    if handler:
        wiz = user_wizards.get(uid, {})
        await handler(query, uid, wiz)
        return

    log.warning("Unhandled callback: %s user=%s", data, uid)
    await query.edit_message_text("\u274c Opci\u00f3n no reconocida.")


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

    wiz = user_wizards.get(uid)
    if not wiz:
        await _chat_api(update, text)
        return

    step = wiz.get("step", "")

    # ── All steps that need target input ──

    if step == "awaiting_target":
        wtype = wiz["type"]
        target = text

        if wtype == "recon":
            error = tools_engine.validate_target(target)
            if error:
                await _safe_reply_text(update.message, f"\u274c {error}")
                return
            scan_type = wiz.get("data", {}).get("scan_type", "normal")
            user_wizards.pop(uid, None)
            try:
                task_id = task_queue.submit("nmap", target, {"scan_type": scan_type, "user_id": uid})
                if not task_id:
                    raise RuntimeError("No task ID")
                msg = await _safe_reply_text(update.message, f"\u2705 `{task_id}` \u2014 Escaneando {target} ({scan_type})", parse_mode="Markdown")
                asyncio.create_task(_poll_nmap_task(msg, task_id, return_to_menu=True))
            except Exception as exc:
                log.exception("Recon failed")
                audit_log.log(uid, _username(update), "wizard:recon", target, "error", str(exc))
                await _safe_reply_text(update.message, "No se pudo iniciar Recon.")
                await _back_to_menu(update.message)

        elif wtype == "red":
            out = wiz.get("data", {})
            red_type = out.get("red_type", "")
            if red_type == "wifi_crack":
                parts = target.split(":")
                if len(parts) != 2:
                    await _safe_reply_text(update.message, "\u274c Formato inv\u00e1lido. Usa BSSID:WordlistPath")
                    return
                bssid, wordlist_path = parts
                user_wizards.pop(uid, None)
                await _safe_reply_text(update.message, f"\U0001f511 Crackeando {bssid}...")
                try:
                    result = tools_engine.tools_engine.run_tool("aircrack-ng", bssid, options={"args": ["-w", wordlist_path, bssid]}, timeout=300)
                    if result.success:
                        await _safe_reply_text(update.message, f"\u2705 WiFi crackeado\n{result.stdout[:2000]}")
                    else:
                        await _safe_reply_text(update.message, f"\u274c WiFi crack fall\u00f3: {result.error or result.stderr[:500]}")
                except Exception as e:
                    await _safe_reply_text(update.message, f"\u274c Error: {str(e)}")
                await _back_to_menu(update.message)
            else:
                error = tools_engine.validate_target(target)
                if error:
                    await _safe_reply_text(update.message, f"\u274c {error}")
                    return

        elif wtype == "web":
            web_type = wiz.get("data", {}).get("web_type", "")
            url = target
            if not url.startswith("http"):
                url = "https://" + url
            user_wizards.pop(uid, None)

            if web_type == "nikto":
                msg = await _safe_reply_text(update.message, f"\U0001f9f0 Nikto sobre {url}...")
                try:
                    result = tools_engine.tools_engine.run_tool("nikto", url, timeout=300)
                    if result.success:
                        await msg.edit_text(f"\u2705 Nikto completado\n```\n{result.stdout[:3000]}\n```", parse_mode="Markdown")
                    else:
                        await msg.edit_text(f"\u274c Nikto fall\u00f3: {result.error or result.stderr[:500]}")
                except Exception as e:
                    await msg.edit_text(f"\u274c Error: {str(e)}")
                await _back_to_menu(update.message)
            elif web_type == "sqli":
                await _safe_reply_text(update.message, f"\U0001f50d Probando SQLi en {url}...\nIntroduce un par\u00e1metro de prueba (ej: id=1):")

    elif step == "awaiting_sqli_url":
        url = wiz.get("data", {}).get("url", "")
        param = text.split("=")[0].strip() if "=" in text else text.strip()
        if not param:
            await _safe_reply_text(update.message, "\u274c Par\u00e1metro inv\u00e1lido.")
            return
        user_wizards.pop(uid, None)
        await _safe_reply_text(update.message, f"\U0001f50d Probando SQLi con par\u00e1metro {param}...")
        try:
            result = await asyncio.to_thread(hacking.web.check_sqli, url, param)
            if result.get("vulnerable"):
                lines = ["\u274c *SQLi Detectada*"]
                for d in result.get("details", []):
                    lines.append(f"- Tipo: {d['tipo']}")
                    lines.append(f"  Payload: `{d['payload'][:60]}`")
                await _safe_reply_text(update.message, "\n".join(lines), parse_mode="Markdown")
            else:
                await _safe_reply_text(update.message, "\u2705 No se detect\u00f3 SQLi en el par\u00e1metro analizado.")
        except Exception as e:
            await _safe_reply_text(update.message, f"\u274c Error SQLi: {str(e)}")
        await _back_to_menu(update.message)

    elif step == "awaiting_ssl_host":
        user_wizards.pop(uid, None)
        parts = text.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 443
        msg = await _safe_reply_text(update.message, f"\U0001f512 Verificando SSL en {host}:{port}...")
        try:
            result = await asyncio.to_thread(hacking.web.ssl_check, host, port)
            if result.get("valid"):
                lines = [f"\u2705 *SSL en {host}:{port}*"]
                lines.append(f"Versi\u00f3n: {result.get('version', '?')}")
                cipher = result.get("cipher", {})
                if cipher:
                    lines.append(f"Cifrado: {cipher.get('name', '?')} ({cipher.get('bits', '?')} bits)")
                lines.append(f"Subject: {result.get('subject', '?')}")
                lines.append(f"Organizaci\u00f3n: {result.get('organization', '?')}")
                lines.append(f"Issuer: {result.get('issuer', '?')}")
                await msg.edit_text("\n".join(lines), parse_mode="Markdown")
            else:
                await msg.edit_text(f"\u274c SSL inv\u00e1lido: {result.get('error', 'desconocido')}")
        except Exception as e:
            await msg.edit_text(f"\u274c Error SSL: {str(e)}")
        await _back_to_menu(update.message)

    elif step == "awaiting_crawler_url":
        url = text
        if not url.startswith("http"):
            url = "https://" + url
        user_wizards.pop(uid, None)
        await _safe_reply_text(update.message, f"\U0001f577\ufe0f Escaneando directorios en {url}...")
        try:
            result = await asyncio.to_thread(hacking.web.dir_bruteforce, url)
            found = result.get("found", [])
            if found:
                lines = [f"\U0001f577\ufe0f *Directorios encontrados* ({len(found)})"]
                for d in found[:30]:
                    lines.append(f"- `{d['path']}` ({d['status']})")
                if len(found) > 30:
                    lines.append(f"... y {len(found) - 30} m\u00e1s")
                await _safe_reply_text(update.message, "\n".join(lines), parse_mode="Markdown")
            else:
                await _safe_reply_text(update.message, "\U0001f50d No se encontraron directorios.")
        except Exception as e:
            await _safe_reply_text(update.message, f"\u274c Error: {str(e)}")
        await _back_to_menu(update.message)

    elif step == "awaiting_hash":
        hash_value = text.strip()
        algorithm, error = _validate_hash_algorithm(hash_value)
        if error:
            await _safe_reply_text(update.message, error)
            return
        wiz["step"] = "awaiting_dict"
        wiz["data"]["hash"] = hash_value
        wiz["data"]["algorithm"] = algorithm
        keyboard = _menu_keyboard([
            ("\U0001f4da Integrado", "crack_dict_integrated"),
            ("\U0001f3b2 Custom", "crack_dict_custom"),
        ], "crack")
        await _safe_reply_text(update.message, "\U0001f511 \u00bfDiccionario?", reply_markup=keyboard)

    elif step == "awaiting_dict":
        hash_value = wiz.get("data", {}).get("hash", "")
        if not hash_value:
            await _safe_reply_text(update.message, "\u274c Hash no encontrado. Vuelve a empezar.")
            user_wizards.pop(uid, None)
            return
        words = [w.strip() for w in text.replace("\n", ",").split(",") if w.strip()]
        if not words:
            await _safe_reply_text(update.message, "\u274c Introduce al menos una palabra.")
            return
        user_wizards.pop(uid, None)
        await _safe_reply_text(update.message, "\u23f3 Analizando hash...")
        try:
            result = await asyncio.to_thread(hacking.crypto.hash_crack, hash_value, words)
        except Exception as e:
            log.exception("Crack failed")
            result = {"error": str(e)}
        if "error" in result:
            await _safe_reply_text(update.message, f"\u274c {result['error']}")
        else:
            lines = ["\U0001f511 *Hash Crack*"]
            lines.append(f"Hash: `{result['hash']}`")
            lines.append(f"Algoritmo: {result['algorithm']}")
            if result.get("cracked"):
                lines.append(f"\u2705 *Crackeado:* `{result['plaintext']}`")
            else:
                lines.append(f"\u274c No se pudo crackear.")
            await _safe_reply_text(update.message, "\n".join(lines), parse_mode="Markdown")
        await _back_to_menu(update.message)

    elif step == "awaiting_payload_endpoint":
        ip, port, err = _parse_endpoint(text)
        if err:
            await _safe_reply_text(update.message, f"\u274c {err}")
            return
        data = wiz.get("data", {})
        lang = data.get("payload_lang", "bash")
        ptype = data.get("payload_type", "reverse")
        user_wizards.pop(uid, None)

        if ptype == "meterpreter":
            await _safe_reply_text(update.message, f"\U0001f916 Generando payload Meterpreter para {ip}:{port}...")
            try:
                result = tools_engine.tools_engine.run_tool("msfvenom", "",
                    options={"args": ["-p", f"linux/x64/meterpreter/reverse_tcp", f"LHOST={ip}", f"LPORT={port}", "-f", "elf"]},
                    timeout=30)
                if result.success:
                    await _safe_reply_text(update.message, f"\u2705 Meterpreter generado\n```\n{result.stdout[:3000]}\n```", parse_mode="Markdown")
                else:
                    await _safe_reply_text(update.message, f"\u274c msfvenom fall\u00f3: {result.stderr[:500]}")
            except Exception as e:
                await _safe_reply_text(update.message, f"\u274c Error: {str(e)}")
        else:
            result = hacking.payloads.reverse_shell(ip, port, lang)
            if "error" in result:
                await _safe_reply_text(update.message, f"\u274c {result['error']}")
            else:
                listener = f"nc -lvnp {port}" if lang in ("bash", "nc") else f"rlwrap nc -lvnp {port}"
                msg = _format_payload(result)
                msg += f"\n\n\U0001f4e1 Listener: `{listener}`"
                await _safe_reply_text(update.message, msg, parse_mode="Markdown")
        await _back_to_menu(update.message)

    elif step == "awaiting_email_target":
        email = text.strip()
        if "@" not in email:
            await _safe_reply_text(update.message, "\u274c Email inv\u00e1lido.")
            return
        user_wizards.pop(uid, None)
        msg = await _safe_reply_text(update.message, f"\U0001f50e Consultando OSINT para {email}...")
        try:
            result = await asyncio.to_thread(hacking.osint.email_osint, email)
            status = result.get("status", "error" if result.get("error") else "ok")
            audit_log.log(uid, _username(update), "wizard:osint:email", email, status, "")
            if result.get("error"):
                await msg.edit_text(f"\u274c {result['error']}")
            else:
                lines = [f"\U0001f50e *Email OSINT*", f"Email: {email}"]
                mx = result.get("mx_records", [])
                if mx:
                    lines.append("MX:")
                    lines.extend(f"- {r}" for r in mx[:10])
                else:
                    lines.append("MX: sin registros")
                certs = result.get("dominio_info", {}).get("total_certs")
                if certs:
                    lines.append(f"Certificados: {certs}")
                warnings = result.get("warnings", [])
                for w in warnings:
                    lines.append(f"\u26a0\ufe0f {w}")
                await msg.edit_text("\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            await msg.edit_text(f"\u274c Error: {str(e)}")
        await _back_to_menu(update.message)

    elif step == "awaiting_domain_target":
        domain = text.strip()
        error = tools_engine.validate_target(domain)
        if error:
            await _safe_reply_text(update.message, f"\u274c {error}")
            return
        user_wizards.pop(uid, None)
        msg = await _safe_reply_text(update.message, f"\U0001f50e Analizando dominio {domain}...")
        try:
            task_id = task_queue.submit("playbook", domain, {"playbook": "osint_domain", "depth": "normal", "user_id": uid})
            if task_id:
                await msg.edit_text(f"\u2705 *OSINT* \u2014 `{task_id}`\n{domain}", parse_mode="Markdown")
                asyncio.create_task(_poll_playbook_task(msg, task_id, "OSINT de Dominio", return_to_menu=True, uid=uid))
            else:
                await msg.edit_text("\u274c No se pudo iniciar OSINT.")
                await _back_to_menu(update.message)
        except Exception as e:
            await msg.edit_text(f"\u274c Error: {str(e)}")
            await _back_to_menu(update.message)

    elif step == "awaiting_person_target":
        target = text.strip()
        user_wizards.pop(uid, None)
        await _safe_reply_text(update.message, f"\U0001f9d1 Buscando informaci\u00f3n de {target}...")
        try:
            result = tools_engine.tools_engine.run_tool("theharvester", target, options={"args": ["-d", target, "-b", "google,linkedin"]}, timeout=60)
            if result.success:
                await _safe_reply_text(update.message, f"\u2705 theHarvester completado\n```\n{result.stdout[:3000]}\n```", parse_mode="Markdown")
            else:
                await _safe_reply_text(update.message, f"\u274c B\u00fasqueda fall\u00f3: {result.error or result.stderr[:500]}")
        except Exception as e:
            await _safe_reply_text(update.message, f"\u274c Error: {str(e)}")
        await _back_to_menu(update.message)

    elif step == "awaiting_wifi_crack":
        parts = text.split(":")
        if len(parts) != 2:
            await _safe_reply_text(update.message, "\u274c Formato inv\u00e1lido. Usa BSSID:WordlistPath")
            return
        bssid, wordlist_path = parts
        user_wizards.pop(uid, None)
        await _safe_reply_text(update.message, f"\U0001f511 Crackeando {bssid}...")
        try:
            result = tools_engine.tools_engine.run_tool("aircrack-ng", bssid, options={"args": ["-w", wordlist_path, bssid]}, timeout=300)
            if result.success:
                await _safe_reply_text(update.message, f"\u2705 WiFi crackeado\n{result.stdout[:2000]}")
            else:
                await _safe_reply_text(update.message, f"\u274c WiFi crack fall\u00f3: {result.error or result.stderr[:500]}")
        except Exception as e:
            await _safe_reply_text(update.message, f"\u274c Error: {str(e)}")
        await _back_to_menu(update.message)

    else:
        await _chat_api(update, text)


async def _objetivo_wizard(update, uid):
    user_wizards.pop(uid, None)
    user_wizards[uid] = {"type": "objetivo", "step": "awaiting_target", "data": {}}
    await update.message.reply_text("Introduce el target (IP, dominio o rango):")


# ─── Polling Functions ───

async def _poll_nmap_task(msg, task_id, timeout=300, return_to_menu=False):
    await asyncio.sleep(2)
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        status = task_queue.get_status(task_id)
        s = status.get("status")
        if not s:
            await _safe_reply_text(msg, f"\u274c Nmap: {status.get('error', 'Tarea no encontrada')}")
            if return_to_menu:
                await _back_to_menu(msg)
            return
        if s in ("cancelled", "failed"):
            error = status.get("error", "Tarea cancelada")
            await _safe_reply_text(msg, f"\u274c Nmap: {error}")
            if return_to_menu:
                await _back_to_menu(msg)
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
            await _safe_reply_text(msg, "\n".join(lines), parse_mode="Markdown")
            if return_to_menu:
                await _back_to_menu(msg)
            return
        if s == "running":
            pct = status.get("progress", 0)
            filled = max(0, min(10, int(pct) // 10))
            bar = "\u2588" * filled + "\u2591" * (10 - filled)
            step = status.get("current_step") or "Procesando..."
            try:
                await _safe_reply_text(msg, f"\u23f3 `{task_id}` \u2014 [{bar}] {pct}%\n\U0001f527 {step}")
            except BadRequest:
                pass
        if asyncio.get_event_loop().time() > deadline:
            await _safe_reply_text(msg, f"\u23f0 `{task_id}` \u2014 Tiempo agotado ({timeout}s)")
            if return_to_menu:
                await _back_to_menu(msg)
            return
        await asyncio.sleep(2)


async def _poll_playbook_task(msg, task_id, label, timeout=600, return_to_menu=False, uid=None):
    await asyncio.sleep(2)
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        status = task_queue.get_status(task_id)
        state = status.get("status")
        if not state:
            await _safe_reply_text(msg, f"{label}: {status.get('error', 'Tarea no encontrada')}")
            if return_to_menu:
                await _back_to_menu(msg)
            return
        if state == "cancelled":
            await _safe_reply_text(msg, f"{label}: tarea cancelada")
            if return_to_menu:
                await _back_to_menu(msg)
            return
        if state == "completed":
            result = status.get("result") or {}
            target = status.get("target") or result.get("target") or ""
            lines = [f"{label} completado", f"Objetivo: {target}"]
            summary = result.get("summary")
            if summary:
                lines.extend(("", summary))
            results = result.get("results") or []
            if results:
                lines.extend(("", "Resultados:"))
                for sr in results:
                    s = "OK" if sr.get("success") else "SKIP"
                    sl = sr.get("label") or ""
                    note = sr.get("note")
                    if note:
                        sl += f" - {note}"
                    lines.append(f"[{s}] {sl}")
            completion = "\n".join(lines)
            if uid:
                ok_count = sum(1 for r in results if r.get("success"))
                audit_log.log(uid, str(uid), "wizard:osint", target, "ok" if ok_count == len(results) else "partial", f"task:{task_id}")
            await _safe_reply_text(msg, completion)
            if return_to_menu:
                await _back_to_menu(msg)
            return
        if state == "failed":
            error = status.get("error") or "Error desconocido"
            if uid:
                audit_log.log(uid, str(uid), "wizard:osint", status.get("target", ""), "error", f"task:{task_id} error:{error}")
            await _safe_reply_text(msg, f"{label} fall\u00f3: {error}")
            if return_to_menu:
                await _back_to_menu(msg)
            return
        if state in ("queued", "running"):
            pct = status.get("progress", 0)
            filled = max(0, min(10, int(pct) // 10))
            bar = "\u2588" * filled + "\u2591" * (10 - filled)
            step = status.get("current_step") or "Sin paso reportado"
            try:
                await _safe_reply_text(msg, f"\u23f3 `{task_id}` \u2014 [{bar}] {pct}%\n\U0001f527 {step}")
            except BadRequest:
                pass
        if asyncio.get_event_loop().time() > deadline:
            await _safe_reply_text(msg, f"\u23f0 `{task_id}` \u2014 Tiempo agotado ({timeout}s)")
            if return_to_menu:
                await _back_to_menu(msg)
            return
        await asyncio.sleep(2)


# ─── Misc ───

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_role(uid):
        await update.message.reply_text("\u274c No autorizado")
        return
    msg = (
        "*Comandos:*\n"
        "`/objetivo <target>` \u2014 Establecer target global\n"
        "`/tarea <id>` \u2014 Ver estado de tarea\n"
        "`/tareas` \u2014 Listar tareas\n"
        "`/ayuda` \u2014 Esta ayuda\n\n"
        "*Botones del men\u00fa:*\n"
        "\U0001f50d Recon \u2014 Escaneo con Nmap\n"
        "\U0001f310 Web \u2014 Nikto, SQLi, SSL, Crawler\n"
        "\U0001f511 Crack \u2014 Cracking de hashes\n"
        "\U0001f4a3 Payloads \u2014 Reverse Shell, Meterpreter, Webshell\n"
        "\U0001f4e1 Red \u2014 WiFi, LAN\n"
        "\U0001f50e OSINT \u2014 Email, Dominio, Persona"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


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
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{API_URL}/upload",
                files={"file": ("photo.jpg", file_bytes, "image/jpeg")},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            )
            if resp.status_code == 200:
                await update.message.reply_text(f"\U0001f4f8 Foto recibida.")
            else:
                await update.message.reply_text(f"\u274c Error al subir: {resp.status_code}")
    except Exception as e:
        await update.message.reply_text(f"\u274c Error: {str(e)}")


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
        await _safe_reply_text(update.message, f"\U0001f3a4 *Transcripci\u00f3n:*\n{text}", parse_mode="Markdown")
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
    await update.message.reply_text("El cracking de archivos no est\u00e1 disponible. Usa el flujo Hash.")


async def _chat_api(update, text):
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
                except ValueError:
                    msg = "\u274c Respuesta inv\u00e1lida de la API."
                else:
                    msg = data.get("response", "Sin respuesta")
            else:
                msg = f"\u274c Error de API: {resp.status_code}"
    except httpx.HTTPError as exc:
        msg = f"\u274c Error de conexi\u00f3n: {str(exc)}"
    await _safe_reply_text(update.message, msg)


# ─── Main ───

def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        log.error("No se encontr\u00f3 la variable TELEGRAM_TOKEN")
        return

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("objetivo", objetivo))
    application.add_handler(CommandHandler("olvidar_objetivo", olvidar_objetivo))
    application.add_handler(CommandHandler("tarea", tarea))
    application.add_handler(CommandHandler("tareas", tareas))
    application.add_handler(CommandHandler("ayuda", ayuda))
    application.add_handler(CommandHandler("help", ayuda))

    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))

    print("[OK] Bot de Artenisa sincronizado y escuchando en Telegram...")
    log.info("Bot de Telegram iniciado con \u00e9xito.")
    application.run_polling()


if __name__ == "__main__":
    main()
