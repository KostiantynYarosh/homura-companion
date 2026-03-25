import re
from pathlib import Path

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QPixmap, QFontDatabase, QPalette

from config import CHAR_SIZE, WINDOW_MARGIN

_ASSETS = Path(__file__).parent / "assets"
_SLICE_MARGIN = 20


def _draw_9slice(painter: QPainter, pixmap: QPixmap, target: QRect, margin: int):
    m  = margin
    sw = pixmap.width()
    sh = pixmap.height()
    tw = target.width()
    th = target.height()
    ox = target.x()
    oy = target.y()

    smw = sw - m * 2   # source middle width
    smh = sh - m * 2   # source middle height
    tmw = tw - m * 2   # target middle width
    tmh = th - m * 2   # target middle height

    # src rects           (x,        y,        w,   h  )
    src_tl = QRect(0,       0,       m,   m  )
    src_tr = QRect(sw-m,    0,       m,   m  )
    src_bl = QRect(0,       sh-m,    m,   m  )
    src_br = QRect(sw-m,    sh-m,    m,   m  )
    src_t  = QRect(m,       0,       smw, m  )
    src_b  = QRect(m,       sh-m,    smw, m  )
    src_l  = QRect(0,       m,       m,   smh)
    src_r  = QRect(sw-m,    m,       m,   smh)
    src_c  = QRect(m,       m,       smw, smh)

    # dst rects
    dst_tl = QRect(ox,         oy,         m,   m  )
    dst_tr = QRect(ox+tw-m,    oy,         m,   m  )
    dst_bl = QRect(ox,         oy+th-m,    m,   m  )
    dst_br = QRect(ox+tw-m,    oy+th-m,    m,   m  )
    dst_t  = QRect(ox+m,       oy,         tmw, m  )
    dst_b  = QRect(ox+m,       oy+th-m,    tmw, m  )
    dst_l  = QRect(ox,         oy+m,       m,   tmh)
    dst_r  = QRect(ox+tw-m,    oy+m,       m,   tmh)
    dst_c  = QRect(ox+m,       oy+m,       tmw, tmh)

    for dst, src in (
        (dst_tl, src_tl), (dst_tr, src_tr), (dst_bl, src_bl), (dst_br, src_br),
        (dst_t,  src_t),  (dst_b,  src_b),
        (dst_l,  src_l),  (dst_r,  src_r),
        (dst_c,  src_c),
    ):
        painter.drawPixmap(dst, pixmap, src)


_PIXEL_FONT_FAMILY: str | None = None

def _pixel_font() -> str:
    global _PIXEL_FONT_FAMILY
    if _PIXEL_FONT_FAMILY is not None:
        return _PIXEL_FONT_FAMILY
    from PyQt6.QtCore import QByteArray
    font_path = _ASSETS / "fonts" / "monogram-extended.ttf"
    font_data = QByteArray(font_path.read_bytes())
    font_id = QFontDatabase.addApplicationFontFromData(font_data)
    families = QFontDatabase.applicationFontFamilies(font_id)

    # monogram.ttf internal family name is always "monogram"
    _PIXEL_FONT_FAMILY = families[0] if families else "monogram"
    return _PIXEL_FONT_FAMILY


class ChatPopup(QWidget):
    popup_opened = pyqtSignal()
    popup_closed = pyqtSignal()

    STATUS_IDLE      = ""
    STATUS_LISTENING = "Слушаю..."
    STATUS_THINKING  = "Думаю..."

    def __init__(self, parent=None):
        super().__init__(parent)

        raw = QPixmap(str(_ASSETS / "emotions" / "talking" / "talk-00.png"))
        self._raw_bg = raw if not raw.isNull() else QPixmap()

        self._popup_w = max(300, CHAR_SIZE * 2 // 3)

        self._setup_window()
        self._build_ui()

        self._current_text = ""
        self._streaming    = False
        self._mirrored     = False

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(10_000)
        self._hide_timer.timeout.connect(self._auto_hide)

    def _setup_window(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFixedWidth(self._popup_w)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        pad_h = max(10, self._popup_w // 12)
        layout.setContentsMargins(pad_h, 9, pad_h, pad_h)
        layout.setSpacing(2)

        font = QFont(_pixel_font())
        font.setPixelSize(32)
        font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)

        text_color = QColor("#1a1a2e")

        def _make_label(text=""):
            lbl = QLabel(text)
            lbl.setFont(font)
            pal = lbl.palette()
            pal.setColor(QPalette.ColorRole.WindowText, text_color)
            lbl.setPalette(pal)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            return lbl

        self._status_label = _make_label()
        layout.addWidget(self._status_label)

        self._text_label = _make_label()
        self._text_label.setWordWrap(True)
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._text_label.setFixedWidth(self._popup_w - pad_h * 2)
        layout.addWidget(self._text_label)

        self.setLayout(layout)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._mirrored:
            p.translate(self.width(), 0)
            p.scale(-1, 1)
        if not self._raw_bg.isNull():
            _draw_9slice(p, self._raw_bg, self.rect(), _SLICE_MARGIN)
        else:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor(30, 30, 46, 210))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(self.rect(), 14, 14)

    def set_status(self, status: str):
        self._status_label.setText(status)
        visible = bool(status) or bool(self._current_text)
        if visible and not self.isVisible():
            self._show_popup()
        self._status_label.setVisible(bool(status))
        self._adjust_size()

    def on_chunk(self, chunk: str):
        if not self._streaming:
            self._streaming    = True
            self._current_text = ""
        self._current_text += chunk
        # стрипаем все теги включая незакрытые (пришедшие частично при стриминге)
        display = re.sub(r'\[(?:EMOTION|REMEMBER|HOODIE|LISTEN_PC)[^\]]*\]?', '', self._current_text, flags=re.IGNORECASE)
        # срезаем любой незакрытый [ в конце (напр. "[", "[E", "[EM")
        display = re.sub(r'\[[^\]]*$', '', display)
        self._text_label.setText(display.strip())
        self._adjust_size()
        if not self.isVisible():
            self._show_popup()
        self._hide_timer.stop()

    def cancel_hide(self):
        self._hide_timer.stop()

    def restart_hide(self):
        if self._current_text and not self._streaming:
            self._hide_timer.start()

    def on_response_done(self, clean_text: str, emotion: str):
        self._streaming    = False
        self._current_text = clean_text
        self._text_label.setText(clean_text)
        self.set_status(self.STATUS_IDLE)
        self._adjust_size()
        self._hide_timer.start()

    def on_error(self, msg: str):
        self._streaming = False
        self._current_text = f"⚠️ {msg}"
        self._text_label.setText(self._current_text)
        self.set_status(self.STATUS_IDLE)
        self._adjust_size()
        self._hide_timer.start()

    def reposition(self, window):
        screen = QApplication.primaryScreen().availableGeometry()

        x_right = window.pos().x() + window.width() + 10
        x_left  = window.pos().x() - self.width() - 10

        if x_right + self.width() <= screen.width() - 8:
            x = x_right
            mirrored = False
        else:
            x = max(8, x_left)
            mirrored = True

        if mirrored != self._mirrored:
            self._mirrored = mirrored
            self.update()

        y = window.pos().y()
        y = max(8, min(y, screen.height() - self.height() - 8))
        self.move(x, y)

    def mousePressEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()

    def _adjust_size(self):
        self.adjustSize()

    def _show_popup(self):
        self.show()
        self.popup_opened.emit()

    def _auto_hide(self):
        self.hide()
        self._current_text = ""
        self._text_label.setText("")
        self._status_label.setText("")
        self.popup_closed.emit()
