import sys
import re
from difflib import SequenceMatcher

# ctranslate2 (faster-whisper) конфликтует с Qt если Qt импортируется первым.
# Грузим модель до любых PyQt6-импортов.
from config import STT_MODEL
print(f"[whisper] loading model '{STT_MODEL}'...")
from faster_whisper import WhisperModel
_whisper = WhisperModel(STT_MODEL, device="auto", compute_type="int8")
print("[whisper] model ready")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from window import CompanionWindow
from character import CharacterWidget
from tray import SystemTrayManager
from chat_popup import ChatPopup
from ai import AICore
from stt import MicListener
from audio_system import SystemAudioListener
from config import WINDOW_MARGIN

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window    = CompanionWindow()
    character = CharacterWidget(parent=window)
    tray      = SystemTrayManager()
    popup     = ChatPopup()
    ai_core   = AICore()
    mic       = MicListener(_whisper)
    sys_audio = SystemAudioListener(_whisper)

    character.move(WINDOW_MARGIN, WINDOW_MARGIN)

    window.manually_moved.connect(lambda: popup.reposition(window) if popup.isVisible() else None)

    tray.toggle_top_requested.connect(window.set_always_on_top)
    tray.hide_requested.connect(window.hide)
    tray.hide_requested.connect(popup.hide)
    tray.show_requested.connect(window.show)
    tray.quit_requested.connect(app.quit)

    _HOODIE_ON_RE  = re.compile(r'(одень|надень|надеть|одеть).{0,15}(худи|кофт|свитер)|холодно|мёрзнешь|мёрзнет', re.IGNORECASE)
    _HOODIE_OFF_RE = re.compile(r'(сними|снять|снимай).{0,15}(худи|кофт|свитер)|жарко', re.IGNORECASE)

    _WAKE_WORDS  = (
        "хомура", "homura", "хомуру", "хамура", "комура", "хамора",
        "мамора", "хомуро", "хомур", "омура", "гомура", "хомурa",
    )
    _WAKE_FUZZY  = ("хомура", "homura")   # для нечёткого совпадения
    _FUZZY_RATIO = 0.65                   # снизили порог: "хамора" = 0.67
    _SESSION_MS  = 60_000  # 60 сек после последней реплики

    _STOP_PC_RE  = re.compile(
        r'(стоп|хватит|остановись|не\s*слушай|хватит\s*слушать|перестань)', re.IGNORECASE
    )

    session_timer = QTimer()
    session_timer.setSingleShot(True)
    session_timer.setInterval(_SESSION_MS)
    session_active  = [False]
    pc_listening    = [False]

    def _end_session():
        session_active[0] = False

    session_timer.timeout.connect(_end_session)

    def _has_wake(t: str) -> bool:
        # точное совпадение подстроки
        if any(w in t for w in _WAKE_WORDS):
            return True
        # нечёткое совпадение по каждому слову
        words = t.split()
        for word in words:
            for wake in _WAKE_FUZZY:
                ratio = SequenceMatcher(None, word, wake).ratio()
                if ratio >= _FUZZY_RATIO:
                    print(f"[wake] fuzzy match: '{word}' ~ '{wake}' = {ratio:.2f}")
                    return True
        # проверяем биграммы - вдруг Whisper разбил "хо мура"
        for i in range(len(words) - 1):
            bigram = words[i] + words[i + 1]
            if any(w in bigram for w in _WAKE_WORDS):
                print(f"[wake] bigram match: '{bigram}'")
                return True
        return False

    def _on_mic(text: str):
        t = text.lower()
        has_wake = _has_wake(t)

        # стоп-команда во время прослушивания ПК
        if pc_listening[0] and has_wake and _STOP_PC_RE.search(t):
            sys_audio.force_stop()
            return

        # пока слушаем ПК - микрофон заблокирован для обычных сообщений
        if pc_listening[0]:
            return

        if has_wake:
            session_active[0] = True
        if session_active[0]:
            session_timer.start()
            print(f"[send] {text}")
            if _HOODIE_ON_RE.search(t):
                character.put_on_hoodie()
            elif _HOODIE_OFF_RE.search(t):
                character.take_off_hoodie()
            ai_core.send(text)

    mic.listening_started.connect(
        lambda: popup.cancel_hide() if session_active[0] else None)
    mic.listening_stopped.connect(lambda: None)
    mic.transcribed.connect(_on_mic)
    mic.transcription_skipped.connect(
        lambda: popup.restart_hide() if session_active[0] else None)
    mic.error_occurred.connect(popup.on_error)

    def _on_listen_pc():
        pc_listening[0] = True
        sys_audio.set_active(True)
        popup.set_status("Слушаю комп...")

    def _on_pc_transcribed(text: str):
        pc_listening[0] = False
        popup.set_status("")
        ai_core.send_pc_audio(text)

    def _on_capture_stopped():
        pc_listening[0] = False
        popup.set_status("")

    ai_core.listen_pc_requested.connect(_on_listen_pc)
    ai_core.hoodie_requested.connect(
        lambda state: character.put_on_hoodie() if state == "on" else character.take_off_hoodie()
    )

    sys_audio.transcribed.connect(_on_pc_transcribed)
    sys_audio.capture_stopped.connect(_on_capture_stopped)
    sys_audio.error_occurred.connect(popup.on_error)

    ai_core.chunk_received.connect(popup.on_chunk)
    ai_core.chunk_received.connect(lambda _: character.start_talking())
    ai_core.talking_done.connect(character.stop_talking)
    ai_core.response_done.connect(popup.on_response_done)
    ai_core.response_done.connect(lambda *_: character.stop_talking())
    ai_core.response_done.connect(
        lambda _, emotion: character.set_emotion(emotion))
    ai_core.error_occurred.connect(popup.on_error)

    screen = app.primaryScreen().availableGeometry()
    window.move(screen.width() * 3 // 4, screen.height() - window.height())
    popup.reposition(window)

    window.show()
    QTimer.singleShot(0,    tray.initialize)

    QTimer.singleShot(100, mic.start)
    QTimer.singleShot(200, sys_audio.start)

    app.aboutToQuit.connect(mic.stop_listening)
    app.aboutToQuit.connect(sys_audio.stop_listening)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
