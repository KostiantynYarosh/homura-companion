import json
import re

import httpx
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from core.config import (
    OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
    TEMPERATURE, NUM_PREDICT, THINK,
    SYSTEM_PROMPT, EMOTION_COLORS, DEFAULT_EMOTION,
)
from core.memory import save_fact, build_memory_block

_EMOTION_RE    = re.compile(r'\[EMOTION:(\w+)\]', re.IGNORECASE)
_LISTEN_PC_RE  = re.compile(r'\[LISTEN_PC\]', re.IGNORECASE)
_HOODIE_RE     = re.compile(r'\[HOODIE:(on|off)\]', re.IGNORECASE)
_REMEMBER_RE   = re.compile(r'\[REMEMBER:([^\]]+)\]', re.IGNORECASE)

def parse_emotion(text: str) -> str:
    matches = _EMOTION_RE.findall(text)
    if matches:
        candidate = matches[-1].lower()
        if candidate in EMOTION_COLORS:
            return candidate
    return DEFAULT_EMOTION

def parse_hoodie(text: str) -> str | None:
    m = _HOODIE_RE.search(text)
    return m.group(1).lower() if m else None

def strip_emotion_tags(text: str) -> str:
    return _EMOTION_RE.sub("", text).strip()

def strip_all_tags(text: str) -> str:
    text = _EMOTION_RE.sub("", text)
    text = _LISTEN_PC_RE.sub("", text)
    text = _HOODIE_RE.sub("", text)
    text = _REMEMBER_RE.sub("", text)
    return text.strip()

class _Signals(QObject):
    chunk_received = pyqtSignal(str)
    talking_done   = pyqtSignal()
    response_done  = pyqtSignal(str, str, bool, object, list)
    error_occurred = pyqtSignal(str)

class AIWorker(QRunnable):
    def __init__(self, messages: list[dict], model: str):
        super().__init__()
        self.signals   = _Signals()
        self._messages = messages
        self._model    = model
        self.setAutoDelete(True)

    def run(self):
        url     = f"{OLLAMA_BASE_URL}/api/chat"
        payload = {
            "model":   self._model,
            "messages": self._messages,
            "stream":  True,
            "options": {
                "temperature": TEMPERATURE,
                "num_predict": NUM_PREDICT,
                **({"think": THINK} if THINK is not None else {}),
            },
        }
        chunks: list[str] = []
        talking_stopped = False
        try:
            with httpx.stream("POST", url, json=payload,
                              timeout=OLLAMA_TIMEOUT) as resp:
                if resp.status_code != 200:
                    self.signals.error_occurred.emit(
                        f"Ollama HTTP {resp.status_code}")
                    return
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if data.get("done"):
                        break
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        chunks.append(chunk)
                        if not talking_stopped and "[" in "".join(chunks):
                            talking_stopped = True
                            self.signals.talking_done.emit()
                        self.signals.chunk_received.emit(chunk)

            full_text  = "".join(chunks)
            emotion    = parse_emotion(full_text)
            listen_pc  = bool(_LISTEN_PC_RE.search(full_text))
            hoodie     = parse_hoodie(full_text)
            facts      = _REMEMBER_RE.findall(full_text)
            clean_text = strip_all_tags(full_text)
            self.signals.response_done.emit(clean_text, emotion, listen_pc, hoodie, facts)

        except httpx.ConnectError:
            self.signals.error_occurred.emit(
                "Ollama недоступен. Запусти: ollama serve")
        except Exception as e:
            self.signals.error_occurred.emit(str(e))

class AICore(QObject):
    chunk_received      = pyqtSignal(str)
    talking_done        = pyqtSignal()
    response_done       = pyqtSignal(str, str)
    error_occurred      = pyqtSignal(str)
    listen_pc_requested = pyqtSignal()
    hoodie_requested    = pyqtSignal(str)


    _MAX_HISTORY = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool  = QThreadPool.globalInstance()
        self._busy  = False
        self._history: list[dict] = []
        self._reset_history()

    def _system_prompt(self) -> str:
        return SYSTEM_PROMPT + build_memory_block()

    def _reset_history(self):
        self._history = [{"role": "system", "content": self._system_prompt()}]

    def send_pc_audio(self, text: str):
        """Отправить транскрипцию звука с ПК как отдельный контекст."""
        if not text.strip():
            return
        labeled = f"[PC_AUDIO] {text.strip()}"
        self.send(labeled, _pc_audio=True)

    def send(self, user_text: str, _pc_audio: bool = False):
        if self._busy or not user_text.strip():
            return
        self._busy = True
        role = "user"
        self._history.append({"role": role, "content": user_text})
        if len(self._history) > self._MAX_HISTORY + 1:
            self._history = [self._history[0]] + self._history[-self._MAX_HISTORY:]

        worker = AIWorker(self._history.copy(), OLLAMA_MODEL)
        worker.signals.chunk_received.connect(self.chunk_received)
        worker.signals.talking_done.connect(self.talking_done)
        worker.signals.response_done.connect(
            lambda t, e, lp, h, f: self._on_worker_done(t, e, lp, h, f))
        worker.signals.error_occurred.connect(self._on_error)
        self._pool.start(worker)

    def _on_worker_done(self, clean_text: str, emotion: str, listen_pc: bool, hoodie, facts: list):
        print(f"[ai] listen_pc={listen_pc} hoodie={hoodie} facts={facts}")
        for fact in facts:
            save_fact(fact)
        if listen_pc:
            self.listen_pc_requested.emit()
        if hoodie:
            self.hoodie_requested.emit(hoodie)
        self._history.append({"role": "assistant", "content": clean_text})
        self._busy = False
        self.response_done.emit(clean_text, emotion)

    def _on_error(self, msg: str):
        self._busy = False
        self.error_occurred.emit(msg)

    def clear_history(self):
        self._reset_history()

    @property
    def busy(self) -> bool:
        return self._busy
