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
        self._update_size()

    def _update_size(self):
        self.cols, self.rows = shutil.get_terminal_size()
        self.conv_rows = max(1, self.rows - 2)
        self.status_row = self.rows - 1
        self.input_row = self.rows

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

    def _draw_conversation(self):
        visible = self.conversation[-(self.conv_rows):]
        for i, line in enumerate(visible):
            row = i + 1
            self._gotoxy(row, 1)
            self._clear_line()
            sys.stdout.write(truncate_ansi(line, self.cols))
        # Clear remaining rows below conversation
        for r in range(len(visible) + 1, self.conv_rows + 1):
            self._gotoxy(r, 1)
            self._clear_line()

    def _draw_status(self):
        self._gotoxy(self.status_row, 1)
        self._clear_line()
        bar = (
            f"{self.theme.BG_STATUS}{self.theme.BOLD}{self.theme.PURPLE}"
            f" ARtenisa {self.theme.RESET}{self.theme.RESET_BG}"
            f" {self.theme.DIM}·{self.theme.RESET}"
            f" {self.theme.MUTED}{self.status_text}{self.theme.RESET}"
        )
        v = visible_len(bar)
        if v > self.cols:
            bar = truncate_ansi(bar, self.cols)
        elif v < self.cols:
            bar += " " * (self.cols - v)
        sys.stdout.write(bar)

    def _draw_input(self):
        self._gotoxy(self.input_row, 1)
        self._clear_line()
        prefix = f"  {self.theme.BORDER}┃{self.theme.RESET} {self.theme.TEXT}> {self.theme.RESET}"
        sys.stdout.write(prefix)
        avail = self.cols - visible_len(prefix)
        sys.stdout.write(self.input_text[:avail])
        # position cursor
        cx = visible_len(prefix + self.input_text[:self.input_cursor]) + 1
        self._gotoxy(self.input_row, min(cx, self.cols))

    def redraw(self):
        self._draw_conversation()
        self._draw_status()
        self._draw_input()
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
        visible = self.conversation[-(self.conv_rows):]
        row = len(visible)
        self._gotoxy(row, 1)
        self._clear_line()
        sys.stdout.write(truncate_ansi(text, self.cols))
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
                    cx = visible_len(f"  ┃ > {self.input_text[:self.input_cursor]}") + 1
                    self._gotoxy(self.input_row, min(cx, self.cols))
                    sys.stdout.flush()
            elif ch2 == b"M":
                if self.input_cursor < len(self.input_text):
                    self.input_cursor += 1
                    cx = visible_len(f"  ┃ > {self.input_text[:self.input_cursor]}") + 1
                    self._gotoxy(self.input_row, min(cx, self.cols))
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
            self.cols = new_cols
            self.rows = new_rows
            self.conv_rows = max(1, self.rows - 2)
            self.status_row = self.rows - 1
            self.input_row = self.rows
            return True
        return False

    def cancel_pressed(self):
        while msvcrt.kbhit():
            if msvcrt.getch() == b"\x03":
                return True
        return False
