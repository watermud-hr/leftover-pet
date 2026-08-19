# -*- coding: utf-8 -*-
"""LEFTOVER macOS beta: drag-to-feed desktop pet with recoverable Trash moves."""
import json
import math
import os
import random
import subprocess
import sys
import time
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk
from send2trash import send2trash
from tkinterdnd2 import DND_FILES, TkinterDnD


ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
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


class LeftoverMac:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("余食 / LEFTOVER")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry("220x235")
        self._make_transparent()
        self.canvas = tk.Canvas(self.root, width=220, height=235, highlightthickness=0,
                                bd=0, bg=self.transparent_bg)
        self.canvas.pack(fill="both", expand=True)
        self.kind = "void"
        self.pending_kind = None
        self.chew = 0
        self.phase = 0.0
        self.last_activity = time.time()
        self.drag_origin = None
        self.dialog = None
        self.dialog_offset = None
        self.stopping = False
        self.load_state()
        self.load_images()
        self.place_bottom_right()
        self.bind_events()
        self.build_menu()
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.root.after(55, self.animate)

    def _make_transparent(self):
        self.transparent_bg = "systemTransparent"
        try:
            self.root.configure(bg=self.transparent_bg)
            self.root.attributes("-transparent", True)
        except tk.TclError:
            self.transparent_bg = "#010203"
            self.root.configure(bg=self.transparent_bg)

    def load_images(self):
        self.states = {k: ImageTk.PhotoImage(Image.open(ASSETS / f"pet-{k}.png").convert("RGBA"))
                       for k in KINDS}
        self.mouths = [ImageTk.PhotoImage(Image.open(ASSETS / f"mouth-{i}.png").convert("RGBA"))
                       for i in range(4)]
        self.liquid = {k: [ImageTk.PhotoImage(Image.open(ASSETS / f"liquid-{k}-{i}.png").convert("RGBA"))
                           for i in range(8)] for k in KINDS}

    def load_state(self):
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
            if data.get("kind") in KINDS:
                self.kind = data["kind"]
        except (OSError, ValueError):
            pass

    def save_state(self):
        try:
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"kind": self.kind}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def place_bottom_right(self):
        self.root.update_idletasks()
        x = max(0, self.root.winfo_screenwidth() - 250)
        y = max(24, self.root.winfo_screenheight() - 315)
        self.root.geometry(f"220x235+{x}+{y}")

    def bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self.drag_start)
        self.canvas.bind("<B1-Motion>", self.drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.drag_end)
        self.canvas.bind("<Button-2>", self.popup_menu)
        self.canvas.bind("<Button-3>", self.popup_menu)
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind("<<DropEnter>>", self.drop_enter)
        self.canvas.dnd_bind("<<DropPosition>>", self.drop_enter)
        self.canvas.dnd_bind("<<DropLeave>>", self.drop_leave)
        self.canvas.dnd_bind("<<Drop>>", self.drop)

    def build_menu(self):
        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label="打开废纸篓", command=self.open_trash)
        self.menu.add_command(label="回到右下角", command=self.place_bottom_right)
        self.menu.add_separator()
        self.menu.add_command(label="退出余食", command=self.quit)

    def popup_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def drag_start(self, event):
        self.last_activity = time.time()
        self.drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())
        if self.dialog:
            self.dialog_offset = (self.dialog.winfo_x() - self.root.winfo_x(),
                                  self.dialog.winfo_y() - self.root.winfo_y())

    def drag_move(self, event):
        if not self.drag_origin:
            return
        sx, sy, x, y = self.drag_origin
        self.root.geometry(f"+{x + event.x_root - sx}+{y + event.y_root - sy}")
        self.follow_dialog()

    def drag_end(self, _event):
        self.drag_origin = None

    def follow_dialog(self):
        if not self.dialog or not self.dialog_offset:
            return
        try:
            dx, dy = self.dialog_offset
            self.dialog.geometry(f"+{self.root.winfo_x() + dx}+{self.root.winfo_y() + dy}")
        except tk.TclError:
            pass

    def drop_enter(self, _event):
        self.last_activity = time.time()
        self.chew = -3
        return "copy"

    def drop_leave(self, _event):
        if self.chew < 0:
            self.chew = 0
        return "copy"

    def drop(self, event):
        self.chew = 0
        paths = []
        try:
            paths = [Path(p) for p in self.root.tk.splitlist(event.data)]
        except tk.TclError:
            pass
        paths = [p for p in paths if p.exists()]
        if paths:
            self.confirm(paths)
        return "copy"

    def close_dialog(self):
        if self.dialog:
            try: self.dialog.destroy()
            except tk.TclError: pass
        self.dialog = None
        self.dialog_offset = None

    def say(self, text, buttons=None, duration=None):
        self.close_dialog()
        w = tk.Toplevel(self.root)
        self.dialog = w
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        frame = tk.Frame(w, bg="#f7f4ea", highlightbackground="#171916", highlightthickness=2)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=text, bg="#f7f4ea", fg="#11130f", font=("PingFang SC", 12),
                 padx=14, pady=11).pack(fill="x")
        if buttons:
            bar = tk.Frame(frame, bg="#f7f4ea")
            bar.pack(fill="x", padx=10, pady=(0, 10))
            for label, command in buttons:
                def run(fn=command):
                    self.close_dialog(); fn()
                tk.Button(bar, text=label, command=run, relief="flat", bd=0,
                          bg="#20241d", fg="#f1f3eb", font=("PingFang SC", 11),
                          padx=10, pady=4).pack(side="left", padx=(0, 7))
        w.update_idletasks()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        x, y = rx + 175, max(28, ry + 28)
        if x + w.winfo_reqwidth() > self.root.winfo_screenwidth():
            x = max(0, rx - w.winfo_reqwidth() + 35)
        w.geometry(f"+{x}+{y}")
        self.dialog_offset = (x - rx, y - ry)
        if duration:
            w.after(duration, self.close_dialog)

    def confirm(self, paths):
        text = "这个不要了吗？" if len(paths) == 1 else f"这 {len(paths)} 个都不要了吗？"
        self.say(text, [("没戳！", lambda: self.eat(paths)), ("啊搞错了嘿嘿嘿", lambda: None)])

    def eat(self, paths):
        kind = classify(paths[-1])
        try:
            send2trash([str(p) for p in paths])
        except Exception:
            self.say("咬不开。它还留在那里。", duration=2300)
            return
        self.pending_kind = kind
        self.chew = 42
        self.last_activity = time.time()
        self.root.after(2500, lambda: self.say(TASTES[kind], duration=2200))

    def draw(self):
        self.canvas.delete("all")
        bob = math.sin(self.phase * 1.7) * 2
        if self.chew < 0:
            image = self.mouths[3]
        elif self.chew > 0:
            image = self.mouths[2 + (self.chew // 3) % 2]
        elif time.time() - self.last_activity > 24:
            image = self.liquid[self.kind][int(self.phase) % 8]
        else:
            image = self.states[self.kind]
        self.canvas.create_image(110, 124 + bob, image=image)

    def animate(self):
        if self.stopping:
            return
        self.phase += .11
        if self.chew > 0:
            self.chew -= 1
            if self.chew == 0 and self.pending_kind:
                self.kind = self.pending_kind
                self.pending_kind = None
                self.save_state()
        self.draw()
        self.root.after(55, self.animate)

    def open_trash(self):
        subprocess.Popen(["open", str(Path.home() / ".Trash")])

    def quit(self):
        self.stopping = True
        self.close_dialog()
        self.save_state()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if sys.platform != "darwin":
        raise SystemExit("This entry point is for macOS. Use leftover_pet.py on Windows.")
    LeftoverMac().run()
