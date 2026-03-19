from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer
from PyQt6.QtGui import QPainter, QColor

from config import CHAR_SIZE, WINDOW_MARGIN

class CompanionWindow(QWidget):
    clicked        = pyqtSignal()
    manually_moved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._setup_window()
        self._drag_offset: QPoint | None = None
        self._click_pending = False
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(200)
        self._click_timer.timeout.connect(self._emit_click)

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
        size = CHAR_SIZE + WINDOW_MARGIN * 2
        self.setFixedSize(size, size)

    def set_always_on_top(self, on_top: bool):
        flags = self.windowFlags()
        flags &= ~Qt.WindowType.WindowStaysOnTopHint
        flags &= ~Qt.WindowType.WindowStaysOnBottomHint
        if on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags |= Qt.WindowType.WindowStaysOnBottomHint
        self.setWindowFlags(flags)
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._click_pending = True

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_offset:
            delta = event.globalPosition().toPoint() - self._drag_offset - self.pos()
            if delta.manhattanLength() > 3:
                self._click_pending = False
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            screen  = QApplication.primaryScreen().availableGeometry()
            x = max(0, min(new_pos.x(), screen.width()  - self.width()))
            y = max(0, min(new_pos.y(), screen.height() - self.height()))
            self.move(x, y)
            self.manually_moved.emit()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            if self._click_pending:
                self._click_pending = False
                self._click_timer.start()

    def _emit_click(self):
        self.clicked.emit()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))
