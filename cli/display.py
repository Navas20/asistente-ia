import os
import re
import sys
import shutil
import time
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live
from rich.table import Table
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich.rule import Rule
from rich.spinner import Spinner
from rich.style import Style
from rich.syntax import Syntax
from rich.columns import Columns
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style as PtStyle
from prompt_toolkit.key_binding import KeyBindings

GENGAR_ART = r"""[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡷⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⡇⠈⠙⢷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡇⠀⠀⠀⠙⢷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣧⠀⠀⠀⠀⠀⠙⢷⣄⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠘⠳⣄⠀⣼⢷⣄⠀⣰⡀⠀⠀⠀⢀⣀⣤⡴⠶⠛⣿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⣿⣀⣙⢷⡏⢻⣤⠶⠟⠛⠉⠀⠀⢀⣼⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⢠⡄⣿⠳⣤⣀⠀⠀⠀⠀⠀⢸⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠁⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⢀⣾⣡⣤⣤⣴⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⣿⡿⠿⠇⠀⠛⠿⣤⣀⠀⠀⢸⡇⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠃⠀⠀⣸⠟⠀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀⣀
[bold #b380ff]⢙⣿⡆⠀⠀⠀⠀⠀⠙⠳⢦⣸⡇⢀⡤⠖⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠉⠉⠉⠙⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⠉⣩⣿⠃
[bold #b380ff]⠸⠿⣭⡄⠀⠀⠀⠀⠀⠀⢹⡷⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⡾⠋⠀⠀
[bold #b380ff]⠀⠀⠈⢿⡄⠀⠀⠀⠀⠀⠀⠉⠀⠀⠀⠀⠀⣴⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⠞⠋⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⢻⡄⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⢀⡼⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⡾⠟⠁⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠻⣄⢠⠏⠀⠀⠀⠀⠀⠀⣰⡏⠀⢻⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣠⡾⠋⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⣹⠏⠀⠀⠀⢠⠀⠀⠀⡟⠀⠀⠘⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣤⠾⠆⠀⠀⠀⠀⢶⢀⣴⠟⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⢠⡏⠀⠀⠀⠀⢸⣇⠀⠠⣷⡀⠀⠀⣿⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⡴⠞⠉⣿⠀⠀⠀⠀⠀⠀⢸⣏⣁⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⣼⠀⠀⠀⠀⠀⢸⡿⣦⡀⠈⠳⢦⣀⣀⣹⡄⠀⠀⠀⠀⠀⠀⠀⣀⣴⠛⠉⠀⠀⢀⡏⠀⠀⠀⠀⠀⠀⣸⠉⠉⠉⠉⠉⠙⠛⠛⠓⢶⣶⣤⡀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⣸⡇⠈⢷⣄⠀⠀⠀⠉⠉⠉⠀⠀⠀⠀⣠⣴⠛⠉⠏⠀⠀⠀⢀⡾⠁⠀⠀⠀⠀⠀⠐⣾⠃⠀⠀⠀⠀⠀⠀⠀⠀⠈⠛⢷⣾⡄
[bold #b380ff]⠀⠀⠀⠀⢀⣿⠀⠀⠀⠀⠀⠹⣷⠀⣸⠋⠛⢦⣄⡀⠀⠀⠀⠀⠀⠀⠀⠈⠛⠶⠦⠤⠤⠞⠋⠀⢀⣤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡀⣾⠛⠉⠀
[bold #b380ff]⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠹⣿⡟⠀⠀⠀⢨⡏⠛⠲⠤⣤⣀⣀⡀⠀⠀⠀⠀⠀⢀⣀⣤⡶⠋⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⣀⣤⡶⠞⠋⠛⠛⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⢀⣿⡀⠀⠀⠀⠀⠀⠀⠈⠻⣄⡀⠀⣾⠀⠀⠀⠀⠀⠈⢹⡏⠉⠛⠛⠛⡿⠉⣍⡾⠁⠀⠀⠀⠀⠀⢀⣏⣀⣤⡴⠶⠛⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⢀⡾⠉⣧⠀⠀⠀⠀⠀⠀⠀⠀⠈⠛⢦⣇⡀⠀⠀⠀⠀⠀⣾⠀⠀⠀⠀⢸⢇⡴⠋⠀⠀⠀⠀⠀⠀⠀⣾⠋⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⣸⠇⠀⠹⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠓⠶⠤⣤⣴⣧⣠⣤⣤⠴⠟⠉⠀⠀⠀⠀⠀⠀⠀⠀⣼⠏⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣼⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⢹⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⣶⡄⣾⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⢻⣦⠀⠀⠀⠀⠻⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠙⠻⣦⡄⠀⢀⣈⣳⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠈⠘⢷⣽⣭⣿⣾⡎⠙⠷⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠙⠟⠀⠁⠀⠀⠀⠉⠻⣗⠲⠶⠴⢦⡶⠶⣦⡀⠀⠀⢀⡀⠀⣀⠀⠀⠀⣠⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠳⣦⣠⡿⠀⠀⠘⣷⡀⢠⠟⢳⠟⢹⡧⣦⣠⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠀⠀⠀⠀⠘⣷⡿⠀⠀⠀⠀⣸⡿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⠳⠦⠤⠴⠞⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
[bold #b380ff]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀"""

SIDEBAR_WIDTH = 28
SIDEBAR_MIN_COLS = 90
HISTORY_FILE = os.path.expanduser("~/.artenisa_history")

def extract_code_blocks(text: str) -> list:
    pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
    return [(lang.strip() or "text", code.strip()) for lang, code in pattern.findall(text)]

def extract_think_tag(text: str):
    parts = re.split(r"</?think>", text)
    thinking = None
    response = text
    if len(parts) > 1:
        thinking = parts[1].strip() if len(parts) >= 3 else parts[0].strip()
        response = (parts[0] + parts[2]) if len(parts) >= 3 else (parts[-1] if len(parts) == 2 else "")
    return thinking, response

class Screen:
    def __init__(self):
        self.console = Console()
        self.conversation = []
        self.status_text = "Artenisa"
        self._input_mode = False
        self.session_info = {
            "session_started": "",
            "tokens": 0,
            "context_pct": 0,
            "cost": 0.0,
            "model": "",
            "provider": "openrouter",
            "jailbreak": False,
            "mcp": [],
            "version": "",
        }
        self.pt_style = PtStyle.from_dict({"prompt": "ansiyellow bold"})
        kb = KeyBindings()
        @kb.add("enter")
        def _(event):
            event.current_buffer.validate_and_handle()
        @kb.add("escape", "enter")
        def _(event):
            event.current_buffer.insert_text("\n")
        self.session = PromptSession(
            history=FileHistory(HISTORY_FILE),
            style=self.pt_style,
            key_bindings=kb,
            multiline=True,
            prompt_continuation=lambda w, ln, sw: " " * (w - 1) + "│",
        )
        self._cols, self._rows = shutil.get_terminal_size()
        self._running = True
        self._last_layout = None

    def start(self):
        self.console.show_cursor(False)

    def stop(self):
        self.console.show_cursor(True)
        self.console.print()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def clear(self):
        self.console.clear()

    def print_banner(self):
        self.clear()
        self.console.print(Align.center(GENGAR_ART))
        self.console.print(Align.center(Text("Artenisa v5.0 · Gengar Theme", style="bold #b380ff")))
        self.console.print(Align.center(Text("━" * 40, style="dim #b380ff")))

    def log(self, text: str):
        self.conversation.append(text)
        self._render()

    def update_last(self, text: str):
        if self.conversation:
            self.conversation[-1] = text
        else:
            self.conversation.append(text)
        self._render()

    def set_status(self, text: str):
        self.status_text = text
        self._render()

    def set_session(self, **kwargs):
        self.session_info.update(kwargs)

    def _render(self):
        self.console.clear()

        cols, rows = shutil.get_terminal_size()
        show_sidebar = cols >= SIDEBAR_MIN_COLS
        main_cols = cols - SIDEBAR_WIDTH - 3 if show_sidebar else cols
        conv_rows = max(5, rows - 4)

        # Status bar
        model = self.session_info.get("model", "?")
        provider = self.session_info.get("provider", "?")
        status = f"[bold #b380ff]ARtenisa[/] [dim]·[/] {self.status_text} [dim]·[/] [dim]{provider}[/] [dim]·[/] [dim]{model}[/]"
        status_bar = Panel(Text.from_markup(status), style="on #2d2d2d", height=1, padding=(0, 1))
        self.console.print(status_bar)

        # Conversation area with sidebar
        if show_sidebar:
            # Main content
            conv_lines = self._render_conversation(main_cols, conv_rows)
            for line in conv_lines[-conv_rows:]:
                self.console.print(line)

            # Sidebar
            t = self.session_info
            side_lines = []
            side_lines.append(f"[bold #b380ff]Sesion[/]")
            if t.get("session_started"):
                side_lines.append(f"[dim]{t['session_started']}[/]")
            side_lines.append("")
            side_lines.append(f"[bold #b380ff]Contexto[/]")
            side_lines.append(f"{t.get('tokens', 0):,} tokens")
            side_lines.append(f"{t.get('context_pct', 0)}% usado")
            side_lines.append(f"[dim]${t.get('cost', 0.0):.4f} cost[/]")
            side_lines.append(f"[dim]{t.get('requests', 0)} req[/]")
            side_lines.append("")
            side_lines.append(f"[bold #b380ff]Provider[/]")
            side_lines.append(f"{t.get('provider', '?')}")
            side_lines.append(f"[dim]{t.get('model', '?')}[/]")
            jailbreak = t.get("jailbreak", False)
            if jailbreak:
                side_lines.append("[bold red]⚠ JAILBREAK[/]")
            mcp = t.get("mcp") or []
            if mcp:
                side_lines.append("")
                side_lines.append(f"[bold #b380ff]MCP[/]")
                for name, status_m in mcp:
                    c = "green" if status_m.lower() in ("ok", "conectado") else "yellow"
                    side_lines.append(f"[dim]•[/] {name} [{c}]{status_m}[/]")
            if t.get("version"):
                side_lines.append("")
                side_lines.append(f"[dim]{t['version']}[/]")
            findings = t.get("findings", {})
            if findings:
                side_lines.append("")
                side_lines.append(f"[bold #b380ff]Findings[/]")
                sevs = [("critical", "🔴"), ("high", "⚠️"), ("medium", "🟡"), ("low", "🟢"), ("info", "ℹ️")]
                parts = [f"{icon} {findings.get(k,0)}" for k, icon in sevs if findings.get(k, 0) > 0]
                if parts:
                    side_lines.append(" ".join(parts))
            phase = t.get("phase", "")
            if phase:
                side_lines.append("")
                side_lines.append(f"[bold #b380ff]Phase[/]")
                side_lines.append(f"{phase}")
            defense = t.get("defense", {})
            if defense:
                side_lines.append("")
                side_lines.append(f"[bold #b380ff]Defense[/]")
                side_lines.append(f"{'🛡️ Active' if defense.get('monitoring') else '⏸️ Stopped'}")
                side_lines.append(f"Blocks: {defense.get('active_blocks', 0)}")

            sidebar_text = "\n".join(side_lines)
            panel = Panel(
                Text.from_markup(sidebar_text),
                border_style="#b380ff",
                width=SIDEBAR_WIDTH,
                height=conv_rows + 1,
                padding=(0, 1),
            )
            self.console.print(panel)
        else:
            conv_lines = self._render_conversation(cols - 2, conv_rows)
            for line in conv_lines[-conv_rows:]:
                self.console.print(line)

        # Input line
        input_style = "bold #b380ff > "

    def _render_conversation(self, width: int, max_rows: int) -> list:
        rendered = []
        for entry in self.conversation[-max_rows:]:
            if entry.startswith("[MARKDOWN]"):
                text = entry[len("[MARKDOWN]"):]
                rendered.append(Markdown(text, code_theme="monokai"))
            elif entry.startswith("[THINK]"):
                text = entry[len("[THINK]"):]
                panel = Panel(Text(text, style="dim cyan"), title="[bold cyan]🧠 Razonamiento[/]", border_style="dim blue", padding=(0, 1), width=width)
                rendered.append(panel)
            elif entry.startswith("[CODE]"):
                parts = entry[len("[CODE]"):].split("|", 1)
                lang = parts[0] if len(parts) > 1 else ""
                code = parts[1] if len(parts) > 1 else parts[0]
                rendered.append(Syntax(code, lang or "text", theme="monokai", line_numbers=True, word_wrap=True))
            elif entry.startswith("[TOOL]"):
                text = entry[len("[TOOL]"):]
                rendered.append(Panel(Text.from_markup(f"[yellow]⚙ {text}[/]"), border_style="yellow", padding=(0, 1), width=width))
            elif entry.startswith("[ERROR]"):
                text = entry[len("[ERROR]"):]
                rendered.append(Panel(Text.from_markup(f"[red]{text}[/]"), border_style="red", padding=(0, 1), width=width))
            elif entry.startswith("[SYSTEM]"):
                text = entry[len("[SYSTEM]"):]
                rendered.append(Panel(Text.from_markup(f"[bold #b380ff]{text}[/]"), border_style="#b380ff", padding=(0, 1), width=width))
            else:
                rendered.append(Text(entry, style="bright_white"))
        return rendered

    def show_help(self):
        cmds = [
            ("/ayuda", "Help"),
            ("/nueva", "New conversation"),
            ("/provider <name>", "Switch provider"),
            ("/providers", "List providers"),
            ("/model <m>", "Switch model"),
            ("/modelos", "List models"),
            ("/modo", "Toggle jailbreak mode"),
            ("/memoria", "View memories"),
            ("/olvidar", "Clear memories"),
            ("/buscar <q>", "Web search"),
            ("/run <cmd>", "Run command"),
            ("/voz", "Toggle voice"),
            ("/archivos", "Project files"),
            ("/add <file>", "Add file context"),
            ("/tokens", "Token stats"),
            ("/editor", "External editor"),
            ("/status", "System status"),
            ("/guardar <n>", "Save session"),
            ("/cargar <n>", "Load session"),
            ("/sesiones", "List sessions"),
            ("/update", "Check updates"),
            ("/gengar", "Show Gengar"),
            ("", ""),
            ("[bold #00ff7f]PENTEST[/]", ""),
            ("/autopentest", "Full pipeline (recon→report)"),
            ("/recon", "Recon phase"),
            ("/enum", "Enumeration phase"),
            ("/vuln", "Vulnerability phase"),
            ("/exploit", "Exploitation phase"),
            ("/post", "Post-exploit phase"),
            ("/pentest status", "Pipeline progress"),
            ("/pentest cancel", "Cancel pipeline"),
            ("/phase", "Show current phase"),
            ("/graph", "Show attack graph (Mermaid)"),
            ("/scope", "Show scope rules"),
            ("/scope add <rule>", "Add scope (CIDR/domain)"),
            ("/scope remove <rule>", "Remove scope rule"),
            ("", ""),
            ("[bold yellow]FINDINGS[/]", ""),
            ("/findings", "List findings"),
            ("/finding <id>", "Finding detail"),
            ("/findings summary", "Counts by severity"),
            ("/findings export json", "Export findings"),
            ("/verificar <id>", "Verify finding"),
            ("", ""),
            ("[bold #ff2040]DEFENSE[/]", ""),
            ("/defense", "Defense status"),
            ("/defense start", "Start monitoring"),
            ("/defense stop", "Stop monitoring"),
            ("/defense auto on|off", "Toggle auto-block"),
            ("/incidents", "List incidents"),
            ("/incident <id>", "Incident detail"),
            ("/incident <id> block", "Block attacker IP"),
            ("/incident <id> investigate", "Intel + forensics"),
            ("/incident <id> report", "Generate legal report"),
            ("/blocks", "List active blocks"),
            ("/intel <ip>", "Threat intel lookup"),
            ("", ""),
            ("", ""),
            ("[bold cyan]MCP[/]", ""),
            ("/mcp", "List MCP tools"),
            ("/mcp call <t> [args]", "Call MCP tool"),
            ("", ""),
            ("[bold #ff9900]SUBAGENTS[/]", ""),
            ("/lanzar <t>\|task\|name", "Launch subagent"),
            ("/subagentes", "List subagents"),
            ("/subagente <id>", "Subagent detail"),
            ("/subagente <id> cancel", "Cancel subagent"),
            ("", ""),
            ("", ""),
            ("[bold magenta]PROJECTS[/]", ""),
            ("/proyectos", "List projects"),
            ("/proyecto <name>", "Create project"),
            ("/activar <id>", "Set active project"),
            ("", ""),
            ("[bold #b380ff]GENERAL[/]", ""),
            ("/salir", "Exit"),
        ]
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Cmd", style="bold #b380ff")
        table.add_column("Desc", style="dim")
        for cmd, desc in cmds:
            table.add_row(cmd, desc)
        self.conversation.append(f"[SYSTEM]Comandos disponibles:")
        for cmd, desc in cmds:
            self.conversation.append(f"  [dim]{cmd}[/]  {desc}")
        self._render()

    def show_code_blocks(self, code_blocks: list):
        if not code_blocks: return
        table = Table(show_header=True, header_style="bold magenta", border_style="dim white", expand=True)
        table.add_column("#", style="cyan", justify="center", width=4)
        table.add_column("Lang", style="green")
        table.add_column("Preview", style="dim white")
        table.add_column("Lines", style="yellow", justify="right")
        for idx, (lang, code) in enumerate(code_blocks, 1):
            fl = code.split("\n")
            preview = fl[0].strip()[:50] + "..." if len(fl[0]) > 50 else fl[0].strip()
            table.add_row(str(idx), lang.upper(), preview, str(len(fl)))
        self.conversation.append(f"[SYSTEM]📦 {len(code_blocks)} bloque(s) de código detectados")
        self.console.print(table)
        self.console.print("[bold cyan][1][/] Save All    [bold cyan][2][/] Copy All    [bold cyan][3][/] Save One    [bold cyan][4][/] Copy One    [dim][Space] Skip[/]")

    def get_input(self, prompt_text: str = "") -> str:
        try:
            return self.session.prompt([("class:prompt", f" ╰─> ")])
        except (KeyboardInterrupt, EOFError):
            return "/salir"

    def get_key(self) -> str:
        try:
            if sys.platform == "win32":
                import msvcrt
                ch = msvcrt.getch()
                if ch == b"\r": return "enter"
                if ch == b" ": return "space"
                try:
                    return ch.decode("utf-8").lower()
                except:
                    return ""
            else:
                import tty, termios
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    ch = sys.stdin.read(1)
                    if ch == "\r": return "enter"
                    if ch == " ": return "space"
                    return ch.lower()
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except:
            return self.get_input("> ")[:1].lower()

    def check_resize(self):
        c, r = shutil.get_terminal_size()
        if c != self._cols or r != self._rows:
            self._cols, self._rows = c, r
            return True
        return False
