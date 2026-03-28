import collections
import queue
import re

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from core.config import (
    MIC_SAMPLE_RATE, MIC_CHANNELS,
    VAD_ENERGY_THRESH, VAD_SPEECH_FRAMES, VAD_SILENCE_MS,
    STT_MODEL, STT_LANGUAGE,
)

_FRAME_MS          = 20
_FRAME_SIZE        = MIC_SAMPLE_RATE * _FRAME_MS // 1000
_SILENCE_FRAMES    = int(VAD_SILENCE_MS / _FRAME_MS)
_PRE_BUFFER_FRAMES = 10

class MicListener(QThread):
    transcribed           = pyqtSignal(str)
    listening_started     = pyqtSignal()
    listening_stopped     = pyqtSignal()
    transcription_skipped = pyqtSignal()
    error_occurred        = pyqtSignal(str)

    def __init__(self, whisper_model, parent=None):
        super().__init__(parent)
        self._running     = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._whisper     = whisper_model

    def run(self):
        try:
            import sounddevice as sd
        except ImportError as e:
            self.error_occurred.emit(f"Зависимость не установлена: {e}")
            return

        pre_buffer: collections.deque = collections.deque(maxlen=_PRE_BUFFER_FRAMES)
        speech_buffer: list[np.ndarray] = []
        speech_frame_count  = 0
        silence_frame_count = 0
        is_speaking         = False
        carry               = np.zeros(0, dtype=np.float32)

        def _cb(indata, frames, time, status):
            self._audio_queue.put(indata[:, 0].copy())

        self._running = True
        with sd.InputStream(samplerate=MIC_SAMPLE_RATE, channels=MIC_CHANNELS,
                            dtype="float32", blocksize=_FRAME_SIZE,
                            callback=_cb):
            while self._running:
                try:
                    chunk = self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                data  = np.concatenate([carry, chunk])
                carry = np.zeros(0, dtype=np.float32)

                while len(data) >= _FRAME_SIZE:
                    frame = data[:_FRAME_SIZE]
                    data  = data[_FRAME_SIZE:]
                    rms   = float(np.sqrt(np.mean(frame ** 2)))

                    if rms >= VAD_ENERGY_THRESH:
                        speech_frame_count  += 1
                        silence_frame_count  = 0
                    else:
                        silence_frame_count += 1
                        if not is_speaking and silence_frame_count > 5:
                            speech_frame_count = 0

                    if not is_speaking:
                        pre_buffer.append(frame)

                    if not is_speaking and speech_frame_count >= VAD_SPEECH_FRAMES:
                        is_speaking   = True
                        speech_buffer = list(pre_buffer)
                        self.listening_started.emit()

                    if is_speaking:
                        speech_buffer.append(frame)

                        if silence_frame_count >= _SILENCE_FRAMES:
                            is_speaking = False
                            self.listening_stopped.emit()
                            if speech_buffer:
                                audio = np.concatenate(speech_buffer)
                                self._transcribe(audio)
                            speech_buffer       = []
                            speech_frame_count  = 0
                            silence_frame_count = 0
                            pre_buffer.clear()

                carry = data

    _NOISE_RE = re.compile(r'^\[.*\]$|^\(.*\)$')

    def _transcribe(self, audio: np.ndarray):
        try:
            lang_kwarg = {} if STT_LANGUAGE is None else {"language": STT_LANGUAGE}
            segments, _info = self._whisper.transcribe(audio, vad_filter=True, **lang_kwarg)
            text = "".join(s.text for s in segments).strip()
            if text:
                print(f"[mic] transcribed: '{text}'")
            if text and not self._NOISE_RE.match(text.lower()) and len(text) > 2:
                self.transcribed.emit(text)
            else:
                self.transcription_skipped.emit()
        except Exception as e:
            self.error_occurred.emit(f"Whisper ошибка: {e}")

    def stop_listening(self):
        self._running = False
        self.wait(3000)
