import json
import re

import httpx
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from config import (
    OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
    TEMPERATURE, NUM_PREDICT, THINK,
    SYSTEM_PROMPT, EMOTION_COLORS, DEFAULT_EMOTION,
)

_EMOTION_RE    = re.compile(r'\[EMOTION:(\w+)\]', re.IGNORECASE)
_LISTEN_PC_RE  = re.compile(r'\[LISTEN_PC\]', re.IGNORECASE)

def parse_emotion(text: str) -> str:
    matches = _EMOTION_RE.findall(text)
    if matches:
        candidate = matches[-1].lower()
        if candidate in EMOTION_COLORS:
            return candidate
    return DEFAULT_EMOTION

def strip_emotion_tags(text: str) -> str:
    return _EMOTION_RE.sub("", text).strip()

def strip_all_tags(text: str) -> str:
    text = _EMOTION_RE.sub("", text)
    text = _LISTEN_PC_RE.sub("", text)
    return text.strip()

class _Signals(QObject):
    chunk_received = pyqtSignal(str)
    response_done  = pyqtSignal(str, str, bool)
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
                        self.signals.chunk_received.emit(chunk)

            full_text  = "".join(chunks)
            emotion    = parse_emotion(full_text)
            listen_pc  = bool(_LISTEN_PC_RE.search(full_text))
            clean_text = strip_all_tags(full_text)
            self.signals.response_done.emit(clean_text, emotion, listen_pc)

        except httpx.ConnectError:
            self.signals.error_occurred.emit(
                "Ollama недоступен. Запусти: ollama serve")
        except Exception as e:
            self.signals.error_occurred.emit(str(e))

class AICore(QObject):
    chunk_received      = pyqtSignal(str)
    response_done       = pyqtSignal(str, str)
    error_occurred      = pyqtSignal(str)
    listen_pc_requested = pyqtSignal()


    _MAX_HISTORY = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]
        self._pool  = QThreadPool.globalInstance()
        self._busy  = False

    def send(self, user_text: str):
        if self._busy or not user_text.strip():
            return
        self._busy = True
        self._history.append({"role": "user", "content": user_text})
        if len(self._history) > self._MAX_HISTORY + 1:
            self._history = [self._history[0]] + self._history[-self._MAX_HISTORY:]

        worker = AIWorker(self._history.copy(), OLLAMA_MODEL)
        worker.signals.chunk_received.connect(self.chunk_received)
        worker.signals.response_done.connect(self._on_worker_done)
        worker.signals.error_occurred.connect(self._on_error)
        self._pool.start(worker)

    def _on_worker_done(self, clean_text: str, emotion: str, listen_pc: bool):
        print(f"[ai] listen_pc={listen_pc}")
        if listen_pc:
            self.listen_pc_requested.emit()
        self._history.append({"role": "assistant", "content": clean_text})
        self._busy = False
        self.response_done.emit(clean_text, emotion)

    def _on_error(self, msg: str):
        self._busy = False
        self.error_occurred.emit(msg)

    def clear_history(self):
        self._history = [{"role": "system", "content": SYSTEM_PROMPT}]

    @property
    def busy(self) -> bool:
        return self._busy
