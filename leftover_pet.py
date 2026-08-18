# -*- coding: utf-8 -*-
import colorsys, ctypes, hashlib, json, math, os, random, subprocess, sys, time, tkinter as tk, threading, winreg
from ctypes import wintypes
from pathlib import Path
from tkinter import messagebox
from PIL import Image, ImageChops, ImageGrab, ImageOps, ImageTk
from tkinterdnd2 import TkinterDnD, DND_FILES
import pystray

REQUEST_DIR=Path(os.getenv("LOCALAPPDATA",str(Path.home())))/"LeftoverPet"/"feed-requests"
_START_POINT=wintypes.POINT();ctypes.windll.user32.GetCursorPos(ctypes.byref(_START_POINT))
START_CURSOR=(_START_POINT.x,_START_POINT.y)
_INSTANCE_MUTEX=ctypes.windll.kernel32.CreateMutexW(None,False,"Local\\LeftoverPetSingleInstanceV2")
if ctypes.windll.kernel32.GetLastError()==183:
    requested=[str(Path(p).resolve()) for p in sys.argv[1:] if Path(p).exists()]
    if requested:
        try:
            REQUEST_DIR.mkdir(parents=True,exist_ok=True)
            request=REQUEST_DIR/f"{time.time_ns()}-{os.getpid()}.json"
            temp=request.with_suffix(".tmp")
            temp.write_text(json.dumps({"paths":requested,"cursor":START_CURSOR},ensure_ascii=False),encoding="utf-8")
            os.replace(temp,request)
        except OSError:pass
    raise SystemExit(0)

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
    self.dialog_offset=None

def 同步对话位置(self):
    if not self.dialog or not getattr(self,"dialog_offset",None):return
    try:
        dx,dy=self.dialog_offset
        self.dialog.geometry(f"+{self.root.winfo_x()+dx}+{self.root.winfo_y()+dy}")
        self.dialog.lift()
    except tk.TclError:pass

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
    self.dialog_offset=(x-rx,y-ry)
    if duration:w.after(duration,lambda:self.关闭对话())

def 宠物确认(self,paths):
    count=len(paths)
    text="这个不要了吗？\n我会把它放进回收站，还能找回来。" if count==1 else f"这 {count} 个都不要了吗？\n我会把它们放进回收站。"
    self.说(text,[("不要了，吃掉",lambda:self.真正吃掉(paths)),("算了",lambda:self.取消进食())])

def 取消进食(self):
    self.mouth_target=0;self.last_activity=time.time()
    self.说("改变主意了？",duration=1400)

def 预先回收(self,paths):
    kind="empty";total=0
    try:
        for p in paths:
            if p.is_dir():raw=p.name.encode("utf-8","replace")
            else:
                total+=p.stat().st_size
                with p.open("rb") as f:raw=f.read(300000)
            kind=classify(p,raw)
    except OSError:
        self.mouth_target=0;self.说("咬不开。它好像还不想走。",duration=2200);return False
    if not move_to_recycle_bin(paths):
        self.mouth_target=0;self.说("没吃到，Windows 把它留下了。",duration=2400);return False
    self.prepared_meal=(kind,total,len(paths));return True

def 完成已回收进食(self):
    meal=getattr(self,"prepared_meal",None)
    if not meal:return
    kind,total,count=meal;self.prepared_meal=None
    self.pending_kind=kind;self.last_meal="";self.chew=44;self.mouth_target=3;self.active_paths=[]
    self.history.append({"kind":kind,"count":count,"size":total,"time":int(time.time())})

def 真正吃掉(self,paths):
    if 预先回收(self,paths):完成已回收进食(self)

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
        # 咀嚼不是单纯切换嘴巴：身体会张开、收缩，再短暂摊开后复原。
        meal=self.pending_kind or self.kind;cycle=self.chew%15
        if cycle<6:
            mouth=1+int(abs(math.sin(self.chew*.78))*2)
            c.create_image(110+math.sin(self.chew)*5,122+math.sin(self.phase*6)*4,image=self.mouths[mouth])
        elif cycle<11:
            c.create_image(110+math.sin(self.chew*.8)*7,132+abs(math.sin(self.chew))*5,
                image=self.liquid[meal][frame])
        else:
            c.create_image(110+math.sin(self.chew)*3,145,image=self.puddle[meal][frame])
        return
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
            if getattr(self,"deferred_paths",None):
                waiting=self.deferred_paths[:];self.deferred_paths.clear()
                self.root.after(2800,lambda p=waiting:从右键召唤(self,p))
    else:
        if self.idle_twitch:self.idle_twitch-=1
        elif time.time()-self.last_activity>3 and random.random()<.0045:self.idle_twitch=random.randint(20,30)
    self.draw();self.root.after(55,self.animate)

Leftover.__init__=bottom_right_start
Leftover.draw=持续活动绘制
Leftover.animate=持续活动动画


# v0.2: 选中文件后召唤余食，以及可保存的基础皮肤。
SKINS={
    "origin":("原生黑","#11151b",.08),
    "deepsea":("深海蓝","#164f68",.34),
    "glitch":("故障紫","#71336f",.34),
    "mold":("霉菌绿","#526235",.32),
    "rust":("锈蚀红","#7b3b2c",.34),
    "pearl":("珍珠白","#c7ccd0",.40),
}
SKIN_GLOW={"origin":None,"deepsea":"#52e6ff","glitch":"#ff4fac",
    "mold":"#b6d96b","rust":"#ff765d","pearl":"#eef3f6"}

def 当前发光色(self):
    return SKIN_GLOW.get(getattr(self,"skin","origin")) or COLORS.get(self.kind,"#d7ff55")

def 读取剪贴板文件():
    CF_HDROP=15;files=[]
    if not ctypes.windll.user32.OpenClipboard(None):return files
    try:
        handle=ctypes.windll.user32.GetClipboardData(CF_HDROP)
        if not handle:return files
        count=ctypes.windll.shell32.DragQueryFileW(handle,0xFFFFFFFF,None,0)
        for i in range(count):
            length=ctypes.windll.shell32.DragQueryFileW(handle,i,None,0)
            buf=ctypes.create_unicode_buffer(length+1)
            ctypes.windll.shell32.DragQueryFileW(handle,i,buf,length+1)
            p=Path(buf.value)
            if p.exists():files.append(p)
    finally:ctypes.windll.user32.CloseClipboard()
    return files

class _LVITEMW(ctypes.Structure):
    _fields_=[("mask",wintypes.UINT),("iItem",ctypes.c_int),("iSubItem",ctypes.c_int),
        ("state",wintypes.UINT),("stateMask",wintypes.UINT),("pszText",ctypes.c_void_p),
        ("cchTextMax",ctypes.c_int),("iImage",ctypes.c_int),("lParam",ctypes.c_ssize_t),
        ("iIndent",ctypes.c_int),("iGroupId",ctypes.c_int),("cColumns",wintypes.UINT),
        ("puColumns",ctypes.c_void_p),("piColFmt",ctypes.c_void_p),("iGroup",ctypes.c_int)]

def 桌面列表句柄():
    u=ctypes.windll.user32
    u.FindWindowW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR];u.FindWindowW.restype=wintypes.HWND
    u.FindWindowExW.argtypes=[wintypes.HWND,wintypes.HWND,wintypes.LPCWSTR,wintypes.LPCWSTR]
    u.FindWindowExW.restype=wintypes.HWND
    progman=u.FindWindowW("Progman",None)
    view=u.FindWindowExW(progman,0,"SHELLDLL_DefView",None) if progman else 0
    if not view:
        worker=0
        while True:
            worker=u.FindWindowExW(0,worker,"WorkerW",None)
            if not worker:break
            view=u.FindWindowExW(worker,0,"SHELLDLL_DefView",None)
            if view:break
    return u.FindWindowExW(view,0,"SysListView32","FolderView") if view else 0

def 桌面选中图标():
    """跨进程读取桌面 ListView 中已选图标的名称和真实屏幕坐标。"""
    hwnd=桌面列表句柄()
    if not hwnd:return []
    u,k=ctypes.windll.user32,ctypes.windll.kernel32
    u.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    u.SendMessageW.restype=ctypes.c_ssize_t
    k.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];k.OpenProcess.restype=ctypes.c_void_p
    k.VirtualAllocEx.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,wintypes.DWORD,wintypes.DWORD]
    k.VirtualAllocEx.restype=ctypes.c_void_p
    k.WriteProcessMemory.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
    k.ReadProcessMemory.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
    k.VirtualFreeEx.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,wintypes.DWORD]
    pid=wintypes.DWORD();u.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    process=k.OpenProcess(0x0008|0x0010|0x0020|0x0400,False,pid.value)
    if not process:return []
    MEM_COMMIT_RESERVE=0x3000;PAGE_READWRITE=0x04;MEM_RELEASE=0x8000
    item_mem=k.VirtualAllocEx(process,None,ctypes.sizeof(_LVITEMW),MEM_COMMIT_RESERVE,PAGE_READWRITE)
    text_mem=k.VirtualAllocEx(process,None,1024,MEM_COMMIT_RESERVE,PAGE_READWRITE)
    point_mem=k.VirtualAllocEx(process,None,ctypes.sizeof(wintypes.POINT),MEM_COMMIT_RESERVE,PAGE_READWRITE)
    rows=[]
    try:
        if not item_mem or not text_mem or not point_mem:return []
        count=u.SendMessageW(hwnd,0x1004,0,0) # LVM_GETITEMCOUNT
        for index in range(max(0,count)):
            if not (u.SendMessageW(hwnd,0x102C,index,0x0002)&0x0002):continue # LVIS_SELECTED
            item=_LVITEMW();item.mask=0x0001;item.iItem=index;item.pszText=text_mem;item.cchTextMax=511
            written=ctypes.c_size_t()
            k.WriteProcessMemory(process,item_mem,ctypes.byref(item),ctypes.sizeof(item),ctypes.byref(written))
            u.SendMessageW(hwnd,0x1073,index,item_mem) # LVM_GETITEMTEXTW
            text=ctypes.create_unicode_buffer(512);read=ctypes.c_size_t()
            k.ReadProcessMemory(process,text_mem,text,ctypes.sizeof(text),ctypes.byref(read))
            u.SendMessageW(hwnd,0x1010,index,point_mem) # LVM_GETITEMPOSITION
            point=wintypes.POINT();k.ReadProcessMemory(process,point_mem,ctypes.byref(point),ctypes.sizeof(point),ctypes.byref(read))
            u.ClientToScreen(hwnd,ctypes.byref(point));rows.append((text.value,point.x,point.y))
    finally:
        for address in (item_mem,text_mem,point_mem):
            if address:k.VirtualFreeEx(process,address,0,MEM_RELEASE)
        k.CloseHandle(process)
    return rows

def 文件选区位置(paths):
    rows=桌面选中图标()
    if not rows:return None
    wanted=[]
    for p in paths:
        p=Path(p);wanted.extend((p.name.casefold(),p.stem.casefold()))
    matched=[(x,y) for name,x,y in rows if name.casefold() in wanted]
    points=matched or [(x,y) for _,x,y in rows]
    if not points:return None
    # 以整组选中图标的包围盒中心为目标，避免被排列稀疏的图标拉偏。
    xs=[p[0] for p in points];ys=[p[1] for p in points]
    return ((min(xs)+max(xs))//2+36,(min(ys)+max(ys))//2+34)

def 桌面选区详情(paths):
    rows=桌面选中图标()
    if not rows:return list(paths),None,[]
    folders=[]
    for p in paths:
        parent=Path(p).parent
        if parent not in folders:folders.append(parent)
    candidates=[]
    for folder in folders:
        try:candidates.extend(folder.iterdir())
        except OSError:pass
    selected_paths=[];points=[]
    for label,x,y in rows:
        key=label.casefold();match=next((p for p in candidates if p.name.casefold()==key or p.stem.casefold()==key),None)
        if match and match not in selected_paths:selected_paths.append(match);points.append((x+36,y+34))
    selected_paths=selected_paths or list(paths)
    points=points or [(x+36,y+34) for _,x,y in rows]
    xs=[p[0] for p in points];ys=[p[1] for p in points]
    center=((min(xs)+max(xs))//2,(min(ys)+max(ys))//2) if points else None
    return selected_paths,center,points

def 发送复制快捷键():
    KEYEVENTF_KEYUP=2;VK_CONTROL=0x11;VK_C=0x43
    u=ctypes.windll.user32
    u.keybd_event(VK_CONTROL,0,0,0);u.keybd_event(VK_C,0,0,0)
    u.keybd_event(VK_C,0,KEYEVENTF_KEYUP,0);u.keybd_event(VK_CONTROL,0,KEYEVENTF_KEYUP,0)

def 染色PIL(src,skin):
    src=src.convert("RGBA")
    if skin=="origin":return ImageTk.PhotoImage(src)
    _,hex_color,_=SKINS[skin]
    rgb=tuple(int(hex_color[i:i+2],16) for i in (1,3,5))
    hue=int(colorsys.rgb_to_hsv(*(v/255 for v in rgb))[0]*255)
    hsv=src.convert("RGB").convert("HSV");h,s,v=hsv.split()
    # 只选中原图里有色且可见的眼睛、像素和边缘微光；黑色身体完全保留。
    chroma=s.point(lambda p:255 if p>=34 else 0)
    visible=v.point(lambda p:255 if p>=30 else 0)
    mask=ImageChops.multiply(chroma,visible)
    target_h=Image.new("L",src.size,hue)
    target_s=Image.new("L",src.size,18 if skin=="pearl" else 205)
    recolored=Image.merge("HSV",(target_h,target_s,v)).convert("RGBA")
    recolored.putalpha(src.getchannel("A"))
    return ImageTk.PhotoImage(Image.composite(recolored,src,mask))

def 染色图片(path,skin):
    return 染色PIL(Image.open(path),skin)

皮肤前加载=Leftover.load_images
def 皮肤加载(self):
    skin=getattr(self,"skin","origin")
    self.states={k:染色图片(ASSETS/f"pet-{k}.png",skin) for k in COLORS}
    self.mouths=[染色图片(ASSETS/f"mouth-{i}.png",skin) for i in range(4)]
    # 余食不是“长出一张嘴”，而是整个身体逐帧变成嘴。背侧尺寸基本不动，
    # 朝目标的一侧逐渐延展，四个方向共用同一套有机形变。
    self.swallow_left=[];self.swallow_right=[];self.swallow_up=[];self.swallow_down=[]
    widths=(150,205,286,326)
    for i in range(4):
        source=Image.open(ASSETS/f"swallow-right-{i}.png").convert("RGBA")
        right=source.resize((widths[i],218),Image.Resampling.LANCZOS)
        left=ImageOps.mirror(right)
        up=right.rotate(90,expand=True,resample=Image.Resampling.BICUBIC)
        down=right.rotate(-90,expand=True,resample=Image.Resampling.BICUBIC)
        # 复用持久皮肤的局部发光色规则，不给黑色身体整体蒙色。
        self.swallow_right.append(染色PIL(right,skin));self.swallow_left.append(染色PIL(left,skin))
        self.swallow_up.append(染色PIL(up,skin));self.swallow_down.append(染色PIL(down,skin))
    self.swallow_widths=widths
    self.peek_image=染色图片(ASSETS/"pet-peek.png",skin)
    self.turn_left=染色图片(ASSETS/"pet-turn-left.png",skin)
    self.turn_right=染色图片(ASSETS/"pet-turn-right.png",skin)
    self.liquid={k:[染色图片(ASSETS/f"liquid-{k}-{i}.png",skin) for i in range(8)] for k in COLORS}
    self.puddle={k:[染色图片(ASSETS/f"puddle-{k}-{i}.png",skin) for i in range(8)] for k in COLORS}

原读状态=Leftover.load_state
def 皮肤读状态(self):
    原读状态(self);self.skin="origin"
    try:
        d=json.loads(STATE.read_text(encoding="utf-8"))
        if d.get("skin") in SKINS:self.skin=d["skin"]
    except Exception:pass

def 完整保存状态(self):
    try:
        STATE.parent.mkdir(parents=True,exist_ok=True)
        STATE.write_text(json.dumps({"kind":self.kind,"last_meal":self.last_meal,
            "history":self.history[-50:],"skin":self.skin},ensure_ascii=False,indent=2),encoding="utf-8")
    except OSError:pass

def 更换皮肤(self,skin):
    if skin not in SKINS or skin==self.skin:return
    self.skin=skin;皮肤加载(self);self.save_state();self.last_activity=time.time()
    self.说(f"换好了。{SKINS[skin][0]}。",duration=1700)

原对话菜单=Leftover.build_menu
def 皮肤菜单(self):
    原对话菜单(self)
    skin_menu=tk.Menu(self.menu,tearoff=False,font=("Microsoft YaHei UI",9))
    for key,(name,_,__) in SKINS.items():
        skin_menu.add_command(label=("✓ " if key==self.skin else "   ")+name,
            command=lambda k=key:更换皮肤(self,k))
    self.menu.insert_cascade(6,label="更换皮肤",menu=skin_menu)
    self.menu.insert_command(0,label="选中文件后召唤（Ctrl+Shift+E）",
        command=lambda:self.说("先在桌面或文件夹里选中它，\n再按 Ctrl+Shift+E。",duration=3300))

召唤前初始化=Leftover.__init__
def 召唤初始化(self):
    self.skin="origin";self.summon_keys_down=False;self.summon_pending=False;self.seeking=False
    self.pointing=False;self.look_back=False;self.seek_target=None;self.point_count=1
    self.bundling=0;self.bundle_count=0;self.bundle_total=0;self.request_batch=[];self.request_job=None
    self.travel_reveal=False;self.wrap_root_hidden=False
    self.request_target=None
    self.capture_pending=False;self.capture_fallback=[];self.active_paths=[];self.deferred_paths=[]
    召唤前初始化(self)
    创建透明特效层(self)
    注册文件右键(self)
    self.root.after(120,lambda:监听召唤(self))
    self.root.after(260,lambda:轮询右键请求(self))
    startup=[Path(p) for p in sys.argv[1:] if Path(p).exists()]
    if startup:self.root.after(650,lambda p=startup:排队右键文件(self,p,START_CURSOR))

def 创建透明特效层(self):
    w=tk.Toplevel(self.root);self.fx_window=w
    w.overrideredirect(True);w.configure(bg=KEY);w.attributes("-topmost",True)
    sw,sh=self.root.winfo_screenwidth(),self.root.winfo_screenheight();w.geometry(f"{sw}x{sh}+0+0")
    try:w.wm_attributes("-transparentcolor",KEY)
    except tk.TclError:pass
    self.fx_canvas=tk.Canvas(w,width=sw,height=sh,bg=KEY,highlightthickness=0)
    self.fx_canvas.pack(fill="both",expand=True);w.update_idletasks()
    try:
        hwnd=ctypes.windll.user32.GetParent(w.winfo_id())
        style=ctypes.windll.user32.GetWindowLongW(hwnd,-20)
        ctypes.windll.user32.SetWindowLongW(hwnd,-20,style|0x20|0x80|0x08000000)
    except Exception:pass
    w.withdraw()

def 注册文件右键(self):
    """按当前 exe 所在位置注册当前用户文件菜单，不需要管理员权限。"""
    if not getattr(sys,"frozen",False):return
    exe=str(Path(sys.executable).resolve())
    for target in (r"Software\Classes\*\shell\LeftoverFeed",
                   r"Software\Classes\Directory\shell\LeftoverFeed"):
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,target) as key:
                winreg.SetValueEx(key,None,0,winreg.REG_SZ,"喂给余食")
                winreg.SetValueEx(key,"Icon",0,winreg.REG_SZ,exe)
                winreg.SetValueEx(key,"MultiSelectModel",0,winreg.REG_SZ,"Player")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER,target+r"\command") as command:
                # Windows 会为多选项目逐项调用静态 verb；每项写入请求队列后由主进程合并。
                winreg.SetValueEx(command,None,0,winreg.REG_SZ,f'"{exe}" "%1"')
        except OSError:pass

def 从右键召唤(self,paths,target=None,icon_targets=None):
    paths=[Path(p) for p in paths if Path(p).exists()]
    if not paths:return
    if self.seeking or self.pointing:
        # 尚未确认时，迟到的 Shell 参数并入当前一餐，不重启动画、不替换对话。
        for p in paths:
            if p not in self.active_paths:self.active_paths.append(p)
        self.point_count=max(1,min(3,len(self.active_paths)))
        if self.pointing:
            self.说("它吗？" if len(self.active_paths)==1 else "它们吗？",
                [("没戳！",lambda:确认指认(self,self.active_paths)),
                 ("啊搞错了嘿嘿嘿",lambda:认错了(self))])
        return
    if self.bundling or self.chew:
        # 一餐已经确认后不允许新请求改变状态；留到当前咽下后再处理。
        for p in paths:
            if p not in self.active_paths and p not in self.deferred_paths:self.deferred_paths.append(p)
        return
    if target is None:
        pt=wintypes.POINT();ctypes.windll.user32.GetCursorPos(ctypes.byref(pt));target=(pt.x,pt.y)
    开始蠕动(self,paths,target[0],target[1],icon_targets)

def 排队右键文件(self,paths,target=None):
    for p in paths:
        p=Path(p)
        if p.exists() and p not in self.request_batch and p not in self.active_paths:self.request_batch.append(p)
    if target is not None:self.request_target=(int(target[0]),int(target[1]))
    if self.request_job:
        try:self.root.after_cancel(self.request_job)
        except tk.TclError:pass
    # Explorer 多选时可能逐个启动命令，留出短暂窗口合并为同一餐。
    self.request_job=self.root.after(260,lambda:提交右键批次(self))

def 提交右键批次(self):
    paths=self.request_batch[:];target=self.request_target
    self.request_batch.clear();self.request_job=None;self.request_target=None
    if paths:
        paths,desktop_target,icon_targets=桌面选区详情(paths)
        从右键召唤(self,paths,desktop_target or target,icon_targets)

def 捕获完整右键选区(self,fallback):
    for p in fallback:
        p=Path(p)
        if p.exists() and p not in self.capture_fallback:self.capture_fallback.append(p)
    if self.capture_pending:return
    self.capture_pending=True;发送复制快捷键()
    def finish():
        selected=读取剪贴板文件();merged=[]
        for p in selected+self.capture_fallback:
            if p.exists() and p not in merged:merged.append(p)
        self.capture_fallback.clear();self.capture_pending=False
        if merged:排队右键文件(self,merged)
    self.root.after(240,finish)

def 轮询右键请求(self):
    if self.stopping:return
    try:requests=sorted(REQUEST_DIR.glob("*.json")) if REQUEST_DIR.exists() else []
    except OSError:requests=[]
    for request in requests:
        try:
            data=json.loads(request.read_text(encoding="utf-8"))
            if isinstance(data,dict):
                paths=[Path(p) for p in data.get("paths",[])];target=data.get("cursor")
            else:
                paths=[Path(p) for p in data];target=None
            request.unlink(missing_ok=True)
            if paths:排队右键文件(self,paths,target)
        except (OSError,ValueError,TypeError):
            try:request.unlink(missing_ok=True)
            except OSError:pass
    self.root.after(260,lambda:轮询右键请求(self))

def 监听召唤(self):
    if self.stopping:return
    u=ctypes.windll.user32
    down=bool(u.GetAsyncKeyState(0x11)&0x8000 and u.GetAsyncKeyState(0x10)&0x8000 and u.GetAsyncKeyState(0x45)&0x8000)
    if down and not self.summon_keys_down and not self.seeking:self.summon_pending=True
    # 等玩家松开 Shift 后再发送 Ctrl+C，否则 Explorer 会收到 Ctrl+Shift+C。
    if not down and self.summon_keys_down and self.summon_pending:
        self.summon_pending=False;发送复制快捷键();self.root.after(220,lambda:读取召唤目标(self))
    self.summon_keys_down=down;self.root.after(90,lambda:监听召唤(self))

def 读取召唤目标(self):
    paths=读取剪贴板文件()
    if not paths:
        self.说("我没看清。先选中文件，再叫我。",duration=2500);return
    full,target,icon_targets=桌面选区详情(paths)
    if target:开始蠕动(self,full,target[0],target[1],icon_targets)
    else:
        pt=wintypes.POINT();ctypes.windll.user32.GetCursorPos(ctypes.byref(pt));开始蠕动(self,paths,pt.x,pt.y)

def 开始蠕动(self,paths,target_x,target_y,icon_targets=None):
    self.关闭对话();self.root.deiconify();self.root.lift();self.folded=False
    self.canvas.configure(width=220,height=235)
    self.seeking=True;self.pointing=False;self.look_back=False;self.active_paths=list(paths)
    self.icon_targets=list(icon_targets or [(target_x,target_y)])
    捕获图标碎片(self,self.icon_targets)
    self.point_count=max(1,min(3,len(paths)));self.last_activity=time.time()
    sx,sy=self.root.winfo_x(),self.root.winfo_y()
    sw=self.root.winfo_screenwidth()
    # 停在图标旁边而不是盖住它，最后一小段距离交给触手。
    # 身体停在文件侧面约一张“大嘴”的距离；透明窗口可以与图标区域重叠，
    # 但可见躯干不会站到文件上，侧向嘴帧恰好能从旁边含住它。
    ex=target_x-210 if target_x>sw/2 else target_x-10
    ex=max(0,min(sw-220,ex))
    ey=max(0,min(self.root.winfo_screenheight()-235,target_y-118))
    steps=max(48,min(72,int(math.hypot(ex-sx,ey-sy)/18)))
    self.travel_disintegrate=True;self.travel_reveal=False
    start_center=(sx+110,sy+135);end_center=(ex+110,ey+135);glow=当前发光色(self)
    self.fx_window.deiconify();self.fx_window.lift();self.root.withdraw()
    def step(i=0):
        if i>steps:
            self.fx_canvas.delete("all");self.fx_window.withdraw();self.travel_disintegrate=False
            self.travel_reveal=False;self.root.geometry(f"220x235+{ex}+{ey}");self.root.deiconify();self.root.lift()
            self.seeking=False;self.pointing=True;self.look_back=False;self.seek_target=(target_x,target_y)
            question="它吗？" if len(paths)==1 else "它们吗？"
            self.last_activity=time.time();self.说(question,[("没戳！",lambda:确认指认(self,self.active_paths)),
                ("啊搞错了嘿嘿嘿",lambda:认错了(self))]);return
        t=i/steps;fx=self.fx_canvas;fx.delete("all")
        if t>.82 and not self.travel_reveal:
            self.travel_reveal=True;self.root.geometry(f"220x235+{ex}+{ey}");self.root.deiconify();self.root.lift()
        breakup=min(1,t/.16);reform=max(0,min(1,(t-.70)/.30))
        distance=max(1,math.hypot(end_center[0]-start_center[0],end_center[1]-start_center[1]))
        vx=(end_center[0]-start_center[0])/distance;vy=(end_center[1]-start_center[1])/distance
        nx=-vy;ny=vx
        for n in range(46):
            # 大小不一的块状组织依次脱落和迁移，不使用科技感的细线拖尾。
            delay=(n%11)*.009+(n//11)*.004
            move=max(0,min(1,(t-.10-delay)/.67));s=move*move*(3-2*move)
            angle=n*2.399;spread=(12+(n%10)*6)*breakup*(1-reform)
            arc=math.sin(math.pi*s)*(30+((n%5)-2)*6)
            swirl=angle+s*math.pi*1.8+reform*math.pi*2.2
            px=start_center[0]+(end_center[0]-start_center[0])*s+nx*arc+math.cos(swirl)*spread
            py=start_center[1]+(end_center[1]-start_center[1])*s+ny*arc+math.sin(swirl)*spread*.68
            color=glow if n%6==0 else ("#2b3036" if n%3 else "#080b0e")
            size=3+(n%5);skew=math.sin(angle+s*4)*size*.7
            if n%4==0:
                fx.create_oval(px-size,py-size*.72,px+size,py+size*.72,fill=color,outline="")
            else:
                fx.create_polygon(px-size,py-skew,px+skew,py-size,
                    px+size,py+skew,px-skew,py+size,fill=color,outline="")
        if reform>0:
            # 到站后由重叠、互相挤压的团块重新长成一个整体。
            for lump in range(13):
                phase=lump*2.399+self.phase*.55;radius=(46-lump*2.1)*(1-reform)
                cx=end_center[0]+math.cos(phase)*radius;cy=end_center[1]+math.sin(phase)*radius*.58
                w=9+(lump%5)*4;h=7+(lump%4)*4
                color=glow if lump==0 else ("#0a0d10" if lump%2 else "#24292e")
                fx.create_oval(cx-w,cy-h,cx+w,cy+h,fill=color,outline="")
        self.root.after(16,lambda:step(i+1))
    step()

def 捕获图标碎片(self,targets):
    """截取桌面上的真实目标图标，供揉皱、碎裂动画使用；不接触原文件。"""
    self.icon_crush=[]
    try:screen=ImageGrab.grab(all_screens=True).convert("RGB")
    except Exception:screen=None
    for tx,ty in targets:
        if screen is None:
            self.icon_crush.append(None);continue
        # Windows 桌面坐标给的是图标中心；只截取图标主体，避开下方文件名。
        crop=screen.crop((round(tx-25),round(ty-27),round(tx+25),round(ty+23))).convert("RGBA")
        squash=[]
        for width in (50,42,54,34,47):
            squeezed=crop.resize((width,50),Image.Resampling.LANCZOS)
            canvas=Image.new("RGBA",(58,54),(0,0,0,0));canvas.alpha_composite(squeezed,((58-width)//2,2))
            squash.append(ImageTk.PhotoImage(canvas))
        tiles=[]
        for row in range(4):
            for col in range(4):
                tile=crop.crop((col*12,row*12,min(50,col*12+14),min(50,row*12+14)))
                tiles.append(ImageTk.PhotoImage(tile))
        self.icon_crush.append({"squash":squash,"tiles":tiles})

def 确认指认(self,paths):
    # 用户已经明确点击“没戳！”，此时先送入可恢复的系统回收站，
    # 桌面原图标立即消失；后续动画使用之前捕获的图标代理。
    if not 预先回收(self,paths):return
    self.pointing=False;self.look_back=False;self.mouth_target=1
    self.bundle_count=max(1,min(3,len(paths)));self.bundle_total=len(paths)
    # 单文件直接吞；多文件先收拢成一团，最后只进行一次整体吞咽。
    self.bundle_duration=1.15 if len(paths)==1 else min(5.8,1.35+len(paths)*.36)
    self.bundling=1;self.bundle_started=time.time()
    self.root.after(round(self.bundle_duration*1000),lambda:完成捏团(self,paths))

def 完成捏团(self,paths):
    self.bundling=0;self.mouth_target=3
    if self.wrap_root_hidden:
        self.wrap_root_hidden=False;self.root.deiconify();self.root.lift()
    完成已回收进食(self)

def 认错了(self):
    self.pointing=False;self.look_back=False;self.active_paths=[];self.last_activity=time.time()
    self.关闭对话();self.root.after(180,lambda:回到角落(self))

def 回到角落(self):
    self.look_back=False
    sw,sh=self.root.winfo_screenwidth(),self.root.winfo_screenheight()
    sx,sy=self.root.winfo_x(),self.root.winfo_y();ex,ey=max(0,sw-238),max(0,sh-305)
    def step(i=0):
        t=min(1,i/52);s=t*t*(3-2*t)
        self.root.geometry(f"+{round(sx+(ex-sx)*s)}+{round(sy+(ey-sy)*s+math.sin(i)*3*(1-t))}")
        if i<52:self.root.after(16,lambda:step(i+1))
    step()

召唤前绘制=Leftover.draw
def 指认绘制(self):
    c=self.canvas
    travelling=getattr(self,"travel_disintegrate",False)
    if hasattr(self,"fx_canvas") and not travelling:self.fx_canvas.delete("all")
    if self.seeking and travelling:
        if self.travel_reveal:召唤前绘制(self)
        else:c.delete("all")
        return
    if self.seeking and not self.folded:
        c.delete("all")
        return
    召唤前绘制(self)
    if self.pointing and not self.folded:
        # 指认时身体也要看向目标，不能只有触手朝过去、脸仍看着用户。
        targets=getattr(self,"icon_targets",[]) or [getattr(self,"seek_target",(self.root.winfo_x(),0))]
        avg_x=sum(p[0] for p in targets)/len(targets)
        facing_left=avg_x<(self.root.winfo_x()+110)
        c.delete("all")
        turn=self.turn_left if facing_left else self.turn_right
        bob=math.sin(self.phase*1.7)*2
        c.create_image(110,126+bob,image=turn)
    if self.folded:return
    if False and self.pointing:
        # 最多三根柔软触手；文件更多时由它们轮流工作。
        glow=当前发光色(self)
        targets=getattr(self,"icon_targets",[]) or [getattr(self,"seek_target",(999,0))]
        count=min(getattr(self,"point_count",1),len(targets))
        chosen=[targets[round(i*(len(targets)-1)/max(1,count-1))] for i in range(count)]
        for i in range(count):
            screen_x,screen_y=chosen[i];dx=screen_x-(self.root.winfo_x()+108);dy=screen_y-(self.root.winfo_y()+143)
            scale=min(1,104/max(1,abs(dx)),94/max(1,abs(dy)))
            tx=108+dx*scale;ty=143+dy*scale;direction=1 if dx>=0 else -1
            spread=(i-(count-1)/2)*4;pulse=math.sin(self.phase*1.8+i*.9)*3
            start_y=143+(i-(count-1)/2)*3
            points=(108,start_y,108+direction*28,151+spread*.16+pulse,
                    108+(tx-108)*.55,143+(ty-143)*.38-pulse,
                    108+(tx-108)*.82,143+(ty-143)*.72+pulse,tx,ty)
            width=5
            c.create_line(*points,fill="#070a0d",width=width+3,smooth=True,splinesteps=36)
            c.create_line(*points,fill="#20262b",width=width,smooth=True,splinesteps=36)
            c.create_line(*points,fill=glow,width=1,smooth=True,splinesteps=36)
            c.create_oval(tx-3,ty-3,tx+3,ty+3,
                fill="#080b0e",outline=glow,width=1)
    if False and self.bundling:
        # 三根触手轮班：抓住一份，揉碎，再把小团送进嘴里。
        elapsed=max(0,time.time()-getattr(self,"bundle_started",time.time()))
        total=max(1,getattr(self,"bundle_total",1));per=getattr(self,"bundle_duration",.72)/total
        item=min(total-1,int(elapsed/per));t=max(0,min(1,(elapsed-item*per)/per))
        icon_targets=getattr(self,"icon_targets",[]) or [getattr(self,"seek_target",(999,0))]
        target=icon_targets[item%len(icon_targets)];dx=target[0]-(self.root.winfo_x()+108);dy=target[1]-(self.root.winfo_y()+143)
        scale=min(1,104/max(1,abs(dx)),94/max(1,abs(dy)));edge_x=108+dx*scale;edge_y=143+dy*scale
        left=dx<0;count=getattr(self,"bundle_count",1);glow=当前发光色(self)
        hand=item%count;spread=(hand-(count-1)/2)*15
        # 前半程在桌面边缘反复挤压，后半程收回嘴边。
        carry=max(0,(t-.46)/.54);squash=abs(math.sin(t*math.pi*5))*(1-carry)
        bx=edge_x+(110-edge_x)*carry;by=(edge_y+spread)*(1-carry)+132*carry
        start_y=143+(hand-(count-1)/2)*4
        wave=math.sin(self.phase*2+hand)*5*(1-carry)
        points=(108,start_y,108+(-1 if left else 1)*35,148+wave,
                edge_x+(110-edge_x)*carry*.55,edge_y+(132-edge_y)*carry*.55-wave,bx,by)
        c.create_line(*points,fill="#080b0e",width=8,smooth=True,splinesteps=36)
        c.create_line(*points,fill="#23282d",width=5,smooth=True,splinesteps=36)
        c.create_line(*points,fill=glow,width=1,smooth=True,splinesteps=36)
        radius=(9+squash*4)*(1-carry*.68)
        c.create_oval(bx-radius,by-radius,bx+radius,by+radius,fill="#10151a",outline=glow,width=2)
    绘制全屏特效(self)

def 绘制全屏特效(self):
    if not hasattr(self,"fx_window"):return
    if not self.pointing and not self.bundling:
        self.fx_window.withdraw();return
    self.fx_window.deiconify();self.fx_window.lift();fx=self.fx_canvas;glow=当前发光色(self)
    start=(self.root.winfo_x()+108,self.root.winfo_y()+143)
    targets=getattr(self,"icon_targets",[]) or [getattr(self,"seek_target",start)]
    if self.pointing:
        count=min(3,len(targets));chosen=[targets[round(i*(len(targets)-1)/max(1,count-1))] for i in range(count)]
        for i,(tx,ty) in enumerate(chosen):
            pulse=math.sin(self.phase*1.7+i)*7;mx=(start[0]+tx)/2;my=(start[1]+ty)/2
            points=(start[0],start[1]+(i-(count-1)/2)*5,mx-pulse,my+18+pulse,tx,ty)
            fx.create_line(*points,fill="#070a0d",width=9,smooth=True,splinesteps=48)
            fx.create_line(*points,fill="#24292e",width=5,smooth=True,splinesteps=48)
            fx.create_line(*points,fill=glow,width=1,smooth=True,splinesteps=48)
            fx.create_oval(tx-4,ty-4,tx+4,ty+4,fill="#090c0f",outline=glow)
    if self.bundling:
        if not self.wrap_root_hidden:
            self.wrap_root_hidden=True;self.root.withdraw()
        elapsed=max(0,time.time()-getattr(self,"bundle_started",time.time()))
        duration=getattr(self,"bundle_duration",1.15);total=max(1,getattr(self,"bundle_total",1))
        body_x=self.root.winfo_x()+110;body_y=self.root.winfo_y()+126
        # 文件团位于余食与目标群之间、靠近嘴的一侧。
        avg_x=sum(p[0] for p in targets)/len(targets);avg_y=sum(p[1] for p in targets)/len(targets)
        adx,ady=avg_x-body_x,avg_y-body_y;alen=max(1,math.hypot(adx,ady))
        pile_x=body_x+adx/alen*82;pile_y=body_y+ady/alen*70

        if total>1 and elapsed<duration-1.08:
            gather_duration=max(.45,duration-1.08)
            phase=max(0,min(total-.001,elapsed/gather_duration*total))
            item=int(phase);t=phase-item;done=item
            tx,ty=targets[item%len(targets)]
            # 收拢阶段显示原形；三根触手使用三个不同根部轮班工作。
            fx.create_image(body_x,body_y,image=self.states.get(self.kind,self.states["void"]))
            hand=item%3;root_offset=(hand-1)*9
            ease=t*t*(3-2*t);mx=tx+(pile_x-tx)*ease;my=ty+(pile_y-ty)*ease
            bend=math.sin(t*math.pi)*((hand-1)*18+14)
            points=(body_x,body_y+root_offset,
                (body_x+mx)/2-bend,(body_y+my)/2+22+bend,mx,my)
            fx.create_line(*points,fill="#050709",width=10,smooth=True,splinesteps=52)
            fx.create_line(*points,fill="#282d31",width=6,smooth=True,splinesteps=52)
            fx.create_line(*points,fill=glow,width=1,smooth=True,splinesteps=52)
            # 先把真实图标左右揉皱，再切成十六块错位碎片卷回嘴边。
            captured=self.icon_crush[item%len(self.icon_crush)] if getattr(self,"icon_crush",[]) else None
            if captured and t<.34:
                squash_frame=min(4,int(t/.34*5))
                fx.create_image(mx,my,image=captured["squash"][squash_frame])
            elif captured:
                break_t=min(1,(t-.34)/.66)
                for n,tile in enumerate(captured["tiles"]):
                    row,col=divmod(n,4);angle=n*2.399+item*.7
                    # 起初仍保持图标的方形构造，随后互相错位并被揉进同一团。
                    base_x=(col-1.5)*12*(1-break_t);base_y=(row-1.5)*12*(1-break_t)
                    scatter=math.sin(break_t*math.pi)*(8+n%4*3)
                    px=mx+base_x+math.cos(angle)*scatter;py=my+base_y+math.sin(angle)*scatter*.68
                    fx.create_image(px,py,image=tile)
            else:
                for n in range(16):
                    angle=n*2.399+item*.7;scatter=(1-ease)*(13+n%4*3)
                    px=mx+math.cos(angle)*scatter;py=my+math.sin(angle)*scatter*.72
                    size=2+n%3;color=glow if n%5==0 else ("#e7e4dc" if n%3 else "#24292e")
                    fx.create_rectangle(px-size,py-size,px+size,py+size,fill=color,outline="")
            # 已收回的内容只在嘴边形成同一个有机文件团，不再给每个图标盖黑圆。
            pile_size=min(31,9+done*3+t*2)
            fx.create_oval(pile_x-pile_size,pile_y-pile_size*.72,
                pile_x+pile_size,pile_y+pile_size*.72,fill="#080b0d",outline=glow,width=1)
            for n in range(min(18,done*3+3)):
                angle=n*2.399+self.phase*.25;radius=(n%5)/5*pile_size*.75
                px=pile_x+math.cos(angle)*radius;py=pile_y+math.sin(angle)*radius*.6
                fx.create_rectangle(px-2,py-2,px+2,py+2,fill=glow if n%4==0 else "#34393d",outline="")
            fx.create_text(pile_x,pile_y-pile_size-11,text=f"×{total}",fill=glow,
                font=("Microsoft YaHei UI",8,"bold"))
            return

        # 单文件直接进入吞咽；多文件完成收拢后只吞文件团一次。
        if total==1:
            t=max(0,min(1,elapsed/duration));tx,ty=targets[0]
        else:
            t=max(0,min(1,(elapsed-(duration-1.08))/1.08));tx,ty=pile_x,pile_y
        dx,dy=tx-body_x,ty-body_y
        if abs(dx)>=abs(dy):
            ux,uy=(1,0) if dx>=0 else (-1,0);vx,vy=0,1
            sprites=self.swallow_right if dx>=0 else self.swallow_left
        else:
            ux,uy=(0,1) if dy>=0 else (0,-1);vx,vy=1,0
            sprites=self.swallow_down if dy>=0 else self.swallow_up
        # 身体始终钉在原地，只让头转向目标，侧嘴逐帧裂开并包住图标。
        if t<.16:frame=0
        elif t<.32:frame=1
        elif t<.68:frame=2
        elif t<.84:frame=3
        else:frame=1
        # 背部锚点不动，整只余食只向目标一侧增长；不是在身体外另画一张嘴。
        bite=0 if t<.68 else math.sin(min(1,(t-.68)/.32)*math.pi)*5
        extension=(self.swallow_widths[frame]-self.swallow_widths[0])/2
        sprite_x=body_x+ux*extension;sprite_y=body_y+uy*extension+bite
        fx.create_image(sprite_x,sprite_y,image=sprites[frame])
        if total>1 and t<.76:
            # 文件团被整个身体形成的口腔含住，闭合前仍可看到内部杂质在蠕动。
            shrink=max(.18,1-max(0,(t-.55)/.21));r=27*shrink
            fx.create_oval(pile_x-r,pile_y-r*.72,pile_x+r,pile_y+r*.72,
                fill="#080b0d",outline=glow,width=1)
            fx.create_text(pile_x,pile_y-r-9,text=f"×{total}",fill=glow,
                font=("Microsoft YaHei UI",8,"bold"))
        if t>.70:
            close=max(0,min(1,(t-.70)/.25));radius=38*(1-close)
            for n in range(10):
                angle=n*2.399;px=tx+math.cos(angle)*radius;py=ty+math.sin(angle)*radius*.65
                size=max(1,4-round(close*3));color=glow if n%4==0 else "#d8d8d2"
                fx.create_rectangle(px-size,py-size,px+size,py+size,fill=color,outline="")

Leftover.load_state=皮肤读状态
Leftover.load_images=皮肤加载
Leftover.save_state=完整保存状态
Leftover.build_menu=皮肤菜单
Leftover.__init__=召唤初始化
Leftover.draw=指认绘制

# 对话框是独立顶层窗口，拖动余食时必须保持相对坐标同步。
原跟随拖动开始=Leftover.drag_start
原跟随拖动中=Leftover.drag_move
原跟随拖动结束=Leftover.drag_end
def 跟随拖动开始(self,e):
    原跟随拖动开始(self,e)
    if self.dialog:
        try:self.dialog_offset=(self.dialog.winfo_x()-self.root.winfo_x(),self.dialog.winfo_y()-self.root.winfo_y())
        except tk.TclError:pass
def 跟随拖动中(self,e):
    原跟随拖动中(self,e);同步对话位置(self)
def 跟随拖动结束(self,e):
    原跟随拖动结束(self,e);同步对话位置(self)
Leftover.drag_start=跟随拖动开始
Leftover.drag_move=跟随拖动中
Leftover.drag_end=跟随拖动结束

if __name__=="__main__":Leftover().run()
