import queue
import re

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    MIC_SAMPLE_RATE, MIC_CHANNELS,
    VAD_ENERGY_THRESH, VAD_SPEECH_FRAMES, VAD_SILENCE_MS,
    STT_MODEL, STT_LANGUAGE,
)

_FRAME_MS     = 20
_FRAME_SIZE   = MIC_SAMPLE_RATE * _FRAME_MS // 1000
_SILENCE_FRAMES = int(VAD_SILENCE_MS / _FRAME_MS)

class MicListener(QThread):
    transcribed          = pyqtSignal(str)
    listening_started    = pyqtSignal()
    listening_stopped    = pyqtSignal()
    transcription_skipped = pyqtSignal()
    error_occurred       = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running     = False
        self._audio_queue: queue.Queue = queue.Queue()

    def run(self):
        try:
            import sounddevice as sd
            from pywhispercpp.model import Model
        except ImportError as e:
            self.error_occurred.emit(f"Зависимость не установлена: {e}")
            return

        try:

            whisper = Model(STT_MODEL, n_threads=4, print_realtime=False,
                            print_progress=False)
        except Exception as e:
            self.error_occurred.emit(f"Ошибка загрузки Whisper: {e}")
            return

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
                        speech_frame_count   = 0

                    if not is_speaking and speech_frame_count >= VAD_SPEECH_FRAMES:
                        is_speaking   = True
                        speech_buffer = []
                        print("[mic] speech detected")
                        self.listening_started.emit()

                    if is_speaking:
                        speech_buffer.append(frame)

                        if silence_frame_count >= _SILENCE_FRAMES:
                            is_speaking = False
                            self.listening_stopped.emit()
                            if speech_buffer:
                                audio = np.concatenate(speech_buffer)
                                self._transcribe(whisper, audio)
                            speech_buffer       = []
                            speech_frame_count  = 0
                            silence_frame_count = 0

                carry = data

    _NOISE_RE = re.compile(r'^\[.*\]$|^\(.*\)$')

    def _transcribe(self, whisper, audio: np.ndarray):
        try:
            lang_kwarg = {} if STT_LANGUAGE is None else {"language": STT_LANGUAGE}
            segments = whisper.transcribe(audio, **lang_kwarg)
            text = "".join(s.text for s in segments).strip()
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
