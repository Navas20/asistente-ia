import os
import re
import sys
import time
import shutil
import msvcrt

ANSI = re.compile(r"\033\[[0-9;]*[a-zA-Z]")

def visible_len(text):
    return len(ANSI.sub("", text))

def truncate_ansi(text, width):
    parts = ANSI.split(text)
    splits = ANSI.findall(text)
    result = []
    v = 0
    for i, p in enumerate(parts):
        if i > 0:
            result.append(splits[i - 1])
        remaining = width - v
        if remaining <= 0:
            break
        if len(p) > remaining:
            result.append(p[:remaining])
            v += remaining
        else:
            result.append(p)
            v += len(p)
    result.append("\033[0m")
    return "".join(result)

class Theme:
    PURPLE = "\033[38;5;141m"
    PURPLE_DIM = "\033[38;5;98m"
    GREEN = "\033[38;5;120m"
    ERROR = "\033[38;5;196m"
    WARNING = "\033[38;5;220m"
    HIGHLIGHT = "\033[38;5;183m"
    TEXT = "\033[38;5;252m"
    MUTED = "\033[38;5;245m"
    DIM = "\033[38;5;240m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    BG_STATUS = "\033[48;5;236m"
    RESET_BG = "\033[49m"
    BORDER = PURPLE_DIM
    SUCCESS = GREEN
    YELLOW = WARNING
    BG_DARK = "\033[48;5;234m"

SIDEBAR_WIDTH = 28
SIDEBAR_MIN_COLS = 90

class Screen:
    def __init__(self, theme=None):
        self.theme = theme or Theme()
        if sys.platform == "win32":
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)
            m = ctypes.c_uint32()
            k32.GetConsoleMode(h, ctypes.byref(m))
            k32.SetConsoleMode(h, m.value | 0x0004)

        self.conversation = []
        self.input_text = ""
        self.input_cursor = 0
        self.history = []
        self.history_idx = -1
        self.status_text = ""
        self._running = True
        self._clean = False
        self.session_info = {
            "session_started": "",
            "tokens": 0,
            "context_pct": 0,
            "cost": 0.0,
            "model": "",
            "mcp": [],
            "version": "",
        }
        self._update_size()

    def _update_size(self):
        self.cols, self.rows = shutil.get_terminal_size()
        self.show_sidebar = self.cols >= SIDEBAR_MIN_COLS
        if self.show_sidebar:
            self.main_cols = self.cols - SIDEBAR_WIDTH - 1
            self.sidebar_col = self.main_cols + 3
        else:
            self.main_cols = self.cols
            self.sidebar_col = None
        self.conv_rows = max(1, self.rows - 2)
        self.status_row = self.rows - 1
        self.input_row = self.rows

    def set_session(self, **kwargs):
        self.session_info.update(kwargs)
        if self.show_sidebar:
            self._draw_sidebar()
            sys.stdout.flush()

    def start(self):
        sys.stdout.write("\033[?25l\033[2J")
        sys.stdout.flush()

    def stop(self):
        if not self._clean:
            self._clean = True
            sys.stdout.write("\033[?25h\033[0m")
            sys.stdout.write(f"\033[{self.rows};1H\n")
            sys.stdout.flush()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def _gotoxy(self, row, col=1):
        sys.stdout.write(f"\033[{row};{col}H")

    def _cls(self):
        sys.stdout.write("\033[J")

    def _clear_line(self):
        sys.stdout.write("\033[K")

    def _wrap_text(self, text, width):
        segments = ANSI.split(text)
        codes = ANSI.findall(text)
        lines = []
        current = ""
        for i, segment in enumerate(segments):
            if i > 0:
                current += codes[i - 1]
            for part in segment.split(" "):
                if not current and not part:
                    continue
                prefix = " " if visible_len(current) > 0 and part else ""
                candidate = current + prefix + part
                if "\n" in candidate:
                    pieces = candidate.split("\n")
                    for piece in pieces[:-1]:
                        if piece:
                            lines.append(piece)
                    current = pieces[-1]
                    continue
                if visible_len(candidate) > width and current:
                    lines.append(current)
                    current = part
                else:
                    current = candidate
        if current:
            lines.append(current)
        return lines

    def _draw_conversation(self):
        visible = self.conversation[-(self.conv_rows):]
        rendered = []
        for line in visible:
            wrapped = self._wrap_text(line, self.main_cols)
            rendered.extend(wrapped)
            if len(rendered) >= self.conv_rows:
                break
        for i, line in enumerate(rendered[: self.conv_rows]):
            row = i + 1
            self._gotoxy(row, 1)
            self._clear_line_main()
            sys.stdout.write(line)
        for r in range(len(rendered) + 1, self.conv_rows + 1):
            self._gotoxy(r, 1)
            self._clear_line_main()

    def _clear_line_main(self):
        if self.show_sidebar:
            sys.stdout.write(" " * self.main_cols)
        else:
            self._clear_line()

    def _draw_sidebar(self):
        if not self.show_sidebar:
            return
        t = self.theme
        info = self.session_info
        divider_col = self.main_cols + 1
        lines = []
        lines.append(f"{t.PURPLE}{t.BOLD}Sesion{t.RESET}")
        if info.get("session_started"):
            lines.append(f"{t.MUTED}{info['session_started']}{t.RESET}")
        lines.append("")
        lines.append(f"{t.PURPLE}{t.BOLD}Contexto{t.RESET}")
        lines.append(f"{t.TEXT}{info.get('tokens', 0):,} tokens{t.RESET}")
        lines.append(f"{t.TEXT}{info.get('context_pct', 0)}% usado{t.RESET}")
        lines.append(f"{t.MUTED}${info.get('cost', 0.0):.2f} gastado{t.RESET}")
        mcp = info.get("mcp") or []
        if mcp:
            lines.append("")
            lines.append(f"{t.PURPLE}{t.BOLD}MCP{t.RESET}")
            for name, status in mcp:
                color = t.GREEN if status.lower() in ("ok", "conectado") else t.WARNING
                lines.append(f"{t.MUTED}\u2022 {name} {color}{status}{t.RESET}")
        lines.append("")
        if info.get("model"):
            lines.append(f"{t.PURPLE}{t.BOLD}Modelo{t.RESET}")
            lines.append(f"{t.TEXT}{info['model']}{t.RESET}")

        for row in range(1, self.rows + 1):
            self._gotoxy(row, divider_col)
            sys.stdout.write(f"{t.BORDER}\u2502{t.RESET}")

        for i in range(self.rows):
            self._gotoxy(i + 1, self.sidebar_col)
            sys.stdout.write(" " * (SIDEBAR_WIDTH - 2))
        for i, line in enumerate(lines):
            if i + 1 > self.rows:
                break
            self._gotoxy(i + 1, self.sidebar_col)
            sys.stdout.write(truncate_ansi(line, SIDEBAR_WIDTH - 2))

        if info.get("version"):
            self._gotoxy(self.rows, self.sidebar_col)
            sys.stdout.write(truncate_ansi(f"{t.DIM}{info['version']}{t.RESET}", SIDEBAR_WIDTH - 2))

    def _draw_status(self):
        self._gotoxy(self.status_row, 1)
        self._clear_line_main()
        bar = (
            f"{self.theme.BG_STATUS}{self.theme.BOLD}{self.theme.PURPLE}"
            f" ARtenisa {self.theme.RESET}{self.theme.RESET_BG}"
            f" {self.theme.DIM}·{self.theme.RESET}"
            f" {self.theme.MUTED}{self.status_text}{self.theme.RESET}"
        )
        v = visible_len(bar)
        if v > self.main_cols:
            bar = truncate_ansi(bar, self.main_cols)
        elif v < self.main_cols:
            bar += " " * (self.main_cols - v)
        self._gotoxy(self.status_row, 1)
        sys.stdout.write(bar)

    def _draw_input(self):
        self._gotoxy(self.input_row, 1)
        self._clear_line_main()
        self._gotoxy(self.input_row, 1)
        prefix = f"  {self.theme.BORDER}\u2503{self.theme.RESET} {self.theme.TEXT}> {self.theme.RESET}"
        sys.stdout.write(prefix)
        avail = self.main_cols - visible_len(prefix)
        sys.stdout.write(self.input_text[:avail])
        cx = visible_len(prefix + self.input_text[:self.input_cursor]) + 1
        self._gotoxy(self.input_row, min(cx, self.main_cols))

    def redraw(self):
        self._draw_conversation()
        self._draw_status()
        self._draw_input()
        self._draw_sidebar()
        sys.stdout.flush()

    def log(self, text):
        self.conversation.append(text)
        self._draw_conversation()
        self._draw_status()
        self._draw_input()
        sys.stdout.flush()

    def update_last(self, text):
        if not self.conversation:
            self.log(text)
            return
        self.conversation[-1] = text
        self._draw_conversation()
        self._draw_input()
        sys.stdout.flush()

    def set_status(self, text):
        self.status_text = text
        self._draw_status()
        sys.stdout.flush()

    def read_key(self):
        if not msvcrt.kbhit():
            return None
        return msvcrt.getch()

    def handle_input(self):
        ch = self.read_key()
        if ch is None:
            return None

        if ch == b"\r":
            msg = self.input_text.strip()
            if msg:
                self.history.append(msg)
                self.history_idx = -1
                self.input_text = ""
                self.input_cursor = 0
                self._draw_input()
                sys.stdout.flush()
                return ("submit", msg)
            return None

        if ch == b"\xe0":
            ch2 = self.read_key()
            if ch2 is None:
                return None
            if ch2 == b"H":
                if self.history:
                    if self.history_idx < len(self.history) - 1:
                        self.history_idx += 1
                    self.input_text = self.history[-(self.history_idx + 1)]
                    self.input_cursor = len(self.input_text)
                    self._draw_input()
                    sys.stdout.flush()
            elif ch2 == b"P":
                if self.history_idx > 0:
                    self.history_idx -= 1
                    self.input_text = self.history[-(self.history_idx + 1)]
                elif self.history_idx == 0:
                    self.history_idx = -1
                    self.input_text = ""
                else:
                    return None
                self.input_cursor = len(self.input_text)
                self._draw_input()
                sys.stdout.flush()
            elif ch2 == b"K":
                if self.input_cursor > 0:
                    self.input_cursor -= 1
                    cx = visible_len(f"  \u2503 > {self.input_text[:self.input_cursor]}") + 1
                    self._gotoxy(self.input_row, min(cx, self.main_cols))
                    sys.stdout.flush()
            elif ch2 == b"M":
                if self.input_cursor < len(self.input_text):
                    self.input_cursor += 1
                    cx = visible_len(f"  \u2503 > {self.input_text[:self.input_cursor]}") + 1
                    self._gotoxy(self.input_row, min(cx, self.main_cols))
                    sys.stdout.flush()
            return None

        if ch in (b"\x08", b"\x7f"):
            if self.input_cursor > 0:
                self.input_text = (
                    self.input_text[:self.input_cursor - 1]
                    + self.input_text[self.input_cursor:]
                )
                self.input_cursor -= 1
                self._draw_input()
                sys.stdout.flush()
            return None

        if ch == b"\x03":
            if not self.input_text:
                return ("exit", None)
            self.input_text = ""
            self.input_cursor = 0
            self._draw_input()
            sys.stdout.flush()
            return None

        if ch == b"\t":
            cmds = [
                "/ayuda", "/nueva", "/model", "/modelos", "/memoria",
                "/olvidar", "/buscar", "/run", "/voz", "/archivos",
                "/add", "/tokens", "/editor", "/multiline", "/status",
                "/gengar", "/tema", "/guardar", "/cargar", "/sesiones", "/salir",
            ]
            if self.input_text.startswith("/"):
                matches = [c for c in cmds if c.startswith(self.input_text)]
                if len(matches) == 1:
                    self.input_text = matches[0] + " "
                    self.input_cursor = len(self.input_text)
                    self._draw_input()
                    sys.stdout.flush()
                elif len(matches) > 1:
                    common = os.path.commonprefix(matches)
                    if common != self.input_text:
                        self.input_text = common
                        self.input_cursor = len(self.input_text)
                        self._draw_input()
                        sys.stdout.flush()
            return None

        try:
            char = ch.decode("utf-8")
        except UnicodeDecodeError:
            return None

        if char and char.isprintable():
            self.input_text = (
                self.input_text[:self.input_cursor]
                + char
                + self.input_text[self.input_cursor:]
            )
            self.input_cursor += 1
            self._draw_input()
            sys.stdout.flush()

        return None

    def check_resize(self):
        new_cols, new_rows = shutil.get_terminal_size()
        if new_cols != self.cols or new_rows != self.rows:
            self._update_size()
            sys.stdout.write("\033[2J")
            return True
        return False

    def cancel_pressed(self):
        while msvcrt.kbhit():
            if msvcrt.getch() == b"\x03":
                return True
        return False