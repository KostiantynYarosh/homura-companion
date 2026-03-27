import struct
import zlib
import random
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRect, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap, QImage, QColor, QBrush, QPainterPath, QPen

from config import CHAR_SIZE, WINDOW_MARGIN, EMOTION_COLORS

_ASSETS = Path(__file__).parent / "assets"

_SIDE_EYE_MIN_MS  = 45_000
_SIDE_EYE_MAX_MS  = 90_000
_FOOT_STOMP_MIN_MS = 20_000
_FOOT_STOMP_MAX_MS = 60_000
_FOOT_STOMP_REPEATS = 5
_RIGHT_FOOT_MIN_MS  = 25_000
_RIGHT_FOOT_MAX_MS  = 65_000
_RIGHT_FOOT_REPEATS = 5
_TIPY_TOES_MIN_MS  = 30_000
_TIPY_TOES_MAX_MS  = 75_000
_TIPY_TOES_REPEATS = 5
_LEFT_EAR_MIN_MS   = 25_000
_LEFT_EAR_MAX_MS   = 60_000
_LEFT_EAR_REPEATS  = 1
_RIGHT_EAR_MIN_MS  = 30_000
_RIGHT_EAR_MAX_MS  = 70_000
_RIGHT_EAR_REPEATS = 1
_YAWN_MIN_MS       = 240_000   # 4 мин
_YAWN_MAX_MS       = 480_000   # 8 мин


def _load_ase(filename: str) -> list[tuple[QPixmap, int]]:
    path = _ASSETS / filename
    try:
        data = path.read_bytes()
    except OSError:
        return []

    if len(data) < 128 or struct.unpack_from('<H', data, 4)[0] != 0xA5E0:
        return []

    num_frames = struct.unpack_from('<H', data, 6)[0]
    canvas_w   = struct.unpack_from('<H', data, 8)[0]
    canvas_h   = struct.unpack_from('<H', data, 10)[0]
    depth      = struct.unpack_from('<H', data, 12)[0]
    transp_idx = struct.unpack_from('<B', data, 28)[0]
    bpp        = depth // 8

    palette = np.zeros((256, 4), dtype=np.uint8)
    palette[:, 3] = 255

    layer_vis: dict[int, bool] = {}
    layer_count = 0
    raw_frames: list[list] = []

    pos = 128
    for _ in range(num_frames):
        if pos + 16 > len(data):
            break
        f_size  = struct.unpack_from('<I', data, pos)[0]
        f_magic = struct.unpack_from('<H', data, pos + 4)[0]
        if f_magic != 0xF1FA:
            pos += f_size
            continue

        old_nc  = struct.unpack_from('<H', data, pos + 6)[0]
        dur_ms  = struct.unpack_from('<H', data, pos + 8)[0]
        nchunks = struct.unpack_from('<I', data, pos + 12)[0] or old_nc

        chunk_pos = pos + 16
        pos       = pos + f_size

        frame_cels: list[list] = []

        for _ in range(nchunks):
            if chunk_pos + 6 > len(data):
                break
            c_size = struct.unpack_from('<I', data, chunk_pos)[0]
            c_type = struct.unpack_from('<H', data, chunk_pos + 4)[0]
            cd     = chunk_pos + 6
            ce     = chunk_pos + c_size
            chunk_pos = ce

            if c_type == 0x2004:
                flags = struct.unpack_from('<H', data, cd)[0]
                layer_vis[layer_count] = bool(flags & 1)
                layer_count += 1

            elif c_type == 0x2005:
                l_idx = struct.unpack_from('<H', data, cd)[0]
                x     = struct.unpack_from('<h', data, cd + 2)[0]
                y     = struct.unpack_from('<h', data, cd + 4)[0]
                op    = struct.unpack_from('<B', data, cd + 6)[0]
                ctype = struct.unpack_from('<H', data, cd + 7)[0]
                pd    = cd + 16

                if ctype == 0:
                    cw = struct.unpack_from('<H', data, pd)[0]
                    ch = struct.unpack_from('<H', data, pd + 2)[0]
                    nb = cw * ch * bpp
                    frame_cels.append([l_idx, x, y, op, bytes(data[pd + 4: pd + 4 + nb]), cw, ch])

                elif ctype == 2:
                    cw = struct.unpack_from('<H', data, pd)[0]
                    ch = struct.unpack_from('<H', data, pd + 2)[0]
                    try:
                        pix = zlib.decompress(data[pd + 4: ce])
                    except Exception:
                        pix = bytes(cw * ch * bpp)
                    frame_cels.append([l_idx, x, y, op, pix, cw, ch])

                elif ctype == 1:
                    linked = struct.unpack_from('<H', data, pd)[0]
                    frame_cels.append([l_idx, x, y, op, None, 0, 0, linked])

            elif c_type == 0x2019:
                first = struct.unpack_from('<I', data, cd + 4)[0]
                last  = struct.unpack_from('<I', data, cd + 8)[0]
                ep    = cd + 20
                for i in range(first, last + 1):
                    if ep + 6 > len(data):
                        break
                    eflags = struct.unpack_from('<H', data, ep)[0]
                    r, g, b, a = struct.unpack_from('BBBB', data, ep + 2)
                    palette[i] = [r, g, b, a]
                    ep += 6
                    if eflags & 1 and ep + 2 <= len(data):
                        ep += 2 + struct.unpack_from('<H', data, ep)[0]

        raw_frames.append([dur_ms, frame_cels])

    for fi, (_, cels) in enumerate(raw_frames):
        for cel in cels:
            if len(cel) == 8 and cel[4] is None:
                linked_fi = cel[7]
                if linked_fi < len(raw_frames):
                    for src in raw_frames[linked_fi][1]:
                        if src[0] == cel[0] and src[4] is not None:
                            cel[1], cel[2] = src[1], src[2]
                            cel[4], cel[5], cel[6] = src[4], src[5], src[6]
                            break

    result: list[tuple[QPixmap, int]] = []
    for dur_ms, cels in raw_frames:
        buf = np.zeros((canvas_h, canvas_w, 4), dtype=np.uint8)

        for cel in cels:
            l_idx, x, y, cel_op, pixels, cw, ch = cel[:7]
            if pixels is None or cw == 0 or ch == 0:
                continue
            if not layer_vis.get(l_idx, True):
                continue
            nb = cw * ch * bpp
            if len(pixels) < nb:
                continue

            if depth == 32:
                src = np.frombuffer(pixels[:nb], dtype=np.uint8).reshape(ch, cw, 4).copy()
            elif depth == 8:
                idx_arr = np.frombuffer(pixels[:nb], dtype=np.uint8).reshape(ch, cw)
                src = palette[idx_arr].copy()
                src[idx_arr == transp_idx, 3] = 0
            else:
                continue

            src[:, :, 3] = (src[:, :, 3].astype(np.uint16) * cel_op // 255).astype(np.uint8)

            sx0, sy0 = max(0, -x), max(0, -y)
            sx1 = min(cw, canvas_w - x)
            sy1 = min(ch, canvas_h - y)
            if sx1 <= sx0 or sy1 <= sy0:
                continue

            dx0, dy0 = x + sx0, y + sy0
            dh, dw   = sy1 - sy0, sx1 - sx0
            s = src[sy0:sy1, sx0:sx1]
            d = buf[dy0:dy0 + dh, dx0:dx0 + dw]

            sa = s[:, :, 3:4].astype(np.uint16)
            da = d[:, :, 3:4].astype(np.uint16)
            out_a  = (sa + da * (255 - sa) // 255).clip(0, 255)
            safe_a = np.where(out_a > 0, out_a, 1)
            out_rgb = (
                s[:, :, :3].astype(np.uint32) * sa +
                d[:, :, :3].astype(np.uint32) * da * (255 - sa) // 255
            ) // safe_a

            buf[dy0:dy0 + dh, dx0:dx0 + dw, :3] = out_rgb.clip(0, 255).astype(np.uint8)
            buf[dy0:dy0 + dh, dx0:dx0 + dw, 3]  = out_a[:, :, 0].astype(np.uint8)

        img = QImage(buf.tobytes(), canvas_w, canvas_h, canvas_w * 4, QImage.Format.Format_RGBA8888)
        result.append((QPixmap.fromImage(img), max(dur_ms, 16)))

    return result


class _SpriteLoader(QThread):
    sprites_ready = pyqtSignal(list, list, list, list, list, list, list, list, list, list, list)

    def run(self):
        breathing        = _load_ase("idle/idle-breathing.ase")
        side_eye         = _load_ase("idle/idle-side-eye.ase")
        foot_stomp       = _load_ase("idle/idle-stoping-left-foot.ase")
        right_foot       = _load_ase("idle/idle-stoping-right-foot.ase")
        tipy_toes        = _load_ase("idle/idle-tipy-toes.ase")
        hoodie           = _load_ase("idle/idle-hoodie.ase")
        hoodie_breathing = _load_ase("idle/idle-hoodie-breathing.ase")
        left_ear         = _load_ase("idle/idle-move-left-ear.ase")
        right_ear        = _load_ase("idle/idle-move-right-ear.ase")
        talking          = _load_ase("emotions/talking/talking.ase")
        yawn             = _load_ase("idle/idle-yawn.ase")
        self.sprites_ready.emit(breathing, side_eye, foot_stomp, right_foot, tipy_toes, hoodie, hoodie_breathing, left_ear, right_ear, talking, yawn)


class CharacterWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(CHAR_SIZE, CHAR_SIZE)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self._flipped          = False
        self._in_side_eye      = False
        self._in_foot_stomp    = False
        self._foot_stomp_count = 0
        self._in_right_foot    = False
        self._right_foot_count = 0
        self._in_tipy_toes     = False
        self._tipy_toes_count  = 0
        self._in_hoodie        = False
        self._hoodie_on        = False
        self._in_left_ear      = False
        self._left_ear_count   = 0
        self._in_right_ear     = False
        self._right_ear_count  = 0
        self._in_yawn          = False
        self._emotion          = "neutral"
        self._glow_alpha       = 0       # 0..255, анимируется
        self._glow_color       = QColor("#7EB8F7")

        self._breathing:        list = []
        self._side_eye:         list = []
        self._foot_stomp:       list = []
        self._right_foot:       list = []
        self._tipy_toes:        list = []
        self._hoodie:           list = []
        self._hoodie_breathing: list = []
        self._left_ear:         list = []
        self._right_ear:        list = []
        self._yawn:             list = []
        self._talking:          list = []
        self._is_talking        = False
        self._frames    = self._breathing
        self._frame_idx = 0

        self._anim_timer = QTimer(self)
        self._anim_timer.setSingleShot(True)
        self._anim_timer.timeout.connect(self._next_frame)

        self._side_eye_timer = QTimer(self)
        self._side_eye_timer.setSingleShot(True)
        self._side_eye_timer.timeout.connect(self._trigger_side_eye)

        self._foot_stomp_timer = QTimer(self)
        self._foot_stomp_timer.setSingleShot(True)
        self._foot_stomp_timer.timeout.connect(self._trigger_foot_stomp)

        self._right_foot_timer = QTimer(self)
        self._right_foot_timer.setSingleShot(True)
        self._right_foot_timer.timeout.connect(self._trigger_right_foot)

        self._tipy_toes_timer = QTimer(self)
        self._tipy_toes_timer.setSingleShot(True)
        self._tipy_toes_timer.timeout.connect(self._trigger_tipy_toes)

        self._left_ear_timer = QTimer(self)
        self._left_ear_timer.setSingleShot(True)
        self._left_ear_timer.timeout.connect(self._trigger_left_ear)

        self._right_ear_timer = QTimer(self)
        self._right_ear_timer.setSingleShot(True)
        self._right_ear_timer.timeout.connect(self._trigger_right_ear)

        self._yawn_timer = QTimer(self)
        self._yawn_timer.setSingleShot(True)
        self._yawn_timer.timeout.connect(self._trigger_yawn)

        # таймер возврата из эмоции в idle
        self._emotion_timer = QTimer(self)
        self._emotion_timer.setSingleShot(True)
        self._emotion_timer.timeout.connect(self._end_emotion)

        # таймер fade-in/out свечения (тикает каждые 30ms)
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(30)
        self._glow_timer.timeout.connect(self._tick_glow)
        self._glow_target = 0   # целевой alpha свечения

        self._loader = _SpriteLoader(self)
        self._loader.sprites_ready.connect(self._on_sprites_ready)
        self._loader.start()

    def _resize_for(self, frames: list):
        if frames:
            px, _ = frames[0]
            new_w = round(CHAR_SIZE * px.width() / px.height()) if px.height() > 0 else CHAR_SIZE
        else:
            new_w = CHAR_SIZE
        if self.width() != new_w:
            self.setFixedSize(new_w, CHAR_SIZE)
            if self.parentWidget():
                self.parentWidget().setFixedSize(
                    new_w + WINDOW_MARGIN * 2,
                    CHAR_SIZE + WINDOW_MARGIN * 2,
                )

    def _set_frames(self, frames: list, idx: int = 0):
        self._frames    = frames
        self._frame_idx = idx
        self._resize_for(frames)

    def _on_sprites_ready(self, breathing: list, side_eye: list, foot_stomp: list, right_foot: list, tipy_toes: list, hoodie: list, hoodie_breathing: list, left_ear: list, right_ear: list, talking: list, yawn: list):
        self._breathing        = breathing
        self._side_eye         = side_eye
        self._foot_stomp       = foot_stomp
        self._right_foot       = right_foot
        self._tipy_toes        = tipy_toes
        self._hoodie           = hoodie
        self._hoodie_breathing = hoodie_breathing
        self._left_ear         = left_ear
        self._right_ear        = right_ear
        self._talking          = talking
        self._yawn             = yawn
        self._set_frames(self._idle_frames)

        self._schedule_frame()
        self._schedule_side_eye()
        self._schedule_foot_stomp()
        self._schedule_right_foot()
        self._schedule_tipy_toes()
        self._schedule_left_ear()
        self._schedule_right_ear()
        self._schedule_yawn()
        self.update()

    @property
    def _idle_frames(self) -> list:
        return self._hoodie_breathing if self._hoodie_on else self._breathing

    def _schedule_frame(self):
        if self._frames:
            _, dur = self._frames[self._frame_idx]
            self._anim_timer.start(dur)

    def _next_frame(self):
        if not self._frames:
            return
        self._frame_idx += 1
        if self._frame_idx >= len(self._frames):
            # talking: зациклить если стриминг ещё идёт, иначе вернуться в idle
            if self._is_talking:
                if self._talking and self._frames is self._talking:
                    self._frame_idx = 0
                    self.update()
                    self._schedule_frame()
                else:
                    self.stop_talking()
                return
            if self._in_hoodie:
                self._end_hoodie()
                return
            if self._in_side_eye:
                self._end_side_eye()
                return
            if self._in_foot_stomp:
                self._foot_stomp_count += 1
                if self._foot_stomp_count >= _FOOT_STOMP_REPEATS:
                    self._end_foot_stomp()
                    return
                self._frame_idx = 0
            elif self._in_right_foot:
                self._right_foot_count += 1
                if self._right_foot_count >= _RIGHT_FOOT_REPEATS:
                    self._end_right_foot()
                    return
                self._frame_idx = 0
            elif self._in_tipy_toes:
                self._tipy_toes_count += 1
                if self._tipy_toes_count >= _TIPY_TOES_REPEATS:
                    self._end_tipy_toes()
                    return
                self._frame_idx = 0
            elif self._in_left_ear:
                self._left_ear_count += 1
                if self._left_ear_count >= _LEFT_EAR_REPEATS:
                    self._end_left_ear()
                    return
                self._frame_idx = 0
            elif self._in_right_ear:
                self._right_ear_count += 1
                if self._right_ear_count >= _RIGHT_EAR_REPEATS:
                    self._end_right_ear()
                    return
                self._frame_idx = 0
            elif self._in_yawn:
                self._end_yawn()
                return
            else:
                self._frame_idx = 0
        self.update()
        self._schedule_frame()

    def _schedule_side_eye(self):
        self._side_eye_timer.start(random.randint(_SIDE_EYE_MIN_MS, _SIDE_EYE_MAX_MS))

    def _trigger_side_eye(self):
        if not self._side_eye or self._hoodie_on:
            self._schedule_side_eye()
            return
        self._in_side_eye = True
        self._set_frames(self._side_eye)
        self.update()
        self._schedule_frame()

    def _end_side_eye(self):
        self._in_side_eye = False
        self._set_frames(self._idle_frames)
        self.update()
        self._schedule_frame()
        self._schedule_side_eye()

    def _schedule_foot_stomp(self):
        self._foot_stomp_timer.start(random.randint(_FOOT_STOMP_MIN_MS, _FOOT_STOMP_MAX_MS))

    def _trigger_foot_stomp(self):
        if not self._foot_stomp or self._in_side_eye or self._in_foot_stomp or self._hoodie_on:
            self._schedule_foot_stomp()
            return
        self._in_foot_stomp    = True
        self._foot_stomp_count = 0
        self._set_frames(self._foot_stomp)
        self.update()
        self._schedule_frame()

    def _end_foot_stomp(self):
        self._in_foot_stomp = False
        self._set_frames(self._idle_frames)
        self.update()
        self._schedule_frame()
        self._schedule_foot_stomp()

    def _schedule_right_foot(self):
        self._right_foot_timer.start(random.randint(_RIGHT_FOOT_MIN_MS, _RIGHT_FOOT_MAX_MS))

    def _trigger_right_foot(self):
        if not self._right_foot or self._in_side_eye or self._in_foot_stomp or self._in_right_foot or self._in_tipy_toes or self._hoodie_on:
            self._schedule_right_foot()
            return
        self._in_right_foot    = True
        self._right_foot_count = 0
        self._set_frames(self._right_foot)
        self.update()
        self._schedule_frame()

    def _end_right_foot(self):
        self._in_right_foot = False
        self._set_frames(self._idle_frames)
        self.update()
        self._schedule_frame()
        self._schedule_right_foot()

    def _schedule_tipy_toes(self):
        self._tipy_toes_timer.start(random.randint(_TIPY_TOES_MIN_MS, _TIPY_TOES_MAX_MS))

    def _trigger_tipy_toes(self):
        if not self._tipy_toes or self._in_side_eye or self._in_foot_stomp or self._in_tipy_toes or self._hoodie_on:
            self._schedule_tipy_toes()
            return
        self._in_tipy_toes    = True
        self._tipy_toes_count = 0
        self._set_frames(self._tipy_toes)
        self.update()
        self._schedule_frame()

    def _end_tipy_toes(self):
        self._in_tipy_toes = False
        self._set_frames(self._idle_frames)
        self.update()
        self._schedule_frame()
        self._schedule_tipy_toes()

    def _schedule_left_ear(self):
        self._left_ear_timer.start(random.randint(_LEFT_EAR_MIN_MS, _LEFT_EAR_MAX_MS))

    def _trigger_left_ear(self):
        if not self._left_ear or self._in_side_eye or self._in_foot_stomp or self._in_right_foot or self._in_tipy_toes or self._in_left_ear or self._in_right_ear or self._hoodie_on:
            self._schedule_left_ear()
            return
        self._in_left_ear    = True
        self._left_ear_count = 0
        self._set_frames(self._left_ear)
        self.update()
        self._schedule_frame()

    def _end_left_ear(self):
        self._in_left_ear = False
        self._set_frames(self._idle_frames)
        self.update()
        self._schedule_frame()
        self._schedule_left_ear()

    def _schedule_right_ear(self):
        self._right_ear_timer.start(random.randint(_RIGHT_EAR_MIN_MS, _RIGHT_EAR_MAX_MS))

    def _trigger_right_ear(self):
        if not self._right_ear or self._in_side_eye or self._in_foot_stomp or self._in_right_foot or self._in_tipy_toes or self._in_left_ear or self._in_right_ear or self._hoodie_on:
            self._schedule_right_ear()
            return
        self._in_right_ear    = True
        self._right_ear_count = 0
        self._set_frames(self._right_ear)
        self.update()
        self._schedule_frame()

    def _end_right_ear(self):
        self._in_right_ear = False
        self._set_frames(self._idle_frames)
        self.update()
        self._schedule_frame()
        self._schedule_right_ear()

    def _schedule_yawn(self):
        self._yawn_timer.start(random.randint(_YAWN_MIN_MS, _YAWN_MAX_MS))

    def _trigger_yawn(self):
        busy = (self._in_side_eye or self._in_foot_stomp or self._in_right_foot
                or self._in_tipy_toes or self._in_left_ear or self._in_right_ear
                or self._in_yawn or self._is_talking or self._hoodie_on)
        if not self._yawn or busy:
            self._schedule_yawn()
            return
        self._in_yawn = True
        self._set_frames(self._yawn)
        self.update()
        self._schedule_frame()

    def _end_yawn(self):
        self._in_yawn = False
        self._set_frames(self._idle_frames)
        self.update()
        self._schedule_frame()
        self._schedule_yawn()

    def _end_hoodie(self):
        self._in_hoodie = False
        self._set_frames(self._hoodie_breathing)
        self.update()
        self._schedule_frame()

    def put_on_hoodie(self):
        if self._hoodie_on or not self._hoodie:
            return
        self._hoodie_on    = True
        self._in_hoodie    = True
        self._in_side_eye  = False
        self._in_foot_stomp = False
        self._in_right_foot = False
        self._in_tipy_toes  = False
        self._set_frames(self._hoodie)
        self.update()
        self._schedule_frame()

    def take_off_hoodie(self):
        if not self._hoodie_on:
            return
        self._hoodie_on = False
        self._in_hoodie = False
        self._set_frames(self._breathing)
        self.update()
        self._schedule_frame()

    def set_flipped(self, flipped: bool):
        if self._flipped != flipped:
            self._flipped = flipped
            self.update()

    def start_talking(self):
        if not self._talking or self._is_talking:
            return
        self._is_talking = True
        self._emotion_timer.stop()
        self._set_frames(self._talking)
        self.update()
        self._schedule_frame()

    def stop_talking(self):
        if not self._is_talking:
            return
        self._is_talking = False
        self._anim_timer.stop()
        self._set_frames(self._idle_frames)
        self._frame_idx = 0
        self.update()
        self._schedule_frame()

    def _tick_glow(self):
        step = 8
        if self._glow_alpha < self._glow_target:
            self._glow_alpha = min(self._glow_alpha + step, self._glow_target)
        elif self._glow_alpha > self._glow_target:
            self._glow_alpha = max(self._glow_alpha - step, self._glow_target)
        if self._glow_alpha == self._glow_target:
            if self._glow_target == 0:
                self._glow_timer.stop()
        self.update()

    def _set_glow(self, emotion: str):
        hex_color = EMOTION_COLORS.get(emotion, "")
        if not hex_color or emotion == "neutral":
            self._glow_target = 0
        else:
            self._glow_color = QColor(hex_color)
            self._glow_target = 90   # max alpha свечения (полупрозрачное)
        self._glow_timer.start()

    def _end_emotion(self):
        # возврат к idle после эмоциональной анимации
        self._set_frames(self._idle_frames)
        self.update()
        self._schedule_frame()
        # начинаем fade-out свечения
        self._glow_target = 0

    def set_emotion(self, emotion: str):
        emotion = emotion.lower().strip()
        self._emotion = emotion
        self._set_glow(emotion)

        ase_path = _ASSETS / "emotions" / f"{emotion}.ase"
        frames = _load_ase(f"emotions/{emotion}.ase") if ase_path.exists() else []
        if not frames:
            folder = _ASSETS / "emotions" / emotion
            if folder.is_dir():
                for ase_file in sorted(folder.glob("*.ase")):
                    frames = _load_ase(f"emotions/{emotion}/{ase_file.name}")
                    if frames:
                        break
        if frames:
            self._emotion_timer.stop()
            self._set_frames(frames)
            self.update()
            self._schedule_frame()
            # возврат к idle через длительность анимации × 2 (минимум 3 сек)
            total_ms = sum(d for _, d in frames)
            self._emotion_timer.start(max(total_ms, 3000))

    def set_state(self, state: str):
        pass

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._frames:
            px, _ = self._frames[self._frame_idx % len(self._frames)]
            if self._flipped:
                p.save()
                p.translate(self.width(), 0)
                p.scale(-1, 1)
            p.drawPixmap(QRect(0, 0, self.width(), self.height()), px, px.rect())
            if self._flipped:
                p.restore()
        else:
            self._paint_fallback(p)

    def _paint_fallback(self, p: QPainter):
        w, h, m = self.width(), self.height(), 6
        p.setBrush(QBrush(QColor("#7EB8F7")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(m, m, w - m * 2, h - m * 2, 16, 16)
        p.setBrush(QBrush(QColor(255, 255, 255, 60)))
        p.drawRoundedRect(m + 4, m + 4, (w - m * 2) // 2, (h - m * 2) // 3, 10, 10)
        cx    = w // 2
        eye_y = m + (h - m * 2) * 2 // 5
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#1a1a2e")))
        lx = cx - 11 if not self._flipped else cx + 11
        rx = cx + 11 if not self._flipped else cx - 11
        p.drawEllipse(QRectF(lx - 4, eye_y - 4, 8, 8))
        p.drawEllipse(QRectF(rx - 4, eye_y - 4, 8, 8))
        p.setBrush(QBrush(QColor(255, 255, 255, 200)))
        p.drawEllipse(QRectF(lx - 1, eye_y - 4, 3, 3))
        p.drawEllipse(QRectF(rx - 1, eye_y - 4, 3, 3))
        mouth_y = m + (h - m * 2) * 3 // 4
        pen = QPen(QColor("#1a1a2e"), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - 7, mouth_y)
        path.lineTo(cx + 7, mouth_y)
        p.drawPath(path)
