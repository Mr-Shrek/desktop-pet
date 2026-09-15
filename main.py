# -*- coding: utf-8 -*-
"""收工喵 —— tkinter 版（纯 Python 标准库，零第三方依赖）

UI 层：窗口/画布动画/菜单/对话框/气泡/托盘（ctypes Shell_NotifyIcon）。
公共逻辑（常量/数据读写/提醒调度/系统动作/单实例等）在 core.py，
与 PyQt5 版（main_qt.py）共用，两个版本数据互通。
用法：双击 run.bat，或命令行执行 python main.py
"""
import ctypes
import ctypes.wintypes
import gc
import json
import math
import os
import random
import sys
import time
import tkinter as tk
import winreg

from core import *   # 公共常量、输入解析、数据读写、自启、系统动作、单实例等


# ---------- 系统托盘（纯 ctypes Shell_NotifyIcon，零第三方依赖） ----------
import queue as _queue
import threading as _threading

_TRAY_QUEUE = _queue.Queue()          # 托盘事件 → 主线程轮询
_WM_TRAY = 0x0400 + 30                # 自定义托盘消息号
_NIM_ADD, _NIM_MODIFY, _NIM_DELETE = 0, 1, 2
_NIF_MESSAGE, _NIF_ICON, _NIF_TIP = 0x1, 0x2, 0x4
_WM_LBUTTONUP, _WM_LBUTTONDBLCLK = 0x0202, 0x0203
_WM_RBUTTONUP = 0x0205
_MF_STRING = 0x0000
_TPM_RETURNCMD = 0x0100
_TPM_RIGHTBUTTON = 0x0002
_WS_OVERLAPPEDWINDOW = 0x00CF0000
_WM_DESTROY = 0x0002
_CS_HREDRAW, _CS_VREDRAW = 0x0001, 0x0002


class _NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hWnd", ctypes.wintypes.HWND),
        ("uID", ctypes.wintypes.UINT),
        ("uFlags", ctypes.wintypes.UINT),
        ("uCallbackMessage", ctypes.wintypes.UINT),
        ("hIcon", ctypes.wintypes.HICON),
        ("szTip", ctypes.wintypes.WCHAR * 128),
        ("dwState", ctypes.wintypes.DWORD),
        ("dwStateMask", ctypes.wintypes.DWORD),
        ("szInfo", ctypes.wintypes.WCHAR * 256),
        ("uTimeout", ctypes.wintypes.UINT),
        ("szInfoTitle", ctypes.wintypes.WCHAR * 64),
        ("dwInfoFlags", ctypes.wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", ctypes.wintypes.HICON),
    ]


class _ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", ctypes.wintypes.BOOL),
        ("xHotspot", ctypes.wintypes.DWORD),
        ("yHotspot", ctypes.wintypes.DWORD),
        ("hbmMask", ctypes.wintypes.HBITMAP),
        ("hbmColor", ctypes.wintypes.HBITMAP),
    ]


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("style", ctypes.wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", ctypes.wintypes.HICON),
    ]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", ctypes.wintypes.POINT),
    ]


_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_shell32 = ctypes.windll.shell32
_kernel32 = ctypes.windll.kernel32

# ---- Win32 API 64 位签名（缺省按 32 位截断句柄/指针 → 托盘菜单空白、回调溢出异常） ----
_wt = ctypes.wintypes
_LRESULT = ctypes.c_longlong
_user32.DefWindowProcW.restype = _LRESULT
_user32.DefWindowProcW.argtypes = [
    _wt.HWND, _wt.UINT, _wt.WPARAM, _wt.LPARAM]
_user32.CreatePopupMenu.restype = ctypes.c_void_p
_user32.CreatePopupMenu.argtypes = []
_user32.AppendMenuW.restype = _wt.BOOL
_user32.AppendMenuW.argtypes = [
    ctypes.c_void_p, _wt.UINT, ctypes.c_size_t, ctypes.c_wchar_p]
_user32.TrackPopupMenu.restype = _wt.BOOL
_user32.TrackPopupMenu.argtypes = [
    ctypes.c_void_p, _wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    _wt.HWND, ctypes.c_void_p]
_user32.DestroyMenu.restype = _wt.BOOL
_user32.DestroyMenu.argtypes = [ctypes.c_void_p]
_user32.GetCursorPos.restype = _wt.BOOL
_user32.GetCursorPos.argtypes = [ctypes.POINTER(_wt.POINT)]
_user32.GetMessageW.restype = _wt.BOOL
_user32.GetMessageW.argtypes = [ctypes.POINTER(_MSG), _wt.HWND, _wt.UINT, _wt.UINT]
_user32.DispatchMessageW.restype = _LRESULT
_user32.DestroyIcon.restype = _wt.BOOL
_user32.DestroyIcon.argtypes = [ctypes.wintypes.HICON]
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
_user32.TranslateMessage.restype = _wt.BOOL
_user32.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
_user32.RegisterClassExW.restype = ctypes.c_ushort
_user32.RegisterClassExW.argtypes = [ctypes.POINTER(_WNDCLASSEXW)]
_user32.CreateWindowExW.restype = _wt.HWND
_user32.CreateWindowExW.argtypes = [
    _wt.DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p, _wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    _wt.HWND, ctypes.c_void_p, _wt.HINSTANCE, ctypes.c_void_p]
_user32.PostMessageW.restype = _wt.BOOL
_user32.PostMessageW.argtypes = [_wt.HWND, _wt.UINT, _wt.WPARAM, _wt.LPARAM]
_user32.CreateIconIndirect.restype = ctypes.c_void_p
_user32.CreateIconIndirect.argtypes = [ctypes.POINTER(_ICONINFO)]
_gdi32.CreateBitmap.restype = ctypes.c_void_p
_gdi32.CreateBitmap.argtypes = [
    ctypes.c_int, ctypes.c_int, _wt.UINT, _wt.UINT, ctypes.c_void_p]
_gdi32.DeleteObject.restype = _wt.BOOL
_gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
_shell32.Shell_NotifyIconW.restype = _wt.BOOL
_shell32.Shell_NotifyIconW.argtypes = [_wt.DWORD, ctypes.c_void_p]
_kernel32.GetModuleHandleW.restype = ctypes.c_void_p
_kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
_kernel32.CreateMutexW.restype = ctypes.c_void_p
_kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL,
                                   ctypes.c_wchar_p]
_kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
_kernel32.GetLastError.restype = ctypes.c_ulong
_kernel32.GetLastError.argtypes = []
_tray_wnd = None          # 托盘隐藏窗口句柄
_tray_nid = None          # NOTIFYICONDATA 实例（防 GC）
_tray_icon = None         # HICON（防 GC）
_tray_thread_alive = False


def _png_to_hicon(path, size=32):
    """用 tkinter PhotoImage 读 PNG 像素 → 32bpp BGRA → CreateIconIndirect。
    透明像素（PhotoImage 中为 (0,0,0)）设为全透明，非透明像素保留原色。"""
    import tkinter as _tk
    img = _tk.PhotoImage(file=path)
    w, h = img.width(), img.height()
    # 最近邻缩放到目标尺寸
    sw, sh = size, size
    rows = []
    for y in range(sh):
        sy = min(h - 1, int(y * h / sh))
        row = []
        for x in range(sw):
            sx = min(w - 1, int(x * w / sw))
            r, g, b = img.get(sx, sy)
            a = 0 if (r == 0 and g == 0 and b == 0) else 255
            row.extend((b, g, r, a))   # BGRA
        rows.append(row)
    pixels = (ctypes.c_ubyte * (sw * sh * 4))()
    flat = [v for row in rows for v in row]
    for i, v in enumerate(flat):
        pixels[i] = v
    hbm_color = _gdi32.CreateBitmap(sw, sh, 1, 32, pixels)
    hbm_mask = _gdi32.CreateBitmap(sw, sh, 1, 1, None)
    info = _ICONINFO(True, 0, 0, hbm_mask, hbm_color)
    hicon = _user32.CreateIconIndirect(ctypes.byref(info))
    _gdi32.DeleteObject(hbm_mask)
    _gdi32.DeleteObject(hbm_color)
    return hicon


_WND_PROC_TYPE = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, ctypes.wintypes.HWND, ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)


def _tray_wnd_proc(hwnd, msg, wparam, lparam):
    if msg == _WM_TRAY:
        evt = lparam & 0xFFFF
        if evt in (_WM_LBUTTONUP, _WM_LBUTTONDBLCLK):
            _TRAY_QUEUE.put("toggle")
        elif evt == _WM_RBUTTONUP:
            # 弹出右键菜单（阻塞直到选择）
            menu = _user32.CreatePopupMenu()
            _user32.AppendMenuW(menu, _MF_STRING, 1, "显示/隐藏桌宠")
            _user32.AppendMenuW(menu, _MF_STRING, 2, "退出")
            pt = ctypes.wintypes.POINT()
            _user32.GetCursorPos(ctypes.byref(pt))
            cmd = _user32.TrackPopupMenu(menu, _TPM_RETURNCMD | _TPM_RIGHTBUTTON,
                                         pt.x, pt.y, 0, hwnd, None)
            _user32.DestroyMenu(menu)
            if cmd == 1:
                _TRAY_QUEUE.put("toggle")
            elif cmd == 2:
                _TRAY_QUEUE.put("quit")
    elif msg == _WM_DESTROY:
        _user32.PostQuitMessage(0)
    return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def tray_start(hicon):
    """在独立线程启动托盘图标。hicon 为已在主线程生成的图标句柄。"""
    global _tray_wnd, _tray_nid, _tray_icon, _tray_thread_alive
    if _tray_thread_alive:
        return
    _tray_thread_alive = True

    def _run():
        global _tray_wnd, _tray_nid, _tray_icon
        _tray_icon = hicon
        hinst = _kernel32.GetModuleHandleW(None)
        cls = "DoubaoPetTrayWnd"
        wnd_proc = _WND_PROC_TYPE(_tray_wnd_proc)
        wc = _WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(wnd_proc, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = cls
        _user32.RegisterClassExW(ctypes.byref(wc))
        hwnd = _user32.CreateWindowExW(0, cls, "DoubaoPetTray", _WS_OVERLAPPEDWINDOW,
                                       0, 0, 0, 0, 0, 0, hinst, None)
        _tray_wnd = hwnd
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = _NIF_MESSAGE | _NIF_ICON | _NIF_TIP
        nid.uCallbackMessage = _WM_TRAY
        nid.hIcon = hicon
        nid.szTip = "收工喵"
        _tray_nid = nid
        ok = _shell32.Shell_NotifyIconW(_NIM_ADD, ctypes.byref(nid))
        if not ok:
            try:
                with open(os.path.join(DATA_DIR, "tray_error.log"), "w",
                          encoding="utf-8") as f:
                    f.write("Shell_NotifyIconW NIM_ADD failed\n")
            except Exception:
                pass
        msg = _MSG()
        while _user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    t = _threading.Thread(target=_run, daemon=True)
    t.start()


def tray_stop():
    """移除托盘图标并结束托盘线程"""
    global _tray_thread_alive, _tray_wnd, _tray_nid
    try:
        if _tray_nid is not None and _tray_wnd is not None:
            _tray_nid.hWnd = _tray_wnd
            _shell32.Shell_NotifyIconW(_NIM_DELETE, ctypes.byref(_tray_nid))
        if _tray_wnd:
            _user32.PostMessageW(_tray_wnd, _WM_DESTROY, 0, 0)
    except Exception:
        pass
    _tray_thread_alive = False
    _tray_wnd = None
    _tray_nid = None


def tray_set_icon(hicon):
    """替换托盘图标（形象切换时用）。hicon 为新的 HICON，旧的会自动销毁。"""
    global _tray_nid, _tray_icon
    old = _tray_icon
    _tray_icon = hicon
    if _tray_nid is not None and _tray_wnd is not None and hicon:
        try:
            _tray_nid.hWnd = _tray_wnd
            _tray_nid.hIcon = hicon
            _shell32.Shell_NotifyIconW(_NIM_MODIFY, ctypes.byref(_tray_nid))
        except Exception:
            pass
    if old and old != hicon:
        try:
            _user32.DestroyIcon(old)
        except Exception:
            pass


class DesktopPet:
    def __init__(self, root):
        self.root = root
        self.state = "idle"
        self._floating = True
        self._follow_mode = False
        self._topmost = True
        self._drag_off = None
        self._press_xy = None
        self._suppress_click = False
        self._revert_id = None    # 状态自动恢复定时器
        self._after_ids = set()   # 一次性 after 句柄（退出时统一取消）
        self._anim_id = None      # 动画循环句柄
        self._follow_id = None    # 跟随循环句柄
        # ---- 动画状态 ----
        self._hop_start = 0.0     # 开心跳跃开始时间
        self._particles = []      # 粒子列表 [canvas_id, 出生时间]
        self._last_z = 0.0        # 上次 zZz 粒子时间
        self._cat_x = 0.0         # 猫的当前坐标（跟随模式用）
        self._cat_y = 0.0
        # ---- 跑动/走动帧动画 ----
        self._motion = None       # 当前运动模式："run" / "walk" / None(状态图)
        self._frame_idx = 0       # 帧交替索引
        self._last_frame_t = 0.0  # 上次换帧时间
        self._facing = 1          # 运动朝向：+1 朝右 / -1 朝左（选镜像帧）
        self._follow_gear = "stop"   # 跟随当前档位："stop" / "walk" / "run"（滞回防闪动）
        # ---- 形象 ----
        self._pet = load_saved_pet()          # 记忆上次选择的形象
        self._sprite_dir = PET_DIR[self._pet] # 当前形象的素材目录
        self._pet_var = tk.StringVar(root, self._pet)
        self._follow_var = tk.BooleanVar(root, False)
        self._topmost_var = tk.BooleanVar(root, True)
        self._autostart_var = tk.BooleanVar(root, is_autostart_enabled())

        # ---- 窗口：无边框 + 透明键色 + 置顶 ----
        root.overrideredirect(True)
        root.configure(bg=KEY)
        try:
            root.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        root.attributes("-topmost", True)

        # ---- 画布与精灵 ----
        self.canvas = tk.Canvas(root, bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.images = {}
        self._native = {}
        for name in ANIM_SPRITES:
            path = os.path.join(self._sprite_dir, name + ".png")
            if not os.path.exists(path):
                raise FileNotFoundError(f"缺少精灵素材：{path}")
            img = tk.PhotoImage(file=path)
            self._native[name] = (img, img.width(), img.height())
        # 最大阈值不超过素材原始尺寸
        self._max_size = min(MAX_PET_SIZE,
                             min(min(w, h) for _, w, h in self._native.values()))
        self._size = max(MIN_PET_SIZE, min(DEFAULT_PET_SIZE, self._max_size))
        saved = load_saved_size()   # 重启后恢复上次的尺寸（钳制在阈值内）
        if saved:
            self._size = max(MIN_PET_SIZE, min(saved, self._max_size))
        self._size_var = tk.IntVar(root, self._size)
        self.win_w = self._size + WIN_MARGIN * 2
        self.win_h = self._size + WIN_TOP
        self._build_images(self._size)

        root.geometry(f"{self.win_w}x{self.win_h}")
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self._win_x = (sw - self.win_w) // 2
        self._win_y = sh - self.win_h - 60
        saved_pos = load_saved_pos()   # 重启后恢复上次的位置（夹回屏幕内）
        if saved_pos:
            self._win_x, self._win_y = self._clamp_pos(*saved_pos)
        root.geometry(f"+{self._win_x}+{self._win_y}")
        self.canvas.config(width=self.win_w, height=self.win_h)

        self._img_id = self.canvas.create_image(
            self.win_w // 2, self.win_h - self._size // 2 - PET_PAD,
            image=self.images["idle"])
        self._base_pet_y = self.win_h - self._size // 2 - PET_PAD

        # ---- 气泡 ----
        self.bubble = tk.Label(root, text="", bg="#ffffff", fg="#333333",
                               font=FONT, bd=1, relief="solid", padx=8, pady=4,
                               justify="left")
        self.bubble.place_forget()

        # ---- 事件 ----
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", self._on_double)
        self.canvas.bind("<Button-3>", self._on_menu)

        # ---- 循环 ----
        self._anim_id = root.after(0, self._animate_loop)
        self._schedule_bubble()
        self._follow_id = root.after(FOLLOW_MS, self._follow_loop)

        # ---- 定时提醒 / 每日提醒 ----
        self._timers = []            # [{due: 时间戳, msg: 内容}] 单次提醒
        self._dailies = []           # [{hour, minute, msg, last, sleep}] 每日闹钟
        self._run_active = False     # 猫正在跑动（提醒跑到屏幕中心）
        self._run_cb = None          # 跑动到达后的回调
        self._run_tx = self._run_ty = 0.0
        self._bubble_win = None       # 微信气泡独立窗口(Toplevel)
        self._bubble_canvas = None    # 气泡 canvas
        self._bubble_items = []       # 气泡 canvas 元素
        self._bubble_btn = None      # 气泡取消按钮(create_window id)
        self._cd_text_id = None      # 倒计时文字 id
        self._countdown = 0          # 剩余秒数
        self._countdown_id = None    # 倒计时定时器
        self._countdown_action = "none"  # 倒计时结束要执行的动作
        self._chat_timer_id = None   # 气泡自动关闭定时器
        self._notify_from = None     # 提醒触发前窗口位置(跑回用)
        self._load_reminders()       # 从本地文件恢复（重启/开机后保留）
        if self._timers or self._dailies:
            self.show_bubble(f"已恢复 {len(self._timers)} 条提醒、{len(self._dailies)} 条每日提醒", 2600)
        self._timer_id = root.after(1000, self._timer_loop)

        # ---- 定时睡觉 ----
        self._sleep_at = None        # 计划入睡时间戳（无计划为 None）
        self._sleep_timer_id = None  # 入睡定时器句柄

        # ---- 睡眠恢复看门狗 ----
        self._watchdog_id = None
        self._last_real = time.time()
        self._last_tick = self._get_tick64()
        self._watchdog_id = root.after(WATCHDOG_MS, self._watchdog_loop)

        # ---- 系统托盘（隐藏/显示/退出） ----
        self._hidden = False
        try:
            _hicon = _png_to_hicon(os.path.join(self._sprite_dir, "idle.png"), 32)
        except Exception:
            _hicon = 0
        tray_start(_hicon)
        self._after(200, self._poll_tray)

    # ---------- 系统托盘 ----------
    def _poll_tray(self):
        """轮询托盘线程事件：toggle=显示/隐藏，quit=退出"""
        try:
            while True:
                evt = _TRAY_QUEUE.get_nowait()
                if evt == "toggle":
                    self.toggle_visible()
                elif evt == "quit":
                    self.quit()
                    return
        except _queue.Empty:
            pass
        self._after(200, self._poll_tray)

    def toggle_visible(self):
        if self._hidden:
            self.root.deiconify()
            try:
                self.root.attributes("-topmost", self._topmost)
                self.root.attributes("-transparentcolor", KEY)
            except Exception:
                pass
            self.root.lift()
            self._hidden = False
        else:
            self.root.withdraw()
            self._hidden = True

    # ---------- 工具 ----------
    def _after(self, ms, fn):
        """登记 after 句柄，退出时可统一取消"""
        aid = self.root.after(ms, fn)
        self._after_ids.add(aid)
        return aid

    def _cancel(self, aid):
        if aid is not None and aid in self._after_ids:
            try:
                self.root.after_cancel(aid)
            except Exception:
                pass
            self._after_ids.discard(aid)

    # ---------- 位置 ----------
    def _clamp_pos(self, x, y):
        """把坐标夹取到虚拟屏幕范围内（多显示器整体范围），防止窗口跑出屏幕"""
        return clamp_to_screen(x, y, self.win_w, self.win_h)

    # ---------- 状态 ----------
    def set_state(self, name, revert_ms=None):
        """切换状态；非 idle 状态会在 revert_ms 后自动恢复默认（睡觉有默认自动醒来时长）。"""
        if name not in self.images:
            name = "idle"
        self.state = name
        self._set_motion(None)   # 恢复状态图（退出跑动/走动帧）
        self.canvas.itemconfigure(self._img_id, image=self.images[name])
        if name == "happy":
            self._hop_start = time.time()   # 触发跳跃动画
            self._spawn_particles("happy", HAPPY_PARTICLES)  # 飘爱心星星
        if name == "sleep":
            self._floating = False
            if revert_ms is None:
                revert_ms = SLEEP_AUTO_WAKE_MS
        else:
            self._floating = not self._follow_mode
        # 取消旧的恢复定时器，并按需安排新的
        self._cancel(getattr(self, "_revert_id", None))
        self._revert_id = None
        if name != "idle" and revert_ms:
            self._revert_id = self._after(revert_ms, self._on_revert)

    def _on_revert(self):
        """状态展示结束，恢复默认 idle"""
        if self.state == "sleep":
            self.show_bubble("睡醒啦～", 1800)
        self.set_state("idle")

    # ---------- 大小调节 ----------
    @staticmethod
    def _scale_image(img, native, target):
        """用 Tk 原生整数缩放把图片缩放到目标尺寸（C 实现，即时完成）。
        交错执行 zoom/subsample，任意中间尺寸不超过 2200px：
        先按需缩小为放大留空间，再 zoom，最后 subsample 收尾。
        （旧版一次性 zoom 大倍数会生成 4200×4200 超大中间图，部分环境挂起）"""
        if target == native:
            return img
        g = math.gcd(target, native)
        t, n = target // g, native // g   # target = native × t / n
        cur = native
        LIMIT = 2200
        # 阶段1：若直接放大将超过上限，先按整除的小因子缩小
        while n > 1 and cur * t > LIMIT:
            b = 2 if n % 2 == 0 else (3 if n % 3 == 0 else n)
            if cur // b < 1:
                break
            img = img.subsample(b)
            cur //= b
            n //= b
        # 阶段2：放大（此时中间图 ≤ LIMIT）
        if t > 1:
            img = img.zoom(t)
            cur *= t
        # 阶段3：收尾缩小到目标尺寸
        if n > 1:
            img = img.subsample(n)
        return img

    def _build_images(self, size):
        """按指定尺寸重新生成全部精灵图（含跑动/走动帧）"""
        self.images = {}
        for name, (img, w, h) in self._native.items():
            side = min(w, h)
            self.images[name] = self._scale_image(img, side, size) if side != size else img
        # 显式回收被替换的旧帧图，避免分代 GC 在事件循环间隙触发导致 Tk 挂起
        gc.collect()

    def set_size(self, size):
        """调节宠物大小（自动限制在最小/最大阈值内），以窗口底部中心为锚点缩放"""
        size = max(MIN_PET_SIZE, min(self._max_size, int(size)))
        if size == self._size:
            self.show_bubble(f"已是{'最大' if size >= self._max_size else '最小'}尺寸", 1200)
            return
        bx = self.root.winfo_x() + self.win_w // 2   # 底部中心锚点
        by = self.root.winfo_y() + self.win_h
        self._size = size
        self._size_var.set(size)
        self.win_w = size + WIN_MARGIN * 2
        self.win_h = size + WIN_TOP
        self._build_images(size)
        self.canvas.config(width=self.win_w, height=self.win_h)
        self._base_pet_y = self.win_h - size // 2 - PET_PAD
        self.canvas.coords(self._img_id, self.win_w // 2, self._base_pet_y)
        self.canvas.itemconfigure(self._img_id, image=self.images[self.state])
        nx = bx - self.win_w // 2
        ny = by - self.win_h
        self.root.geometry(f"{self.win_w}x{self.win_h}+{nx}+{ny}")
        self._save_reminders()   # 持久化尺寸，重启后保持
        self.show_bubble(f"大小：{size}px", 1200)

    # ---------- 形象切换 ----------
    def _set_pet(self, pet):
        """切换形象：重载素材、重算窗口/托盘图标，并持久化记忆"""
        if pet == self._pet:
            return
        new_dir = PET_DIR.get(pet)
        if not new_dir or not os.path.isdir(new_dir):
            self.show_bubble("形象素材不存在", 1800)
            return
        # 预校验素材齐全，避免加载到一半失败
        try:
            for name in ANIM_SPRITES:
                if not os.path.exists(os.path.join(new_dir, name + ".png")):
                    raise FileNotFoundError(name)
        except Exception:
            self.show_bubble("形象素材不完整", 1800)
            return
        self._pet = pet
        self._sprite_dir = new_dir
        self._pet_var.set(pet)
        # 重载原生帧
        self._native = {}
        for name in ANIM_SPRITES:
            img = tk.PhotoImage(file=os.path.join(new_dir, name + ".png"))
            self._native[name] = (img, img.width(), img.height())
        gc.collect()   # 显式回收旧形象的原生帧
        self._max_size = min(MAX_PET_SIZE,
                             min(min(w, h) for _, w, h in self._native.values()))
        self._size = max(MIN_PET_SIZE, min(self._size, self._max_size))
        self._size_var.set(self._size)
        self.win_w = self._size + WIN_MARGIN * 2
        self.win_h = self._size + WIN_TOP
        self._build_images(self._size)
        self.canvas.config(width=self.win_w, height=self.win_h)
        self._base_pet_y = self.win_h - self._size // 2 - PET_PAD
        self.canvas.coords(self._img_id, self.win_w // 2, self._base_pet_y)
        self.canvas.itemconfigure(self._img_id, image=self.images[self.state])
        # 窗口位置保持（夹回屏幕内）
        nx, ny = self.root.winfo_x(), self.root.winfo_y()
        nx, ny = self._clamp_pos(nx, ny)
        self.root.geometry(f"{self.win_w}x{self.win_h}+{nx}+{ny}")
        self._win_x, self._win_y = nx, ny
        # 托盘图标同步
        try:
            _hicon = _png_to_hicon(os.path.join(new_dir, "idle.png"), 32)
            tray_set_icon(_hicon)
        except Exception:
            pass
        self._save_reminders()   # 持久化形象
        gc.collect()   # 再次全代回收，确保切换产生的图像垃圾清空（避免事件循环中触发 GC 重入 Tcl 挂起）
        self.show_bubble(f"已切换为{PET_LABEL.get(pet, pet)}", 2000)

    # ---------- 气泡 ----------
    def show_bubble(self, text, ms=BUBBLE_SHOW_MS):
        if not text:
            return
        # 长文本按窗口宽度自动换行；超过 5 行截断加省略号，避免超出窗口显示不全
        import tkinter.font as tkfont
        f = tkfont.Font(family=FONT[0], size=FONT[1])
        max_w = max(60, self.win_w - 16)
        lines, cur = [], ""
        for ch in text:
            if cur and f.measure(cur + ch) > max_w:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        if len(lines) > 5:
            text = "".join(lines[:4]) + "…"
        self.bubble.config(text=text, wraplength=max_w, justify="left")
        self.bubble.place(relx=0.5, y=6, anchor="n")
        self.bubble.lift()
        self._cancel(getattr(self, "_bubble_hide_id", None))
        self._bubble_hide_id = self._after(ms, self.bubble.place_forget)

    def _schedule_bubble(self):
        self._cancel(getattr(self, "_bubble_sched_id", None))
        self._bubble_sched_id = self._after(
            random.randint(*BUBBLE_INTERVAL), self._on_bubble_time
        )

    def _on_bubble_time(self):
        if self.state == "sleep":
            self.show_bubble(random.choice(MESSAGES["sleep"]), 1800)
        elif self.state == "idle":
            self.show_bubble(random.choice(MESSAGES["idle"]))
        self._schedule_bubble()

    # ---------- 动画：待机浮动+微摆 / 跳跃 / 粒子 ----------
    def _hop_offset(self):
        """开心跳跃位移（0 → -HOP_HEIGHT → 0 单次弹跳）"""
        if self.state != "happy":
            return 0
        elapsed = (time.time() - self._hop_start) * 1000
        if elapsed >= HOP_MS:
            return 0
        return -int(math.sin(math.pi * elapsed / HOP_MS) * HOP_HEIGHT)

    def _spawn_particles(self, kind, count):
        """在宠物头顶飘出粒子：happy=爱心/星星，sleep=z"""
        chars = {"happy": ("♥", "★", "✿"), "sleep": ("z",)}
        colors = {"happy": ("#ff6b81", "#ffa502", "#ff4757"),
                  "sleep": ("#a4b0be",)}
        cx = self.win_w // 2 + random.randint(-30, 30)
        cy = self._base_pet_y - self._size // 2 - random.randint(0, 12)
        for _ in range(count):
            item = self.canvas.create_text(
                cx, cy, text=random.choice(chars[kind]),
                fill=random.choice(colors[kind]),
                font=("Microsoft YaHei UI", random.randint(14, 22), "bold"))
            self._particles.append([item, time.time()])

    def _update_particles(self, now):
        """粒子向上飘动，超时自动清除"""
        for p in list(self._particles):
            item, born = p
            if now - born > PARTICLE_LIFE_MS / 1000.0:
                try:
                    self.canvas.delete(item)
                except Exception:
                    pass
                self._particles.remove(p)
            else:
                self.canvas.move(item, 0, -2)

    # ---------- 跑动/走动帧动画 ----------
    def _motion_frames(self):
        """当前模式的基础帧名序列（朝右版）"""
        return RUN_FRAMES if self._motion == "run" else WALK_FRAMES

    def _display_frame(self, base):
        """按朝向返回实际显示的帧名（朝左时用镜像帧）"""
        return base + "_l" if self._facing < 0 else base

    def _set_motion(self, mode):
        """切换猫的移动动画：run=跑步帧 / walk=走路帧 / None=恢复状态图"""
        if mode == self._motion:
            return
        self._motion = mode
        self._frame_idx = 0
        self._last_frame_t = time.time()
        if mode is None:
            self.canvas.itemconfigure(self._img_id, image=self.images[self.state])
        else:
            base = self._motion_frames()[0]
            self.canvas.itemconfigure(self._img_id,
                                      image=self.images[self._display_frame(base)])

    def _tick_motion_frame(self):
        """按当前运动模式推进帧交替（跑步快、走路慢），帧名随朝向选镜像"""
        if self._motion is None:
            return
        now = time.time()
        gap = FRAME_CHASE_MS / 1000.0 if self._motion == "run" else FRAME_WALK_MS / 1000.0
        if now - self._last_frame_t >= gap:
            frames = self._motion_frames()
            self._frame_idx = (self._frame_idx + 1) % len(frames)
            self._last_frame_t = now
            base = frames[self._frame_idx]
            self.canvas.itemconfigure(self._img_id,
                                      image=self.images[self._display_frame(base)])

    def _set_facing(self, target_x):
        """按目标 x 方向设置朝向（目标在左→朝左，在右→朝右）。
        带死区：目标几乎在正前方(|dx|<12)时不翻转，避免左右横跳。"""
        if abs(target_x) < 12:
            return
        f = 1 if target_x > 0 else -1
        if f != self._facing:
            self._facing = f
            if self._motion is not None:
                base = self._motion_frames()[self._frame_idx]
                self.canvas.itemconfigure(self._img_id,
                                          image=self.images[self._display_frame(base)])

    def _animate_loop(self):
        if self._run_active:
            # 提醒跑动期间由 _run_loop 驱动，本循环挂起但必须继续排队
            self._anim_id = self.root.after(FRAME_MS, self._animate_loop)
            return
        if self._drag_off is None:
            if self._floating:
                # 待机静止：无浮动、无摇摆，猫停在窗口中央底部
                self.canvas.coords(self._img_id, self.win_w // 2, self._base_pet_y)
                self._cat_x, self._cat_y = self.win_w // 2, self._base_pet_y
                if self._motion is not None:
                    self._set_motion(None)   # 回到状态图（走动/跑动已结束）
            elif self.state == "happy":
                # 跟随模式下不浮动，也显示跳跃
                self.canvas.coords(self._img_id, self.win_w // 2,
                                   self._base_pet_y + self._hop_offset())
                self._cat_x, self._cat_y = self.win_w // 2, self._base_pet_y
                if self._motion is not None:
                    self._set_motion(None)
            # 粒子：睡觉时周期性飘 zZz
            now = time.time()
            if self.state == "sleep" and now - self._last_z > SLEEP_Z_MS / 1000.0:
                self._last_z = now
                self._spawn_particles("sleep", 1)
            self._update_particles(now)
        self._anim_id = self.root.after(FRAME_MS, self._animate_loop)

    # ---------- 拖拽 / 单击 / 双击 ----------
    def _on_press(self, event):
        self._press_xy = (event.x_root, event.y_root)
        self._drag_off = (event.x_root - self.root.winfo_x(),
                          event.y_root - self.root.winfo_y())
        self._cancel(getattr(self, "_click_delay_id", None))

    def _on_drag(self, event):
        if self._drag_off is None:
            return
        x = event.x_root - self._drag_off[0]
        y = event.y_root - self._drag_off[1]
        self.root.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        if self._suppress_click:
            self._suppress_click = False
            self._drag_off = None
            return
        moved = 0
        if self._press_xy is not None:
            moved = abs(event.x_root - self._press_xy[0]) + abs(event.y_root - self._press_xy[1])
        self._press_xy = None
        was_drag = bool(self._drag_off)
        self._drag_off = None
        if was_drag and moved > MOVE_THRESHOLD:
            self._save_reminders()  # 记住新位置（含提醒/尺寸），重启后保持
            return  # 拖拽结束，不动画打断
        # 单击：延迟判定，给双击留时间
        self._cancel(getattr(self, "_click_delay_id", None))
        self._click_delay_id = self._after(CLICK_DELAY_MS, self._single_click)

    def _on_double(self, event):
        self._cancel(getattr(self, "_click_delay_id", None))
        self._suppress_click = True
        self._after(400, self._clear_suppress)
        self.set_state("happy", REACT_MS)
        self.show_bubble(random.choice(MESSAGES["happy"]))

    def _clear_suppress(self):
        self._suppress_click = False

    def _single_click(self):
        name = random.choice(["surprise", "happy"])
        self.set_state(name, REACT_MS)
        self.show_bubble(random.choice(MESSAGES[name]))

    # ---------- 跟随鼠标 ----------
    def set_follow(self, enabled):
        self._follow_mode = enabled
        self._follow_var.set(enabled)
        if enabled:
            self._floating = False
            self._follow_gear = "stop"   # 重置档位，避免上一轮档位残留

    def _follow_loop(self):
        if self._follow_mode and self._drag_off is None:
            pt = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
            cx, cy = pt.x, pt.y
            px, py = self.root.winfo_x(), self.root.winfo_y()
            dx, dy = cx - (px + self.win_w // 2), cy - (py + self.win_h // 2)
            dist = (dx * dx + dy * dy) ** 0.5
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            in_window = (px <= cx <= px + self.win_w and
                         py <= cy <= py + self.win_h)
            if self._follow_gear == "stop":
                # 静止档：鼠标需明确离开（出窗且距离 > 26+60=86px）才恢复动画，
                # 避免在动画/静止临界点反复闪动
                if not in_window and dist > FOLLOW_STOP_DIST + FOLLOW_STOP_HYST:
                    gear = "run" if dist > FOLLOW_WALK_DIST + FOLLOW_HYST else "walk"
                else:
                    gear = "stop"
            else:
                # 动画档：鼠标进入窗体内或贴得很近(≤26px) → 停住（恢复状态图）
                if in_window or dist <= FOLLOW_STOP_DIST:
                    gear = "stop"
                elif self._follow_gear == "run":
                    # 已在快跑：距离跌回「阈值-滞回」以下才降级为走，避免临界点闪动
                    gear = "walk" if dist <= FOLLOW_WALK_DIST - FOLLOW_HYST else "run"
                else:
                    # 走/停状态：距离升过「阈值+滞回」才升级为快跑
                    gear = "run" if dist > FOLLOW_WALK_DIST + FOLLOW_HYST else "walk"
            if gear == "stop":
                if self._motion is not None:
                    self._set_motion(None)
            else:
                self._set_facing(dx)   # 面向鼠标方向
                self._set_motion("run" if gear == "run" else "walk")
                self._tick_motion_frame()
                step = FOLLOW_RUN_STEP if gear == "run" else FOLLOW_WALK_STEP
                nx = int(px + dx / dist * step)
                ny = int(py + dy / dist * step)
                nx = max(0, min(nx, sw - self.win_w))
                ny = max(0, min(ny, sh - self.win_h))
                self.root.geometry(f"+{nx}+{ny}")
            self._follow_gear = gear
        self._follow_id = self.root.after(FOLLOW_MS, self._follow_loop)

    # ---------- 定时提醒 ----------
    def _load_reminders(self):
        """启动时从本地文件恢复定时提醒与每日提醒（重启/开机后保留）。"""
        data = load_data()
        if not data:
            return
        entries = data.get("reminders", [])
        self._timers = timers_from_entries(entries)
        self._dailies = dailies_from_entries(data.get("dailies", []))
        if len(self._timers) < len(entries):
            self._save_reminders()  # 有过期条目被丢弃 → 同步清理文件

    def _save_reminders(self):
        """把提醒、每日提醒与宠物尺寸/形象/位置写入本地文件，任何增删/变更都同步"""
        save_data(reminders_payload(
            self._timers, self._dailies,
            size=self._size,
            pet=self._pet,
            pos={"x": self.root.winfo_x(), "y": self.root.winfo_y()},
        ))

    # ---------- UI 辅助（统一主题） ----------
    def _mk_dialog(self, title):
        """创建统一主题的设置窗口，返回 (dlg, frm)。"""
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        dlg.configure(bg=UI_BG)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        tk.Label(dlg, text=title, bg=UI_BG, fg=UI_ACCENT,
                 font=("Microsoft YaHei UI", 12, "bold")).pack(
                     anchor="w", padx=18, pady=(14, 0))
        tk.Frame(dlg, bg=UI_INPUT_BD, height=1).pack(fill="x",
                                                     padx=18, pady=(8, 0))
        frm = tk.Frame(dlg, bg=UI_BG, padx=18, pady=10)
        frm.pack(fill="both", expand=True)
        return dlg, frm

    def _mk_btn(self, parent, text, command, primary=True):
        if primary:
            return tk.Button(parent, text=text, font=FONT, padx=20, pady=4,
                             bg=UI_ACCENT, fg="#FFFFFF",
                             activebackground=UI_ACCENT_HI,
                             activeforeground="#FFFFFF",
                             relief="flat", bd=0, highlightthickness=0,
                             cursor="hand2", command=command)
        return tk.Button(parent, text=text, font=FONT, padx=20, pady=4,
                         bg=UI_BG2, fg=UI_FG, activebackground="#EAD9C4",
                         activeforeground=UI_FG,
                         relief="flat", bd=0, highlightthickness=0,
                         cursor="hand2", command=command)

    def _mk_entry(self, parent, width=10, justify="center"):
        return tk.Entry(parent, font=FONT, width=width, justify=justify,
                        relief="flat", bd=0, bg="#FFFFFF", fg=UI_FG,
                        highlightthickness=1, highlightbackground=UI_INPUT_BD,
                        highlightcolor=UI_ACCENT, insertbackground=UI_FG)

    def _mk_lbl(self, parent, text, sub=False, **kw):
        kw.setdefault("bg", UI_BG)
        kw.setdefault("fg", UI_SUB if sub else UI_FG)
        kw.setdefault("font", (FONT[0], 8) if sub else FONT)
        return tk.Label(parent, text=text, **kw)

    def _mk_submenu(self, menu):
        return tk.Menu(menu, tearoff=0, bg="#FFFFFF", fg=UI_FG,
                       activebackground=UI_MENU_HI, activeforeground=UI_ACCENT,
                       bd=0, font=FONT)

    def _center_dialog(self, dlg):
        """把设置窗口居中到屏幕中间（修改2：不再显示在左上角）"""
        try:
            dlg.update_idletasks()
        except Exception:
            pass
        w = dlg.winfo_reqwidth()
        h = dlg.winfo_reqheight()
        sw = dlg.winfo_screenwidth()
        sh = dlg.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        dlg.geometry(f"+{x}+{y}")

    def _open_reminder_dialog(self):
        """弹出自定义提醒设置窗口（美化版 + 支持分钟轮询）"""
        dlg, frm = self._mk_dialog("添加定时提醒")

        # 行0：提醒时间
        self._mk_lbl(frm, "提醒时间：").grid(row=0, column=0, sticky="e", pady=5)
        time_var = tk.StringVar(dlg)
        entry_time = self._mk_entry(frm, width=10)
        entry_time.config(textvariable=time_var)
        entry_time.grid(row=0, column=1, sticky="w", pady=5)
        self._mk_lbl(frm, "输入分钟数，或时刻如 14:30", sub=True).grid(
            row=0, column=2, sticky="w", padx=(8, 0))

        # 行1：轮询（仅输入整数分钟时可开启）
        repeat_var = tk.BooleanVar(dlg, False)
        repeat_chk = tk.Checkbutton(
            frm, text="开启轮询：每隔相同分钟数重复提醒", variable=repeat_var,
            bg=UI_BG, fg=UI_FG, activebackground=UI_BG, selectcolor="#FFFFFF",
            activeforeground=UI_FG, font=FONT, bd=0, highlightthickness=0,
            anchor="w", cursor="hand2")
        repeat_chk.grid(row=1, column=1, columnspan=2, sticky="w", pady=(2, 2))

        def _on_time_key(*_):
            txt = time_var.get().strip()
            ok = False
            if txt and ":" not in txt:
                try:
                    v = float(txt)
                    ok = v > 0 and v.is_integer()
                except ValueError:
                    ok = False
            if ok:
                repeat_chk.config(state="normal", fg=UI_FG)
            else:
                repeat_var.set(False)
                repeat_chk.config(state="disabled", fg=UI_SUB)
        time_var.trace_add("write", _on_time_key)
        _on_time_key()

        # 行2：提醒内容
        self._mk_lbl(frm, "提醒内容：").grid(row=2, column=0, sticky="e", pady=5)
        entry_msg = self._mk_entry(frm, width=26, justify="left")
        entry_msg.grid(row=2, column=1, columnspan=2, sticky="we", pady=5)
        entry_msg.insert(0, "该休息一下啦！")

        def do_ok(_=None):
            secs, err = parse_reminder(entry_time.get())
            if err:
                entry_time.config(highlightbackground=UI_ERR)
                err_lbl.config(text=err)
                return
            msg = entry_msg.get().strip() or "时间到啦！"
            repeat_min = None
            if repeat_var.get():
                try:
                    v = float(entry_time.get().strip())
                    repeat_min = int(v)
                except ValueError:
                    repeat_min = None
            self.add_reminder(secs, msg, repeat_min)
            dlg.destroy()

        def do_cancel(_=None):
            dlg.destroy()

        err_lbl = self._mk_lbl(frm, "", fg=UI_ERR)
        err_lbl.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 0))

        btns = tk.Frame(frm, bg=UI_BG)
        btns.grid(row=4, column=0, columnspan=3, pady=(10, 2))
        self._mk_btn(btns, "确定", do_ok).pack(side="left", padx=6)
        self._mk_btn(btns, "取消", do_cancel, primary=False).pack(side="left", padx=6)

        dlg.bind("<Return>", do_ok)
        dlg.bind("<Escape>", do_cancel)
        dlg.transient(self.root)
        self._center_dialog(dlg)
        dlg.grab_set()
        entry_time.focus_set()

    def add_reminder(self, secs, msg, repeat_min=None):
        self._timers.append({"due": time.time() + secs, "msg": msg,
                             "repeat_min": repeat_min})
        self._save_reminders()
        self.set_state("happy", 2000)
        if repeat_min:
            self.show_bubble(f"已设提醒：{msg}（每 {repeat_min} 分钟重复）", 3000)
        else:
            self.show_bubble(f"已设提醒：{msg}（{fmt_remaining(secs)}后）", 3000)

    def _cancel_reminder(self, timer):
        if timer in self._timers:
            self._timers.remove(timer)
        self._save_reminders()
        self.show_bubble("已取消提醒：" + timer["msg"], 1800)

    def _timer_loop(self):
        fired_r, fired_d, changed = check_reminders(self._timers, self._dailies)
        for msg in fired_r:
            self._fire_reminder(msg)
        for d in fired_d:
            self._fire_daily(d)
        if changed:
            self._save_reminders()
        self._timer_id = self.root.after(1000, self._timer_loop)

    # ---------- 每日提醒（闹钟） ----------
    def _open_daily_dialog(self):
        """弹出自定义每日提醒（闹钟）设置窗口（美化版）"""
        dlg, frm = self._mk_dialog("设置每日提醒")

        # 行0：提醒时间
        self._mk_lbl(frm, "提醒时间：").grid(row=0, column=0, sticky="e", pady=5)
        entry_time = self._mk_entry(frm, width=10)
        entry_time.grid(row=0, column=1, sticky="w", pady=5)
        self._mk_lbl(frm, "时刻如 08:30（每天这个时间提醒）", sub=True).grid(
            row=0, column=2, sticky="w", padx=(8, 0))

        # 行1：提醒内容
        self._mk_lbl(frm, "提醒内容：").grid(row=1, column=0, sticky="e", pady=5)
        entry_msg = self._mk_entry(frm, width=26, justify="left")
        entry_msg.grid(row=1, column=1, columnspan=2, sticky="we", pady=5)
        entry_msg.insert(0, "该休息一下啦！")

        action_var = tk.StringVar(dlg, "无操作")
        self._mk_lbl(frm, "到点后动作：").grid(row=2, column=0, sticky="e", pady=(4, 0))
        om = tk.OptionMenu(frm, action_var,
                           *[lbl for _, lbl in DAILY_ACTIONS])
        om.config(bg="#FFFFFF", fg=UI_FG, relief="flat", bd=0,
                  highlightthickness=1, highlightbackground=UI_INPUT_BD,
                  activebackground=UI_BG2, font=FONT, cursor="hand2")
        om["menu"].config(bg="#FFFFFF", fg=UI_FG, activebackground=UI_BG2,
                          activeforeground=UI_ACCENT, font=FONT)
        om.grid(row=2, column=1, columnspan=2, sticky="w", pady=(4, 0))

        self._mk_lbl(frm, "倒计时(秒)：").grid(row=3, column=0, sticky="e", pady=(4, 0))
        entry_cd = self._mk_entry(frm, width=6)
        entry_cd.insert(0, str(SLEEP_COUNTDOWN_S))
        entry_cd.grid(row=3, column=1, sticky="w", pady=(4, 0))
        self._mk_lbl(frm, "选锁屏/睡眠/关机后生效", sub=True).grid(
            row=3, column=2, sticky="w", padx=(8, 0))

        def _on_action_change(*_):
            state = "normal" if action_var.get() != "无操作" else "disabled"
            entry_cd.config(state=state)
        action_var.trace_add("write", _on_action_change)
        _on_action_change()

        def do_ok(_=None):
            clock, err = parse_clock(entry_time.get())
            if err:
                entry_time.config(highlightbackground=UI_ERR)
                err_lbl.config(text=err)
                return
            msg = entry_msg.get().strip() or "时间到啦！"
            act = ACTION_KEY.get(action_var.get(), "none")
            cd = SLEEP_COUNTDOWN_S
            if act != "none":
                try:
                    cd = int(entry_cd.get().strip())
                except (TypeError, ValueError):
                    entry_cd.config(highlightbackground=UI_ERR)
                    err_lbl.config(text="倒计时秒数需为 1~300 的整数")
                    return
                if not 1 <= cd <= 300:
                    entry_cd.config(highlightbackground=UI_ERR)
                    err_lbl.config(text="倒计时秒数需为 1~300 的整数")
                    return
            self.add_daily(clock[0], clock[1], msg, act, cd)
            dlg.destroy()

        def do_cancel(_=None):
            dlg.destroy()

        err_lbl = self._mk_lbl(frm, "", fg=UI_ERR)
        err_lbl.grid(row=4, column=0, columnspan=3, sticky="w", pady=(2, 0))

        btns = tk.Frame(frm, bg=UI_BG)
        btns.grid(row=5, column=0, columnspan=3, pady=(10, 2))
        self._mk_btn(btns, "确定", do_ok).pack(side="left", padx=6)
        self._mk_btn(btns, "取消", do_cancel, primary=False).pack(side="left", padx=6)

        dlg.bind("<Return>", do_ok)
        dlg.bind("<Escape>", do_cancel)
        dlg.transient(self.root)
        self._center_dialog(dlg)
        dlg.grab_set()
        entry_time.focus_set()

    def add_daily(self, hour, minute, msg, action="none",
                  countdown=SLEEP_COUNTDOWN_S):
        for d in self._dailies:
            if d["hour"] == hour and d["minute"] == minute and d["msg"] == msg:
                self.show_bubble("该每日提醒已存在", 1500)
                return
        self._dailies.append({"hour": hour, "minute": minute, "msg": msg,
                              "last": "", "action": action,
                              "countdown": int(countdown)})
        self._save_reminders()
        self.set_state("happy", 2000)
        if action != "none":
            tail = f"，到点 {int(countdown)} 秒后自动{ACTION_LABEL[action]}"
        else:
            tail = ""
        self.show_bubble(f"已设置每日提醒：{msg}（每天 {hour:02d}:{minute:02d}{tail}）", 3200)

    def _cancel_daily(self, d):
        if d in self._dailies:
            self._dailies.remove(d)
        self._save_reminders()
        self.show_bubble("已取消每日提醒：" + d["msg"], 1800)

    # ---------- 提醒呈现：猫跑到屏幕中间 + 微信式气泡 ----------
    def _notify_cat(self, msg, action="none", countdown=SLEEP_COUNTDOWN_S):
        """提醒到点：猫自动跑动到屏幕中心，猫头方向弹出微信式气泡显示内容。
        action 非 none（每日提醒选了锁屏/睡眠/关机）时额外显示倒计时与取消按钮，
        倒计时结束未取消则执行对应系统动作。"""
        self._clear_chat_bubble()
        if self._follow_mode:
            self.set_follow(False)
        if self.state == "sleep":
            self.set_state("idle")
        try:
            ctypes.windll.kernel32.Beep(880, 220)
            ctypes.windll.kernel32.Beep(660, 220)
        except Exception:
            pass
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        tx, ty = max(0, (sw - self.win_w) // 2), max(0, (sh - self.win_h) // 2)
        if self._drag_off is not None:
            # 拖拽中：不跑动，原地弹气泡
            self._notify_from = None
            self._show_chat_bubble(msg, action, countdown)
            return
        self._notify_from = (self.root.winfo_x(), self.root.winfo_y())
        self._run_to(tx, ty,
                     lambda: self._show_chat_bubble(msg, action, countdown))

    def _run_to(self, tx, ty, cb):
        """猫从当前位置用跑步动画跑到目标位置，到达后回调"""
        tx = max(0, min(int(tx), self.root.winfo_screenwidth() - self.win_w))
        ty = max(0, min(int(ty), self.root.winfo_screenheight() - self.win_h))
        self._run_tx, self._run_ty = tx, ty
        self._run_cb = cb
        self._run_active = True
        self._set_motion("run")
        self._run_loop()

    def _run_loop(self):
        if not self._run_active:
            return
        px, py = self.root.winfo_x(), self.root.winfo_y()
        dx, dy = self._run_tx - px, self._run_ty - py
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= FOLLOW_RUN_STEP:
            self.root.geometry(f"+{self._run_tx}+{self._run_ty}")
            self._run_active = False
            self._set_motion(None)
            self._cat_x, self._cat_y = (self._run_tx + self.win_w // 2,
                                        self._run_ty + self.win_h // 2)
            cb = self._run_cb
            self._run_cb = None
            if cb:
                cb()
            return
        self._set_facing(dx)
        self._set_motion("run")
        self._tick_motion_frame()
        nx = px + dx / dist * FOLLOW_RUN_STEP
        ny = py + dy / dist * FOLLOW_RUN_STEP
        if not hasattr(self, "_screen_size"):
            self._screen_size = (self.root.winfo_screenwidth(),
                                 self.root.winfo_screenheight())
        sw, sh = self._screen_size
        nx = max(0, min(int(nx), sw - self.win_w))
        ny = max(0, min(int(ny), sh - self.win_h))
        self.root.geometry(f"+{nx}+{ny}")
        self._run_id = self._after(FRAME_MS, self._run_loop)

    def _show_chat_bubble(self, msg, action="none", countdown=SLEEP_COUNTDOWN_S):
        """在猫头一侧弹出独立的微信式气泡（透明窗口、白底圆角+小尾巴指向猫头）。
        气泡宽度自适应文字、不再受宠物窗口宽度限制；猫头朝右气泡在右侧、朝左在左侧，
        屏幕边缘放不下会自动翻到另一侧。action 非 none 时附倒计时与取消按钮。"""
        self._clear_chat_bubble()
        import tkinter.font as tkfont
        f = tkfont.Font(family=FONT[0], size=FONT[1])
        max_w = 380
        # 按字符宽度折行，避免长文字把气泡撑得又窄又高
        lines, cur = [], ""
        for ch in msg:
            if cur and f.measure(cur + ch) > max_w - 36:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            lines.append(cur)
        if not lines:
            lines = [""]
        line_h = 20
        text_w = max(f.measure(l) for l in lines)
        B_w = max(140, min(max_w, text_w + 32))
        pad = 12
        text_h = len(lines) * line_h
        if action not in (None, "", "none"):   # 仅锁屏/睡眠/关机才显示倒计时+取消
            B_h = pad + text_h + 6 + 24 + 8 + 34
        else:
            B_h = pad + text_h + pad

        TAIL = 14
        cw = B_w + TAIL
        # 先决定气泡放在猫窗口哪一侧：优先猫头朝向侧，屏幕边缘放不下则自动翻到另一侧
        wx, wy = self.root.winfo_x(), self.root.winfo_y()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        side_right = self._facing > 0
        if side_right and wx + self.win_w + cw - TAIL + 2 > sw:
            side_right = False   # 右侧放不下 → 翻到左侧
        if not side_right and wx - cw + TAIL - 2 < 0:
            side_right = True    # 左侧放不下 → 翻到右侧
        if side_right:
            body_x, tip = TAIL, 0          # 主体偏右、尾巴尖在最左（指向猫）
        else:
            body_x, tip = 0, B_w + TAIL    # 主体偏左、尾巴尖在最右（指向猫）

        self.root.update()   # 先处理挂起的窗口消息（跑动刚结束），避免气泡映射挂起
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-transparentcolor", KEY)
        win.configure(bg=KEY)
        c = tk.Canvas(win, width=cw, height=B_h, bg=KEY, highlightthickness=0)
        c.pack()

        # 气泡主体（白色圆角矩形）
        x0, y0, r = body_x, 0, 14
        pts = [x0 + r, y0, x0 + B_w - r, y0, x0 + B_w, y0 + r,
               x0 + B_w, y0 + B_h - r, x0 + B_w - r, y0 + B_h,
               x0 + r, y0 + B_h, x0, y0 + B_h - r, x0, y0 + r]
        self._bubble_items.append(c.create_polygon(
            pts, smooth=True, fill="#ffffff", outline="#e3e3e3", width=1))
        # 小尾巴：尖角指向猫窗口（朝右→尖在左边缘；朝左→尖在右边缘）
        cy = B_h // 2
        if side_right:
            tail_pts = [TAIL, cy - 8, tip, cy, TAIL, cy + 8]
        else:
            tail_pts = [B_w, cy - 8, tip, cy, B_w, cy + 8]
        self._bubble_items.append(c.create_polygon(
            tail_pts, fill="#ffffff", outline=""))

        # 文字（逐行左对齐，微信风格）
        for i, line in enumerate(lines):
            self._bubble_items.append(c.create_text(
                body_x + 16, pad + i * line_h, text=line, anchor="nw",
                fill="#333333", font=FONT))
        act_label = ACTION_LABEL.get(action, "操作")
        if action not in (None, "", "none"):
            self._countdown = int(countdown)
            self._countdown_action = action
            cd_y = pad + text_h + 6
            self._cd_text_id = c.create_text(
                body_x + 16, cd_y, text=f"⏳ {int(countdown)} 秒后自动{act_label}",
                anchor="nw", fill="#d35400", font=(FONT[0], 9))
            self._bubble_items.append(self._cd_text_id)
            btn = tk.Button(c, text="取消", font=FONT, padx=10, pady=0,
                            command=self._cancel_daily_action, bg="#ffffff",
                            activebackground="#f2f2f2", relief="solid", bd=1)
            self._bubble_btn = c.create_window(
                body_x + B_w - 78, cd_y + 24 + 17, window=btn)
            self._countdown_id = self._after(1000, self._tick_countdown)
        else:
            self._chat_timer_id = self._after(CHAT_BUBBLE_MS, self._clear_chat_and_go_home)

        # 定位：贴在猫窗口的猫头一侧，垂直与猫头对齐
        head_cy = wy + self._base_pet_y - self._size // 2 - 6
        by = max(0, min(int(head_cy - B_h // 2), sh - B_h))
        bx = wx + self.win_w - TAIL + 2 if side_right else wx - cw + TAIL - 2
        bx = max(0, min(bx, sw - cw))
        win.geometry(f"+{int(bx)}+{int(by)}")
        win.lift()
        self._bubble_win = win
        self._bubble_canvas = c

    def _tick_countdown(self):
        self._countdown -= 1
        if self._countdown <= 0:
            self._clear_chat_bubble()
            self._do_system_action(getattr(self, "_countdown_action", "none"))
            self._return_home()
            return
        try:
            if self._bubble_canvas is not None:
                act_label = ACTION_LABEL.get(
                    getattr(self, "_countdown_action", "none"), "操作")
                self._bubble_canvas.itemconfigure(
                    self._cd_text_id, text=f"⏳ {self._countdown} 秒后自动{act_label}")
        except Exception:
            pass
        self._countdown_id = self._after(1000, self._tick_countdown)

    def _cancel_daily_action(self):
        self._clear_chat_bubble()
        self._return_home()
        self.show_bubble("已取消，电脑不会执行该操作", 2200)

    def _clear_chat_and_go_home(self):
        self._clear_chat_bubble()
        self._return_home()

    def _return_home(self):
        """气泡关闭后猫跑回提醒触发前的位置"""
        if self._notify_from:
            fx, fy = self._notify_from
            self._notify_from = None
            self._run_to(fx, fy, None)

    def _clear_chat_bubble(self):
        if self._bubble_win is not None:
            try:
                self._bubble_win.destroy()
            except Exception:
                pass
            self._bubble_win = None
        self._bubble_canvas = None
        self._bubble_items = []
        self._bubble_btn = None
        self._cd_text_id = None
        for aid in (self._countdown_id, self._chat_timer_id):
            if aid is not None:
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
        self._countdown_id = None
        self._chat_timer_id = None

    def _do_system_action(self, action):
        """执行每日提醒到点后的系统动作：lock=锁屏 / sleep=睡眠 / shutdown=关机"""
        do_system_action(action)

    def _fire_daily(self, d):
        """每日提醒到点：猫跑到屏幕中心弹气泡（选了锁屏/睡眠/关机则倒计时自动执行）"""
        self._notify_cat(d["msg"], action=_normalize_daily_action(d),
                         countdown=int(d.get("countdown") or SLEEP_COUNTDOWN_S))

    def _fire_reminder(self, msg):
        """到点：猫跑到屏幕中心弹气泡显示内容"""
        self._notify_cat(msg, "none")

    # ---------- 定时睡觉 ----------
    def _open_sleep_dialog(self):
        """弹出自定义睡觉时间设置窗口（美化版）"""
        dlg, frm = self._mk_dialog("设置睡觉时间")

        self._mk_lbl(frm, "睡觉时间：").grid(row=0, column=0, sticky="e", pady=5)
        entry_time = self._mk_entry(frm, width=10)
        entry_time.grid(row=0, column=1, sticky="w", pady=5)
        self._mk_lbl(frm, "输入分钟数，或时刻如 22:00", sub=True).grid(
            row=0, column=2, sticky="w", padx=(8, 0))

        def do_ok(_=None):
            secs, err = parse_reminder(entry_time.get())
            if err:
                entry_time.config(highlightbackground=UI_ERR)
                err_lbl.config(text=err)
                return
            self._schedule_sleep(secs)
            dlg.destroy()

        def do_cancel(_=None):
            dlg.destroy()

        err_lbl = self._mk_lbl(frm, "", fg=UI_ERR)
        err_lbl.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        btns = tk.Frame(frm, bg=UI_BG)
        btns.grid(row=2, column=0, columnspan=3, pady=(10, 2))
        self._mk_btn(btns, "确定", do_ok).pack(side="left", padx=6)
        self._mk_btn(btns, "取消", do_cancel, primary=False).pack(side="left", padx=6)

        dlg.bind("<Return>", do_ok)
        dlg.bind("<Escape>", do_cancel)
        dlg.transient(self.root)
        self._center_dialog(dlg)
        dlg.grab_set()
        entry_time.focus_set()

    def _cancel_sleep_timer(self):
        self._cancel(self._sleep_timer_id)
        self._sleep_timer_id = None
        self._sleep_at = None

    def _schedule_sleep(self, secs):
        """设置定时睡觉：到点后小猫入睡（睡到被点击唤醒），可随时取消"""
        self._cancel_sleep_timer()
        self._sleep_at = time.time() + secs
        self._sleep_timer_id = self._after(int(secs * 1000) + 200, self._fire_sleep)
        self.set_state("happy", 2000)
        self.show_bubble(f"已设置：{fmt_remaining(secs)}后睡觉（右键菜单可取消）", 3200)

    def _cancel_sleep(self):
        if self._sleep_at is None:
            self.show_bubble("当前没有睡觉计划", 1500)
            return
        self._cancel_sleep_timer()
        self.show_bubble("已取消睡觉计划", 1800)

    def _fire_sleep(self):
        """到点入睡：进入睡觉状态，直到被点击/菜单叫醒（不自动醒）"""
        self._sleep_at = None
        self._sleep_timer_id = None
        self.set_state("sleep", 0)  # 0 = 不安排自动恢复，等用户交互叫醒
        self.show_bubble("到点啦，睡觉觉～（点我一下叫醒）", 3200)

    # ---------- 睡眠恢复看门狗 ----------
    def _get_tick64(self):
        """系统开机以来的毫秒数；睡眠/休眠期间停止增长，用于检测系统刚唤醒"""
        return get_tick64()

    def _watchdog_loop(self):
        """周期性自检：系统睡眠唤醒后窗口可能丢失映射/置顶/透明属性，或跑到屏幕外。
        用真实时间与系统滴答的差异判断是否刚从睡眠恢复，恢复后立即修复并打招呼。"""
        now = time.time()
        tick = self._get_tick64()
        resumed = detect_resume(self._last_real, self._last_tick, now, tick)
        self._last_real = now
        self._last_tick = tick
        try:
            self._restore_window(resumed)
        except Exception:
            pass
        self._watchdog_id = self.root.after(WATCHDOG_MS, self._watchdog_loop)

    def _restore_window(self, resumed):
        if resumed and not self._hidden:
            # 睡眠恢复（用户未主动隐藏）：重新应用置顶/透明键色 + 1px 位移强制重绘（透明窗口经典修复）
            try:
                self.root.attributes("-topmost", self._topmost)
            except Exception:
                pass
            try:
                self.root.attributes("-transparentcolor", KEY)
            except Exception:
                pass
            try:
                x, y = self.root.winfo_x(), self.root.winfo_y()
                self.root.geometry(f"+{x + 1}+{y}")
                self.root.update_idletasks()
                self.root.geometry(f"+{x}+{y}")
                self.root.update_idletasks()
            except Exception:
                pass
            # 睡眠期间显示器配置可能变化导致窗口跑出屏幕：夹取回虚拟屏幕内
            try:
                x, y = self.root.winfo_x(), self.root.winfo_y()
                nx, ny = clamp_to_screen(x, y, self.win_w, self.win_h)
                if (nx, ny) != (x, y):
                    self.root.geometry(f"+{nx}+{ny}")
            except Exception:
                pass
            self.show_bubble("我回来啦～", 2200)
        elif not self.root.winfo_ismapped() and not self._hidden:
            # 窗口丢失映射（非用户主动隐藏）：重新显示 + 重新应用置顶与透明
            try:
                self.root.deiconify()
                self.root.attributes("-topmost", self._topmost)
                self.root.attributes("-transparentcolor", KEY)
            except Exception:
                pass

    # ---------- 右键菜单 ----------
    def _on_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0, bg="#FFFFFF", fg=UI_FG,
                       activebackground=UI_MENU_HI, activeforeground=UI_ACCENT,
                       bd=0, font=FONT)
        menu.add_command(label="😄 开心一下",
                         command=lambda: self.set_state("happy", STATE_SHOW_MS))
        menu.add_command(label="😴 睡觉", command=lambda: self.set_state("sleep"))
        menu.add_command(label="😱 吓一跳",
                         command=lambda: self.set_state("surprise", STATE_SHOW_MS))

        # 定时提醒子菜单
        remind = self._mk_submenu(menu)
        remind.add_command(label="➕ 添加提醒…", command=self._open_reminder_dialog)
        if self._timers:
            remind.add_separator()
            for t in list(self._timers):
                left = int(t["due"] - time.time())
                if t.get("repeat_min"):
                    label = (f"取消：{t['msg'][:10]}"
                             f"（每 {t['repeat_min']} 分钟，下次 {fmt_remaining(left)}）")
                else:
                    label = f"取消：{t['msg'][:10]}（剩 {fmt_remaining(left)}）"
                remind.add_command(
                    label=label,
                    command=lambda tt=t: self._cancel_reminder(tt))
        menu.add_cascade(label="⏰ 定时提醒", menu=remind)

        # 每日提醒子菜单（闹钟）
        daily_menu = self._mk_submenu(menu)
        daily_menu.add_command(label="➕ 设置每日提醒…", command=self._open_daily_dialog)
        if self._dailies:
            daily_menu.add_separator()
            for d in list(self._dailies):
                act = _normalize_daily_action(d)
                if act != "none":
                    mark = (f"{ACTION_ICON.get(act, '')} "
                            f"{int(d.get('countdown') or SLEEP_COUNTDOWN_S)}s ")
                else:
                    mark = ""
                daily_menu.add_command(
                    label=f"取消：{mark}{d['msg'][:10]}（每天 {d['hour']:02d}:{d['minute']:02d}）",
                    command=lambda dd=d: self._cancel_daily(dd))
        menu.add_cascade(label="🔔 每日提醒", menu=daily_menu)

        # 定时睡觉子菜单
        sleep_menu = self._mk_submenu(menu)
        sleep_menu.add_command(label="➕ 设置睡觉时间…", command=self._open_sleep_dialog)
        if self._sleep_at:
            left = int(self._sleep_at - time.time())
            sleep_menu.add_separator()
            sleep_menu.add_command(
                label=f"取消睡觉计划（剩 {fmt_remaining(left)}）",
                command=self._cancel_sleep)
        menu.add_cascade(label="🌙 定时睡觉", menu=sleep_menu)

        # 形象子菜单（记忆上次选择）
        pet_menu = self._mk_submenu(menu)
        for key, label in PETS:
            pet_menu.add_radiobutton(
                label=label, value=key, variable=self._pet_var,
                command=lambda k=key: self._set_pet(k))
        menu.add_cascade(label="🐾 选择形象", menu=pet_menu)

        # 大小子菜单（最小/最大阈值内）
        size_menu = self._mk_submenu(menu)
        size_menu.add_command(label="增大（+50）",
                              command=lambda: self.set_size(self._size + SIZE_STEP))
        size_menu.add_command(label="减小（-50）",
                              command=lambda: self.set_size(self._size - SIZE_STEP))
        size_menu.add_separator()
        for s in range(MIN_PET_SIZE, self._max_size + 1, SIZE_STEP):
            size_menu.add_radiobutton(label=f"{s}px", value=s,
                                      variable=self._size_var,
                                      command=lambda: self.set_size(self._size_var.get()))
        if (self._max_size - MIN_PET_SIZE) % SIZE_STEP:
            size_menu.add_radiobutton(label=f"{self._max_size}px", value=self._max_size,
                                      variable=self._size_var,
                                      command=lambda: self.set_size(self._size_var.get()))
        menu.add_cascade(label="📐 大小", menu=size_menu)

        menu.add_separator()
        menu.add_checkbutton(label="🖱 跟随鼠标", variable=self._follow_var,
                             command=self._toggle_follow)
        menu.add_checkbutton(label="📌 始终置顶", variable=self._topmost_var,
                             command=self._toggle_topmost)
        menu.add_checkbutton(label="🚀 开机自启", variable=self._autostart_var,
                             command=self._toggle_autostart)
        menu.add_separator()
        menu.add_command(label="🚪 退出", command=self.quit)
        try:
            menu.tk_popup(event.x_root, event.y_root)
            try:
                # 尽力把菜单本身也置顶（部分系统支持）
                self.root.tk.call("wm", "attributes", menu._w, "-topmost", True)
            except Exception:
                pass
            # 菜单打开期间临时关闭宠物置顶，避免菜单被盖住；菜单关闭后恢复
            self.root.attributes("-topmost", False)
            self._watch_menu_close(menu)
        finally:
            menu.grab_release()

    def _watch_menu_close(self, menu):
        """轮询菜单是否已关闭，关闭后恢复宠物置顶"""
        self._cancel(getattr(self, "_menu_watch_id", None))

        def check():
            try:
                if menu.winfo_exists() and menu.winfo_ismapped():
                    self._menu_watch_id = self._after(120, check)
                    return
            except Exception:
                pass
            try:
                self.root.attributes("-topmost", self._topmost)
            except Exception:
                pass
            self._menu_watch_id = None

        self._menu_watch_id = self._after(120, check)

    def _toggle_follow(self):
        self.set_follow(self._follow_var.get())

    def _toggle_topmost(self):
        self._topmost = self._topmost_var.get()
        self.root.attributes("-topmost", self._topmost)

    def _toggle_autostart(self):
        enabled = self._autostart_var.get()
        try:
            set_autostart(enabled)
        except Exception:
            self._autostart_var.set(not enabled)
            self.show_bubble("开机自启设置失败", 1800)
            return
        self.show_bubble("已开启开机自启（下次开机自动运行）"
                         if enabled else "已关闭开机自启", 2200)

    def quit(self):
        try:
            self._save_reminders()  # 退出前保存提醒/尺寸/位置
        except Exception:
            pass
        tray_stop()
        for aid in list(self._after_ids):
            try:
                self.root.after_cancel(aid)
            except Exception:
                pass
        for aid in (self._anim_id, self._follow_id, self._timer_id, self._watchdog_id):
            if aid is not None:
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
        self._clear_chat_bubble()
        self.root.destroy()


def _acquire_single_instance():
    """单实例互斥体：已有实例在运行时返回 False（新实例直接退出）。
    tk 版与 qt 版共用同一互斥体，防止两个版本同时运行。"""
    return acquire_single_instance()


def main():
    if not _acquire_single_instance():
        return
    set_dpi_aware()
    root = tk.Tk()
    root.title("收工喵")
    pet = DesktopPet(root)
    root.mainloop()


if __name__ == "__main__":
    main()
