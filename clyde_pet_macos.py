"""Clyde desktop pet for Apple Silicon macOS, built with Qt."""
import math
import random
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QActionGroup, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QWidget
from send2trash import send2trash


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


ASSETS = resource_path("clyde-assets")


def scaled(path, max_width=210, max_height=195):
    pixmap = QPixmap(str(path))
    return pixmap.scaled(max_width, max_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class ClydeWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clyde")
        # Keep Clyde visible across apps without re-raising the animated window
        # on every application-state change, which can make macOS focus flicker.
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setFixedSize(230, 230)
        self.mode = "awake"
        self.state = "sit"
        self.facing = "left"
        self.drag_offset = None
        self.frame_index = 0
        self.last_frame = time.monotonic()
        self.move_from = None
        self.move_to = None
        self.move_started = 0.0
        self.move_duration = 1.0
        self.next_action_at = time.monotonic() + 5
        self.pending_files = []
        self.chew_step = 0
        self.load_images()
        self.move_bottom_right()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        # A transparent always-on-top window is expensive to composite on
        # macOS. Use an adaptive cadence instead of repainting at 60+ FPS even
        # while Clyde is sitting or asleep.
        self.timer.start(125)

    def set_timer_interval(self, milliseconds):
        if self.timer.interval() != milliseconds:
            self.timer.setInterval(milliseconds)

    def load_images(self):
        sprites = ASSETS / "sprites"
        self.sit = {"right": scaled(sprites / "clyde-sit.png"),
                    "left": scaled(sprites / "clyde-sit.png").transformed(self.flip())}
        self.headbutt = {"right": scaled(sprites / "clyde-headbutt.png"),
                        "left": scaled(sprites / "clyde-headbutt.png").transformed(self.flip())}
        self.run_frames = {"right": [], "left": []}
        for index in range(8):
            pix = scaled(ASSETS / "saltire-gallop-v5-strict" / f"gallop-{index:02d}.png", 205, 175)
            self.run_frames["right"].append(pix)
            self.run_frames["left"].append(pix.transformed(self.flip()))
        self.rest_frames = {"right": [], "left": []}
        for index in range(5):
            pix = scaled(ASSETS / "rest-transition-v4-strict" / f"rest-{index}.png", 205, 185)
            self.rest_frames["right"].append(pix)
            self.rest_frames["left"].append(pix.transformed(self.flip()))
        self.chew_frames = {"right": [], "left": []}
        for index in range(6):
            pix = scaled(ASSETS / "chew-cycle-v1-strict" / f"chew-{index:02d}.png", 205, 190)
            self.chew_frames["right"].append(pix)
            self.chew_frames["left"].append(pix.transformed(self.flip()))

    @staticmethod
    def flip():
        from PySide6.QtGui import QTransform
        return QTransform().scale(-1, 1)

    def move_bottom_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24)

    def current_pixmap(self):
        if self.state == "run":
            return self.run_frames[self.facing][self.frame_index % len(self.run_frames[self.facing])]
        if self.state == "sleep":
            return self.rest_frames[self.facing][-1]
        if self.state == "run_rest":
            return self.rest_frames[self.facing][1]
        if self.state == "headbutt":
            return self.headbutt[self.facing]
        if self.state == "chew":
            return self.chew_frames[self.facing][self.chew_step % len(self.chew_frames[self.facing])]
        return self.sit[self.facing]

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        pixmap = self.current_pixmap()
        bob = 2 * math.sin(time.monotonic() * 4) if self.state in {"sit", "run_rest"} else 0
        painter.drawPixmap((self.width() - pixmap.width()) // 2,
                           round((self.height() - pixmap.height()) // 2 + bob), pixmap)
        if self.state == "sleep":
            painter.setPen(QPen(Qt.white, 2))
            painter.drawText(158, 70, "z")
            painter.drawText(172, 52, "Z")
            painter.drawText(190, 32, "Z")
        elif self.state == "run_rest":
            phase = int(time.monotonic() * 5) % 10
            if 3 <= phase <= 5:
                painter.setPen(QPen(Qt.white, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                direction = 1 if self.facing == "right" else -1
                x = 125 if direction > 0 else 105
                for offset in (-5, 0, 5):
                    painter.drawArc(x + direction * 8 - (18 if direction < 0 else 0),
                                    146 + offset, 18, 8, 0, 150 * 16)

    def tick(self):
        now = time.monotonic()
        needs_repaint = self.state in {"sit", "run_rest"}
        if now - self.last_frame > .08:
            self.last_frame = now
            self.frame_index += 1
            needs_repaint = needs_repaint or self.state in {"run", "chew"}
            if self.state == "chew":
                self.chew_step += 1
                if self.chew_step >= 18:
                    self.finish_eating()
                    needs_repaint = True
        if self.state == "run" and self.move_to:
            t = min(1.0, (now - self.move_started) / self.move_duration)
            eased = .5 - math.cos(t * math.pi) / 2
            x = self.move_from.x() + (self.move_to.x() - self.move_from.x()) * eased
            y = self.move_from.y() + (self.move_to.y() - self.move_from.y()) * eased
            self.move(round(x), round(y - 5 * abs(math.sin(t * math.pi * 4))))
            needs_repaint = True
            if t >= 1:
                self.move_to = None
                if self.mode == "run" and random.random() < .25:
                    self.state = "run_rest"
                    self.next_action_at = now + random.uniform(5, 8)
                else:
                    self.state = "sit"
                    self.next_action_at = now + random.uniform(.6, 1.8)
        elif now >= self.next_action_at and not self.pending_files:
            if self.mode == "run":
                self.start_random_run()
                needs_repaint = True
            elif self.mode == "rest" and self.state != "sleep":
                self.state = "sleep"
                needs_repaint = True
            elif self.mode == "awake":
                self.state = "sit"
                self.facing = random.choice(("left", "right"))
                self.next_action_at = now + random.uniform(5, 10)
                needs_repaint = True
        if needs_repaint:
            self.update()
        if self.state in {"run", "chew"}:
            self.set_timer_interval(40)
        elif self.state == "sleep":
            self.set_timer_interval(1000)
        else:
            self.set_timer_interval(125)

    def start_random_run(self):
        screen = QApplication.primaryScreen().availableGeometry()
        target = QPoint(random.randint(screen.left() + 20, screen.right() - self.width() - 20),
                        random.randint(screen.top() + 30, screen.bottom() - self.height() - 30))
        self.move_from = self.pos()
        self.move_to = target
        self.move_started = time.monotonic()
        distance = math.hypot(target.x() - self.x(), target.y() - self.y())
        self.move_duration = max(1.1, min(3.8, distance / 260))
        self.facing = "right" if target.x() > self.x() else "left"
        self.state = "run"
        self.set_timer_interval(40)

    def set_mode(self, mode):
        self.mode = mode
        self.move_to = None
        if mode == "run":
            self.state = "sit"
            self.next_action_at = time.monotonic() + .2
        elif mode == "rest":
            self.state = "sleep"
            self.next_action_at = float("inf")
        else:
            self.state = "sit"
            self.next_action_at = time.monotonic() + 5
        self.set_timer_interval(1000 if self.state == "sleep" else 125)
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        elif event.button() == Qt.RightButton:
            self.show_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move_to = None
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_offset = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.state = "headbutt"
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.state = "sit"
        self.update()
        event.accept()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        paths = [path for path in paths if path.exists()]
        if paths:
            self.confirm(paths)
        event.acceptProposedAction()

    def confirm(self, paths):
        self.state = "headbutt"
        box = QMessageBox(self)
        box.setWindowTitle("Clyde")
        box.setText("This one?" if len(paths) == 1 else f"All {len(paths)} of these?")
        yes = box.addButton("Aye" if len(paths) == 1 else "Aye, all of them",
                            QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Not that one" if len(paths) == 1 else "No, leave them",
                      QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.pending_files = paths
            self.chew_step = 0
            self.state = "chew"
            self.set_timer_interval(40)
            self.update()
        else:
            self.state = "sit"
            self.set_timer_interval(125)
            self.update()
            QMessageBox.information(self, "Clyde", "Och, wrong one. My mistake." if len(paths) == 1
                                    else "Och, wrong lot. My mistake.")

    def finish_eating(self):
        failures = []
        for path in self.pending_files:
            try:
                send2trash(str(path))
            except Exception:
                failures.append(path.name)
        self.pending_files = []
        self.state = "sit"
        self.set_timer_interval(125)
        self.update()
        if failures:
            QMessageBox.warning(self, "Clyde", "That one fought back.")
        else:
            QMessageBox.information(self, "Clyde", "Still not as good as Scottish whisky.")
        self.next_action_at = time.monotonic() + 2

    def choose_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Feed Clyde")
        paths = [Path(name) for name in names]
        if paths:
            self.confirm(paths)

    def show_menu(self, position: QPoint):
        menu = QMenu(self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for label, mode in (("Awake — stand by", "awake"), ("Run about", "run"),
                            ("Rest — do not disturb", "rest")):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.mode == mode)
            action.triggered.connect(lambda _checked=False, value=mode: self.set_mode(value))
            group.addAction(action)
        menu.addSeparator()
        feed = menu.addAction("Feed Clyde files…")
        feed.triggered.connect(self.choose_files)
        trash = menu.addAction("Open Trash")
        trash.triggered.connect(lambda: subprocess.Popen(["open", str(Path.home() / ".Trash")]))
        corner = menu.addAction("Back to bottom-right")
        corner.triggered.connect(self.move_bottom_right)
        about = menu.addAction("About Clyde")
        about.triggered.connect(lambda: QMessageBox.information(
            self, "Clyde", "I'm Clyde, from Glasgow.\nDo you like Scotland?"))
        menu.addSeparator()
        quit_action = menu.addAction("Quit Clyde")
        quit_action.triggered.connect(QApplication.quit)
        menu.exec(position)


def main():
    if sys.platform != "darwin":
        raise SystemExit("This build is for macOS.")
    app = QApplication(sys.argv)
    app.setApplicationName("Clyde")
    app.setQuitOnLastWindowClosed(False)
    window = ClydeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
