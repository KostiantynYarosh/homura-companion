import sys
from difflib import SequenceMatcher

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
    mic       = MicListener()
    sys_audio = SystemAudioListener()

    character.move(WINDOW_MARGIN, WINDOW_MARGIN)

    window.manually_moved.connect(lambda: popup.reposition(window) if popup.isVisible() else None)

    tray.toggle_top_requested.connect(window.set_always_on_top)
    tray.hide_requested.connect(window.hide)
    tray.hide_requested.connect(popup.hide)
    tray.show_requested.connect(window.show)
    tray.quit_requested.connect(app.quit)

    _WAKE_WORDS  = ("хомура", "homura", "хомуру", "хамура", "комура", "хамора", "мамора")
    _WAKE_FUZZY  = ("хомура", "homura")   # для нечёткого совпадения
    _FUZZY_RATIO = 0.75
    _SESSION_MS  = 60_000  # 60 сек после последней реплики

    session_timer = QTimer()
    session_timer.setSingleShot(True)
    session_timer.setInterval(_SESSION_MS)
    session_active = [False]

    def _end_session():
        session_active[0] = False

    session_timer.timeout.connect(_end_session)

    def _has_wake(t: str) -> bool:
        if any(w in t for w in _WAKE_WORDS):
            return True
        words = t.split()
        for word in words:
            for wake in _WAKE_FUZZY:
                ratio = SequenceMatcher(None, word, wake).ratio()
                if ratio >= _FUZZY_RATIO:
                    return True
        return False

    def _on_mic(text: str):
        t = text.lower()
        has_wake = _has_wake(t)
        if has_wake:
            session_active[0] = True
        if session_active[0]:
            session_timer.start()
            print(f"[send] {text}")
            ai_core.send(text)

    mic.listening_started.connect(
        lambda: popup.cancel_hide() if session_active[0] else None)
    mic.listening_stopped.connect(lambda: None)
    mic.transcribed.connect(_on_mic)
    mic.transcription_skipped.connect(
        lambda: popup.restart_hide() if session_active[0] else None)
    mic.error_occurred.connect(popup.on_error)

    ai_core.listen_pc_requested.connect(lambda: sys_audio.set_active(True))
    ai_core.listen_pc_requested.connect(lambda: popup.set_status("Слушаю комп..."))

    sys_audio.transcribed.connect(ai_core.send)
    sys_audio.capture_stopped.connect(lambda: popup.set_status(""))
    sys_audio.error_occurred.connect(popup.on_error)

    ai_core.chunk_received.connect(popup.on_chunk)
    ai_core.response_done.connect(popup.on_response_done)
    ai_core.response_done.connect(
        lambda text, emotion: character.set_emotion(emotion))
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
