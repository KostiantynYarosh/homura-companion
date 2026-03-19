import random
from enum import Enum

from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QRect
from PyQt6.QtWidgets import QApplication

from config import (
    WALK_SPEED_PX, WALK_TIMER_MS,
    PAUSE_MIN_MS, PAUSE_MAX_MS,
    WALK_MIN_MS, WALK_MAX_MS,
)

class State(Enum):
    IDLE    = "idle"
    WALKING = "walking"
    TALKING = "talking"

class BehaviorEngine(QObject):
    position_changed  = pyqtSignal(int, int)
    direction_changed = pyqtSignal(bool)
    state_changed     = pyqtSignal(str)

    def __init__(self, window_ref, parent=None):
        super().__init__(parent)
        self._win        = window_ref
        self._state      = State.IDLE
        self._walk_dir   = 1
        self._pre_talk_state = State.IDLE

        self._screen_rect: QRect | None = None

        self._walk_timer = QTimer(self)
        self._walk_timer.setInterval(WALK_TIMER_MS)
        self._walk_timer.timeout.connect(self._walk_tick)

        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.timeout.connect(self._transition)

    def start(self):
        self._walk_timer.start()
        self._schedule()

    def _screen(self) -> QRect:
        if self._screen_rect is None:
            self._screen_rect = QApplication.primaryScreen().availableGeometry()
        return self._screen_rect

    def _schedule(self):
        if self._state == State.IDLE:
            delay = random.randint(PAUSE_MIN_MS, PAUSE_MAX_MS)
        else:
            delay = random.randint(WALK_MIN_MS, WALK_MAX_MS)
        self._state_timer.start(delay)

    def _transition(self):
        if self._state == State.IDLE:
            self._set_state(State.WALKING)
            if random.random() < 0.4:
                self._flip()
        elif self._state == State.WALKING:
            self._set_state(State.IDLE)
        self._schedule()

    def _set_state(self, s: State):
        self._state = s
        self.state_changed.emit(s.value)

    def _walk_tick(self):
        if self._state != State.WALKING:
            return
        pos    = self._win.pos()
        scr    = self._screen()
        win_w  = self._win.width()
        new_x  = pos.x() + self._walk_dir * WALK_SPEED_PX

        if new_x <= 0:
            new_x = 0
            self._flip()
        elif new_x + win_w >= scr.width():
            new_x = scr.width() - win_w
            self._flip()

        self.position_changed.emit(new_x, pos.y())

    def _flip(self):
        self._walk_dir *= -1
        self.direction_changed.emit(self._walk_dir == -1)

    def on_manual_move(self):
        self._state_timer.stop()
        self._set_state(State.IDLE)
        self._schedule()

    def set_talking(self, talking: bool):
        if talking:
            self._pre_talk_state = self._state
            self._state_timer.stop()
            self._set_state(State.TALKING)
        else:
            self._set_state(self._pre_talk_state)
            self._schedule()
