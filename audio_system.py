import collections
import queue

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from config import (
    VAD_ENERGY_THRESH, VAD_SPEECH_FRAMES, VAD_SILENCE_MS,
    STT_MODEL, STT_LANGUAGE,
)

_TARGET_SR         = 16_000
_FRAME_MS          = 20
_FRAME_SIZE        = _TARGET_SR * _FRAME_MS // 1000
_SILENCE_FRAMES    = int(VAD_SILENCE_MS / _FRAME_MS)
_PRE_BUFFER_FRAMES = 10   # 200 ms перед началом речи

class SystemAudioListener(QThread):
    transcribed     = pyqtSignal(str)
    error_occurred  = pyqtSignal(str)
    capture_started = pyqtSignal()
    capture_stopped = pyqtSignal()

    def __init__(self, whisper_model, parent=None):
        super().__init__(parent)
        self._running     = False
        self._active      = False
        self._audio_queue: queue.Queue = queue.Queue()
        self._whisper     = whisper_model

    def set_active(self, active: bool):
        print(f"[sysaudio] set_active={active}")
        self._active = active

    def run(self):
        try:
            import pyaudiowpatch as pyaudio
        except ImportError as e:
            self.error_occurred.emit(f"Системное аудио недоступно: {e}")
            return

        try:
            pa       = pyaudio.PyAudio()
            wasapi   = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            speakers = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            loopback = None

            if speakers.get("isLoopbackDevice", False):
                loopback = speakers
            else:
                for dev in pa.get_loopback_device_info_generator():
                    if speakers["name"] in dev["name"]:
                        loopback = dev
                        break

            if loopback is None:
                self.error_occurred.emit("WASAPI loopback не найден")
                pa.terminate()
                return

            src_rate   = int(loopback["defaultSampleRate"])
            src_ch     = loopback["maxInputChannels"]
            chunk_size = int(src_rate * _FRAME_MS / 1000)
        except Exception as e:
            self.error_occurred.emit(f"PyAudio: {e}")
            return

        pre_buffer: collections.deque = collections.deque(maxlen=_PRE_BUFFER_FRAMES)
        speech_buffer: list[np.ndarray] = []
        speech_frame_count  = 0
        silence_frame_count = 0
        is_speaking         = False

        def _cb(in_data, frame_count, time_info, status):
            raw = np.frombuffer(in_data, dtype=np.float32)
            self._audio_queue.put(raw.copy())
            return (None, pyaudio.paContinue)

        stream = pa.open(
            format=pyaudio.paFloat32,
            channels=src_ch,
            rate=src_rate,
            frames_per_buffer=chunk_size,
            input=True,
            input_device_index=loopback["index"],
            stream_callback=_cb,
        )

        self._running = True
        stream.start_stream()

        try:
            while self._running and stream.is_active():
                try:
                    raw = self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if not self._active:
                    speech_buffer       = []
                    speech_frame_count  = 0
                    silence_frame_count = 0
                    is_speaking         = False
                    pre_buffer.clear()
                    continue

                if src_ch > 1:
                    raw = raw.reshape(-1, src_ch).mean(axis=1)
                frame = _resample(raw, src_rate, _TARGET_SR)

                rms = float(np.sqrt(np.mean(frame ** 2)))

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
                    print("[sysaudio] capture started")
                    self.capture_started.emit()

                if is_speaking:
                    speech_buffer.append(frame)

                    if silence_frame_count >= _SILENCE_FRAMES:
                        is_speaking   = False
                        self._active  = False
                        self.capture_stopped.emit()
                        if speech_buffer:
                            audio = np.concatenate(speech_buffer)
                            self._transcribe(audio)
                        speech_buffer       = []
                        speech_frame_count  = 0
                        silence_frame_count = 0
                        pre_buffer.clear()
        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _transcribe(self, audio: np.ndarray):
        try:
            lang_kwarg = {} if STT_LANGUAGE is None else {"language": STT_LANGUAGE}
            segments, _info = self._whisper.transcribe(audio, vad_filter=True, **lang_kwarg)
            text = "".join(s.text for s in segments).strip()
            if text:
                self.transcribed.emit(f"Слышу с компа: {text}")
        except Exception as e:
            self.error_occurred.emit(f"Whisper (system): {e}")

    def stop_listening(self):
        self._running = False
        self.wait(3000)


from fractions import Fraction
from scipy.signal import resample_poly

_RESAMPLE_CACHE: dict[tuple[int, int], tuple[int, int]] = {}

def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return audio
    key = (orig_sr, target_sr)
    if key not in _RESAMPLE_CACHE:
        frac = Fraction(target_sr, orig_sr).limit_denominator(100)
        _RESAMPLE_CACHE[key] = (frac.numerator, frac.denominator)
    num, den = _RESAMPLE_CACHE[key]
    return resample_poly(audio, num, den).astype(np.float32)
