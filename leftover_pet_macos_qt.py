# -*- coding: utf-8 -*-
"""Apple Silicon macOS build of LEFTOVER using native Qt drag and drop."""
import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QWidget
from send2trash import send2trash


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


ASSETS = resource_path("assets")
STATE = Path.home() / "Library" / "Application Support" / "LeftoverPet" / "state-macos.json"
KINDS = ("void", "text", "code", "image", "archive", "metal", "empty", "trash")
TASTES = {
    "text": "还行，纸味有点重。", "code": "有点扎嘴。", "image": "颜色很多。",
    "archive": "压得很实。", "metal": "硬。", "empty": "什么也没有。",
    "trash": "熟悉的味道。", "void": "说不上来。",
}


def classify(path):
    if path.is_dir():
        return "archive"
    ext = path.suffix.lower()
    if ext in {".txt", ".md", ".pdf", ".doc", ".docx", ".rtf"}: return "text"
    if ext in {".py", ".js", ".ts", ".html", ".css", ".json", ".swift"}: return "code"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".svg"}: return "image"
    if ext in {".zip", ".rar", ".7z", ".tar", ".gz", ".dmg", ".pkg"}: return "archive"
    if ext in {".exe", ".dll", ".bin", ".iso", ".app"}: return "metal"
    try:
        return "empty" if path.stat().st_size == 0 else "void"
    except OSError:
        return "void"


class LeftoverWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("余食 / LEFTOVER")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setFixedSize(220, 235)
        self.kind = "void"
        self.pending_kind = None
        self.chew = 0
        self.phase = 0.0
        self.last_activity = time.time()
        self.drag_offset = None
        self.load_state()
        self.states = {k: QPixmap(str(ASSETS / f"pet-{k}.png")) for k in KINDS}
        self.mouths = [QPixmap(str(ASSETS / f"mouth-{i}.png")) for i in range(4)]
        self.liquid = {k: [QPixmap(str(ASSETS / f"liquid-{k}-{i}.png")) for i in range(8)]
                       for k in KINDS}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(55)
        self.move_bottom_right()

    def load_state(self):
        try:
            value = json.loads(STATE.read_text(encoding="utf-8")).get("kind")
            if value in KINDS:
                self.kind = value
        except (OSError, ValueError):
            pass

    def save_state(self):
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"kind": self.kind}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def move_bottom_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24)

    def current_pixmap(self):
        if self.chew < 0:
            return self.mouths[3]
        if self.chew > 0:
            return self.mouths[2 + (self.chew // 3) % 2]
        if time.time() - self.last_activity > 24:
            return self.liquid[self.kind][int(self.phase) % 8]
        return self.states[self.kind]

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        pixmap = self.current_pixmap()
        bob = round(math.sin(self.phase * 1.7) * 2)
        painter.drawPixmap((self.width() - pixmap.width()) // 2,
                           (self.height() - pixmap.height()) // 2 + bob, pixmap)

    def animate(self):
        self.phase += .11
        if self.chew > 0:
            self.chew -= 1
            if self.chew == 0 and self.pending_kind:
                self.kind = self.pending_kind
                self.pending_kind = None
                self.save_state()
        self.update()

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
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_offset = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.chew = -3
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        if self.chew < 0:
            self.chew = 0
        event.accept()

    def dropEvent(self, event):
        self.chew = 0
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        paths = [path for path in paths if path.exists()]
        if paths:
            self.confirm(paths)
        event.acceptProposedAction()

    def confirm(self, paths):
        box = QMessageBox(self)
        box.setWindowTitle("余食")
        box.setText("这个不要了吗？" if len(paths) == 1 else f"这 {len(paths)} 个都不要了吗？")
        yes = box.addButton("没戳！", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("啊搞错了嘿嘿嘿", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.eat(paths)

    def eat(self, paths):
        kind = classify(paths[-1])
        try:
            for path in paths:
                send2trash(str(path))
        except Exception:
            QMessageBox.warning(self, "余食", "咬不开。它还留在那里。")
            return
        self.pending_kind = kind
        self.chew = 42
        self.last_activity = time.time()
        QTimer.singleShot(2500, lambda: QMessageBox.information(self, "余食", TASTES[kind]))

    def choose_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, "喂给余食")
        paths = [Path(name) for name in names]
        if paths:
            self.confirm(paths)

    def show_menu(self, position: QPoint):
        menu = QMenu(self)
        feed = menu.addAction("选择文件喂给余食…")
        feed.triggered.connect(self.choose_files)
        trash = menu.addAction("打开废纸篓")
        trash.triggered.connect(lambda: subprocess.Popen(["open", str(Path.home() / ".Trash")]))
        corner = menu.addAction("回到右下角")
        corner.triggered.connect(self.move_bottom_right)
        menu.addSeparator()
        quit_action = menu.addAction("退出余食")
        quit_action.triggered.connect(QApplication.quit)
        menu.exec(position)

    def closeEvent(self, event):
        self.save_state()
        event.accept()


def main():
    if sys.platform != "darwin":
        raise SystemExit("This build is for macOS.")
    app = QApplication(sys.argv)
    app.setApplicationName("余食 LEFTOVER")
    window = LeftoverWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
