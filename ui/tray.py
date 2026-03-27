from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PyQt6.QtCore import QObject, pyqtSignal, Qt

class SystemTrayManager(QObject):
    toggle_top_requested = pyqtSignal(bool)
    hide_requested       = pyqtSignal()
    show_requested       = pyqtSignal()
    quit_requested       = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on_top = True
        self._tray   = None

    def initialize(self):
        icon = self._make_icon()

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("Companion")

        menu = QMenu()

        self._top_action = QAction("Поверх окон: ВКЛ", menu)
        self._top_action.triggered.connect(self._toggle_top)
        menu.addAction(self._top_action)

        menu.addSeparator()

        hide_a = QAction("Скрыть", menu)
        hide_a.triggered.connect(self.hide_requested)
        menu.addAction(hide_a)

        show_a = QAction("Показать", menu)
        show_a.triggered.connect(self.show_requested)
        menu.addAction(show_a)

        menu.addSeparator()

        quit_a = QAction("Выйти", menu)
        quit_a.triggered.connect(self.quit_requested)
        menu.addAction(quit_a)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _make_icon(self) -> QIcon:

        icon = QIcon("assets/tray_icon.png")
        if not icon.isNull():
            return icon

        px = QPixmap(32, 32)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#7EB8F7"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(2, 2, 28, 28, 8, 8)
        p.setBrush(QColor("#1a1a2e"))
        p.drawEllipse(9, 11, 5, 5)
        p.drawEllipse(18, 11, 5, 5)
        p.end()
        return QIcon(px)

    def _toggle_top(self):
        self._on_top = not self._on_top
        label = "ВКЛ" if self._on_top else "ВЫКЛ"
        self._top_action.setText(f"Поверх окон: {label}")
        self.toggle_top_requested.emit(self._on_top)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_requested.emit()
