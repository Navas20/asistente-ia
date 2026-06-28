import os
import sys
import re
import json
import time
import shutil
import httpx
import readline
import tempfile
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
#  ARTENISA SHELL v4.0 — OpenCode-style TUI + Gengar Theme
# ═══════════════════════════════════════════════════════════════

API_URL = os.getenv("API_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "test-token")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except:
        pass

# ─── State ───
conv_id = None
voice_mode = False
current_model = "personal"
session_start = time.time()
session_tokens = 0
session_cost = 0.0
messages_history = []

# ═══════════════════════════════════════════════════════════════
#  GENGAR THEME (paleta de colores)
# ═══════════════════════════════════════════════════════════════

class Theme:
    # Backgrounds
    BG = "\033[48;5;234m"           # ~#1c1c1c dark
    BG_PANEL = "\033[48;5;236m"     # ~#303030 panel
    BG_ELEMENT = "\033[48;5;238m"   # ~#444444 input
    BG_STATUS = "\033[48;5;53m"     # ~#5f005f purple dark

    # Foregrounds
    TEXT = "\033[38;5;252m"         # ~#d0d0d0 primary text
    MUTED = "\033[38;5;245m"        # ~#8a8a8a muted
    DIM = "\033[38;5;240m"          # ~#585858 dim

    # Accents — Gengar palette
    PURPLE = "\033[38;5;141m"       # #af87ff bright purple
    PURPLE_DIM = "\033[38;5;98m"    # #875faf dim purple
    RED = "\033[38;5;203m"          # #ff5f5f Gengar red eyes
    RED_DIM = "\033[38;5;131m"      # #af5f5f dim red
    PINK = "\033[38;5;213m"         # #ff87af pink accent
    GREEN = "\033[38;5;114m"        # #87d787 soft green
    YELLOW = "\033[38;5;221m"       # #ffd787 warm yellow
    CYAN = "\033[38;5;117m"         # #87d7d7 cyan

    # Semantic
    SUCCESS = "\033[38;5;114m"
    WARNING = "\033[38;5;221m"
    ERROR = "\033[38;5;203m"
    HIGHLIGHT = "\033[38;5;141m"

    # Decorators
    BORDER = "\033[38;5;98m"        # dim purple border
    BORDER_ACTIVE = "\033[38;5;141m"  # bright purple active border

    # Modifiers
    BOLD = "\033[1m"
    ITALIC = "\033[3m"
    RESET = "\033[0m"
    UNDERLINE = "\033[4m"

T = Theme

# ═══════════════════════════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════════════════════════

def visible_len(s):
    return len(re.sub(r"\033\[[0-9;]*m", "", s))

def pad_vis(s, width):
    diff = width - visible_len(s)
    return s + (" " * max(0, diff))

def get_tw():
    return shutil.get_terminal_size().columns

def get_th():
    return shutil.get_terminal_size().lines

def elapsed_str():
    elapsed = int(time.time() - session_start)
    m, s = divmod(elapsed, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"

# ═══════════════════════════════════════════════════════════════
#  GENGAR ASCII ART (pequeño)
# ═══════════════════════════════════════════════════════════════

GENGAR_SMALL = [
    f"{T.PURPLE}      ▄████▄      {T.RESET}",
    f"{T.PURPLE}    ██▀▀▀▀██    {T.RED}██{T.RESET}",
    f"{T.PURPLE}   █▀░░░░░░▀█  {T.RED}████{T.RESET}",
    f"{T.PURPLE}  █░░░░░░░░░░█{T.RED}█░░░██{T.RESET}",
    f"{T.PURPLE}  █░░░░░░░░░░██░░░░██{T.RESET}",
    f"{T.PURPLE}  █░▀▀▄▄▀▀░░█{T.RED}██░░░██{T.RESET}",
    f"{T.PURPLE}  █░░░░░░░░░██░░░░░██{T.RESET}",
    f"{T.PURPLE}   █▀░░░░░░▀█░░░░██{T.RESET}",
    f"{T.PURPLE}    ██▄▄▄▄██  {T.RED}████{T.RESET}",
    f"{T.PURPLE}      ▀████▀    {T.RED}██{T.RESET}",
]

# ═══════════════════════════════════════════════════════════════
#  LAYOUT COMPONENTS (OpenCode style)
# ═══════════════════════════════════════════════════════════════

def print_left_border(text, color=T.BORDER, width=None):
    """Imprime texto con borde izquierdo estilo OpenCode (┃)."""
    tw = width or get_tw() - 4
    print(f"  {color}┃{T.RESET} {text}")

def print_separator(title="", color=T.BORDER):
    """Línea separadora horizontal con título opcional."""
    tw = get_tw()
    if title:
        sep_len = (tw - len(title) - 6) // 2
        left = "─" * sep_len
        right = "─" * (tw - len(title) - 6 - sep_len)
        print(f"  {color}{left} {T.TEXT}{title} {color}{right}{T.RESET}")
    else:
        print(f"  {color}{'─' * (tw - 4)}{T.RESET}")

def print_empty_lines(n=1):
    for _ in range(n):
        print()

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# ═══════════════════════════════════════════════════════════════
#  HOME SCREEN (OpenCode style — vertically centered)
# ═══════════════════════════════════════════════════════════════

def print_home_screen():
    clear_screen()
    tw = get_tw()
    th = get_th()

    # Calcular espacio para centrar
    content_height = len(GENGAR_SMALL) + 8  # logo + text + prompt
    top_pad = max(3, (th - content_height) // 2 - 2)

    # Top spacer
    for _ in range(top_pad):
        print()

    # ─── Gengar ASCII Art (centrado) ───
    max_art_w = max(visible_len(l) for l in GENGAR_SMALL)
    for line in GENGAR_SMALL:
        pad_left = max(1, (tw - max_art_w) // 2)
        print(" " * pad_left + line)

    print_empty_lines(1)

    # ─── Title ───
    title = f"{T.BOLD}{T.PURPLE}Artenisa{T.RESET}"
    subtitle = f"{T.MUTED}v4.0 · Gengar Theme{T.RESET}"
    print_centered(title, tw)
    print_centered(subtitle, tw)

    print_empty_lines(2)

    # ─── Prompt Input Area (OpenCode style) ───
    prompt_w = min(70, tw - 8)
    prompt_left = (tw - prompt_w) // 2

    # Top decorative line
    print(" " * prompt_left + f"{T.BORDER}╹{'─' * (prompt_w - 1)}{T.RESET}")

    # Input box with left border
    print(" " * prompt_left + f"{T.BORDER}┃{T.RESET} {T.BG_ELEMENT}  Ask anything... {' ' * (prompt_w - 22)}{T.RESET}")

    # Agent/model info line
    agent_info = f"{T.HIGHLIGHT}{T.BOLD}Artenisa{T.RESET} {T.DIM}·{T.RESET} {T.TEXT}{current_model}{T.RESET} {T.DIM}·{T.RESET} {T.MUTED}local{T.RESET}"
    print(" " * prompt_left + f"{T.BORDER}┃{T.RESET} {agent_info}")

    # Bottom decorative shadow
    print(" " * prompt_left + f"{T.BORDER}╹{T.BG_ELEMENT}▀{'▀' * (prompt_w - 2)}{T.RESET}")

    print_empty_lines(2)

    # ─── Keyboard hints ───
    hints = f"{T.DIM}/ayuda comandos  ·  Tab autocompletar  ·  Ctrl+C salir{T.RESET}"
    print_centered(hints, tw)

    print_empty_lines(1)

def print_centered(text, tw=None):
    tw = tw or get_tw()
    vlen = visible_len(text)
    pad_left = max(1, (tw - vlen) // 2)
    print(" " * pad_left + text)

# ═══════════════════════════════════════════════════════════════
#  STATUS BAR (OpenCode style — bottom bar)
# ═══════════════════════════════════════════════════════════════

def print_status_bar(spinner_frame=""):
    tw = get_tw()

    # ─── Left: Mode label ───
    mode_label = " ARtenisa "
    mode_str = f"{T.BG_STATUS}{T.BOLD}{T.WHITE}{mode_label}{T.RESET}"

    # ─── Center: Status/spinner ───
    if spinner_frame:
        status_str = f" {spinner_frame} {T.MUTED}thinking...{T.RESET}"
    else:
        status_str = f" {T.DIM}·{T.RESET} "

    # ─── Right: Model + Tokens + Time ───
    model_str = f"{T.TEXT}{current_model}{T.RESET}"
    tokens_str = f"{T.MUTED}{session_tokens} tok{T.RESET}"
    time_str = f"{T.MUTED}{elapsed_str()}{T.RESET}"

    # ─── Far right: Keyboard hints ───
    hints_str = f"{T.DIM}Ctrl+X cmd{T.RESET}"

    # Build status bar
    # Calculate widths
    left_w = visible_len(mode_label) + 4
    model_w = visible_len(current_model) + 6
    tokens_w = len(str(session_tokens)) + 8
    time_w = len(elapsed_str()) + 3
    hints_w = 14
    dots_w = 1

    center_w = max(2, tw - left_w - model_w - tokens_w - time_w - hints_w - 6)

    bar = f"\r{mode_str}"
    bar += f" {T.BORDER}│{T.RESET}"
    bar += f" {spinner_frame} " if spinner_frame else f" {T.MUTED}·{T.RESET} "
    bar += f"{' ' * max(0, center_w - 10)}"
    bar += f"{model_str} {T.DIM}·{T.RESET} "
    bar += f"{tokens_str} {T.DIM}·{T.RESET} "
    bar += f"{time_str}"
    bar += f" {T.DIM}·{T.RESET} "
    bar += f"{hints_str}"

    # Pad to fill width
    current_len = visible_len(bar.replace("\r", ""))
    remaining = max(0, tw - current_len)
    bar += " " * remaining

    sys.stdout.write(bar)
    sys.stdout.flush()

def clear_status_bar():
    tw = get_tw()
    sys.stdout.write("\r" + " " * tw + "\r")
    sys.stdout.flush()

# ═══════════════════════════════════════════════════════════════
#  MESSAGE RENDERING (OpenCode style with left borders)
# ═══════════════════════════════════════════════════════════════

def render_user_message(text):
    """Renderiza mensaje del usuario con borde izquierdo estilo OpenCode."""
    tw = get_tw()
    msg_w = tw - 6

    # Left border with agent color
    print(f"  {T.BORDER_ACTIVE}┃{T.RESET}")
    # Wrap text manually
    lines = text.split('\n')
    for line in lines:
        # Simple word wrap
        while visible_len(line) > msg_w:
            # Find last space before msg_w
            cut = msg_w
            while cut > 0 and line[cut] != ' ':
                cut -= 1
            if cut == 0:
                cut = msg_w
            print(f"  {T.BORDER_ACTIVE}┃{T.RESET} {T.TEXT}{line[:cut]}{T.RESET}")
            line = line[cut:].lstrip()
        print(f"  {T.BORDER_ACTIVE}┃{T.RESET} {T.TEXT}{line}{T.RESET}")

def render_assistant_message(text, tool_executed=False, tool_cmd="", tool_output=""):
    """Renderiza respuesta del asistente con borde izquierdo."""
    tw = get_tw()
    msg_w = tw - 6

    print(f"  {T.PURPLE_DIM}┃{T.RESET}")

    # Split by newlines and render
    lines = text.split('\n')
    in_code_block = False
    for line in lines:
        # Track code blocks
        if line.strip().startswith('```'):
            in_code_block = not in_code_block

        # Word wrap
        while visible_len(line) > msg_w:
            cut = msg_w
            while cut > 0 and line[cut] != ' ':
                cut -= 1
            if cut == 0:
                cut = msg_w
            prefix = f"  {T.PURPLE_DIM}┃{T.RESET} "
            if in_code_block:
                print(f"{prefix}{T.BG_PANEL}{T.GREEN}{line[:cut]}{T.RESET}")
            else:
                print(f"{prefix}{T.GREEN}{line[:cut]}{T.RESET}")
            line = line[cut:].lstrip()

        prefix = f"  {T.PURPLE_DIM}┃{T.RESET} "
        if in_code_block:
            print(f"{prefix}{T.BG_PANEL}{T.GREEN}{line}{T.RESET}")
        elif line.strip().startswith('#'):
            print(f"{prefix}{T.BOLD}{T.GREEN}{line}{T.RESET}")
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            print(f"{prefix}{T.GREEN}{line}{T.RESET}")
        elif line.strip().startswith('>'):
            print(f"{prefix}{T.DIM}{T.GREEN}{line}{T.RESET}")
        else:
            print(f"{prefix}{T.GREEN}{line}{T.RESET}")

    # Tool output
    if tool_executed and tool_cmd:
        print(f"  {T.PURPLE_DIM}┃{T.RESET}")
        print(f"  {T.PURPLE_DIM}┃{T.RESET} {T.YELLOW}⚙ {tool_cmd}{T.RESET}")
        if tool_output:
            for line in tool_output.split('\n')[:8]:
                print(f"  {T.PURPLE_DIM}┃{T.RESET} {T.DIM}{line}{T.RESET}")

    print(f"  {T.PURPLE_DIM}┃{T.RESET}")

# ═══════════════════════════════════════════════════════════════
#  SPINNER (OpenCode blocks style)
# ═══════════════════════════════════════════════════════════════

class Spinner:
    FRAMES = ["█", "▓", "▒", "░", "▒", "▓"]
    COLORS = [T.PURPLE, T.PURPLE_DIM, T.RED_DIM, T.RED, T.RED_DIM, T.PURPLE_DIM]

    def __init__(self, text="thinking"):
        self.text = text
        self.running = False
        self.thread = None
        self.idx = 0

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def _spin(self):
        while self.running:
            frame = self.FRAMES[self.idx % len(self.FRAMES)]
            color = self.COLORS[self.idx % len(self.COLORS)]
            print_status_bar(f"{color}{frame}{T.RESET}")
            time.sleep(0.08)
            self.idx += 1

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        clear_status_bar()

# ═══════════════════════════════════════════════════════════════
#  INPUT HANDLING (OpenCode style prompt)
# ═══════════════════════════════════════════════════════════════

def print_prompt_area():
    """Renderiza el área de input estilo OpenCode."""
    tw = get_tw()

    # Top border
    print(f"  {T.BORDER}╹{'─' * (tw - 5)}{T.RESET}")

    # Input with left border
    print(f"  {T.BORDER}┃{T.RESET} {T.BG_ELEMENT}{' ' * (tw - 7)}{T.RESET}")

    # Agent/model line
    agent_info = f"{T.HIGHLIGHT}{T.BOLD}Artenisa{T.RESET} {T.DIM}·{T.RESET} {T.TEXT}{current_model}{T.RESET} {T.DIM}·{T.RESET} {T.MUTED}local{T.RESET}"
    print(f"  {T.BORDER}┃{T.RESET} {agent_info}")

    # Bottom shadow
    print(f"  {T.BORDER}╹{T.BG_ELEMENT}▀{'▀' * (tw - 7)}{T.RESET}")

def read_input():
    """Lee input del usuario."""
    tw = get_tw()
    prompt_text = f"{T.BORDER}┃{T.RESET} {T.TEXT}"
    try:
        msg = input(f"  {prompt_text}> {T.RESET}")
        return msg
    except (EOFError, KeyboardInterrupt):
        return None

# ═══════════════════════════════════════════════════════════════
#  HTTP HELPERS
# ═══════════════════════════════════════════════════════════════

def api_get(path, params=None):
    try:
        with httpx.Client(timeout=30) as c:
            resp = c.get(f"{API_URL}{path}", params=params,
                         headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
            return resp.json() if resp.status_code == 200 else {"error": resp.text}
    except Exception as e:
        return {"error": str(e)}

def api_post(path, data=None):
    try:
        with httpx.Client(timeout=120) as c:
            resp = c.post(f"{API_URL}{path}", json=data,
                          headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
            return resp.json() if resp.status_code == 200 else {"error": resp.text}
    except Exception as e:
        return {"error": str(e)}

# ═══════════════════════════════════════════════════════════════
#  STREAMING (OpenCode style — token by token)
# ═══════════════════════════════════════════════════════════════

def send_message_stream(msg):
    global conv_id, session_tokens

    payload = {"message": msg}
    if conv_id:
        payload["conversation_id"] = conv_id

    full_response = []

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{API_URL}/chat/stream",
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {AUTH_TOKEN}"
            },
            method="POST"
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
                    token = obj["content"]
                    full_response.append(token)
                    sys.stdout.write(f"{T.GREEN}{token}{T.RESET}")
                    sys.stdout.flush()
                    session_tokens += 1
                elif obj.get("type") == "done":
                    conv_id = obj.get("conversation_id", conv_id)
                    print()
                    return obj
                elif obj.get("type") == "error":
                    return {"error": obj.get("error")}
            except json.JSONDecodeError:
                continue
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}

    return {"response": "".join(full_response), "conversation_id": conv_id}

def send_message(msg):
    global conv_id
    payload = {"message": msg}
    if conv_id:
        payload["conversation_id"] = conv_id
    data = api_post("/chat", payload)
    if "conversation_id" in data:
        conv_id = data["conversation_id"]
    return data

# ═══════════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════════

COMMANDS = {
    "/ayuda": "show this help",
    "/nueva": "new conversation",
    "/model": "switch model",
    "/modelos": "list models",
    "/memoria": "view memories",
    "/olvidar": "clear memories",
    "/buscar": "web search",
    "/run": "execute command",
    "/voz": "toggle voice mode",
    "/workflows": "list workflows",
    "/wf": "run workflow",
    "/archivos": "list files",
    "/add": "add file to context",
    "/tokens": "token usage",
    "/editor": "open external editor",
    "/multiline": "toggle multi-line",
    "/status": "system status",
    "/gengar": "show splash",
    "/tema": "color themes",
    "/salir": "exit",
}

def show_help():
    print()
    print_separator("COMANDOS")
    for cmd, desc in sorted(COMMANDS.items()):
        print_left_border(f"{T.HIGHLIGHT}{cmd:14s}{T.RESET} {T.MUTED}{desc}{T.RESET}")
    print_separator()
    print_left_border(f"{T.DIM}Multi-línea: Shift+Enter | Tab: autocomplete{T.RESET}")
    print()

# ═══════════════════════════════════════════════════════════════
#  SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════

SESSIONS_DIR = Path(__file__).parent.parent / "backend" / "data" / "sessions"

def ensure_sessions_dir():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

def save_session(name=None):
    ensure_sessions_dir()
    if not name:
        name = f"session_{int(time.time())}"
    data = {
        "conversation_id": conv_id,
        "model": current_model,
        "tokens": session_tokens,
        "start": session_start,
        "saved_at": time.time()
    }
    (SESSIONS_DIR / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print_left_border(f"{T.SUCCESS}Session saved: {name}{T.RESET}")

def load_session(name):
    global conv_id, current_model, session_tokens, session_start
    ensure_sessions_dir()
    path = SESSIONS_DIR / f"{name}.json"
    if not path.exists():
        print_left_border(f"{T.ERROR}Session not found: {name}{T.RESET}")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    conv_id = data.get("conversation_id")
    current_model = data.get("model", "personal")
    session_tokens = data.get("tokens", 0)
    session_start = time.time()
    print_left_border(f"{T.SUCCESS}Session loaded: {name}{T.RESET}")

def list_sessions():
    ensure_sessions_dir()
    sessions = sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not sessions:
        print_left_border(f"{T.MUTED}No saved sessions{T.RESET}")
        return
    print_separator("SESSIONS")
    for s in sessions:
        data = json.loads(s.read_text(encoding="utf-8"))
        t = time.strftime("%Y-%m-%d %H:%M", time.localtime(data.get("saved_at", 0)))
        conv = data.get("conversation_id", "?")[:8]
        tokens = data.get("tokens", 0)
        print_left_border(f"{T.HIGHLIGHT}{s.stem:20s}{T.RESET} {T.DIM}{t}{T.RESET} conv:{conv} {tokens}tok")
    print_separator()
    print_left_border(f"{T.DIM}/cargar <name>{T.RESET}")

# ═══════════════════════════════════════════════════════════════
#  MAIN LOOP
# ═══════════════════════════════════════════════════════════════

def main():
    global conv_id, voice_mode, current_model, session_tokens

    # Show home screen
    print_home_screen()

    # Check server
    info = api_get("/")
    if "error" in info:
        print_left_border(f"{T.ERROR}Server not available: {info['error']}{T.RESET}")
        print_left_border(f"{T.DIM}Start backend: python main.py{T.RESET}")
        return

    while True:
        try:
            # Read input
            msg = read_input()
            if msg is None:
                break

            msg = msg.strip()
            if not msg:
                continue

            # ─── Commands ───
            cmd_lower = msg.lower()

            if cmd_lower in ("/salir", "salir", "exit", "quit"):
                break

            if cmd_lower in ("/gengar", "gengar"):
                clear_screen()
                print_home_screen()
                continue

            if cmd_lower in ("/ayuda", "help"):
                show_help()
                continue

            if cmd_lower in ("/nueva", "new", "reset"):
                conv_id = None
                session_tokens = 0
                print_left_border(f"{T.WARNING}New conversation{T.RESET}")
                continue

            if cmd_lower == "/modelos":
                data = api_get("/models")
                models = data.get("models", [])
                if models:
                    print_separator("MODELS")
                    for m in models:
                        marker = f" {T.SUCCESS}← current{T.RESET}" if m == current_model else ""
                        print_left_border(f"  {T.HIGHLIGHT}{m}{T.RESET}{marker}")
                    print_separator()
                continue

            if cmd_lower.startswith("/model "):
                current_model = msg.split(" ", 1)[1].strip()
                print_left_border(f"{T.SUCCESS}Model: {current_model}{T.RESET}")
                continue

            if cmd_lower == "/memoria":
                mems = api_get("/memories").get("memories", {})
                if mems:
                    print_separator("MEMORIES")
                    for k, v in sorted(mems.items()):
                        print_left_border(f"{T.HIGHLIGHT}{k.replace('_',' ').title():20s}{T.RESET} {T.TEXT}{v}{T.RESET}")
                    print_separator()
                else:
                    print_left_border(f"{T.MUTED}No memories stored{T.RESET}")
                continue

            if cmd_lower == "/olvidar":
                mems = api_get("/memories").get("memories", {})
                for k in mems:
                    httpx.delete(f"{API_URL}/memories/{k}", headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
                print_left_border(f"{T.ERROR}Memories cleared{T.RESET}")
                continue

            if cmd_lower.startswith("/buscar "):
                query = msg.split(" ", 1)[1]
                print_left_border(f"{T.WARNING}Searching: {query}...{T.RESET}")
                result = api_get("/search", {"query": query})
                print_left_border(result.get("results", "No results"))
                continue

            if cmd_lower.startswith("/run "):
                cmd = msg.split(" ", 1)[1]
                print_left_border(f"{T.WARNING}Running: {cmd}{T.RESET}")
                with httpx.Client(timeout=120) as c:
                    resp = c.post(f"{API_URL}/execute", data={"command": cmd},
                                  headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
                    if resp.status_code == 200:
                        data = resp.json()
                        icon = f"{T.SUCCESS}✓{T.RESET}" if data.get("success") else f"{T.ERROR}✗{T.RESET}"
                        print_left_border(f"{icon} exit:{data.get('returncode')}")
                        for line in data.get("output", "").split('\n')[:20]:
                            print_left_border(f"  {T.DIM}{line}{T.RESET}")
                continue

            if cmd_lower == "/workflows":
                wfs = api_get("/workflows")
                if isinstance(wfs, dict) and "error" not in wfs:
                    print_separator("WORKFLOWS")
                    for name, wf in wfs.items():
                        print_left_border(f"{T.HIGHLIGHT}{name:20s}{T.RESET} {T.MUTED}{wf.get('description','')}{T.RESET}")
                    print_separator()
                continue

            if cmd_lower.startswith("/wf "):
                wf_name = msg.split(" ", 1)[1].strip()
                print_left_border(f"{T.WARNING}Workflow: {wf_name}{T.RESET}")
                result = api_post(f"/workflows/{wf_name}", {})
                if "reporte" in result:
                    for line in result["reporte"].split('\n'):
                        print_left_border(f"  {T.TEXT}{line}{T.RESET}")
                continue

            if cmd_lower == "/archivos":
                files = api_get("/files").get("files", [])
                if files:
                    print_separator("FILES")
                    for f in files:
                        print_left_border(f"{T.HIGHLIGHT}{f['id']}{T.RESET} {T.TEXT}{f['name']}{T.RESET} {T.DIM}{f['size']}b{T.RESET}")
                    print_separator()
                continue

            if cmd_lower.startswith("/add "):
                filepath = msg.split(" ", 1)[1].strip()
                try:
                    p = Path(filepath)
                    if p.exists() and p.is_file():
                        content = p.read_text(encoding="utf-8", errors="replace")[:8000]
                        msg = f"[File: {filepath}]\n```\n{content}\n```"
                    else:
                        print_left_border(f"{T.ERROR}File not found: {filepath}{T.RESET}")
                        continue
                except Exception as e:
                    print_left_border(f"{T.ERROR}Error: {e}{T.RESET}")
                    continue

            if cmd_lower == "/tokens":
                print_separator("TOKEN USAGE")
                print_left_border(f"  Tokens: {T.HIGHLIGHT}{session_tokens}{T.RESET}")
                print_left_border(f"  Cost:   {T.HIGHLIGHT}${session_cost:.4f}{T.RESET}")
                print_left_border(f"  Time:   {T.HIGHLIGHT}{elapsed_str()}{T.RESET}")
                print_left_border(f"  Model:  {T.HIGHLIGHT}{current_model}{T.RESET}")
                print_separator()
                continue

            if cmd_lower.startswith("/guardar"):
                parts = msg.split(" ", 1)
                save_session(parts[1].strip() if len(parts) > 1 else None)
                continue

            if cmd_lower.startswith("/cargar "):
                load_session(msg.split(" ", 1)[1].strip())
                continue

            if cmd_lower == "/sesiones":
                list_sessions()
                continue

            if cmd_lower == "/multiline":
                print_left_border(f"{T.WARNING}Multi-line: use Shift+Enter or paste{T.RESET}")
                continue

            if cmd_lower == "/editor":
                # Open external editor
                editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "notepad"))
                tmp = Path(tempfile.gettempdir()) / f"artenisa_{os.urandom(4).hex()}.txt"
                tmp.write_text("", encoding="utf-8")
                subprocess.run([editor, str(tmp)], timeout=120)
                msg = tmp.read_text(encoding="utf-8").strip()
                tmp.unlink(missing_ok=True)
                if not msg:
                    continue

            if cmd_lower == "/status":
                print_separator("SYSTEM STATUS")
                print_left_border(f"  API:     {T.SUCCESS}Online{T.RESET}")
                print_left_border(f"  Model:   {T.HIGHLIGHT}{current_model}{T.RESET}")
                print_left_border(f"  Tokens:  {T.HIGHLIGHT}{session_tokens}{T.RESET}")
                print_left_border(f"  Time:    {T.HIGHLIGHT}{elapsed_str()}{T.RESET}")
                print_left_border(f"  Conv:    {T.HIGHLIGHT}{'Active' if conv_id else 'New'}{T.RESET}")
                print_separator()
                continue

            if cmd_lower == "/tema":
                print_separator("THEMES")
                print_left_border(f"  {T.PURPLE}● Gengar{T.RESET} (current)")
                print_left_border(f"  {T.DIM}More themes coming soon...{T.RESET}")
                print_separator()
                continue

            # ─── Send message (with streaming) ───
            render_user_message(msg)
            print()

            spinner = Spinner("thinking")
            spinner.start()

            try:
                data = send_message_stream(msg)
                if "error" in data:
                    spinner.stop()
                    spinner.start()
                    data = send_message(msg)
            except Exception as e:
                spinner.stop()
                print_left_border(f"{T.ERROR}Error: {e}{T.RESET}")
                continue

            spinner.stop()

            if "error" in data:
                print_left_border(f"{T.ERROR}{data['error']}{T.RESET}")
                continue

            resp = data.get("response", "")
            tool_exec = data.get("tool_executed", False)
            tool_cmd = data.get("tool_command", "")
            tool_out = data.get("tool_output", "")

            render_assistant_message(resp, tool_exec, tool_cmd, tool_out)

        except (EOFError, KeyboardInterrupt):
            break

    # Exit message
    print()
    print_left_border(f"{T.MUTED}Session ended · {session_tokens} tokens used{T.RESET}")
    print()

if __name__ == "__main__":
    main()
