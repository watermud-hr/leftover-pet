# -*- coding: utf-8 -*-
import ctypes, hashlib, json, math, os, random, subprocess, time, tkinter as tk, threading
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox
from PIL import Image
from tkinterdnd2 import TkinterDnD, DND_FILES
import pystray

_INSTANCE_MUTEX=ctypes.windll.kernel32.CreateMutexW(None,False,"Local\\LeftoverPetSingleInstanceV2")
if ctypes.windll.kernel32.GetLastError()==183: raise SystemExit(0)

KEY="#010203"
ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/"assets"
STATE=Path(os.getenv("LOCALAPPDATA",str(Path.home())))/"LeftoverPet"/"state-v2.json"
COLORS={"void":"#d7ff55","text":"#d7ff55","code":"#52e6ff","image":"#ff4fac",
"archive":"#a78bfa","metal":"#e5edf5","empty":"#84908b","trash":"#ff9b45"}

class FileOp(ctypes.Structure):
    _fields_=[("hwnd",wintypes.HWND),("func",wintypes.UINT),("src",wintypes.LPCWSTR),
    ("dst",wintypes.LPCWSTR),("flags",wintypes.WORD),("aborted",wintypes.BOOL),
    ("maps",ctypes.c_void_p),("title",wintypes.LPCWSTR)]

def move_to_recycle_bin(paths):
    op=FileOp();op.func=3
    op.src="\0".join(str(Path(p).resolve()) for p in paths)+"\0\0"
    op.flags=0x40|0x10|0x04
    return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))==0 and not op.aborted

def classify(path,raw):
    if path.is_file() and path.stat().st_size==0:return "empty"
    e=path.suffix.lower()
    if e in {".py",".js",".ts",".json",".html",".css",".md",".csv",".xlsx",".sql"}:return "code"
    if e in {".png",".jpg",".jpeg",".gif",".webp",".svg",".mp4",".mov",".mp3",".wav"}:return "image"
    if e in {".zip",".rar",".7z",".tar",".gz"} or path.is_dir():return "archive"
    return "metal" if e in {".exe",".dll",".bin",".iso"} or b"\0" in raw[:200] else "text"

class Leftover:
    def __init__(self):
        try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:pass
        self.root=TkinterDnD.Tk();self.root.title("余食 / LEFTOVER")
        self.root.geometry("220x235+100+140");self.root.overrideredirect(True)
        self.root.attributes("-topmost",True);self.root.configure(bg=KEY)
        try:self.root.wm_attributes("-transparentcolor",KEY)
        except tk.TclError:pass
        self.canvas=tk.Canvas(self.root,width=220,height=235,bg=KEY,highlightthickness=0,cursor="hand2")
        self.canvas.pack(fill="both",expand=True)
        self.kind="void";self.last_meal="";self.phase=0.0
        self.mouth_level=0.0;self.mouth_target=0.0;self.chew=0
        self.pending_kind=None;self.message="";self.message_until=0
        self.drag_origin=None;self.docked=None;self.folded=False;self.stopping=False
        self.last_activity=time.time();self.peek=0
        self.load_state();self.load_images();self.build_menu();self.bind();self.build_tray()
        self.root.update_idletasks()
        hwnd=ctypes.windll.user32.GetParent(self.root.winfo_id())
        style=ctypes.windll.user32.GetWindowLongW(hwnd,-20)
        ctypes.windll.user32.SetWindowLongW(hwnd,-20,(style|0x80)&~0x40000)
        self.animate()

    def load_images(self):
        self.states={k:tk.PhotoImage(file=str(ASSETS/f"pet-{k}.png")) for k in COLORS}
        self.mouths=[tk.PhotoImage(file=str(ASSETS/f"mouth-{i}.png")) for i in range(4)]
        self.peek_image=tk.PhotoImage(file=str(ASSETS/"pet-peek.png"))

    def load_state(self):
        try:
            d=json.loads(STATE.read_text(encoding="utf-8"))
            self.kind=d.get("kind","void") if d.get("kind") in COLORS else "void"
            self.last_meal=d.get("last_meal","")
        except (OSError,ValueError,TypeError):pass
    def save_state(self):
        try:
            STATE.parent.mkdir(parents=True,exist_ok=True)
            STATE.write_text(json.dumps({"kind":self.kind,"last_meal":self.last_meal},
            ensure_ascii=False,indent=2),encoding="utf-8")
        except OSError:pass

    def bind(self):
        self.canvas.bind("<ButtonPress-1>",self.drag_start)
        self.canvas.bind("<B1-Motion>",self.drag_move)
        self.canvas.bind("<ButtonRelease-1>",self.drag_end)
        self.canvas.bind("<Button-3>",self.popup_menu)
        self.canvas.bind("<Double-Button-1>",lambda e:self.toggle_fold())
        self.root.bind("<Escape>",lambda e:self.hide_to_tray())
        self.canvas.drop_target_register(DND_FILES)
        self.canvas.dnd_bind("<<DropEnter>>",self.drop_enter)
        self.canvas.dnd_bind("<<DropPosition>>",self.drop_position)
        self.canvas.dnd_bind("<<DropLeave>>",self.drop_leave)
        self.canvas.dnd_bind("<<Drop>>",self.drop)

    def build_menu(self):
        self.menu=tk.Menu(self.root,tearoff=False,font=("Microsoft YaHei UI",9))
        self.menu.add_command(label="查看上一餐",command=self.show_last_meal)
        self.menu.add_command(label="打开系统回收站",command=self.open_recycle_bin)
        self.menu.add_separator()
        self.menu.add_command(label="折叠到屏幕侧边",command=self.toggle_fold)
        self.menu.add_command(label="隐藏到系统托盘",command=self.hide_to_tray)
        self.menu.add_separator()
        self.menu.add_command(label="退出余食",command=self.quit)
    def popup_menu(self,e):
        try:self.menu.tk_popup(e.x_root,e.y_root)
        finally:self.menu.grab_release()

    def build_tray(self):
        image=Image.open(ASSETS/"tray-icon-v2.png")
        menu=pystray.Menu(
            pystray.MenuItem("显示余食",lambda i,x:self.root.after(0,self.show),default=True),
            pystray.MenuItem("打开回收站",lambda i,x:self.root.after(0,self.open_recycle_bin)),
            pystray.MenuItem("退出余食",lambda i,x:self.root.after(0,self.quit)))
        self.tray=pystray.Icon("leftover_v2",image,"余食",menu);self.tray.run_detached()

    def say(self,text,seconds=2.4):
        self.message=text;self.message_until=time.time()+seconds
    def drag_start(self,e):
        self.last_activity=time.time()
        self.drag_origin=(e.x_root,e.y_root,self.root.winfo_x(),self.root.winfo_y())
    def drag_move(self,e):
        if self.drag_origin:
            sx,sy,x,y=self.drag_origin;self.root.geometry(f"+{x+e.x_root-sx}+{y+e.y_root-sy}")
    def drag_end(self,e):
        self.drag_origin=None;x=self.root.winfo_x();y=max(0,self.root.winfo_y());sw=self.root.winfo_screenwidth()
        if x<22:self.docked="left";self.root.geometry(f"+0+{y}")
        elif x>sw-self.root.winfo_width()-22:self.docked="right";self.root.geometry(f"+{sw-self.root.winfo_width()}+{y}")
        else:self.docked=None

    def drop_enter(self,e):
        self.last_activity=time.time();self.mouth_target=3;self.say("这个不要了吗？",5);return "copy"
    def drop_position(self,e):
        self.mouth_target=3;return "copy"
    def drop_leave(self,e):
        self.mouth_target=0;self.say("改变主意了？",1.5);return "copy"
    def drop(self,e):
        self.mouth_target=3;self.last_activity=time.time()
        try:paths=[Path(p) for p in self.root.tk.splitlist(e.data) if Path(p).exists()]
        except Exception:
            self.mouth_target=0;self.say("没接住，再试一次。");return "copy"
        if not paths:
            self.mouth_target=0;self.say("没找到这个文件。");return "copy"
        self.say("这个真的不要了吗？",10)
        self.root.after(30,lambda p=paths:self.confirm_eat(p))
        return "copy"

    def confirm_eat(self,paths):
        names=paths[0].name if len(paths)==1 else f"{paths[0].name} 等 {len(paths)} 项"
        ok=messagebox.askyesno("投喂余食",
            f"这个不要了吗？\n\n{names}\n\n确认后会移入系统回收站，之后仍可恢复。",
            parent=self.root)
        if not ok:
            self.mouth_target=0;self.say("改变主意了？",1.6);return
        mixed=b"";kind="empty"
        try:
            for p in paths:
                if p.is_dir():raw=p.name.encode("utf-8","replace")
                else:
                    with p.open("rb") as f:raw=f.read(300000)
                mixed+=hashlib.sha256(raw).digest();kind=classify(p,raw)
        except OSError as exc:
            self.mouth_target=0;self.say(f"咬不开：{str(exc)[:20]}",3);return
        if not move_to_recycle_bin(paths):
            self.mouth_target=0;self.say("Windows 没有把它移进回收站。",3);return
        self.pending_kind=kind;self.last_meal=names;self.chew=44;self.mouth_target=3
        self.say("嚼嚼嚼……",4)

    def show_last_meal(self):
        self.last_activity=time.time()
        self.say(f"上一餐：{self.last_meal}" if self.last_meal else "还没有吃过东西。",3)
    def open_recycle_bin(self):
        subprocess.Popen(["explorer.exe","shell:RecycleBinFolder"])
    def hide_to_tray(self):self.root.withdraw()
    def show(self):
        self.folded=False;self.root.geometry(f"220x235+{max(0,self.root.winfo_x())}+{max(0,self.root.winfo_y())}")
        self.canvas.configure(width=220,height=235);self.root.deiconify();self.root.lift()
    def toggle_fold(self):
        sw=self.root.winfo_screenwidth();y=max(0,self.root.winfo_y())
        if self.folded:
            side=self.docked or "right";x=0 if side=="left" else sw-220
            self.folded=False;self.root.geometry(f"220x235+{x}+{y}");self.canvas.configure(width=220,height=235)
        else:
            side=self.docked or ("left" if self.root.winfo_x()<sw/2 else "right");self.docked=side
            x=0 if side=="left" else sw-68;self.folded=True
            self.root.geometry(f"68x88+{x}+{y}");self.canvas.configure(width=68,height=88)
    def quit(self):
        self.stopping=True
        try:self.tray.stop()
        except Exception:pass
        self.root.destroy()

    def draw(self):
        c=self.canvas;c.delete("all")
        if self.folded:
            c.create_image(34,42,image=self.peek_image);return
        bob=math.sin(self.phase)*2.2
        if self.chew:
            frame=1+int(abs(math.sin(self.chew*.72))*2)
            c.create_image(110,132+bob,image=self.mouths[frame])
        elif self.mouth_level>.45:
            frame=max(1,min(3,round(self.mouth_level)))
            c.create_image(110,132+bob,image=self.mouths[frame])
        else:
            c.create_image(110,132+bob,image=self.states[self.kind])
            if self.peek:
                c.create_image(110,132+bob,image=self.mouths[1])
        if time.time()<self.message_until:
            c.create_polygon(15,7,205,7,205,48,128,48,111,62,106,48,15,48,
                fill="#f7f4ea",outline="#171916",width=2)
            c.create_text(110,27,text=self.message,width=174,fill="#11130f",
                font=("Microsoft YaHei UI",8),justify="center")

    def animate(self):
        if self.stopping:return
        self.phase+=.09
        speed=.32
        self.mouth_level+=(self.mouth_target-self.mouth_level)*speed
        if self.chew:
            self.chew-=1
            if self.chew==0:
                self.kind=self.pending_kind or self.kind;self.pending_kind=None
                self.mouth_target=0;self.save_state()
                self.say(f"吃掉了：{self.last_meal}\n已放进回收站。",3)
        elif self.mouth_target==0 and random.random()<.0025:self.peek=12
        if self.peek:self.peek-=1
        self.draw();self.root.after(55,self.animate)
    def run(self):self.root.mainloop()


味道={"void":"肚子还是空的。","text":"还行，纸味有点重。","code":"好吃，逻辑是脆的。","image":"好吃，像素有点甜。","archive":"太实了，得慢慢消化。","metal":"有点硌牙，但很香。","empty":"空白最好吃。","trash":"味道复杂，像隔夜剩饭。"}

原加载图片=Leftover.load_images
def 新加载图片(self):
    原加载图片(self)
    self.liquid={k:[tk.PhotoImage(file=str(ASSETS/f"liquid-{k}-{i}.png")) for i in range(8)] for k in COLORS}
    self.puddle={k:[tk.PhotoImage(file=str(ASSETS/f"puddle-{k}-{i}.png")) for i in range(8)] for k in COLORS}

def 新菜单(self):
    self.menu=tk.Menu(self.root,tearoff=False,font=("Microsoft YaHei UI",9))
    self.menu.add_command(label="扫描重复文件…",command=lambda:self.开始扫描("duplicate"))
    self.menu.add_command(label="扫描桌面与下载垃圾…",command=lambda:self.开始扫描("garbage"))
    self.menu.add_separator()
    self.menu.add_command(label="上一餐好不好吃",command=lambda:self.tray.notify(味道[self.kind],"余食"))
    self.menu.add_command(label="打开系统回收站",command=self.open_recycle_bin)
    self.menu.add_separator()
    self.menu.add_command(label="折叠到屏幕侧边",command=self.toggle_fold)
    self.menu.add_command(label="隐藏到系统托盘",command=self.hide_to_tray)
    self.menu.add_separator();self.menu.add_command(label="退出余食",command=self.quit)

def 新拖入(self,e):
    self.last_activity=time.time();self.mouth_target=3;return "copy"
def 新离开(self,e):
    self.mouth_target=0;return "copy"
def 新松手(self,e):
    self.mouth_target=3;self.last_activity=time.time()
    try:paths=[Path(p) for p in self.root.tk.splitlist(e.data) if Path(p).exists()]
    except Exception:
        self.mouth_target=0;self.tray.notify("没接住，再试一次。","余食");return "copy"
    if paths:self.root.after(20,lambda p=paths:self.confirm_eat(p))
    else:self.mouth_target=0
    return "copy"

def 新确认(self,paths):
    names=paths[0].name if len(paths)==1 else f"{paths[0].name} 等 {len(paths)} 项"
    if not messagebox.askyesno("这个不要了吗？",
        f"{names}\n\n确认后会移入系统回收站，之后仍可恢复。",parent=self.root):
        self.mouth_target=0;return
    kind="empty"
    try:
        for p in paths:
            if p.is_dir():raw=p.name.encode("utf-8","replace")
            else:
                with p.open("rb") as f:raw=f.read(300000)
            kind=classify(p,raw)
    except OSError as exc:
        self.mouth_target=0;messagebox.showerror("咬不开",str(exc)[:80],parent=self.root);return
    if not move_to_recycle_bin(paths):
        self.mouth_target=0;messagebox.showerror("没有吃到","Windows 没有把它移进回收站。",parent=self.root);return
    self.pending_kind=kind;self.last_meal=names;self.chew=44;self.mouth_target=3
    self.message_until=0

def 新绘制(self):
    c=self.canvas;c.delete("all")
    if self.folded:c.create_image(34,42,image=self.peek_image);return
    frame=int(self.phase*1.7)%8;idle=time.time()-self.last_activity
    if self.chew:
        mouth=1+int(abs(math.sin(self.chew*.72))*2)
        c.create_image(110,123+math.sin(self.phase*5)*3,image=self.mouths[mouth])
    elif self.mouth_level>.45:
        mouth=max(1,min(3,round(self.mouth_level)));c.create_image(110,123,image=self.mouths[mouth])
    elif idle>24:
        c.create_image(110,143,image=self.puddle[self.kind][frame])
    else:
        c.create_image(110,124+math.sin(self.phase)*1.4,image=self.liquid[self.kind][frame])

def 新动画(self):
    if self.stopping:return
    self.phase+=.09;self.mouth_level+=(self.mouth_target-self.mouth_level)*.30
    if self.chew:
        self.chew-=1
        if self.chew==0:
            self.kind=self.pending_kind or self.kind;self.pending_kind=None;self.mouth_target=0
            self.last_activity=time.time();self.save_state()
            try:self.tray.notify(味道[self.kind],"余食")
            except Exception:pass
    self.draw();self.root.after(55,self.animate)

def 收集文件(self):
    roots=[Path.home()/"Desktop",Path.home()/"Downloads"];files=[]
    for root in roots:
        if not root.exists():continue
        try:
            for p in root.rglob("*"):
                if p.is_file():
                    files.append(p)
                    if len(files)>=2500:return files
        except OSError:pass
    return files

def 开始扫描(self,mode):
    try:self.tray.notify("正在扫描桌面与下载目录…","余食")
    except Exception:pass
    def work():
        files=self.收集文件();result=[]
        if mode=="duplicate":
            sizes={}
            for p in files:
                try:sizes.setdefault(p.stat().st_size,[]).append(p)
                except OSError:pass
            for size,group in sizes.items():
                if size==0 or len(group)<2:continue
                hashes={}
                for p in group:
                    try:
                        h=hashlib.sha256()
                        with p.open("rb") as f:
                            for chunk in iter(lambda:f.read(1048576),b""):h.update(chunk)
                        hashes.setdefault(h.hexdigest(),[]).append(p)
                    except OSError:pass
                for same in hashes.values():
                    if len(same)>1:result.extend((p,size,"重复") for p in same[1:])
        else:
            now=time.time()
            for p in files:
                try:
                    st=p.stat();days=int((now-st.st_mtime)/86400)
                    reason="空文件" if st.st_size==0 else ("疑似副本" if any(x in p.stem.lower() for x in ("copy","副本","(1)")) else (f"{days}天未修改" if days>=45 else ""))
                    if reason:result.append((p,st.st_size,reason))
                except OSError:pass
        self.root.after(0,lambda:self.显示扫描结果(mode,result))
    threading.Thread(target=work,daemon=True).start()

def 显示扫描结果(self,mode,rows):
    if not rows:
        messagebox.showinfo("扫描完成","没有发现符合条件的文件。",parent=self.root);return
    w=tk.Toplevel(self.root);w.title("重复文件" if mode=="duplicate" else "垃圾候选")
    w.geometry("650x430");w.attributes("-topmost",True)
    tk.Label(w,text=f"发现 {len(rows)} 个候选；默认不选择，余食不会自动删除。",font=("Microsoft YaHei UI",9)).pack(pady=9)
    lb=tk.Listbox(w,selectmode=tk.EXTENDED,font=("Microsoft YaHei UI",9))
    lb.pack(fill="both",expand=True,padx=12)
    for p,size,reason in rows:lb.insert(tk.END,f"[{reason}]  {p.name}  ·  {size/1024:.1f} KB  ·  {p.parent}")
    def remove_selected():
        chosen=[rows[i][0] for i in lb.curselection()]
        if not chosen:return
        if not messagebox.askyesno("移入回收站",f"将选中的 {len(chosen)} 项移入系统回收站？\n之后仍可恢复。",parent=w):return
        if move_to_recycle_bin(chosen):
            w.destroy();self.pending_kind="trash";self.chew=36;self.mouth_target=3
        else:messagebox.showerror("没有完成","Windows 没有完成移动。",parent=w)
    tk.Button(w,text="把选中项移入回收站",command=remove_selected,font=("Microsoft YaHei UI",9)).pack(pady=10)

Leftover.load_images=新加载图片
Leftover.build_menu=新菜单
Leftover.drop_enter=新拖入
Leftover.drop_position=新拖入
Leftover.drop_leave=新离开
Leftover.drop=新松手
Leftover.confirm_eat=新确认
Leftover.draw=新绘制
Leftover.animate=新动画
Leftover.收集文件=收集文件
Leftover.开始扫描=开始扫描
Leftover.显示扫描结果=显示扫描结果


对话版初始化=Leftover.__init__
def 对话初始化(self):
    self.dialog=None;self.history=[]
    对话版初始化(self)
    try:
        d=json.loads(STATE.read_text(encoding="utf-8"));self.history=d.get("history",[])[-50:]
    except Exception:pass

def 保存含食谱(self):
    try:
        STATE.parent.mkdir(parents=True,exist_ok=True)
        STATE.write_text(json.dumps({"kind":self.kind,"last_meal":self.last_meal,
            "history":self.history[-50:]},ensure_ascii=False,indent=2),encoding="utf-8")
    except OSError:pass

def 关闭对话(self):
    if self.dialog:
        try:self.dialog.destroy()
        except tk.TclError:pass
        self.dialog=None

def 说(self,text,buttons=None,duration=None):
    self.关闭对话()
    w=tk.Toplevel(self.root);self.dialog=w
    w.overrideredirect(True);w.attributes("-topmost",True);w.configure(bg="#171916")
    frame=tk.Frame(w,bg="#f7f4ea",highlightbackground="#171916",highlightthickness=1)
    frame.pack(fill="both",expand=True,padx=2,pady=2)
    tk.Label(frame,text=text,bg="#f7f4ea",fg="#11130f",justify="left",wraplength=230,
        font=("Microsoft YaHei UI",9)).pack(fill="x",padx=12,pady=(10,7))
    if buttons:
        bar=tk.Frame(frame,bg="#f7f4ea");bar.pack(fill="x",padx=10,pady=(0,9))
        for label,command in buttons:
            def run(fn=command):
                self.关闭对话();fn()
            tk.Button(bar,text=label,command=run,relief="flat",bd=0,bg="#20241d",fg="#f1f3eb",
                activebackground="#d7ff55",activeforeground="#11130f",
                font=("Microsoft YaHei UI",8),padx=9,pady=3).pack(side="left",padx=(0,6))
    w.update_idletasks();ww=max(220,w.winfo_reqwidth());wh=w.winfo_reqheight()
    rx,ry=self.root.winfo_x(),self.root.winfo_y();sw=self.root.winfo_screenwidth()
    x=rx+self.root.winfo_width()-20
    if x+ww>sw:x=max(0,rx-ww+20)
    y=max(0,ry+20);w.geometry(f"{ww}x{wh}+{x}+{y}")
    if duration:w.after(duration,lambda:self.关闭对话())

def 宠物确认(self,paths):
    count=len(paths)
    text="这个不要了吗？\n我会把它放进回收站，还能找回来。" if count==1 else f"这 {count} 个都不要了吗？\n我会把它们放进回收站。"
    self.说(text,[("不要了，吃掉",lambda:self.真正吃掉(paths)),("算了",lambda:self.取消进食())])

def 取消进食(self):
    self.mouth_target=0;self.last_activity=time.time()
    self.说("改变主意了？",duration=1400)

def 真正吃掉(self,paths):
    kind="empty";total=0
    try:
        for p in paths:
            if p.is_dir():raw=p.name.encode("utf-8","replace")
            else:
                total+=p.stat().st_size
                with p.open("rb") as f:raw=f.read(300000)
            kind=classify(p,raw)
    except OSError:
        self.mouth_target=0;self.说("咬不开。它好像还不想走。",duration=2200);return
    if not move_to_recycle_bin(paths):
        self.mouth_target=0;self.说("没吃到，Windows 把它留下了。",duration=2400);return
    self.pending_kind=kind;self.last_meal="";self.chew=44;self.mouth_target=3
    self.history.append({"kind":kind,"count":len(paths),"size":total,"time":int(time.time())})

def 对话动画(self):
    if self.stopping:return
    self.phase+=.09;self.mouth_level+=(self.mouth_target-self.mouth_level)*.30
    if self.chew:
        self.chew-=1
        if self.chew==0:
            self.kind=self.pending_kind or self.kind;self.pending_kind=None;self.mouth_target=0
            self.last_activity=time.time();self.save_state()
            self.说(味道[self.kind],duration=2600)
    self.draw();self.root.after(55,self.animate)

def 食谱(self):
    if not self.history:self.说("还没有食谱。我的肚子是空的。",duration=2300);return
    counts={}
    for meal in self.history:counts[meal.get("kind","void")]=counts.get(meal.get("kind","void"),0)+meal.get("count",1)
    names={"text":"文字","code":"代码","image":"图片和影音","archive":"压缩包","metal":"二进制","empty":"空文件","trash":"混合剩饭","void":"空气"}
    lines=["最近的食谱："]+[f"{names.get(k,k)} × {v}" for k,v in sorted(counts.items(),key=lambda x:x[1],reverse=True)]
    self.说("\n".join(lines[:6]),duration=4200)

def 上一餐评价(self):self.说(味道[self.kind],duration=2400)
def 帮我找一口(self):
    self.说("我去桌面和下载目录闻一闻。",duration=1600)
    self.root.after(200,lambda:self.开始扫描("garbage"))
def 去睡觉(self):
    self.last_activity=0;self.说("那我化开一会儿。",duration=1400)

def 对话菜单(self):
    self.menu=tk.Menu(self.root,tearoff=False,font=("Microsoft YaHei UI",9))
    self.menu.add_command(label="帮我找一口…",command=lambda:帮我找一口(self))
    self.menu.add_command(label="扫描重复文件…",command=lambda:self.开始扫描("duplicate"))
    self.menu.add_command(label="扫描桌面与下载垃圾…",command=lambda:self.开始扫描("garbage"))
    self.menu.add_separator()
    self.menu.add_command(label="看看它的食谱",command=lambda:食谱(self))
    self.menu.add_command(label="问上一餐好不好吃",command=lambda:上一餐评价(self))
    self.menu.add_command(label="打开系统回收站",command=self.open_recycle_bin)
    self.menu.add_separator()
    self.menu.add_command(label="让它睡觉",command=lambda:去睡觉(self))
    self.menu.add_command(label="折叠到屏幕侧边",command=self.toggle_fold)
    self.menu.add_command(label="隐藏到系统托盘",command=self.hide_to_tray)
    self.menu.add_separator();self.menu.add_command(label="退出余食",command=self.quit)

def 安静扫描(self,mode):
    self.说("我闻闻……",duration=1300)
    def work():
        files=self.收集文件();result=[]
        if mode=="duplicate":
            sizes={}
            for p in files:
                try:sizes.setdefault(p.stat().st_size,[]).append(p)
                except OSError:pass
            for size,group in sizes.items():
                if size==0 or len(group)<2:continue
                hashes={}
                for p in group:
                    try:
                        h=hashlib.sha256()
                        with p.open("rb") as f:
                            for chunk in iter(lambda:f.read(1048576),b""):h.update(chunk)
                        hashes.setdefault(h.hexdigest(),[]).append(p)
                    except OSError:pass
                for same in hashes.values():
                    if len(same)>1:result.extend((p,size,"重复") for p in same[1:])
        else:
            now=time.time()
            for p in files:
                try:
                    st=p.stat();days=int((now-st.st_mtime)/86400)
                    reason="空文件" if st.st_size==0 else ("疑似副本" if any(x in p.stem.lower() for x in ("copy","副本","(1)")) else (f"{days}天未修改" if days>=45 else ""))
                    if reason:result.append((p,st.st_size,reason))
                except OSError:pass
        self.root.after(0,lambda:self.显示扫描结果(mode,result))
    threading.Thread(target=work,daemon=True).start()

def 对话扫描结果(self,mode,rows):
    if not rows:
        self.说("闻完了，没有发现明显的剩饭。",duration=2600);return
    self.说(f"闻到了 {len(rows)} 份候选。\n要打开菜单看看吗？",
        [("看看",lambda:self.候选窗口(mode,rows)),("先不了",lambda:None)])

def 候选窗口(self,mode,rows):
    w=tk.Toplevel(self.root);w.title("重复文件" if mode=="duplicate" else "垃圾候选")
    w.geometry("650x430");w.attributes("-topmost",True)
    tk.Label(w,text=f"发现 {len(rows)} 个候选；默认不选择，不会自动删除。",
        font=("Microsoft YaHei UI",9)).pack(pady=9)
    lb=tk.Listbox(w,selectmode=tk.EXTENDED,font=("Microsoft YaHei UI",9));lb.pack(fill="both",expand=True,padx=12)
    for p,size,reason in rows:lb.insert(tk.END,f"[{reason}]  {p.name}  ·  {size/1024:.1f} KB  ·  {p.parent}")
    def ask_remove():
        chosen=[rows[i][0] for i in lb.curselection()]
        if not chosen:return
        w.destroy()
        self.说(f"选中了 {len(chosen)} 项。\n真的都不要了吗？",
            [("不要了，吃掉",lambda:self.真正吃掉(chosen)),("算了",lambda:None)])
    tk.Button(w,text="投喂选中项",command=ask_remove,font=("Microsoft YaHei UI",9)).pack(pady=10)

Leftover.说=说
Leftover.关闭对话=关闭对话
Leftover.真正吃掉=真正吃掉
Leftover.取消进食=取消进食
Leftover.__init__=对话初始化
Leftover.load_images=新加载图片
Leftover.build_menu=对话菜单
Leftover.save_state=保存含食谱
Leftover.confirm_eat=宠物确认
Leftover.animate=对话动画
Leftover.开始扫描=安静扫描
Leftover.显示扫描结果=对话扫描结果
Leftover.候选窗口=候选窗口


悬停版初始化=Leftover.__init__
def 悬停初始化(self):
    悬停版初始化(self)
    self.canvas.bind("<Enter>",lambda e:self.醒来())
    self.canvas.bind("<Motion>",lambda e:self.醒来())

def 醒来(self):
    self.last_activity=time.time()

def 休息绘制(self):
    c=self.canvas;c.delete("all")
    if self.folded:c.create_image(34,42,image=self.peek_image);return
    now=time.time();idle=now-self.last_activity;frame=int(self.phase*1.7)%8
    if self.chew:
        mouth=1+int(abs(math.sin(self.chew*.72))*2)
        c.create_image(110,123+math.sin(self.phase*5)*3,image=self.mouths[mouth]);return
    if self.mouth_level>.45:
        mouth=max(1,min(3,round(self.mouth_level)));c.create_image(110,123,image=self.mouths[mouth]);return
    if idle>=8:
        order=("text","code","image","archive","metal","trash","empty")
        ambient=order[int((idle-8)/2.0)%len(order)]
        if idle>=18:c.create_image(110,143,image=self.puddle[ambient][frame])
        else:c.create_image(110,139,image=self.liquid[ambient][frame])
    else:
        c.create_image(110,124+math.sin(self.phase)*1.4,image=self.liquid[self.kind][frame])

Leftover.醒来=醒来
Leftover.__init__=悬停初始化
Leftover.draw=休息绘制


bottom_right_base=Leftover.__init__
def bottom_right_start(self):
    self.idle_twitch=0
    bottom_right_base(self)
    sw=self.root.winfo_screenwidth();sh=self.root.winfo_screenheight()
    self.root.geometry(f"220x235+{max(0,sw-238)}+{max(0,sh-305)}")

def 持续活动绘制(self):
    c=self.canvas;c.delete("all")
    if self.folded:c.create_image(34,42,image=self.peek_image);return
    now=time.time();idle=now-self.last_activity;frame=int(self.phase*1.9)%8
    twitch=getattr(self,"idle_twitch",0)
    kick=math.sin(twitch*1.55)*6 if twitch else 0
    drift=math.sin(self.phase*.38)*4+math.sin(self.phase*.91)*1.5
    breathe=math.sin(self.phase*.72)*2
    if self.chew:
        mouth=1+int(abs(math.sin(self.chew*.72))*2)
        c.create_image(110+kick,123+math.sin(self.phase*5)*3,image=self.mouths[mouth]);return
    if self.mouth_level>.45:
        mouth=max(1,min(3,round(self.mouth_level)))
        c.create_image(110+drift,123+breathe,image=self.mouths[mouth]);return
    if twitch and 7<twitch<15:
        c.create_image(110+kick,124-abs(kick)*.35,image=self.mouths[1]);return
    if idle>=8:
        order=("text","code","image","archive","metal","trash","empty")
        ambient=order[int((idle-8)/2.0)%len(order)]
        if idle>=18:
            c.create_image(110+drift+kick*.45,143+math.sin(self.phase*.55)*2,image=self.puddle[ambient][frame])
        else:
            c.create_image(110+drift+kick,139+breathe,image=self.liquid[ambient][frame])
    else:
        c.create_image(110+drift*.7+kick,124+breathe,image=self.liquid[self.kind][frame])

def 持续活动动画(self):
    if self.stopping:return
    self.phase+=.09;self.mouth_level+=(self.mouth_target-self.mouth_level)*.30
    if self.chew:
        self.chew-=1
        if self.chew==0:
            self.kind=self.pending_kind or self.kind;self.pending_kind=None;self.mouth_target=0
            self.last_activity=time.time();self.save_state();self.说(味道[self.kind],duration=2600)
    else:
        if self.idle_twitch:self.idle_twitch-=1
        elif time.time()-self.last_activity>3 and random.random()<.0045:self.idle_twitch=random.randint(20,30)
    self.draw();self.root.after(55,self.animate)

Leftover.__init__=bottom_right_start
Leftover.draw=持续活动绘制
Leftover.animate=持续活动动画

if __name__=="__main__":Leftover().run()
