# -*- coding: utf-8 -*-
"""Feature-complete Apple Silicon macOS port of LEFTOVER."""
import colorsys
import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageChops, ImageOps
from PySide6.QtCore import QFileInfo, QPoint, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import (QActionGroup, QColor, QCursor, QImage, QMouseEvent,
                           QPainter, QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QFileDialog, QFileIconProvider,
                               QHBoxLayout, QLabel, QMenu, QPushButton,
                               QVBoxLayout, QWidget)
from send2trash import send2trash


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


ASSETS = resource_path("assets")
STATE = Path.home() / "Library" / "Application Support" / "LeftoverPet" / "state-macos.json"
KINDS = ("void", "text", "code", "image", "archive", "metal", "empty", "trash")
COLORS = {
    "void": "#d7ff55", "text": "#d7ff55", "code": "#52e6ff", "image": "#ff4fac",
    "archive": "#a78bfa", "metal": "#e5edf5", "empty": "#84908b", "trash": "#ff9b45",
}
TASTES = {
    "text": "还行，纸味有点重。", "code": "好吃，逻辑是脆的。", "image": "好吃，像素有点甜。",
    "archive": "太实了，得慢慢消化。", "metal": "有点硌牙，但很香。", "empty": "空白最好吃。",
    "trash": "味道复杂，像隔夜剩饭。", "void": "肚子还是空的。",
}
SKINS = {
    "origin": ("原生黑", "#11151b"), "deepsea": ("深海蓝", "#164f68"),
    "glitch": ("故障紫", "#71336f"), "mold": ("霉菌绿", "#526235"),
    "rust": ("锈蚀红", "#7b3b2c"), "pearl": ("珍珠白", "#c7ccd0"),
}


def classify(path):
    if path.is_dir():
        return "archive"
    ext = path.suffix.lower()
    if ext in {".txt", ".md", ".pdf", ".doc", ".docx", ".rtf", ".pages"}: return "text"
    if ext in {".py", ".js", ".ts", ".html", ".css", ".json", ".swift"}: return "code"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".svg", ".mov", ".mp4"}: return "image"
    if ext in {".zip", ".rar", ".7z", ".tar", ".gz", ".dmg", ".pkg"}: return "archive"
    if ext in {".exe", ".dll", ".bin", ".iso", ".app"}: return "metal"
    try:
        return "empty" if path.stat().st_size == 0 else "void"
    except OSError:
        return "void"


def pil_to_pixmap(image):
    image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    qimage = QImage(data, image.width, image.height, image.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


def tinted_pil(image, skin):
    image = image.convert("RGBA")
    if skin == "origin":
        return image
    rgb = tuple(int(SKINS[skin][1][index:index + 2], 16) for index in (1, 3, 5))
    hue = int(colorsys.rgb_to_hsv(*(value / 255 for value in rgb))[0] * 255)
    hsv = image.convert("RGB").convert("HSV")
    _, saturation, value = hsv.split()
    chroma = saturation.point(lambda pixel: 255 if pixel >= 34 else 0)
    visible = value.point(lambda pixel: 255 if pixel >= 30 else 0)
    mask = ImageChops.multiply(chroma, visible)
    target_hue = Image.new("L", image.size, hue)
    target_saturation = Image.new("L", image.size, 18 if skin == "pearl" else 205)
    recolored = Image.merge("HSV", (target_hue, target_saturation, value)).convert("RGBA")
    recolored.putalpha(image.getchannel("A"))
    return Image.composite(recolored, image, mask)


def load_tinted(path, skin):
    return pil_to_pixmap(tinted_pil(Image.open(path), skin))


def draw_centered(painter, pixmap, x, y):
    painter.drawPixmap(round(x - pixmap.width() / 2), round(y - pixmap.height() / 2), pixmap)


def smooth_path(points):
    path = QPainterPath(QPointF(points[0][0], points[0][1]))
    if len(points) == 3:
        start, control, end = points
        path.quadTo(QPointF(control[0], control[1]), QPointF(end[0], end[1]))
    else:
        for point in points[1:]:
            path.lineTo(QPointF(point[0], point[1]))
    return path


class SpeechBubble(QWidget):
    def __init__(self, owner, text, buttons=None):
        super().__init__()
        self.owner = owner
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setStyleSheet("""
            QWidget { background: #f4f0e6; color: #171a17; border: 2px solid #171a17; }
            QLabel { border: none; font-size: 13px; padding: 7px; }
            QPushButton { background: #1c241e; color: white; border: none; padding: 7px 12px; font-size: 12px; }
            QPushButton:hover { background: #334137; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        if buttons:
            row = QHBoxLayout()
            for caption, callback in buttons:
                button = QPushButton(caption)
                button.clicked.connect(lambda _checked=False, cb=callback: cb())
                row.addWidget(button)
            layout.addLayout(row)
        self.setFixedWidth(300)
        self.adjustSize()
        self.reposition()

    def reposition(self):
        screen = QApplication.screenAt(self.owner.frameGeometry().center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = self.owner.x() + (self.owner.width() - self.width()) // 2
        y = self.owner.y() - self.height() - 8
        if y < area.top():
            y = self.owner.y() + self.owner.height() + 8
        x = max(area.left(), min(area.right() - self.width(), x))
        self.move(x, y)


class EffectsWindow(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.sync_geometry()
        self.hide()

    def sync_geometry(self):
        screens = QApplication.screens()
        if not screens:
            return
        union = QRect(screens[0].geometry())
        for screen in screens[1:]:
            union = union.united(screen.geometry())
        self.setGeometry(union)

    def local_point(self, point):
        return QPointF(point.x() - self.x(), point.y() - self.y())

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.translate(-self.x(), -self.y())
        self.owner.paint_effects(painter)


class LeftoverWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("余食 / LEFTOVER")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setFixedSize(220, 235)
        self.kind = "void"
        self.skin = "origin"
        self.pending_kind = None
        self.chew = 0
        self.phase = 0.0
        self.last_activity = time.time()
        self.drag_offset = None
        self.bubble = None
        self.fx_mode = None
        self.fx_started = 0.0
        self.fx_duration = 1.0
        self.travel_start = QPointF()
        self.travel_end = QPointF()
        self.target_positions = []
        self.active_paths = []
        self.icon_proxies = []
        self.bundle_pile = QPointF()
        self.swallow_target = QPointF()
        self.swallow_direction = "right"
        self.deferred_requests = []
        self.load_state()
        self.load_images()
        self.effects = EffectsWindow(self)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(70)
        self.move_bottom_right()

    def load_state(self):
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
            if data.get("kind") in KINDS:
                self.kind = data["kind"]
            if data.get("skin") in SKINS:
                self.skin = data["skin"]
        except (OSError, ValueError, TypeError):
            pass

    def save_state(self):
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"kind": self.kind, "skin": self.skin}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        except OSError:
            pass

    def load_images(self):
        self.states = {kind: load_tinted(ASSETS / f"pet-{kind}.png", self.skin) for kind in KINDS}
        self.mouths = [load_tinted(ASSETS / f"mouth-{index}.png", self.skin) for index in range(4)]
        self.turn_left = load_tinted(ASSETS / "pet-turn-left.png", self.skin)
        self.turn_right = load_tinted(ASSETS / "pet-turn-right.png", self.skin)
        self.peek = load_tinted(ASSETS / "pet-peek.png", self.skin)
        self.liquid = {
            kind: [load_tinted(ASSETS / f"liquid-{kind}-{index}.png", self.skin) for index in range(8)]
            for kind in KINDS
        }
        self.puddle = {
            kind: [load_tinted(ASSETS / f"puddle-{kind}-{index}.png", self.skin) for index in range(8)]
            for kind in KINDS
        }
        widths = (150, 205, 286, 326)
        self.swallow_widths = widths
        self.swallow = {direction: [] for direction in ("left", "right", "up", "down")}
        for index, width in enumerate(widths):
            source = tinted_pil(Image.open(ASSETS / f"swallow-right-{index}.png"), self.skin)
            right = source.resize((width, 218), Image.Resampling.LANCZOS)
            self.swallow["right"].append(pil_to_pixmap(right))
            self.swallow["left"].append(pil_to_pixmap(ImageOps.mirror(right)))
            self.swallow["up"].append(pil_to_pixmap(right.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)))
            self.swallow["down"].append(pil_to_pixmap(right.rotate(-90, expand=True, resample=Image.Resampling.BICUBIC)))

    def current_glow(self):
        return SKINS[self.skin][1] if self.skin != "origin" else COLORS.get(self.kind, COLORS["void"])

    def move_bottom_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24)
        self.sync_bubble()

    def sync_bubble(self):
        if self.bubble and self.bubble.isVisible():
            self.bubble.reposition()

    def close_bubble(self):
        if self.bubble:
            self.bubble.close()
            self.bubble.deleteLater()
            self.bubble = None

    def say(self, text, buttons=None, duration=None):
        self.close_bubble()
        self.bubble = SpeechBubble(self, text, buttons)
        self.bubble.show()
        if duration:
            bubble = self.bubble
            QTimer.singleShot(duration, lambda: self.close_bubble() if self.bubble is bubble else None)

    def current_pixmap(self):
        if self.chew < 0:
            return self.mouths[3]
        if self.chew > 30:
            return self.mouths[1 + (self.chew // 3) % 3]
        if self.chew > 14:
            return self.puddle[self.pending_kind or self.kind][int(self.phase * 1.5) % 8]
        if self.chew > 0:
            return self.liquid[self.pending_kind or self.kind][int(self.phase * 1.7) % 8]
        if time.time() - self.last_activity > 24:
            return self.liquid[self.kind][int(self.phase) % 8]
        return self.states[self.kind]

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        pixmap = self.current_pixmap()
        bob = round(math.sin(self.phase * 1.7) * 2)
        draw_centered(painter, pixmap, self.width() / 2, self.height() / 2 + 7 + bob)

    def set_fx(self, mode, duration):
        self.fx_mode = mode
        self.fx_started = time.monotonic()
        self.fx_duration = duration
        self.effects.sync_geometry()
        self.effects.show()
        self.effects.raise_()
        self.timer.setInterval(16)

    def finish_fx(self):
        self.fx_mode = None
        self.effects.hide()
        self.timer.setInterval(70)

    def animate(self):
        self.phase += .11
        now = time.monotonic()
        if self.fx_mode:
            progress = min(1.0, (now - self.fx_started) / max(.01, self.fx_duration))
            self.effects.update()
            if self.fx_mode == "travel" and progress >= 1:
                self.finish_travel()
            elif self.fx_mode == "bundle" and progress >= 1:
                self.start_swallow()
            elif self.fx_mode == "swallow" and progress >= 1:
                self.finish_swallow()
            elif self.fx_mode == "return" and progress >= 1:
                self.finish_return()
        if self.chew > 0:
            self.chew -= 1
            if self.chew == 0 and self.pending_kind:
                self.kind = self.pending_kind
                self.pending_kind = None
                self.save_state()
        self.update()

    def desktop_position(self, path):
        try:
            if path.parent.resolve() != (Path.home() / "Desktop").resolve():
                return None
            script = """on run argv
tell application \"Finder\"
set targetItem to (POSIX file (item 1 of argv)) as alias
set itemPosition to position of targetItem
return (item 1 of itemPosition as text) & \",\" & (item 2 of itemPosition as text)
end tell
end run"""
            result = subprocess.run(["osascript", "-e", script, str(path)], capture_output=True,
                                    text=True, timeout=2, check=False)
            parts = result.stdout.strip().split(",")
            if len(parts) == 2:
                return QPointF(float(parts[0]), float(parts[1]))
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return None

    def resolve_targets(self, paths, anchor):
        positions = []
        for index, path in enumerate(paths):
            exact = self.desktop_position(path)
            if exact:
                positions.append(exact)
            else:
                offset = index - (len(paths) - 1) / 2
                positions.append(QPointF(anchor.x() + (index % 2) * 28, anchor.y() + offset * 62))
        return positions

    def stop_position_for(self, target):
        point = QPoint(round(target.x()), round(target.y()))
        screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        if target.x() > area.center().x():
            x = target.x() - 210
        else:
            x = target.x() - 10
        y = target.y() - 118
        return QPointF(max(area.left(), min(area.right() - self.width(), x)),
                       max(area.top(), min(area.bottom() - self.height(), y)))

    def summon_files(self, paths, anchor=None):
        paths = [Path(path) for path in paths if Path(path).exists()]
        if not paths:
            return
        if self.fx_mode in {"travel", "bundle", "swallow"} or self.chew:
            for path in paths:
                if path not in self.deferred_requests:
                    self.deferred_requests.append(path)
            return
        self.close_bubble()
        self.active_paths = paths
        anchor = QPointF(anchor or QCursor.pos())
        self.target_positions = self.resolve_targets(paths, anchor)
        average = QPointF(sum(point.x() for point in self.target_positions) / len(self.target_positions),
                          sum(point.y() for point in self.target_positions) / len(self.target_positions))
        self.travel_start = QPointF(self.x(), self.y())
        self.travel_end = self.stop_position_for(average)
        self.last_activity = time.time()
        self.hide()
        self.set_fx("travel", max(.85, min(1.45, math.hypot(self.travel_end.x() - self.x(),
                                                           self.travel_end.y() - self.y()) / 700)))

    def finish_travel(self):
        self.move(round(self.travel_end.x()), round(self.travel_end.y()))
        self.show()
        self.raise_()
        self.fx_mode = "point"
        self.timer.setInterval(55)
        self.effects.update()
        self.confirm_active()

    def confirm_active(self):
        question = "它吗？" if len(self.active_paths) == 1 else "它们吗？"
        self.say(question, [("没戳！", self.accept_active), ("啊搞错了嘿嘿嘿", self.reject_active)])

    def reject_active(self):
        self.close_bubble()
        self.active_paths = []
        self.target_positions = []
        self.return_start = QPointF(self.x(), self.y())
        screen = QApplication.primaryScreen().availableGeometry()
        self.return_end = QPointF(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24)
        self.fx_mode = None
        self.effects.hide()
        self.set_fx("return", 1.0)

    def capture_icons(self, paths):
        provider = QFileIconProvider()
        proxies = []
        for path in paths:
            base = provider.icon(QFileInfo(str(path))).pixmap(64, 64)
            squash = [base.scaled(width, 54, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                      for width in (64, 52, 68, 42, 58)]
            tiles = [base.copy(column * 16, row * 16, 16, 16)
                     for row in range(4) for column in range(4)]
            proxies.append({"base": base, "squash": squash, "tiles": tiles})
        return proxies

    def accept_active(self):
        self.close_bubble()
        self.icon_proxies = self.capture_icons(self.active_paths)
        successful_paths, successful_targets, successful_icons, failures = [], [], [], []
        for path, target, proxy in zip(self.active_paths, self.target_positions, self.icon_proxies):
            try:
                send2trash(str(path))
                successful_paths.append(path)
                successful_targets.append(target)
                successful_icons.append(proxy)
            except Exception:
                failures.append(path.name)
        if not successful_paths:
            self.fx_mode = "point"
            self.say("咬不开。它还留在那里。", [("知道了", self.reject_active)])
            return
        self.active_paths = successful_paths
        self.target_positions = successful_targets
        self.icon_proxies = successful_icons
        self.pending_kind = classify(successful_paths[-1]) if len(successful_paths) == 1 else "trash"
        if failures:
            self.say(f"有 {len(failures)} 个咬不动，先吃掉剩下的。", duration=1800)
        self.set_fx("bundle", min(6.2, .9 + len(successful_paths) * .62))

    def start_swallow(self):
        body = QPointF(self.x() + 110, self.y() + 126)
        targets = self.target_positions or [body]
        average = QPointF(sum(point.x() for point in targets) / len(targets),
                          sum(point.y() for point in targets) / len(targets))
        vector = average - body
        length = max(1.0, math.hypot(vector.x(), vector.y()))
        self.bundle_pile = QPointF(body.x() + vector.x() / length * 82,
                                  body.y() + vector.y() / length * 70)
        self.swallow_target = targets[0] if len(targets) == 1 else self.bundle_pile
        delta = self.swallow_target - body
        if abs(delta.x()) >= abs(delta.y()):
            self.swallow_direction = "right" if delta.x() >= 0 else "left"
        else:
            self.swallow_direction = "down" if delta.y() >= 0 else "up"
        self.hide()
        self.set_fx("swallow", 1.18)

    def finish_swallow(self):
        self.finish_fx()
        self.show()
        self.raise_()
        self.chew = 48
        self.last_activity = time.time()
        self.active_paths = []
        self.target_positions = []
        self.icon_proxies = []
        taste_kind = self.pending_kind or self.kind
        QTimer.singleShot(2900, lambda kind=taste_kind: self.say(TASTES[kind], duration=2600))
        QTimer.singleShot(5800, self.return_to_corner)

    def return_to_corner(self):
        if self.fx_mode or self.drag_offset is not None:
            return
        self.close_bubble()
        self.return_start = QPointF(self.x(), self.y())
        screen = QApplication.primaryScreen().availableGeometry()
        self.return_end = QPointF(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24)
        if math.hypot(self.return_end.x() - self.x(), self.return_end.y() - self.y()) < 10:
            self.process_deferred()
            return
        self.set_fx("return", 1.0)

    def finish_return(self):
        self.move(round(self.return_end.x()), round(self.return_end.y()))
        self.finish_fx()
        self.show()
        self.process_deferred()

    def process_deferred(self):
        if self.deferred_requests:
            paths = self.deferred_requests[:]
            self.deferred_requests.clear()
            QTimer.singleShot(200, lambda: self.summon_files(paths, QCursor.pos()))

    def paint_effects(self, painter):
        if not self.fx_mode:
            return
        progress = min(1.0, (time.monotonic() - self.fx_started) / max(.01, self.fx_duration))
        if self.fx_mode == "travel":
            self.paint_travel(painter, progress)
        elif self.fx_mode == "point":
            self.paint_pointing(painter)
        elif self.fx_mode == "bundle":
            self.paint_bundle(painter, progress)
        elif self.fx_mode == "swallow":
            self.paint_swallow(painter, progress)
        elif self.fx_mode == "return":
            self.paint_return(painter, progress)

    def paint_travel(self, painter, progress):
        start = self.travel_start + QPointF(110, 126)
        end = self.travel_end + QPointF(110, 126)
        delta = end - start
        length = max(1.0, math.hypot(delta.x(), delta.y()))
        normal = QPointF(-delta.y() / length, delta.x() / length)
        glow = QColor(self.current_glow())
        for index in range(52):
            delay = (index % 13) * .008 + (index // 13) * .004
            moving = max(0.0, min(1.0, (progress - .08 - delay) / .76))
            eased = moving * moving * (3 - 2 * moving)
            angle = index * 2.399
            arc = math.sin(math.pi * eased) * (28 + ((index % 5) - 2) * 6)
            spread = (12 + (index % 9) * 5) * min(1, progress / .16) * (1 - max(0, (progress - .72) / .28))
            point = start + delta * eased + normal * arc
            point += QPointF(math.cos(angle + eased * 5) * spread, math.sin(angle + eased * 5) * spread * .68)
            color = glow if index % 6 == 0 else QColor("#24292e" if index % 3 else "#080b0e")
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            size = 3 + index % 5
            if index % 4:
                painter.drawRect(round(point.x() - size), round(point.y() - size), size * 2, size * 2)
            else:
                painter.drawEllipse(point, size, size * .72)

    def paint_pointing(self, painter):
        start = QPointF(self.x() + 108, self.y() + 143)
        targets = self.target_positions[:3]
        glow = QColor(self.current_glow())
        for index, target in enumerate(targets):
            pulse = math.sin(self.phase * 1.7 + index) * 7
            middle = QPointF((start.x() + target.x()) / 2 - pulse,
                             (start.y() + target.y()) / 2 + 18 + pulse)
            path = smooth_path([(start.x(), start.y() + (index - (len(targets) - 1) / 2) * 5),
                                (middle.x(), middle.y()), (target.x(), target.y())])
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#070a0d"), 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            painter.setPen(QPen(QColor("#24292e"), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            painter.setPen(QPen(glow, 1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            painter.setBrush(QColor("#090c0f"))
            painter.drawEllipse(target, 4, 4)

    def pile_point(self):
        body = QPointF(self.x() + 110, self.y() + 126)
        targets = self.target_positions or [body]
        average = QPointF(sum(point.x() for point in targets) / len(targets),
                          sum(point.y() for point in targets) / len(targets))
        delta = average - body
        length = max(1.0, math.hypot(delta.x(), delta.y()))
        return QPointF(body.x() + delta.x() / length * 82, body.y() + delta.y() / length * 70)

    def paint_bundle(self, painter, progress):
        body = QPointF(self.x() + 108, self.y() + 143)
        targets = self.target_positions
        total = max(1, len(targets))
        phase = max(0, min(total - .001, progress * total))
        item = int(phase)
        item_t = phase - item
        target = targets[item % total]
        pile = self.pile_point()
        hand = item % 3
        eased = item_t * item_t * (3 - 2 * item_t)
        moving = target + (pile - target) * eased
        bend = math.sin(item_t * math.pi) * ((hand - 1) * 18 + 14)
        middle = QPointF((body.x() + moving.x()) / 2 - bend, (body.y() + moving.y()) / 2 + 22 + bend)
        path = smooth_path([(body.x(), body.y() + (hand - 1) * 9),
                            (middle.x(), middle.y()), (moving.x(), moving.y())])
        glow = QColor(self.current_glow())
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#050709"), 10, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)
        painter.setPen(QPen(QColor("#282d31"), 6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)
        painter.setPen(QPen(glow, 1, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPath(path)
        proxy = self.icon_proxies[item % len(self.icon_proxies)]
        if item_t < .34:
            frame = min(4, int(item_t / .34 * 5))
            draw_centered(painter, proxy["squash"][frame], moving.x(), moving.y())
        else:
            breakup = min(1.0, (item_t - .34) / .66)
            for tile_index, tile in enumerate(proxy["tiles"]):
                row, column = divmod(tile_index, 4)
                angle = tile_index * 2.399 + item * .7
                base_x = (column - 1.5) * 16 * (1 - breakup)
                base_y = (row - 1.5) * 16 * (1 - breakup)
                scatter = math.sin(breakup * math.pi) * (8 + tile_index % 4 * 3)
                x = moving.x() + base_x + math.cos(angle) * scatter
                y = moving.y() + base_y + math.sin(angle) * scatter * .68
                draw_centered(painter, tile, x, y)
        completed = item + item_t
        pile_size = min(32, 9 + completed * 3)
        painter.setPen(QPen(glow, 1))
        painter.setBrush(QColor("#080b0d"))
        painter.drawEllipse(pile, pile_size, pile_size * .72)
        painter.setPen(glow)
        painter.drawText(round(pile.x() - 12), round(pile.y() - pile_size - 9), 30, 14,
                         Qt.AlignCenter, f"×{total}")

    def paint_swallow(self, painter, progress):
        body = QPointF(self.x() + 110, self.y() + 126)
        if progress < .16: frame = 0
        elif progress < .32: frame = 1
        elif progress < .68: frame = 2
        elif progress < .84: frame = 3
        else: frame = 1
        direction_vectors = {"right": QPointF(1, 0), "left": QPointF(-1, 0),
                             "up": QPointF(0, -1), "down": QPointF(0, 1)}
        vector = direction_vectors[self.swallow_direction]
        extension = (self.swallow_widths[frame] - self.swallow_widths[0]) / 2
        bite = 0 if progress < .68 else math.sin(min(1, (progress - .68) / .32) * math.pi) * 5
        sprite = self.swallow[self.swallow_direction][frame]
        draw_centered(painter, sprite, body.x() + vector.x() * extension, body.y() + vector.y() * extension + bite)
        if len(self.active_paths) > 1 and progress < .76:
            shrink = max(.18, 1 - max(0, (progress - .55) / .21))
            radius = 27 * shrink
            painter.setBrush(QColor("#080b0d"))
            painter.setPen(QPen(QColor(self.current_glow()), 1))
            painter.drawEllipse(self.bundle_pile, radius, radius * .72)
        if progress > .70:
            close = max(0, min(1, (progress - .70) / .25))
            radius = 38 * (1 - close)
            for index in range(10):
                angle = index * 2.399
                point = QPointF(self.swallow_target.x() + math.cos(angle) * radius,
                                self.swallow_target.y() + math.sin(angle) * radius * .65)
                size = max(1, 4 - round(close * 3))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(self.current_glow() if index % 4 == 0 else "#d8d8d2"))
                painter.drawRect(round(point.x() - size), round(point.y() - size), size * 2, size * 2)

    def paint_return(self, painter, progress):
        eased = progress * progress * (3 - 2 * progress)
        position = self.return_start + (self.return_end - self.return_start) * eased
        bob = math.sin(progress * math.pi * 8) * 3 * (1 - progress)
        self.move(round(position.x()), round(position.y() + bob))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.last_activity = time.time()
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.RightButton:
            self.show_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            self.sync_bubble()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_offset = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.chew = -3
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        if self.chew < 0:
            self.chew = 0
        self.update()
        event.accept()

    def dropEvent(self, event):
        self.chew = 0
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        paths = [path for path in paths if path.exists()]
        if paths:
            self.active_paths = paths
            anchor = QPointF(self.x() + self.width() / 2, self.y() + self.height() / 2)
            self.target_positions = self.resolve_targets(paths, anchor)
            self.confirm_active()
        event.acceptProposedAction()

    def choose_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "喂给余食")
        paths = [Path(name) for name in names]
        if paths:
            self.summon_files(paths, QCursor.pos())

    def set_skin(self, skin):
        if skin == self.skin or skin not in SKINS:
            return
        self.skin = skin
        self.load_images()
        self.save_state()
        self.last_activity = time.time()
        self.update()
        self.say(f"换好了。{SKINS[skin][0]}。", duration=1800)

    def show_menu(self, position):
        menu = QMenu(self)
        feed = menu.addAction("选择文件喂给余食…")
        feed.triggered.connect(self.choose_files)
        finder_help = menu.addAction("Finder 右键喂食说明")
        finder_help.triggered.connect(lambda: self.say("在 Finder 选中文件，右键打开“快速操作”或“服务”，选择“喂给余食”。", duration=4200))
        trash = menu.addAction("打开废纸篓")
        trash.triggered.connect(lambda: subprocess.Popen(["open", str(Path.home() / ".Trash")]))
        corner = menu.addAction("回到右下角")
        corner.triggered.connect(self.return_to_corner)
        skin_menu = menu.addMenu("更换皮肤")
        skin_group = QActionGroup(skin_menu)
        skin_group.setExclusive(True)
        for key, (name, _color) in SKINS.items():
            action = skin_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(key == self.skin)
            action.triggered.connect(lambda _checked=False, value=key: self.set_skin(value))
            skin_group.addAction(action)
        menu.addSeparator()
        quit_action = menu.addAction("退出余食")
        quit_action.triggered.connect(QApplication.quit)
        menu.exec(position)

    def closeEvent(self, event):
        self.save_state()
        self.close_bubble()
        self.effects.close()
        event.accept()


_service_provider = None


def register_finder_service(window):
    global _service_provider
    try:
        import Cocoa
        import objc

        def service_selector(function):
            return objc.selector(function, signature=b"v@:@@o^@")

        class FinderServiceProvider(Cocoa.NSObject):
            @service_selector
            def feedToLeftover_userData_error_(self, pasteboard, _data, _error):
                try:
                    paths = pasteboard.propertyListForType_(Cocoa.NSFilenamesPboardType) or []
                    if not paths:
                        urls = pasteboard.readObjectsForClasses_options_(
                            [Cocoa.NSURL], {Cocoa.NSPasteboardURLReadingFileURLsOnlyKey: True}) or []
                        paths = [url.path() for url in urls]
                    paths = [str(path) for path in paths if Path(str(path)).exists()]
                    if paths:
                        cursor = QCursor.pos()
                        QTimer.singleShot(0, lambda selected=paths, point=cursor: window.summon_files(selected, point))
                    return None
                except Exception as error:
                    return str(error)

        _service_provider = FinderServiceProvider.alloc().init()
        Cocoa.NSApplication.sharedApplication().setServicesProvider_(_service_provider)
        Cocoa.NSUpdateDynamicServices()
        return True
    except Exception:
        return False


def main():
    if sys.platform != "darwin":
        raise SystemExit("This build is for macOS.")
    app = QApplication(sys.argv)
    app.setApplicationName("余食 LEFTOVER")
    app.setQuitOnLastWindowClosed(False)
    window = LeftoverWindow()
    finder_service_ok = register_finder_service(window)
    if "--self-test" in sys.argv:
        checks = {
            "states": len(window.states) == len(KINDS),
            "mouths": len(window.mouths) == 4,
            "swallow": all(len(frames) == 4 for frames in window.swallow.values()),
            "finder_service": finder_service_ok,
        }
        print(json.dumps(checks, sort_keys=True))
        window.close()
        return 0 if all(checks.values()) else 1
    window.show()
    QTimer.singleShot(900, lambda: window.say(
        "Finder 右键“喂给余食”已注册。" if finder_service_ok
        else "Finder 服务没有注册成功，仍可直接拖文件给我。", duration=3000))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
