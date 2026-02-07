"""
Human Text Editor (HTE)
Simulates realistic human typing into any application.
"""

import sys
import os
import re
import json
import random
import time
import threading
import difflib
import base64
import html
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QObject,
    QPoint,
    QRect,
    QSize,
    QTimer,
    Signal,
    QPropertyAnimation,
    QEasingCurve,
    Property,
    QUrl,
)
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QKeySequence,
    QPainter,
    QPen,
    QBrush,
    QColor,
    QPolygon,
    QIcon,
    QPixmap,
    QTextCursor,
    QTextCharFormat,
    QDesktopServices,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QStyle,
    QStyleOptionSpinBox,
    QVBoxLayout,
    QWidget,
    QWidgetItem,
)

import pyautogui

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.0

# Try to import keyboard for global hotkeys
_keyboard_available = False
try:
    import keyboard as _kb
    _keyboard_available = True
except Exception:
    _kb = None

# ---------------------------------------------------------------------------
# Paths & Icon
# ---------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _ASSETS = Path(sys._MEIPASS) / "assets"
else:
    _ASSETS = Path(__file__).resolve().parent / "assets"

_SETTINGS_FILE = Path(__file__).resolve().parent / "hte_settings.json"
_ICON_PATH = _ASSETS / "icon.ico"

# ---------------------------------------------------------------------------
# Catppuccin Mocha palette
# ---------------------------------------------------------------------------
BASE = "#1e1e2e"
MANTLE = "#181825"
CRUST = "#11111b"
SURFACE0 = "#313244"
SURFACE1 = "#45475a"
SURFACE2 = "#585b70"
OVERLAY0 = "#6c7086"
TEXT = "#cdd6f4"
SUBTEXT0 = "#a6adc8"
SUBTEXT1 = "#bac2de"
LAVENDER = "#b4befe"
BLUE = "#89b4fa"
SAPPHIRE = "#74c7ec"
GREEN = "#a6e3a1"
YELLOW = "#f9e2af"
PEACH = "#fab387"
MAROON = "#eba0ac"
RED = "#f38ba8"
MAUVE = "#cba6f7"
PINK = "#f5c2e7"
TEAL = "#94e2d5"
FLAMINGO = "#f2cdcd"

# ---------------------------------------------------------------------------
# Keyboard neighbor map (QWERTY layout – nearby keys for realistic typos)
# ---------------------------------------------------------------------------
_KEYBOARD_NEIGHBORS: dict[str, str] = {
    "q": "was", "w": "qeasd", "e": "wrsd", "r": "etdf", "t": "ryfg",
    "y": "tugh", "u": "yijh", "i": "uojk", "o": "iplk", "p": "ol",
    "a": "qwsz", "s": "wedazx", "d": "erfscx", "f": "rtgdcv",
    "g": "tyhfvb", "h": "yujgnb", "j": "uikhm", "k": "iojlm",
    "l": "opk", "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb",
    "b": "vghn", "n": "bhjm", "m": "njk",
    "1": "2q", "2": "13qw", "3": "24we", "4": "35er", "5": "46rt",
    "6": "57ty", "7": "68yu", "8": "79ui", "9": "80io", "0": "9op",
}

_COMMON_LETTERS = set("etaoinshrdlu")
_MEDIUM_LETTERS = set("cmfwypvbg")
_RARE_LETTERS = set("kjqxz")


def _nearby_key(ch: str) -> str:
    """Return a random neighboring key on a QWERTY keyboard."""
    lower = ch.lower()
    neighbors = _KEYBOARD_NEIGHBORS.get(lower, "")
    if not neighbors:
        # Fallback: pick a random letter
        neighbors = "abcdefghijklmnopqrstuvwxyz"
    picked = random.choice(neighbors)
    return picked.upper() if ch.isupper() else picked


def _iter_chars_with_word_len(text: str):
    """Yield (char, word_len) pairs, preserving word length for each char."""
    i = 0
    n = len(text)
    whitespace = {" ", "\n", "\t"}
    while i < n:
        ch = text[i]
        if ch in whitespace:
            yield ch, 0
            i += 1
            continue
        j = i
        while j < n and text[j] not in whitespace:
            j += 1
        word_len = j - i
        for k in range(i, j):
            yield text[k], word_len
        i = j


# ---------------------------------------------------------------------------
# Default hotkeys
# ---------------------------------------------------------------------------
DEFAULT_HOTKEYS = {
    "start": "F9",
    "pause": "F10",
    "skip": "F11",
    "stop": "F12",
}


# ---------------------------------------------------------------------------
# Settings persistence – saves EVERYTHING
# ---------------------------------------------------------------------------
def _load_settings() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text("utf-8"))
    except Exception:
        return {}


def _save_settings(data: dict):
    try:
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2), "utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Diff helpers – word-level diff between original and replacement text
# ---------------------------------------------------------------------------
@dataclass
class DiffOp:
    """A single diff operation."""
    kind: str  # "equal", "insert", "delete", "replace"
    old_text: str = ""
    new_text: str = ""


def _word_tokenize(text: str) -> list[str]:
    return re.findall(r'\S+|\s+', text)


def _compute_diff(original: str, replacement: str) -> list[DiffOp]:
    old_tokens = _word_tokenize(original)
    new_tokens = _word_tokenize(replacement)
    sm = difflib.SequenceMatcher(None, old_tokens, new_tokens)
    ops: list[DiffOp] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        old_chunk = "".join(old_tokens[i1:i2])
        new_chunk = "".join(new_tokens[j1:j2])
        if tag == "equal":
            ops.append(DiffOp(kind="equal", old_text=old_chunk, new_text=new_chunk))
        elif tag == "insert":
            ops.append(DiffOp(kind="insert", new_text=new_chunk))
        elif tag == "delete":
            ops.append(DiffOp(kind="delete", old_text=old_chunk))
        elif tag == "replace":
            ops.append(DiffOp(kind="replace", old_text=old_chunk, new_text=new_chunk))
    return ops


def _map_old_index_to_new_index(old_text: str, new_text: str, old_index: int) -> int:
    """Map an index in old_text to an approximate index in new_text."""
    if old_index <= 0:
        return 0
    if old_index >= len(old_text):
        return len(new_text)
    sm = difflib.SequenceMatcher(None, list(old_text), list(new_text))
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if i1 <= old_index < i2:
            if tag == "equal":
                return j1 + (old_index - i1)
            if tag == "replace":
                span_old = max(1, i2 - i1)
                span_new = max(0, j2 - j1)
                ratio = (old_index - i1) / span_old
                return j1 + int(round(ratio * span_new))
            if tag == "delete":
                return j1
    return len(new_text)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class TypingOptions:
    wpm: int = 65
    variability: float = 0.5
    typo_rate: float = 0.0
    start_delay: int = 3
    type_mode: str = "Human"


# ---------------------------------------------------------------------------
# Worker signals
# ---------------------------------------------------------------------------
class WorkerSignals(QObject):
    progress = Signal(int)
    char_typed = Signal(str)
    status = Signal(str)
    finished = Signal()
    log = Signal(str)
    cursor_pos = Signal(int)       # Current character position in text
    pause_info = Signal(int, str)  # Position + surrounding context snippet


# ---------------------------------------------------------------------------
# Typing worker (runs in background thread)
# ---------------------------------------------------------------------------
class TypingWorker:
    def __init__(self, text: str, options: TypingOptions, mode: str,
                 diff_ops: list[DiffOp] | None = None, start_pos: int = 0):
        self.text = text
        self.options = options
        self.mode = mode
        self.diff_ops = diff_ops or []
        self.signals = WorkerSignals()
        self._is_bot = (self.options.type_mode or "").lower() == "bot"
        self._stopped = False
        self._paused = False
        self._skip = False
        self._cursor_pos = 0
        self._start_pos = max(0, start_pos)
        self._pause_notified = False
        self._tempo = 1.0
        self._short_bias = 0
        self._long_bias = 0
        self._last_delay: float | None = None
        self._jump_to: int | None = None
        self._words_since_pause = 0
        self._thread: threading.Thread | None = None

    # -- control --
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stopped = True

    def pause(self):
        self._paused = not self._paused
        if self._paused:
            self._pause_notified = False

    def skip(self):
        self._skip = True

    def request_jump(self, pos: int):
        self._jump_to = max(0, pos)

    # -- interruptible sleep --
    def _sleep(self, seconds: float):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stopped:
                return
            if self._paused:
                self._handle_pause(self._cursor_pos)
            time.sleep(min(0.05, max(0, end - time.monotonic())))

    def _consume_jump(self) -> int | None:
        if self._jump_to is None:
            return None
        val = self._jump_to
        self._jump_to = None
        return val

    # -- compute delay from WPM + variability --
    def _char_complexity(self, ch: str | None, word_len: int | None) -> float:
        if not ch:
            return 1.0
        lower = ch.lower()
        factor = 1.0
        if lower in _RARE_LETTERS:
            factor += 0.25
        elif lower in _MEDIUM_LETTERS:
            factor += 0.12
        elif lower in _COMMON_LETTERS:
            factor -= 0.05
        if ch.isdigit() or ch in {"@", "#", "$", "%", "&", "*", "_"}:
            factor += 0.15
        if word_len:
            if word_len >= 12:
                factor += 0.25
            elif word_len >= 8:
                factor += 0.15
        return max(0.5, min(1.8, factor))

    def _update_tempo(self, base_delay: float, complexity: float) -> float:
        if base_delay <= 0:
            return 1.0
        if self._last_delay is not None:
            if self._last_delay < base_delay * 0.85:
                self._short_bias += 1
                self._long_bias = max(0, self._long_bias - 1)
            elif self._last_delay > base_delay * 1.15:
                self._long_bias += 1
                self._short_bias = max(0, self._short_bias - 1)
            else:
                self._short_bias = max(0, self._short_bias - 1)
                self._long_bias = max(0, self._long_bias - 1)

        drift = random.uniform(-0.04, 0.04)
        drift += 0.03 * self._short_bias
        drift -= 0.03 * self._long_bias
        self._tempo = max(0.5, min(1.5, self._tempo + drift))
        return max(0.5, min(1.5, self._tempo * complexity))

    def _char_delay(self, ch: str | None = None, word_len: int | None = None) -> float:
        if self._is_bot:
            return 0.0
        base = 60.0 / (self.options.wpm * 5.0)
        v = self.options.variability
        base_var = base * random.uniform(1.0 - v, 1.0 + v)
        complexity = self._char_complexity(ch, word_len)
        mult = self._update_tempo(base_var, complexity)
        delay = base_var * mult
        self._last_delay = delay
        return delay

    def _scaled_delay(self, seconds: float) -> float:
        if self._is_bot:
            return 0.0
        base = max(0.0, seconds)
        if base == 0:
            return 0.0
        mult = self._update_tempo(base, 1.0)
        delay = base * mult
        self._last_delay = delay
        return delay

    # -- type a single character via pyautogui --
    def _type_char(self, ch: str):
        if self._stopped:
            return
        if self._paused:
            self._handle_pause(self._cursor_pos)
            if self._stopped:
                return
        if ch == '"':
            pyautogui.keyDown("shift")
            pyautogui.press("'")
            pyautogui.keyUp("shift")
        elif ch == "'":
            pyautogui.press("'")
        elif ch == "\n":
            pyautogui.press("enter")
        elif ch == "\t":
            pyautogui.press("tab")
        else:
            try:
                pyautogui.write(ch, interval=0)
            except Exception:
                pyautogui.press(ch)

    def _is_sentence_end(self, ch: str) -> bool:
        """True for characters that end a sentence or paragraph."""
        return ch in {".", "!", "?", "\n"}

    def _thinking_pause(self, ch: str):
        """Insert a 'thinking pause' at sentence/paragraph boundaries.
        These pauses are NOT counted towards WPM timing."""
        if self._is_bot:
            return
        if not self._is_sentence_end(ch):
            return
        duration = random.uniform(0.5, 5.0)
        label = "end of paragraph" if ch == "\n" else f"'{ch}'"
        self.signals.log.emit(f"Thinking pause ({duration:.1f}s) at {label}")
        self.signals.status.emit("Thinking…")
        # Sleep without updating tempo bias so WPM stays unaffected
        saved_last = self._last_delay
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if self._stopped:
                return
            if self._paused:
                self._handle_pause(self._cursor_pos)
            time.sleep(min(0.05, max(0, end - time.monotonic())))
        self._last_delay = saved_last
        self.signals.status.emit("Typing…")

    def _maybe_word_pause(self):
        """Chance-based pauses between words (not counted towards WPM)."""
        if self._is_bot:
            return
        self._words_since_pause += 1
        chance = min(0.9, 0.07 + self._words_since_pause * 0.05)
        if random.random() > chance:
            return
        base = random.uniform(0.4, 1.1)
        scale = max(1, self._words_since_pause)
        duration = base * (1 + 0.35 * scale) + random.uniform(-0.2, 0.6)
        duration = max(0.5, min(6.0, duration))
        self.signals.log.emit(
            f"Word pause ({duration:.1f}s) after {self._words_since_pause} words"
        )
        self.signals.status.emit("Thinking…")
        saved_last = self._last_delay
        end = time.monotonic() + duration
        while time.monotonic() < end:
            if self._stopped:
                return
            if self._paused:
                self._handle_pause(self._cursor_pos)
            time.sleep(min(0.05, max(0, end - time.monotonic())))
        self._last_delay = saved_last
        self.signals.status.emit("Typing…")
        self._words_since_pause = 0

    def _emit_cursor(self, pos: int):
        self._cursor_pos = pos
        self.signals.cursor_pos.emit(pos)

    def _get_context_snippet(self, pos: int) -> str:
        """Get a ±20 char snippet around the cursor for logging."""
        text = self.text
        start = max(0, pos - 20)
        end = min(len(text), pos + 20)
        before = text[start:pos].replace("\n", "↵")
        after = text[pos:end].replace("\n", "↵")
        return f"…{before}▌{after}…"

    def _handle_pause(self, pos: int):
        """Block while paused, emit position info."""
        if self._paused and not self._pause_notified:
            snippet = self._get_context_snippet(pos)
            self.signals.pause_info.emit(pos, snippet)
            self.signals.status.emit("Paused")
            self._pause_notified = True
        while self._paused and not self._stopped:
            time.sleep(0.05)

    # -- main run loop --
    def _run(self):
        try:
            for i in range(self.options.start_delay, 0, -1):
                if self._stopped:
                    self.signals.finished.emit()
                    return
                self.signals.status.emit(f"Starting in {i}…")
                self._sleep(1)
            self.signals.status.emit("Typing…")

            if self.mode == "replace" and self.diff_ops:
                self._run_replace()
            else:
                self._run_fresh()

            self.signals.status.emit("Done" if not self._stopped else "Stopped")
            self.signals.log.emit("Typing finished." if not self._stopped else "Typing stopped.")
        except Exception as exc:
            self.signals.status.emit(f"Error: {exc}")
            self.signals.log.emit(f"Error: {exc}")
        finally:
            self.signals.finished.emit()

    # -------------------------------------------------------------------
    # FRESH TYPE – realistic typos with keyboard-neighbor errors
    # -------------------------------------------------------------------
    def _run_fresh(self):
        text = self.text
        total = len(text)
        idx = min(self._start_pos, total)
        done = idx
        if total:
            self._emit_cursor(idx)
            self.signals.progress.emit(int(done / total * 100))

        whitespace = {" ", "\n", "\t"}
        current_word_len = 0
        remaining_in_word = 0
        prev_was_word = False

        while idx < total:
            if self._stopped:
                break

            # Skip – fast type remainder
            if self._skip:
                self._skip = False
                for rc in text[idx:]:
                    if self._paused:
                        self._handle_pause(idx)
                        if self._stopped:
                            break
                    self._type_char(rc)
                    done += 1
                self._emit_cursor(total)
                self.signals.progress.emit(100)
                break

            jump = self._consume_jump()
            if jump is not None:
                idx = min(jump, total)
                done = idx
                prev_was_word = False
                self._words_since_pause = 0
                self._emit_cursor(idx)
                self.signals.progress.emit(int(done / total * 100) if total else 100)
                continue

            self._handle_pause(idx)
            if self._stopped:
                break
            self.signals.status.emit("Typing…")

            ch = text[idx]
            if ch in whitespace:
                current_word_len = 0
                remaining_in_word = 0
                word_len = 0
            else:
                if idx == 0 or text[idx - 1] in whitespace or remaining_in_word <= 0:
                    word_end = idx
                    while word_end < total and text[word_end] not in whitespace:
                        word_end += 1
                    current_word_len = word_end - idx
                    remaining_in_word = current_word_len
                word_len = current_word_len
                remaining_in_word = max(0, remaining_in_word - 1)

            # --- Typo simulation (realistic) ---
            if (not self._is_bot and self.options.typo_rate > 0
                    and ch.isalpha()
                    and random.random() < self.options.typo_rate / 100):
                # Find the end of the current word
                word_end = idx
                while word_end < total and text[word_end] not in whitespace:
                    word_end += 1
                word_len = word_end - idx

                # Type the wrong letter now
                wrong = _nearby_key(ch)
                self._type_char(wrong)
                self.signals.log.emit(f"Typo at pos {idx}: '{ch}' → '{wrong}'")

                # Continue typing the rest of the word normally
                chars_after_typo = 0
                for j in range(idx + 1, word_end):
                    if self._stopped:
                        break
                    self._type_char(text[j])
                    chars_after_typo += 1
                    self._sleep(self._char_delay(text[j], word_len))

                if self._stopped:
                    break

                # Pause to "notice" the mistake (~1 second)
                self._sleep(self._scaled_delay(random.uniform(0.5, 2.0)))

                # Backspace from the end of the word to the typo position
                backspaces_needed = chars_after_typo + 1  # +1 for the wrong char
                for _ in range(backspaces_needed):
                    if self._stopped:
                        break
                    pyautogui.press("backspace")
                    self._sleep(self._scaled_delay(random.uniform(0.04, 0.2)))

                if self._stopped:
                    break

                # Pause to "find" the correct letter (~1 second)
                self._sleep(self._scaled_delay(random.uniform(0.5, 2.0)))

                # Now retype from the typo position to word end correctly
                for j in range(idx, word_end):
                    if self._stopped:
                        break
                    self._type_char(text[j])
                    done += 1
                    self._emit_cursor(j + 1)
                    self.signals.progress.emit(int(done / total * 100))
                    self._sleep(self._char_delay(text[j], word_len))

                idx = word_end
                continue

            # --- Normal character ---
            self._type_char(ch)
            done += 1
            idx += 1
            self._emit_cursor(idx)
            self.signals.char_typed.emit(ch)
            self.signals.progress.emit(int(done / total * 100) if total else 100)

            delay = self._char_delay(ch, word_len)
            self._sleep(delay)

            # Thinking pause at sentence / paragraph boundaries
            self._thinking_pause(ch)

            # Word pause after word boundaries (space/tab/newline)
            if ch in {" ", "\t", "\n"} and prev_was_word:
                self._maybe_word_pause()

            prev_was_word = ch not in whitespace

    def _op_work(self, op: DiffOp) -> int:
        if op.kind == "equal":
            return len(op.new_text)
        if op.kind == "insert":
            return len(op.new_text)
        if op.kind == "delete":
            return len(op.old_text)
        if op.kind == "replace":
            return len(op.old_text) + len(op.new_text)
        return 0

    def _trim_ops_for_start(self, start_pos: int) -> tuple[list[DiffOp], int]:
        """Trim diff ops so processing starts from start_pos in original text.
        Returns (trimmed_ops, skipped_work)."""
        if start_pos <= 0:
            return list(self.diff_ops), 0
        trimmed: list[DiffOp] = []
        skipped_work = 0
        cursor = 0
        ops = self.diff_ops
        i = 0
        while i < len(ops):
            op = ops[i]
            old_len = len(op.old_text) if op.kind in ("equal", "delete", "replace") else 0

            if cursor + old_len <= start_pos:
                skipped_work += self._op_work(op)
                cursor += old_len
                i += 1
                continue

            if start_pos <= cursor:
                trimmed.extend(ops[i:])
                break

            offset = start_pos - cursor
            if op.kind == "equal":
                skipped_work += offset
                trimmed.append(
                    DiffOp(kind="equal", old_text=op.old_text[offset:], new_text=op.new_text[offset:])
                )
            elif op.kind == "delete":
                skipped_work += offset
                trimmed.append(DiffOp(kind="delete", old_text=op.old_text[offset:]))
            elif op.kind == "replace":
                new_offset = _map_old_index_to_new_index(op.old_text, op.new_text, offset)
                skipped_work += offset + new_offset
                trimmed.append(
                    DiffOp(kind="replace", old_text=op.old_text[offset:], new_text=op.new_text[new_offset:])
                )
            elif op.kind == "insert":
                skipped_work += len(op.new_text)
            trimmed.extend(ops[i + 1:])
            break

        return trimmed, skipped_work

    # -------------------------------------------------------------------
    # REPLACE TYPE – diff-based editing with position tracking
    # -------------------------------------------------------------------
    def _run_replace(self):
        total_work = sum(self._op_work(op) for op in self.diff_ops) or 1
        total_old_len = sum(
            len(op.old_text) for op in self.diff_ops if op.kind in ("equal", "delete", "replace")
        )
        start_pos = min(self._start_pos, total_old_len)
        whitespace = {" ", "\n", "\t"}
        prev_was_word = False

        while True:
            jump = self._consume_jump()
            if jump is not None:
                start_pos = min(jump, total_old_len)
                prev_was_word = False
                self._words_since_pause = 0

            ops, skipped_work = self._trim_ops_for_start(start_pos)
            done = skipped_work
            cursor_in_original = start_pos
            self._emit_cursor(cursor_in_original)
            self.signals.progress.emit(int(done / total_work * 100))

            last_change_idx = -1
            for i, op in enumerate(ops):
                if op.kind != "equal" and (op.old_text or op.new_text):
                    last_change_idx = i

            if last_change_idx == -1:
                self.signals.progress.emit(100)
                self.signals.log.emit("No changes detected. Ending early.")
                return
            is_bot = self._is_bot
            use_select = not is_bot

            restart = False
            for i, op in enumerate(ops):
                if self._stopped:
                    break

                if self._skip:
                    self._skip = False
                    self.signals.progress.emit(100)
                    self._emit_cursor(len(self.text))
                    break

                if self._jump_to is not None:
                    restart = True
                    break

                self._handle_pause(cursor_in_original)
                if self._stopped:
                    break
                self.signals.status.emit("Typing…")

                if op.kind == "equal":
                    if is_bot:
                        n = len(op.new_text)
                        if n:
                            if self._jump_to is not None:
                                restart = True
                            elif self._paused:
                                self._handle_pause(cursor_in_original)
                            if not restart and not self._stopped:
                                pyautogui.press("right", presses=n, interval=0)
                                cursor_in_original += n
                                done += n
                                self._emit_cursor(cursor_in_original)
                                self.signals.progress.emit(int(done / total_work * 100))
                        if restart or self._stopped:
                            break
                    else:
                        for ch, word_len in _iter_chars_with_word_len(op.new_text):
                            if self._stopped:
                                break
                            if self._jump_to is not None:
                                restart = True
                                break
                            if self._paused:
                                self._handle_pause(cursor_in_original)
                                if self._stopped:
                                    break
                            pyautogui.press("right")
                            cursor_in_original += 1
                            done += 1
                            self._emit_cursor(cursor_in_original)
                            self.signals.progress.emit(int(done / total_work * 100))
                            delay = self._char_delay(ch, word_len) * 0.3
                            self._last_delay = delay
                            self._sleep(delay)
                            self._thinking_pause(ch)
                            if ch in {" ", "\t", "\n"} and prev_was_word:
                                self._maybe_word_pause()
                            prev_was_word = ch not in whitespace
                        if restart:
                            break

                elif op.kind == "delete":
                    n = len(op.old_text)
                    if is_bot:
                        if n:
                            pyautogui.press("delete", presses=n, interval=0)
                    elif use_select:
                        for _ in range(n):
                            if self._stopped:
                                break
                            if self._jump_to is not None:
                                restart = True
                                break
                            if self._paused:
                                self._handle_pause(cursor_in_original)
                                if self._stopped:
                                    break
                            pyautogui.hotkey("shift", "right")
                            self._sleep(self._scaled_delay(0.04))
                        pyautogui.press("delete")
                    else:
                        for _ in range(n):
                            if self._stopped:
                                break
                            if self._jump_to is not None:
                                restart = True
                                break
                            if self._paused:
                                self._handle_pause(cursor_in_original)
                                if self._stopped:
                                    break
                            pyautogui.press("delete")
                            self._sleep(self._scaled_delay(0.06))
                    done += n
                    self._emit_cursor(cursor_in_original)
                    self.signals.progress.emit(int(done / total_work * 100))
                    self.signals.log.emit(f"Deleted: '{op.old_text[:30]}'")
                    if restart:
                        break

                elif op.kind == "insert":
                    for ch, word_len in _iter_chars_with_word_len(op.new_text):
                        if self._stopped:
                            break
                        if self._jump_to is not None:
                            restart = True
                            break
                        if self._paused:
                            self._handle_pause(cursor_in_original)
                            if self._stopped:
                                break
                        self._type_char(ch)
                        done += 1
                        self._emit_cursor(cursor_in_original)
                        self.signals.progress.emit(int(done / total_work * 100))
                        self._sleep(self._char_delay(ch, word_len))
                        self._thinking_pause(ch)
                        if ch in {" ", "\t", "\n"} and prev_was_word:
                            self._maybe_word_pause()
                        prev_was_word = ch not in whitespace
                    self.signals.log.emit(f"Inserted: '{op.new_text[:30]}'")
                    if restart:
                        break

                elif op.kind == "replace":
                    n_del = len(op.old_text)
                    if is_bot:
                        if n_del:
                            pyautogui.press("delete", presses=n_del, interval=0)
                    elif use_select:
                        for _ in range(n_del):
                            if self._stopped:
                                break
                            if self._jump_to is not None:
                                restart = True
                                break
                            if self._paused:
                                self._handle_pause(cursor_in_original)
                                if self._stopped:
                                    break
                            pyautogui.hotkey("shift", "right")
                            self._sleep(self._scaled_delay(0.04))
                    else:
                        for _ in range(n_del):
                            if self._stopped:
                                break
                            if self._jump_to is not None:
                                restart = True
                                break
                            if self._paused:
                                self._handle_pause(cursor_in_original)
                                if self._stopped:
                                    break
                            pyautogui.press("delete")
                            self._sleep(self._scaled_delay(0.06))
                    done += n_del

                    for ch, word_len in _iter_chars_with_word_len(op.new_text):
                        if self._stopped:
                            break
                        if self._jump_to is not None:
                            restart = True
                            break
                        if self._paused:
                            self._handle_pause(cursor_in_original)
                            if self._stopped:
                                break
                        self._type_char(ch)
                        done += 1
                        self._emit_cursor(cursor_in_original)
                        self.signals.progress.emit(int(done / total_work * 100))
                        self._sleep(self._char_delay(ch, word_len))
                        self._thinking_pause(ch)
                        if ch in {" ", "\t", "\n"} and prev_was_word:
                            self._maybe_word_pause()
                        prev_was_word = ch not in whitespace
                    self.signals.log.emit(
                        f"Replaced: '{op.old_text[:20]}' → '{op.new_text[:20]}'"
                    )
                    if restart:
                        break

                if i >= last_change_idx:
                    break

            if self._stopped or not restart:
                break


# ---------------------------------------------------------------------------
# Cursor overlay widget – animated blinking bar drawn on top of QPlainTextEdit
# ---------------------------------------------------------------------------
class CursorOverlay(QWidget):
    """Draws a blinking cursor bar at a given character position
    inside a QPlainTextEdit."""

    def __init__(self, text_edit: QPlainTextEdit):
        super().__init__(text_edit.viewport())
        self._text_edit = text_edit
        self._char_pos = 0
        self._visible = False
        self._blink_on = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Blink timer
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(530)
        self._blink_timer.timeout.connect(self._toggle_blink)

        self.hide()

    def start(self, pos: int = 0):
        self._char_pos = pos
        self._visible = True
        self._blink_on = True
        self._blink_timer.start()
        self.show()
        self._reposition()

    def stop(self):
        self._visible = False
        self._blink_timer.stop()
        self.hide()

    def set_position(self, pos: int):
        self._char_pos = pos
        self._blink_on = True
        self._reposition()

    def _toggle_blink(self):
        self._blink_on = not self._blink_on
        self.update()

    def _reposition(self):
        te = self._text_edit
        doc = te.document()
        text_len = doc.characterCount() - 1  # doc adds trailing \n
        pos = min(self._char_pos, max(0, text_len))

        cursor = QTextCursor(doc)
        cursor.setPosition(pos)
        rect = te.cursorRect(cursor)

        # Scroll the text edit so the cursor is visible
        te.setTextCursor(cursor)
        te.ensureCursorVisible()

        # Place overlay to cover entire viewport
        vp = te.viewport()
        self.setGeometry(0, 0, vp.width(), vp.height())
        self._cursor_rect = rect
        self.update()

    def paintEvent(self, event):
        if not self._visible or not self._blink_on:
            return
        if not hasattr(self, "_cursor_rect"):
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(BLUE)
        color.setAlpha(220)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        r = self._cursor_rect
        painter.drawRect(r.x(), r.y(), 2, r.height())
        painter.end()


# ---------------------------------------------------------------------------
# Flow layout
# ---------------------------------------------------------------------------
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=4, spacing=4):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QLayoutItem):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for item in self._items:
            s = s.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        s += QSize(m.left() + m.right(), m.top() + m.bottom())
        return s

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        row_h = 0
        for item in self._items:
            sz = item.sizeHint()
            next_x = x + sz.width() + self._spacing
            if next_x - self._spacing > effective.right() and row_h > 0:
                x = effective.x()
                y += row_h + self._spacing
                next_x = x + sz.width() + self._spacing
                row_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), sz))
            x = next_x
            row_h = max(row_h, sz.height())
        return y + row_h - rect.y() + m.bottom()


# ---------------------------------------------------------------------------
# Hotkey configuration dialog
# ---------------------------------------------------------------------------
class HotkeyDialog(QDialog):
    def __init__(self, current: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Hotkeys – HTE")
        self.setFixedSize(380, 320)
        if _ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(_ICON_PATH)))
        self.setStyleSheet(f"""
            QDialog {{ background: {BASE}; color: {TEXT}; }}
            QLabel {{ color: {TEXT}; font-size: 13px; }}
            QPushButton {{
                background: {SURFACE0}; color: {TEXT};
                border: 1px solid {SURFACE1}; border-radius: 6px;
                padding: 6px 14px; font-size: 13px;
            }}
            QPushButton:hover {{ background: {SURFACE1}; }}
            QPushButton:focus {{ border-color: {LAVENDER}; }}
        """)

        self.hotkeys = dict(current)
        self._active_button: QPushButton | None = None
        self._active_action: str | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("Press a button, then press the desired key(s).")
        title.setWordWrap(True)
        title.setStyleSheet(f"color: {SUBTEXT0}; font-size: 12px; margin-bottom: 4px;")
        layout.addWidget(title)

        self._buttons: dict[str, QPushButton] = {}
        for action in ("start", "pause", "skip", "stop"):
            row = QHBoxLayout()
            lbl = QLabel(f"{action.capitalize()}:")
            lbl.setFixedWidth(60)
            btn = QPushButton(self.hotkeys.get(action, DEFAULT_HOTKEYS[action]))
            btn.setFixedHeight(32)
            btn.clicked.connect(lambda checked=False, a=action, b=btn: self._begin_capture(a, b))
            self._buttons[action] = btn
            row.addWidget(lbl)
            row.addWidget(btn)
            layout.addLayout(row)

        layout.addStretch()

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset Defaults")
        reset_btn.clicked.connect(self._reset)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setStyleSheet(f"background: {BLUE}; color: {CRUST}; font-weight: bold;")
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _begin_capture(self, action: str, btn: QPushButton):
        if self._active_button and self._active_button is not btn:
            self._active_button.setText(self.hotkeys.get(self._active_action, ""))
        self._active_action = action
        self._active_button = btn
        btn.setText("Press a key…")
        btn.setStyleSheet(
            f"background: {SURFACE1}; color: {YELLOW}; border: 1px solid {YELLOW}; "
            f"border-radius: 6px; padding: 6px 14px; font-size: 13px;"
        )
        btn.setFocus()

    def keyPressEvent(self, event):
        if self._active_button is None:
            return super().keyPressEvent(event)
        mods = event.modifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift,
                   Qt.Key.Key_Meta, Qt.Key.Key_AltGr):
            return
        key_name = QKeySequence(key).toString()
        if key_name:
            parts.append(key_name)
        combo = "+".join(parts) if parts else "Unknown"
        self.hotkeys[self._active_action] = combo
        self._active_button.setText(combo)
        self._active_button.setStyleSheet(
            f"background: {SURFACE0}; color: {TEXT}; border: 1px solid {SURFACE1}; "
            f"border-radius: 6px; padding: 6px 14px; font-size: 13px;"
        )
        self._active_button = None
        self._active_action = None

    def _reset(self):
        self.hotkeys = dict(DEFAULT_HOTKEYS)
        for action, btn in self._buttons.items():
            btn.setText(DEFAULT_HOTKEYS[action])


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class HumanTextEditor(QMainWindow):
    """Human Text Editor – simulates realistic typing."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Human Text Editor (HTE)")
        if _ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(_ICON_PATH)))
        self.resize(900, 640)

        self._worker: TypingWorker | None = None
        self._hotkey_hooks: list = []
        self._manual_start_pos_fresh = 0
        self._manual_start_pos_replace = 0

        # Load ALL settings
        self._settings = _load_settings()
        self._hotkeys = self._settings.get("hotkeys", dict(DEFAULT_HOTKEYS))
        self._settings_expanded = self._settings.get("settings_expanded", True)

        self._build_ui()
        self._apply_styles()
        self._restore_settings()
        self._register_global_hotkeys()

        # Auto-save timer – saves settings periodically and on text changes
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(2000)
        self._save_timer.timeout.connect(self._persist_all)
        self._save_timer.start()

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # === TOP BAR ===
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        self._info_btn = QPushButton("ℹ")
        self._info_btn.setObjectName("infoBtn")
        self._info_btn.setFixedSize(28, 28)
        self._info_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._info_btn.setToolTip("Configure hotkeys")
        self._info_btn.clicked.connect(self._on_info)

        self._support_btn = self._make_button("❤ Support", PINK, self._on_support)
        self._support_btn.setFixedHeight(28)
        self._support_btn.setToolTip("Support me on GitHub Sponsors")

        self._start_btn = self._make_button("▶ Start", GREEN, self._on_start)
        self._pause_btn = self._make_button("⏸ Pause", YELLOW, self._on_pause)
        self._stop_btn = self._make_button("⏹ Stop", RED, self._on_stop)
        self._skip_btn = self._make_button("⏭ Skip", BLUE, self._on_skip)

        self._mode_label = QLabel("Mode:")
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Fresh Type", "Replace Type"])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_change)
        self._mode_combo.setFixedHeight(30)

        top_bar.addWidget(self._info_btn)
        top_bar.addWidget(self._start_btn)
        top_bar.addWidget(self._pause_btn)
        top_bar.addWidget(self._stop_btn)
        top_bar.addWidget(self._skip_btn)
        top_bar.addStretch()
        top_bar.addWidget(self._support_btn)
        root.addLayout(top_bar)

        # === PROGRESS BAR ===
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(14)
        self._progress_bar.setTextVisible(False)
        root.addWidget(self._progress_bar)

        # === COLLAPSIBLE SETTINGS ===
        self._settings_toggle = QPushButton("▼ Settings")
        self._settings_toggle.setObjectName("settingsToggle")
        self._settings_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_toggle.setFixedHeight(26)
        self._settings_toggle.clicked.connect(self._toggle_settings)
        root.addWidget(self._settings_toggle)

        self._settings_widget = QWidget()
        settings_layout = QHBoxLayout(self._settings_widget)
        settings_layout.setContentsMargins(4, 4, 4, 4)
        settings_layout.setSpacing(12)

        self._wpm_spin = QSpinBox()
        self._wpm_spin.setRange(10, 500)
        self._wpm_spin.setValue(65)
        self._wpm_spin.setSuffix(" wpm")
        self._wpm_spin.setFixedHeight(28)
        self._wpm_spin.setFixedWidth(100)

        self._variability_spin = QDoubleSpinBox()
        self._variability_spin.setRange(0.0, 1.0)
        self._variability_spin.setValue(0.30)
        self._variability_spin.setSingleStep(0.05)
        self._variability_spin.setDecimals(2)
        self._variability_spin.setFixedHeight(28)
        self._variability_spin.setFixedWidth(80)

        self._typo_spin = QDoubleSpinBox()
        self._typo_spin.setRange(0.0, 50.0)
        self._typo_spin.setValue(0.0)
        self._typo_spin.setSuffix("%")
        self._typo_spin.setSingleStep(0.5)
        self._typo_spin.setDecimals(1)
        self._typo_spin.setFixedHeight(28)
        self._typo_spin.setFixedWidth(80)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["Human", "Bot"])
        self._type_combo.setFixedHeight(28)

        self._countdown_spin = QSpinBox()
        self._countdown_spin.setRange(0, 30)
        self._countdown_spin.setValue(3)
        self._countdown_spin.setSuffix(" s")
        self._countdown_spin.setFixedHeight(28)
        self._countdown_spin.setFixedWidth(70)

        for label_text, widget in [
            ("WPM:", self._wpm_spin),
            ("Variability:", self._variability_spin),
            ("Typo %:", self._typo_spin),
            ("Type:", self._type_combo),
            ("Countdown:", self._countdown_spin),
            ("Mode:", self._mode_combo),
        ]:
            settings_layout.addWidget(QLabel(label_text))
            settings_layout.addWidget(widget)

        settings_layout.addStretch()
        root.addWidget(self._settings_widget)

        self._settings_widget.setVisible(self._settings_expanded)
        self._settings_toggle.setText(
            "▼ Settings" if self._settings_expanded else "▶ Settings"
        )

        # === FRESH TYPE: single text area ===
        self._fresh_group = QGroupBox("Your Text")
        fresh_lay = QVBoxLayout(self._fresh_group)
        fresh_lay.setContentsMargins(6, 6, 6, 6)
        self._your_text = QPlainTextEdit()
        self._your_text.setPlaceholderText("Type or paste the text you want the app to type out…")
        self._your_text.cursorPositionChanged.connect(self._on_fresh_cursor_moved)
        fresh_lay.addWidget(self._your_text)
        root.addWidget(self._fresh_group, 1)

        # Create cursor overlay for the Your Text box
        self._fresh_cursor = CursorOverlay(self._your_text)

        # === REPLACE TYPE ===
        self._replace_widget = QWidget()
        replace_root = QVBoxLayout(self._replace_widget)
        replace_root.setContentsMargins(0, 0, 0, 0)
        replace_root.setSpacing(6)

        self._replace_splitter = QSplitter(Qt.Orientation.Horizontal)

        orig_group = QGroupBox("Original Text")
        orig_lay = QVBoxLayout(orig_group)
        orig_lay.setContentsMargins(6, 6, 6, 6)
        self._original_text = QPlainTextEdit()
        self._original_text.setPlaceholderText("Paste the original text here…")
        self._original_text.cursorPositionChanged.connect(self._on_original_cursor_moved)
        orig_lay.addWidget(self._original_text)
        self._replace_splitter.addWidget(orig_group)

        repl_group = QGroupBox("Replacement Text")
        repl_lay = QVBoxLayout(repl_group)
        repl_lay.setContentsMargins(6, 6, 6, 6)
        self._replacement_text = QPlainTextEdit()
        self._replacement_text.setPlaceholderText("Paste the replacement / new version here…")
        repl_lay.addWidget(self._replacement_text)
        self._replace_splitter.addWidget(repl_group)

        self._replace_splitter.setStretchFactor(0, 1)
        self._replace_splitter.setStretchFactor(1, 1)
        replace_root.addWidget(self._replace_splitter, 1)

        # Cursor overlay for original text
        self._orig_cursor = CursorOverlay(self._original_text)

        # Diff preview
        self._diff_group = QGroupBox("Diff Preview")
        diff_lay = QVBoxLayout(self._diff_group)
        diff_lay.setContentsMargins(6, 6, 6, 6)
        self._diff_view = QTextEdit()
        self._diff_view.setReadOnly(True)
        self._diff_view.setAcceptRichText(True)
        self._diff_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._diff_view.setFixedHeight(140)
        diff_lay.addWidget(self._diff_view)

        self._preview_btn = QPushButton("Preview Diff")
        self._preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._preview_btn.clicked.connect(self._build_diff_preview)
        diff_lay.addWidget(self._preview_btn)

        replace_root.addWidget(self._diff_group)

        self._replace_widget.setVisible(False)
        root.addWidget(self._replace_widget, 1)

        # === ACTIVITY LOG ===
        self._log_toggle = QPushButton("▼ Activity Log")
        self._log_toggle.setObjectName("settingsToggle")
        self._log_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._log_toggle.setFixedHeight(26)
        self._log_toggle.clicked.connect(self._toggle_log)
        root.addWidget(self._log_toggle)

        self._log_widget = QWidget()
        log_inner = QVBoxLayout(self._log_widget)
        log_inner.setContentsMargins(0, 0, 0, 0)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setFixedHeight(120)
        log_inner.addWidget(self._log)
        root.addWidget(self._log_widget)
        self._log_visible = True

        # === STATUS BAR ===
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("Ready")
        self._status_bar.addWidget(self._status_label, 1)

        self._on_mode_change(0)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def _make_button(self, text, color, slot):
        btn = QPushButton(text)
        btn.setFixedHeight(30)
        btn.setMinimumWidth(80)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        btn.setProperty("accent", color)
        return btn

    def _reset_cursors_to_start(self):
        cursor = self._your_text.textCursor()
        cursor.setPosition(0)
        self._your_text.setTextCursor(cursor)

        cursor = self._original_text.textCursor()
        cursor.setPosition(0)
        self._original_text.setTextCursor(cursor)

        self._manual_start_pos_fresh = 0
        self._manual_start_pos_replace = 0
        self._progress_bar.setValue(0)
        self._status_label.setText("Ready")
        self._fresh_cursor.set_position(0)
        self._orig_cursor.set_position(0)

    def _update_manual_progress(self, pos: int, total: int, label: str):
        if self._worker and not self._worker._paused:
            return
        total = max(1, total)
        pos = max(0, min(pos, total))
        pct = int(pos / total * 100)
        self._progress_bar.setValue(pct)
        self._status_label.setText(f"{label} cursor at {pos}/{total} ({pct}%)")

    def _on_fresh_cursor_moved(self):
        pos = self._your_text.textCursor().position()
        self._manual_start_pos_fresh = pos
        # If worker is paused, update its internal position so resume starts here
        if self._worker and self._worker._paused and self._worker.mode == "fresh":
            self._worker._cursor_pos = pos
            self._worker._start_pos = pos
            self._worker.request_jump(pos)
        self._fresh_cursor.set_position(pos)
        self._update_manual_progress(pos, len(self._your_text.toPlainText()), "Fresh")

    def _on_original_cursor_moved(self):
        pos = self._original_text.textCursor().position()
        self._manual_start_pos_replace = pos
        # If worker is paused, update its internal position so resume starts here
        if self._worker and self._worker._paused and self._worker.mode == "replace":
            self._worker._cursor_pos = pos
            self._worker._start_pos = pos
            self._worker.request_jump(pos)
        self._orig_cursor.set_position(pos)
        self._update_manual_progress(pos, len(self._original_text.toPlainText()), "Replace")

    # -----------------------------------------------------------------------
    # Settings persistence – save & restore everything
    # -----------------------------------------------------------------------
    def _persist_all(self):
        """Save all widget states + text contents to JSON."""
        self._settings["hotkeys"] = self._hotkeys
        self._settings["settings_expanded"] = self._settings_expanded
        self._settings["mode"] = self._mode_combo.currentIndex()
        self._settings["wpm"] = self._wpm_spin.value()
        self._settings["variability"] = self._variability_spin.value()
        self._settings["typo_rate"] = self._typo_spin.value()
        self._settings["type_mode"] = self._type_combo.currentText()
        self._settings.pop("edit_style", None)
        self._settings["countdown"] = self._countdown_spin.value()
        self._settings["your_text"] = self._your_text.toPlainText()
        self._settings["original_text"] = self._original_text.toPlainText()
        self._settings["replacement_text"] = self._replacement_text.toPlainText()
        _save_settings(self._settings)

    def _restore_settings(self):
        """Restore all widget states from loaded settings."""
        s = self._settings
        self._mode_combo.setCurrentIndex(s.get("mode", 0))
        self._wpm_spin.setValue(s.get("wpm", 65))
        self._variability_spin.setValue(s.get("variability", 0.30))
        self._typo_spin.setValue(s.get("typo_rate", 0.0))
        type_value = s.get("type_mode") or s.get("type") or "Human"
        idx = self._type_combo.findText(type_value)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        self._countdown_spin.setValue(s.get("countdown", 3))
        self._your_text.setPlainText(s.get("your_text", ""))
        self._original_text.setPlainText(s.get("original_text", ""))
        self._replacement_text.setPlainText(s.get("replacement_text", ""))

    # -----------------------------------------------------------------------
    # Styling
    # -----------------------------------------------------------------------
    def _apply_styles(self):
        up_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
            f'<polygon points="5,2 9,8 1,8" fill="{TEXT}"/>'
            "</svg>"
        )
        down_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
            f'<polygon points="5,8 9,2 1,2" fill="{TEXT}"/>'
            "</svg>"
        )
        up_b64 = base64.b64encode(up_svg.encode()).decode()
        dn_b64 = base64.b64encode(down_svg.encode()).decode()
        up_uri = f"data:image/svg+xml;base64,{up_b64}"
        dn_uri = f"data:image/svg+xml;base64,{dn_b64}"

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {BASE}; color: {TEXT};
                font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px;
            }}
            QGroupBox {{
                border: 1px solid {SURFACE1}; border-radius: 8px;
                margin-top: 14px; padding: 10px 6px 6px 6px;
                color: {TEXT}; font-weight: bold;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 2px 8px;
            }}
            QPlainTextEdit, QTextEdit {{
                background: {MANTLE}; color: {TEXT};
                border: 1px solid {SURFACE0}; border-radius: 6px; padding: 6px;
                font-family: "Cascadia Code", "Consolas", monospace; font-size: 13px;
                selection-background-color: {SURFACE1};
            }}
            QScrollArea {{
                background: {MANTLE}; border: 1px solid {SURFACE0}; border-radius: 6px;
            }}
            QLabel {{
                color: {SUBTEXT1}; font-size: 12px; background: transparent;
            }}
            QComboBox {{
                background: {SURFACE0}; color: {TEXT};
                border: 1px solid {SURFACE1}; border-radius: 6px;
                padding: 4px 10px; min-width: 120px;
            }}
            QComboBox::drop-down {{ border: none; width: 20px; }}
            QComboBox QAbstractItemView {{
                background: {SURFACE0}; color: {TEXT};
                selection-background-color: {SURFACE1}; border: 1px solid {SURFACE1};
            }}
            QSpinBox, QDoubleSpinBox {{
                background: {SURFACE0}; color: {TEXT};
                border: 1px solid {SURFACE1}; border-radius: 6px;
                padding: 2px 4px; font-size: 12px;
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button {{
                subcontrol-origin: border; subcontrol-position: top right;
                width: 18px; border: none;
                border-left: 1px solid {SURFACE1}; border-top-right-radius: 6px;
                image: url("{up_uri}");
            }}
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                subcontrol-origin: border; subcontrol-position: bottom right;
                width: 18px; border: none;
                border-left: 1px solid {SURFACE1}; border-bottom-right-radius: 6px;
                image: url("{dn_uri}");
            }}
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
                background: {SURFACE1};
            }}
            QProgressBar {{
                background: {SURFACE0}; border: 1px solid {SURFACE1};
                border-radius: 7px; text-align: center;
            }}
            QProgressBar::chunk {{
                background: {BLUE}; border-radius: 6px;
            }}
            QPushButton {{
                background: {SURFACE0}; color: {TEXT};
                border: 1px solid {SURFACE1}; border-radius: 6px;
                padding: 5px 14px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {SURFACE1}; }}
            QPushButton:pressed {{ background: {SURFACE2}; }}
            QPushButton#infoBtn {{
                background: {SURFACE0}; color: {LAVENDER};
                border: 1px solid {SURFACE1}; border-radius: 14px;
                font-size: 14px; font-weight: bold; padding: 0px;
            }}
            QPushButton#infoBtn:hover {{
                background: {SURFACE1}; border-color: {LAVENDER};
            }}
            QPushButton#settingsToggle {{
                background: {MANTLE}; color: {SUBTEXT0};
                border: 1px solid {SURFACE0}; border-radius: 4px;
                padding: 2px 10px; font-size: 12px; font-weight: 600;
                text-align: left;
            }}
            QPushButton#settingsToggle:hover {{
                background: {SURFACE0}; color: {TEXT};
            }}
            QSplitter::handle {{
                background: {SURFACE1}; width: 3px; border-radius: 1px;
            }}
            QStatusBar {{
                background: {MANTLE}; color: {SUBTEXT0};
                border-top: 1px solid {SURFACE0}; font-size: 12px;
            }}
            QScrollBar:vertical {{
                background: {MANTLE}; width: 10px; border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {SURFACE1}; min-height: 30px; border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
            QScrollBar:horizontal {{
                background: {MANTLE}; height: 10px; border-radius: 5px;
            }}
            QScrollBar::handle:horizontal {{
                background: {SURFACE1}; min-width: 30px; border-radius: 5px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
        """)

        for btn, color in [
            (self._start_btn, GREEN),
            (self._pause_btn, YELLOW),
            (self._stop_btn, RED),
            (self._skip_btn, BLUE),
            (self._support_btn, PINK),
        ]:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {SURFACE0}; color: {color};
                    border: 1px solid {SURFACE1}; border-radius: 6px;
                    padding: 5px 14px; font-size: 13px; font-weight: 600;
                }}
                QPushButton:hover {{ background: {color}; color: {CRUST}; }}
                QPushButton:pressed {{ background: {color}; color: {CRUST}; }}
            """)

    # -----------------------------------------------------------------------
    # Global hotkeys
    # -----------------------------------------------------------------------
    def _invoke_ui(self, fn, *args, **kwargs):
        QTimer.singleShot(0, lambda: fn(*args, **kwargs))

    def _make_hotkey_callback(self, fn):
        return lambda: self._invoke_ui(fn)

    def _register_global_hotkeys(self):
        self._unregister_global_hotkeys()
        if not _keyboard_available:
            self._append_log("Global hotkeys unavailable (keyboard package not found).")
            return
        try:
            for action, key_combo in self._hotkeys.items():
                kb_combo = "+".join(p.strip().lower() for p in key_combo.split("+"))
                callback = {
                    "start": self._on_start,
                    "pause": self._on_pause,
                    "skip": self._on_skip,
                    "stop": self._on_stop,
                }.get(action)
                if callback:
                    hook = _kb.add_hotkey(kb_combo, self._make_hotkey_callback(callback), suppress=False)
                    self._hotkey_hooks.append(hook)
            names = ", ".join(f"{a.capitalize()}={k}" for a, k in self._hotkeys.items())
            self._append_log(f"Hotkeys registered: {names}")
        except Exception as exc:
            self._append_log(f"Hotkey registration error: {exc}")

    def _unregister_global_hotkeys(self):
        if not _keyboard_available:
            return
        for hook in self._hotkey_hooks:
            try:
                _kb.remove_hotkey(hook)
            except Exception:
                pass
        self._hotkey_hooks.clear()

    # -----------------------------------------------------------------------
    # Collapsible sections
    # -----------------------------------------------------------------------
    def _toggle_settings(self):
        self._settings_expanded = not self._settings_expanded
        self._settings_widget.setVisible(self._settings_expanded)
        self._settings_toggle.setText(
            "▼ Settings" if self._settings_expanded else "▶ Settings"
        )

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        self._log_widget.setVisible(self._log_visible)
        self._log_toggle.setText(
            "▼ Activity Log" if self._log_visible else "▶ Activity Log"
        )

    # -----------------------------------------------------------------------
    # Mode switching
    # -----------------------------------------------------------------------
    def _on_mode_change(self, index: int):
        is_replace = index == 1
        self._fresh_group.setVisible(not is_replace)
        self._replace_widget.setVisible(is_replace)
        if is_replace:
            self._update_manual_progress(
                self._manual_start_pos_replace,
                len(self._original_text.toPlainText()),
                "Replace",
            )
        else:
            self._update_manual_progress(
                self._manual_start_pos_fresh,
                len(self._your_text.toPlainText()),
                "Fresh",
            )

    # -----------------------------------------------------------------------
    # Diff preview
    # -----------------------------------------------------------------------
    def _build_diff_preview(self):
        orig = self._original_text.toPlainText()
        repl = self._replacement_text.toPlainText()
        if not orig and not repl:
            self._diff_view.clear()
            return

        ops = _compute_diff(orig, repl)
        parts: list[str] = []
        for op in ops:
            if op.kind == "equal":
                txt = html.escape(op.new_text)
                txt = txt.replace("\t", "    ").replace("\n", "<br>")
                parts.append(
                    f"<span style='background:{SURFACE0}; color:{TEXT};'>" + txt + "</span>"
                )
            elif op.kind == "delete":
                txt = html.escape(op.old_text)
                txt = txt.replace("\t", "    ").replace("\n", "<br>")
                parts.append(
                    f"<span style='background:#44{RED[1:]}; color:{RED}; text-decoration:line-through;'>"
                    + txt + "</span>"
                )
            elif op.kind == "insert":
                txt = html.escape(op.new_text)
                txt = txt.replace("\t", "    ").replace("\n", "<br>")
                parts.append(
                    f"<span style='background:#44{GREEN[1:]}; color:{GREEN};'>" + txt + "</span>"
                )
            elif op.kind == "replace":
                old_txt = html.escape(op.old_text).replace("\t", "    ").replace("\n", "<br>")
                new_txt = html.escape(op.new_text).replace("\t", "    ").replace("\n", "<br>")
                parts.append(
                    f"<span style='background:#44{RED[1:]}; color:{RED}; text-decoration:line-through;'>"
                    + old_txt + "</span>"
                )
                parts.append(
                    f"<span style='background:#44{GREEN[1:]}; color:{GREEN};'>" + new_txt + "</span>"
                )

        html_doc = (
            "<div style='white-space: pre-wrap; font-family: Cascadia Code, Consolas, monospace; "
            "font-size: 11px;'>" + "".join(parts) + "</div>"
        )
        self._diff_view.setHtml(html_doc)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------
    def _on_info(self):
        dlg = HotkeyDialog(self._hotkeys, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._hotkeys = dlg.hotkeys
            self._settings["hotkeys"] = self._hotkeys
            _save_settings(self._settings)
            self._register_global_hotkeys()

    def _on_support(self):
        QDesktopServices.openUrl(QUrl("https://github.com/sponsors/Wart050"))

    def _on_start(self):
        if self._worker is not None:
            return

        is_replace = self._mode_combo.currentIndex() == 1
        start_pos = 0
        orig = ""

        if is_replace:
            orig = self._original_text.toPlainText()
            repl = self._replacement_text.toPlainText()
            if not orig.strip() and not repl.strip():
                self._append_log("No text to type.")
                return
            text = repl
            diff_ops = _compute_diff(orig, repl) if orig else None
            mode = "replace"
            start_pos = max(0, min(self._manual_start_pos_replace, len(orig)))
        else:
            text = self._your_text.toPlainText()
            if not text.strip():
                self._append_log("No text to type.")
                return
            diff_ops = None
            mode = "fresh"
            start_pos = max(0, min(self._manual_start_pos_fresh, len(text)))

        options = TypingOptions(
            wpm=self._wpm_spin.value(),
            variability=self._variability_spin.value(),
            typo_rate=self._typo_spin.value(),
            start_delay=self._countdown_spin.value(),
            type_mode=self._type_combo.currentText(),
        )

        self._worker = TypingWorker(text, options, mode, diff_ops, start_pos=start_pos)
        self._worker.signals.status.connect(self._on_status)
        self._worker.signals.log.connect(self._append_log)
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.char_typed.connect(self._on_char_typed)
        self._worker.signals.finished.connect(self._on_finished)
        self._worker.signals.cursor_pos.connect(self._on_cursor_pos)
        self._worker.signals.pause_info.connect(self._on_pause_info)

        total_len = len(orig) if is_replace else len(text)
        start_pct = int(start_pos / total_len * 100) if total_len else 0
        self._progress_bar.setValue(start_pct)
        self._set_running_ui(True)
        self._append_log(f"Starting ({mode} mode, {options.wpm} WPM)…")

        # Start the animated cursor
        if mode == "fresh":
            self._fresh_cursor.start(start_pos)
        else:
            self._orig_cursor.start(start_pos)

        # Save before starting
        self._persist_all()

        self._worker.start()

    def _on_pause(self):
        if self._worker:
            self._worker.pause()
            is_paused = self._worker._paused
            state = "paused" if is_paused else "resumed"
            self._append_log(f"Typing {state}.")
            # Unlock text boxes while paused so user can reposition cursor
            self._your_text.setReadOnly(not is_paused)
            self._original_text.setReadOnly(not is_paused)
            self._replacement_text.setReadOnly(not is_paused)

    def _on_stop(self):
        if self._worker:
            self._worker.stop()
            self._append_log("Stop requested.")
        self._reset_cursors_to_start()

    def _on_skip(self):
        if self._worker:
            self._worker.skip()
            self._append_log("Skip requested – fast-typing remainder.")

    # -----------------------------------------------------------------------
    # Worker signal handlers
    # -----------------------------------------------------------------------
    def _on_status(self, msg: str):
        self._status_label.setText(msg)

    def _on_progress(self, pct: int):
        self._progress_bar.setValue(pct)
        self._status_label.setText(f"Typing… {pct}%")

    def _on_char_typed(self, ch: str):
        pass

    def _on_cursor_pos(self, pos: int):
        """Move the animated cursor overlay to the given character position."""
        is_replace = self._mode_combo.currentIndex() == 1
        if is_replace:
            self._orig_cursor.set_position(pos)
        else:
            self._fresh_cursor.set_position(pos)

    def _on_pause_info(self, pos: int, snippet: str):
        """Show a popup and log entry with the exact pause position."""
        self._append_log(f"Paused at position {pos}: {snippet}")
        # Show a non-blocking message
        QMessageBox.information(
            self,
            "Typing Paused",
            f"Paused at character {pos}.\n\n{snippet}",
        )

    def _on_finished(self):
        self._worker = None
        self._set_running_ui(False)
        self._status_label.setText("Ready")
        self._progress_bar.setValue(0)
        self._fresh_cursor.stop()
        self._orig_cursor.stop()
        self._append_log("Finished.")

    def _set_running_ui(self, running: bool):
        self._start_btn.setEnabled(not running)
        self._pause_btn.setEnabled(running)
        self._stop_btn.setEnabled(running)
        self._skip_btn.setEnabled(running)
        self._your_text.setReadOnly(running)
        self._original_text.setReadOnly(running)
        self._replacement_text.setReadOnly(running)

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------
    def _append_log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{ts}] {msg}")

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------
    def closeEvent(self, event):
        if self._worker:
            self._worker.stop()
        self._unregister_global_hotkeys()
        self._persist_all()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Human Text Editor")
    app.setApplicationDisplayName("Human Text Editor (HTE)")
    if _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))
    window = HumanTextEditor()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
