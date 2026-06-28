import os
import sys
import json
import time
import queue
import httpx
import tempfile
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path

from display import Screen, Theme, truncate_ansi, visible_len

T = Theme()

API_URL = os.getenv("API_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "test-token")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

conv_id = None
voice_mode = False
current_model = "personal"
session_start = time.time()
session_tokens = 0
messages_history = []

def elapsed_str():
    t = int(time.time() - session_start)
    if t < 60:
        return f"{t}s"
    return f"{t // 60}m{t % 60:02d}s"

def api_get(path):
    try:
        r = httpx.get(
            f"{API_URL}{path}",
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            timeout=10,
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def api_post(path, payload):
    try:
        r = httpx.post(
            f"{API_URL}{path}",
            json=payload,
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            timeout=60,
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def send_message(msg):
    global conv_id
    payload = {"message": msg}
    if conv_id:
        payload["conversation_id"] = conv_id
    data = api_post("/chat", payload)
    if "conversation_id" in data:
        conv_id = data["conversation_id"]
    return data

def send_message_stream(msg, token_callback=None):
    global conv_id, session_tokens
    payload = {"message": msg}
    if conv_id:
        payload["conversation_id"] = conv_id
    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{API_URL}/chat/stream",
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AUTH_TOKEN}",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=120)
        if resp.status != 200:
            return {"error": f"HTTP {resp.status}"}
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data: "):
                continue
            line = line[6:]
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if obj.get("type") == "token":
                    session_tokens += 1
                    if token_callback:
                        token_callback(obj["content"])
                elif obj.get("type") == "done":
                    conv_id = obj.get("conversation_id", conv_id)
                    return obj
                elif obj.get("type") == "error":
                    return {"error": obj.get("error")}
            except json.JSONDecodeError:
                pass
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}
    return {"response": "", "conversation_id": conv_id}

GENGAR_ART = """\
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡷⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⡇⠈⠙⢷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡇⠀⠀⠀⠙⢷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣧⠀⠀⠀⠀⠀⠙⢷⣄⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠘⠳⣄⠀⣼⢷⣄⠀⣰⡀⠀⠀⠀⢀⣀⣤⡴⠶⠛⣿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⣿⣀⣙⢷⡏⢻⣤⠶⠟⠛⠉⠀⠀⢀⣼⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⢠⡄⣿⠳⣤⣀⠀⠀⠀⠀⠀⢸⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠁⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⢀⣾⣡⣤⣤⣴⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⣿⡿⠿⠇⠀⠛⠿⣤⣀⠀⠀⢸⡇⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠃⠀⠀⣸⠟⠀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⠀\033[0m
          \033[38;5;141m⢙⣿⡆⠀⠀⠀⠀⠀⠙⠳⢦⣸⡇⢀⡤⠖⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠉⠉⠉⠙⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⣩⣿⠃\033[0m
          \033[38;5;141m⠸⠿⣭⡄⠀⠀⠀⠀⠀⠀⢹⡷⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⡾⠋⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠈⢿⡄⠀⠀⠀⠀⠀⠀⠉⠀⠀⠀⠀⠀⣴⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⠞⠋⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⢻⡄⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⢀⡼⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⡾⠟⠁⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠻⣄⢠⠏⠀⠀⠀⠀⠀⠀⣰⡏⠀⢻⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⡾⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⣹⠏⠀⠀⠀⢠⠀⠀⠀⡟⠀⠀⠘⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣤⠾⠆⠀⠀⠀⠀⢶⢀⣴⠟⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⢠⡏⠀⠀⠀⠀⢸⣇⠀⠠⣷⡀⠀⠀⣿⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⡴⠞⠉⣿⠀⠀⠀⠀⠀⠀⢸⣏⣁⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⣼⠀⠀⠀⠀⠀⢸⡿⣦⡀⠈⠳⢦⣀⣀⣹⡄⠀⠀⠀⠀⠀⠀⠀⣀⣴⠛⠉⠀⠀⢀⡏⠀⠀⠀⠀⠀⠀⣸⠉⠉⠉⠉⠉⠙⠛⠛⠓⢶⣶⣤⡀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⣸⡇⠈⢷⣄⠀⠀⠀⠉⠉⠉⠀⠀⠀⠀⣠⣴⠛⠉⠏⠀⠀⠀⢀⡾⠁⠀⠀⠀⠀⠀⠐⣾⠃⠀⠀⠀⠀⠀⠀⠀⠀⠈⠛⢷⣾⡄⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⢀⣿⠀⠀⠀⠀⠀⠹⣷⠀⣸⠋⠛⢦⣄⡀⠀⠀⠀⠀⠀⠀⠀⠈⠛⠶⠦⠤⠤⠞⠋⠀⢀⣤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡀⣾⠛⠉⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠹⣿⡟⠀⠀⠀⢨⡏⠛⠲⠤⣤⣀⣀⡀⠀⠀⠀⠀⠀⢀⣀⣤⡶⠋⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⣀⣤⡶⠞⠋⠛⠛⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⢀⣿⡀⠀⠀⠀⠀⠀⠀⠈⠻⣄⡀⠀⣾⠀⠀⠀⠀⠀⠈⢹⡏⠉⠛⠛⠛⡿⠉⣍⡾⠁⠀⠀⠀⠀⠀⢀⣏⣀⣤⡴⠶⠛⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⢀⡾⠉⣧⠀⠀⠀⠀⠀⠀⠀⠀⠈⠛⢦⣇⡀⠀⠀⠀⠀⠀⣾⠀⠀⠀⠀⢸⢇⡴⠋⠀⠀⠀⠀⠀⠀⠀⣾⠋⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⣸⠇⠀⠹⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠓⠶⠤⣤⣴⣧⣠⣤⣤⠴⠟⠉⠀⠀⠀⠀⠀⠀⠀⠀⣼⠏⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⢹⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⣶⡄⣾⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⢻⣦⠀⠀⠀⠀⠻⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠙⠻⣦⡄⠀⢀⣈⣳⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠈⠘⢷⣽⣭⣿⣾⡎⠙⠷⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠙⠟⠀⠁⠀⠀⠀⠉⠻⣗⠲⠶⠴⢦⡶⠶⣦⡀⠀⠀⢀⡀⠀⣀⠀⠀⠀⣠⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⣦⣠⡿⠀⠀⠘⣷⡀⢠⠟⢳⠟⢹⡧⣦⣠⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠀⠀⠀⠀⠘⣷⡿⠀⠀⠀⠀⣸⡿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⠳⠦⠤⠴⠞⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m
          \033[38;5;141m⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀\033[0m"""

def show_help(screen):
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.BOLD}COMANDOS{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/ayuda{T.RESET}     {T.MUTED}Help{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/nueva{T.RESET}     {T.MUTED}New conversation{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/model <m>{T.RESET}  {T.MUTED}Switch model{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/modelos{T.RESET}   {T.MUTED}List models{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/memoria{T.RESET}   {T.MUTED}View memories{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/olvidar{T.RESET}   {T.MUTED}Clear memories{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/buscar{T.RESET}    {T.MUTED}Web search{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/run{T.RESET}       {T.MUTED}Run command{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/voz{T.RESET}       {T.MUTED}Toggle voice{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/archivos{T.RESET}  {T.MUTED}Project files{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/add <file>{T.RESET}{T.MUTED}Add file context{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/tokens{T.RESET}    {T.MUTED}Token stats{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/editor{T.RESET}    {T.MUTED}External editor{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/multiline{T.RESET} {T.MUTED}Multi-line input{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/status{T.RESET}    {T.MUTED}System status{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/gengar{T.RESET}    {T.MUTED}Show Gengar{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/tema{T.RESET}      {T.MUTED}Theme info{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/guardar{T.RESET}   {T.MUTED}Save session{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/cargar{T.RESET}    {T.MUTED}Load session{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/sesiones{T.RESET}  {T.MUTED}List sessions{T.RESET}")
    screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}/salir{T.RESET}     {T.MUTED}Exit{T.RESET}")

def show_gengar(screen):
    for line in GENGAR_ART.split("\n"):
        screen.log(f"  {T.BORDER}┃{T.RESET} {line}")

COMMANDS = {
    "/ayuda": "show help",
    "/nueva": "new conversation",
    "/model": "switch model",
    "/modelos": "list models",
    "/memoria": "view memories",
    "/olvidar": "clear memories",
    "/buscar": "web search",
    "/run": "execute command",
    "/voz": "toggle voice mode",
    "/archivos": "list project files",
    "/add": "add file context",
    "/tokens": "show token stats",
    "/editor": "open external editor",
    "/multiline": "multi-line input mode",
    "/status": "system status",
    "/gengar": "display Gengar art",
    "/tema": "theme info",
    "/guardar": "save session",
    "/cargar": "load session",
    "/sesiones": "list sessions",
    "/salir": "exit",
}

def main():
    global conv_id, session_start, session_tokens, current_model, voice_mode

    with Screen(Theme()) as screen:
        screen.set_status(f"{current_model} · 0 tok · {elapsed_str()}")
        show_gengar(screen)
        screen.log(f"  {T.BORDER}┃{T.RESET} {T.PURPLE}{T.BOLD}Artenisa v4.0{T.RESET} {T.MUTED}· Gengar Theme{T.RESET}")
        screen.log(f"  {T.BORDER}┃{T.RESET} {T.DIM}/ayuda para comandos · Ctrl+C para salir{T.RESET}")

        try:
            while True:
                if screen.check_resize():
                    screen.redraw()

                action = screen.handle_input()

                if action is None:
                    time.sleep(0.01)
                    continue

                action_type, msg = action

                if action_type == "exit":
                    break

            if action_type == "submit":
                cmd_lower = msg.lower()

                # ── Commands ──
                if cmd_lower in ("/salir", "salir", "exit", "quit"):
                    break

                if cmd_lower in ("/gengar", "gengar"):
                    show_gengar(screen)
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower in ("/ayuda", "help", "/?"):
                    show_help(screen)
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower in ("/nueva", "new", "reset"):
                    conv_id = None
                    session_tokens = 0
                    session_start = time.time()
                    screen.conversation.clear()
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.PURPLE}{T.BOLD}Artenisa v4.0{T.RESET} {T.MUTED}· Gengar Theme{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.WARNING}New conversation{T.RESET}")
                    screen.set_status(f"{current_model} · 0 tok · {elapsed_str()}")
                    continue

                if cmd_lower == "/modelos":
                    data = api_get("/models")
                    models = data.get("models", [])
                    if models:
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.BOLD}MODELS{T.RESET}")
                        for m in models:
                            marker = f" {T.SUCCESS}← current{T.RESET}" if m == current_model else ""
                            screen.log(f"  {T.BORDER}┃{T.RESET}  {T.HIGHLIGHT}{m}{T.RESET}{marker}")
                    else:
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.MUTED}No models available{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower.startswith("/model "):
                    current_model = msg.split(" ", 1)[1].strip()
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.SUCCESS}Model: {current_model}{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower == "/memoria":
                    mems = api_get("/memories").get("memories", {})
                    if mems:
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.BOLD}MEMORIES{T.RESET}")
                        for k, v in sorted(mems.items()):
                            label = k.replace("_", " ").title()
                            screen.log(f"  {T.BORDER}┃{T.RESET} {T.HIGHLIGHT}{label:20s}{T.RESET} {T.TEXT}{v}{T.RESET}")
                    else:
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.MUTED}No memories stored{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower.startswith("/olvidar"):
                    data = api_post("/memories/clear", {})
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.WARNING}Memories cleared{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower.startswith("/buscar "):
                    query = msg.split(" ", 1)[1].strip()
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.YELLOW}🔍 Searching: {query}{T.RESET}")
                    data = api_post("/web_search", {"query": query})
                    result = data.get("result", data.get("response", "No results"))
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.TEXT}{result}{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower.startswith("/run "):
                    cmd = msg.split(" ", 1)[1].strip()
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.YELLOW}⚙ {cmd}{T.RESET}")
                    try:
                        import shlex
                        try:
                            cmd_args = shlex.split(cmd, posix=False)
                        except:
                            cmd_args = cmd.split()
                        result = subprocess.run(
                            cmd_args, capture_output=True, text=True, timeout=30
                        )
                        out = (result.stdout or "") + (result.stderr or "")
                        for line in out.split("\n")[:10]:
                            if line.strip():
                                screen.log(f"  {T.BORDER}┃{T.RESET} {T.DIM}{line}{T.RESET}")
                        if result.returncode != 0:
                            screen.log(f"  {T.BORDER}┃{T.RESET} {T.ERROR}Exit code: {result.returncode}{T.RESET}")
                    except subprocess.TimeoutExpired:
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.ERROR}Command timed out{T.RESET}")
                    except Exception as e:
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.ERROR}Error: {e}{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower == "/voz":
                    voice_mode = not voice_mode
                    status = "on" if voice_mode else "off"
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.WARNING}Voice mode: {status}{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower == "/archivos":
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.BOLD}PROJECT FILES{T.RESET}")
                    try:
                        cwd = Path.cwd()
                        for f in sorted(cwd.iterdir()):
                            if f.name.startswith(".") or f.name.startswith("__"):
                                continue
                            icon = "📁" if f.is_dir() else "📄"
                            screen.log(f"  {T.BORDER}┃{T.RESET}  {icon} {T.TEXT}{f.name}{T.RESET}")
                    except:
                        pass
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower.startswith("/add "):
                    fname = msg.split(" ", 1)[1].strip()
                    try:
                        content = Path(fname).read_text(encoding="utf-8", errors="replace")[:2000]
                        messages_history.append({"role": "user", "content": f"File {fname}:\n{content}"})
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.SUCCESS}Added: {fname}{T.RESET}")
                    except Exception as e:
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.ERROR}Error: {e}{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower == "/tokens":
                    t = int(time.time() - session_start)
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.BOLD}TOKEN STATS{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  Tokens:  {T.HIGHLIGHT}{session_tokens}{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  Time:    {T.HIGHLIGHT}{elapsed_str()}{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  Cost:    {T.HIGHLIGHT}local (free){T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower == "/editor":
                    screen.stop()
                    editor = os.environ.get("EDITOR", "notepad" if sys.platform == "win32" else "nano")
                    tmp = tempfile.NamedTemporaryFile(
                        mode="w", suffix=".md", delete=False, encoding="utf-8"
                    )
                    tmp.close()
                    try:
                        subprocess.run([editor, tmp.name])
                        text = Path(tmp.name).read_text(encoding="utf-8").strip()
                        if text:
                            msg = text
                            screen.start()
                            screen.redraw()
                        else:
                            screen.start()
                            screen.redraw()
                            screen.log(f"  {T.BORDER}┃{T.RESET} {T.WARNING}Editor cancelled{T.RESET}")
                            screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                            continue
                    except Exception as e:
                        screen.start()
                        screen.redraw()
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.ERROR}Editor error: {e}{T.RESET}")
                        screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                        continue
                    finally:
                        try:
                            Path(tmp.name).unlink()
                        except:
                            pass

                if cmd_lower == "/multiline":
                    screen.stop()
                    print(f"  {T.BORDER}┃{T.RESET} {T.YELLOW}Multi-line mode (Ctrl+Z + Enter to finish):{T.RESET}")
                    lines = []
                    try:
                        while True:
                            line = input()
                            lines.append(line)
                    except EOFError:
                        pass
                    msg = "\n".join(lines).strip()
                    if not msg:
                        screen.start()
                        screen.redraw()
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.WARNING}Cancelled{T.RESET}")
                        screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                        continue
                    screen.start()
                    screen.redraw()

                if cmd_lower == "/status":
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.BOLD}SYSTEM STATUS{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  API:     {T.SUCCESS}Online{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  Model:   {T.HIGHLIGHT}{current_model}{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  Tokens:  {T.HIGHLIGHT}{session_tokens}{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  Time:    {T.HIGHLIGHT}{elapsed_str()}{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  Conv:    {T.HIGHLIGHT}{'Active' if conv_id else 'New'}{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                if cmd_lower == "/tema":
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.BOLD}THEMES{T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  {T.PURPLE}● Gengar{T.RESET} {T.MUTED}(current){T.RESET}")
                    screen.log(f"  {T.BORDER}┃{T.RESET}  {T.DIM}More coming soon...{T.RESET}")
                    screen.set_status(f"{current_model} · {session_tokens} tok · {elapsed_str()}")
                    continue

                # ── Send message ──
                screen.log(f"  {T.BORDER}┃{T.RESET} {T.TEXT}{msg}{T.RESET}")
                screen.log(f"  {T.BORDER}┃{T.RESET} {T.PURPLE}⏳{T.RESET} ")

                result_queue = queue.Queue()

                def on_token(tok):
                    result_queue.put(("token", tok))

                def stream_worker():
                    try:
                        data = send_message_stream(msg, token_callback=on_token)
                        result_queue.put(("result", data))
                    except Exception as e:
                        result_queue.put(("result", {"error": str(e)}))

                t = threading.Thread(target=stream_worker, daemon=True)
                t.start()

                current_line = f"  {T.BORDER}┃{T.RESET} {T.PURPLE}⏳{T.RESET} "
                streaming = True
                cancelled = False

                while streaming:
                    if screen.check_resize():
                        screen.redraw()

                    try:
                        item = result_queue.get(timeout=0.05)
                        if item[0] == "token":
                            current_line += f"{T.GREEN}{item[1]}{T.RESET}"
                            screen.update_last(current_line)
                            screen.set_status(
                                f"{current_model} · {session_tokens} tok · {elapsed_str()}"
                            )
                        elif item[0] == "result":
                            done_data = item[1]
                            streaming = False
                    except queue.Empty:
                        pass

                    if screen.cancel_pressed():
                        cancelled = True
                        streaming = False

                if cancelled:
                    screen.update_last(
                        f"  {T.BORDER}┃{T.RESET} {T.WARNING}Cancelled.{T.RESET}"
                    )
                    screen.set_status(
                        f"{current_model} · {session_tokens} tok · {elapsed_str()}"
                    )
                    continue

                if done_data and "error" not in done_data:
                    resp = done_data.get("response", "")
                    tool_exec = done_data.get("tool_executed", False)
                    tool_cmd = done_data.get("tool_command", "")
                    tool_out = done_data.get("tool_output", "")

                    if tool_exec and tool_cmd:
                        screen.log(f"  {T.BORDER}┃{T.RESET} {T.YELLOW}⚙ {tool_cmd}{T.RESET}")
                        if tool_out:
                            for line in tool_out.split("\n")[:8]:
                                if line.strip():
                                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.DIM}{line}{T.RESET}")
                elif done_data and "error" in done_data:
                    screen.log(f"  {T.BORDER}┃{T.RESET} {T.ERROR}{done_data['error']}{T.RESET}")

                screen.set_status(
                    f"{current_model} · {session_tokens} tok · {elapsed_str()}"
                )

        except KeyboardInterrupt:
            pass

if __name__ == "__main__":
    main()
