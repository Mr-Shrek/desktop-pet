# -*- coding: utf-8 -*-
"""收工喵 —— 公共核心模块（tkinter 版与 PyQt5 版共用）

本模块只包含与 UI 无关的纯逻辑：路径/素材/数据文件常量、输入解析、
开机自启、数据读写、提醒调度检查、系统动作（锁屏/睡眠/关机）、
单实例互斥、DPI 感知、睡眠恢复判断、虚拟屏幕夹取。
窗口、动画、菜单、对话框、托盘等 UI 层由各版本自行实现。

用法：from core import *   （或 import core）
"""
import ctypes
import json
import math
import os
import random
import sys
import time
import winreg

# 打包(frozen/__compiled__)模式下：素材从解压目录读取（onefile 每次解压到临时目录）。
# 兼容 PyInstaller(_MEIPASS) 与 Nuitka(__compiled__，资源在 __file__ 所在解压目录)。
if getattr(sys, "frozen", False) or "__compiled__" in globals():
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = BASE_DIR
SPRITE_DIR = os.path.join(RES_DIR, "sprites")   # 宠物素材
# 可切换形象：key → (目录, 显示名)。cat 沿用 sprites/ 根目录，其余在 sprites/<key>/
PETS = (
    ("cat", "黄色小猫"),
    ("redpanda", "小熊猫"),
    ("panda", "大熊猫"),
    ("capybara", "卡皮巴拉"),
    ("husky", "哈士奇"),
)
PET_KEYS = [k for k, _ in PETS]
PET_LABEL = dict(PETS)
PET_DIR = {k: (SPRITE_DIR if k == "cat" else os.path.join(SPRITE_DIR, k))
           for k, _ in PETS}
DEFAULT_PET = "cat"

# 数据文件：存到 %APPDATA%\DoubaoPet（稳定位置）。
# Nuitka onefile 主进程的 sys.executable 指向随机临时目录（每次启动不同），
# 数据若写 exe 旁会"重启即丢"；%APPDATA% 是 Windows 标准用户数据目录。
DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "DoubaoPet")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = BASE_DIR
DATA_FILE = os.path.join(DATA_DIR, "pet_data.json")  # 提醒等本地持久化数据


def real_exe_path():
    """返回桌宠主程序真实可执行文件路径：
    - Nuitka onefile：主进程 sys.executable 指向临时解压目录，真实路径在 sys.argv[0]
    - PyInstaller：sys.executable 即 exe
    - 源码运行：sys.executable 即 python 解释器
    """
    if "__compiled__" in globals():
        return os.path.abspath(sys.argv[0])
    return os.path.abspath(sys.executable)


def _migrate_legacy_data():
    """首次运行（%APPDATA% 无数据）时，从旧位置(exe旁/源码旁)的 pet_data.json 迁移，
    延续用户之前的大小/位置/提醒设置。"""
    if os.path.exists(DATA_FILE):
        return
    for cand in (os.path.join(BASE_DIR, "pet_data.json"),):
        try:
            if os.path.exists(cand):
                os.makedirs(DATA_DIR, exist_ok=True)
                import shutil
                shutil.copy2(cand, DATA_FILE)
                return
        except Exception:
            continue


_migrate_legacy_data()

# ---------- 通用常量 ----------
KEY = "#160015"            # 透明键色（深品红：与深色描边混合后边缘晕染几乎不可见）
DEFAULT_PET_SIZE = 300     # 宠物默认显示尺寸(px)
MIN_PET_SIZE = 50          # 宠物最小尺寸阈值(px)
MAX_PET_SIZE = 600         # 宠物最大尺寸阈值(px，= 素材原始分辨率上限)
SIZE_STEP = 50             # 尺寸调节步长(px)
WIN_MARGIN = 20            # 窗口比宠物宽出的边距
WIN_TOP = 160              # 窗口顶部预留气泡空间
PET_PAD = 12               # 宠物底部距窗口底边
FRAME_MS = 33              # 动画帧间隔(ms)
BUBBLE_SHOW_MS = 2600      # 气泡显示时长(ms)
BUBBLE_INTERVAL = (15000, 38000)  # 待机随机气泡间隔(ms)
REACT_MS = 900             # 点击/双击反应时长(ms)
STATE_SHOW_MS = 1500       # 菜单选择开心/惊讶后的展示时长(ms)
SLEEP_AUTO_WAKE_MS = 180000  # 睡觉状态自动醒来的时长(3 分钟)
CLICK_DELAY_MS = 260       # 单击判定延迟（区分双击）
FOLLOW_STOP_DIST = 26     # 跟随：鼠标距离小于该值则停（待机）
FOLLOW_STOP_HYST = 60     # 静止档脱离滞回(px)：停住后需离开窗口且距离>26+60=86px 才恢复动画，防动画/静止闪动
FOLLOW_WALK_DIST = 220    # 跟随：鼠标距离小于该值→走动，大于→快速跑
FOLLOW_HYST = 40          # 跟随分档滞回带(px)：±40 内保持当前档位，防临界点跑/走闪动
FOLLOW_WALK_STEP = 4       # 跟随·走动每帧位移(px)（FOLLOW_MS 15ms 下 ≈267px/s）
FOLLOW_RUN_STEP = 13       # 跟随·快跑每帧位移(px)（FOLLOW_MS 15ms 下 ≈867px/s）
FOLLOW_MS = 15             # 跟随模式帧间隔(ms)
MOVE_THRESHOLD = 6        # 超过该位移视为拖拽而非点击
RUN_FRAMES = ("run1", "run5", "run6", "run7", "run8", "run9", "run10", "run11")  # 跑动 8 帧（run1 原始 + 7 帧 AI 递进连续循环）
WALK_FRAMES = ("walk1", "walk2", "walk3", "walk4")  # 走动动画 4 帧步态循环
FRAME_CHASE_MS = 45       # 快跑（跟随模式）换帧间隔(ms)，8 帧递进约 22fps 同源连续
FRAME_WALK_MS = 250       # 走动换帧间隔(ms)
WATCHDOG_MS = 2500         # 窗口看门狗轮询间隔(ms)：睡眠恢复/置顶丢失自检
RESUME_GAP_S = 8           # 真实时间差超过该值且系统滴答几乎不动 → 判定刚睡眠恢复
HOP_HEIGHT = 26            # 开心跳跃高度(px)
HOP_MS = 480               # 开心跳跃时长(ms)
PARTICLE_LIFE_MS = 1400    # 粒子（爱心/zZz）存活时长(ms)
SLEEP_Z_MS = 1700          # 睡觉时 zZz 粒子间隔(ms)
HAPPY_PARTICLES = 4        # 开心时一次飘出的粒子数
CHAT_BUBBLE_MS = 8000      # 提醒气泡自动消失时长(ms)
SLEEP_COUNTDOWN_S = 10     # 每日提醒(自动动作)的倒计时秒数
# 每日提醒到点后的系统动作：none=仅提醒 / lock=锁屏 / sleep=睡眠 / shutdown=关机
DAILY_ACTIONS = (("none", "无操作"), ("lock", "锁屏"), ("sleep", "睡眠"),
                 ("shutdown", "关机"))
ACTION_LABEL = {"none": "无操作", "lock": "锁屏", "sleep": "睡眠",
                "shutdown": "关机"}
ACTION_ICON = {"lock": "🔒", "sleep": "🌙", "shutdown": "⏻"}
ACTION_KEY = {lbl: key for key, lbl in DAILY_ACTIONS}   # 中文标签 → 动作 key

SPRITES = ("idle", "happy", "sleep", "surprise")
ANIM_SPRITES = SPRITES + RUN_FRAMES + WALK_FRAMES   # 含跑动/走动动画帧
# 动画帧的水平镜像副本（跟随鼠标时朝向目标）
ANIM_SPRITES += tuple(f + "_l" for f in RUN_FRAMES + WALK_FRAMES)
FONT = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 13, "bold")

# ---------- 设置窗口 / 右键菜单统一主题（暖橙系） ----------
UI_BG = "#FFF6EC"         # 对话框背景（暖米白）
UI_BG2 = "#FFEFDD"        # 次级背景（按钮/输入条）
UI_FG = "#4A3B32"         # 主文字（深棕）
UI_SUB = "#B39B87"        # 提示文字（浅棕）
UI_ACCENT = "#FF8A3D"     # 主色（橙）
UI_ACCENT_HI = "#F0761F"  # 主色悬停
UI_ERR = "#D94F4F"        # 错误提示红
UI_INPUT_BD = "#E5CFB8"   # 输入框边框
UI_MENU_HI = "#FFF0E2"    # 菜单项悬停背景

# 提示语按形象区分（结合各动物实际叫声的中文拟声；自定义覆盖存 pet_data.json）
PET_MSGS = {
    "cat": {
        "idle": ["喵～", "喵呜～", "今天也要加油哦！", "摸摸我嘛～",
                 "我在这里陪你～", "起来活动一下！", "写累了就休息会儿吧"],
        "happy": ["嘿嘿，好开心！", "被投喂啦！", "最喜欢你啦！", "再玩一次！"],
        "sleep": ["zZz…", "呼噜呼噜…", "别吵我…", "好困…"],
        "surprise": ["哇！", "吓我一跳！", "呜哇！"],
    },
    "redpanda": {   # 小熊猫：高频啾啾（chirp），似鸟鸣
        "idle": ["啾啾～", "叽叽～", "今天也要加油哦！", "摸摸我嘛～",
                 "我在这里陪你～", "起来活动一下！"],
        "happy": ["啾！好开心！", "被投喂啦！", "最喜欢你啦！", "再玩一次！"],
        "sleep": ["zZz…", "呼噜呼噜…", "别吵我…", "好困…"],
        "surprise": ["哇！", "吓我一跳！", "呜哇！"],
    },
    "panda": {      # 大熊猫：咩咩（似羊）/哞哞（低鸣）
        "idle": ["咩～", "哞哞～", "今天也要加油哦！", "摸摸我嘛～",
                 "我在这里陪你～", "起来活动一下！"],
        "happy": ["咩！好开心！", "被投喂啦！", "最喜欢你啦！", "再玩一次！"],
        "sleep": ["zZz…", "呼噜呼噜…", "别吵我…", "好困…"],
        "surprise": ["哇！", "吓我一跳！", "呜哇！"],
    },
    "capybara": {   # 卡皮巴拉：咕噜咕噜（purr）/哼哼（哼唧）
        "idle": ["咕噜～", "哼哼～", "今天也要加油哦！", "摸摸我嘛～",
                 "我在这里陪你～", "起来活动一下！"],
        "happy": ["咕噜咕噜！", "被投喂啦！", "最喜欢你啦！", "再玩一次！"],
        "sleep": ["zZz…", "呼噜呼噜…", "别吵我…", "好困…"],
        "surprise": ["哇！", "吓我一跳！", "呜哇！"],
    },
    "husky": {      # 哈士奇：嗷呜（狼嚎）/汪汪
        "idle": ["嗷呜～", "汪汪～", "今天也要加油哦！", "摸摸我嘛～",
                 "我在这里陪你～", "起来活动一下！"],
        "happy": ["嗷呜！好开心！", "被投喂啦！", "最喜欢你啦！", "再玩一次！"],
        "sleep": ["zZz…", "呼噜呼噜…", "别吵我…", "好困…"],
        "surprise": ["哇！", "吓我一跳！", "呜哇！"],
    },
}
MESSAGES = PET_MSGS["cat"]   # 兼容旧引用（tk 版等）


# ---------- 输入解析 ----------
def parse_reminder(raw):
    """解析提醒时间输入：支持分钟数（如 30 / 1.5）或时刻（如 14:30）。
    返回 (秒数, 错误信息)；错误时秒数为 0。"""
    raw = (raw or "").strip()
    if not raw:
        return 0, "时间不能为空"
    if ":" in raw:
        try:
            hh, mm = raw.split(":")
            hh, mm = int(hh), int(mm)
        except ValueError:
            return 0, "时间格式错误，请输入如 14:30"
        if not (0 <= hh < 24 and 0 <= mm < 60):
            return 0, "时间格式错误，请输入如 14:30"
        now = time.localtime()
        due = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hh, mm, 0, 0, 0, -1))
        if due <= time.time():
            due += 86400  # 今天该时刻已过，顺延到明天
        return int(due - time.time()), None
    try:
        minutes = float(raw)
    except ValueError:
        return 0, "请输入分钟数（如 30）或时刻（如 14:30）"
    if minutes <= 0:
        return 0, "时间必须大于 0"
    return int(minutes * 60), None


def fmt_remaining(secs):
    """把剩余秒数格式化为 'X 小时 Y 分' / 'Y 分' / 'Z 秒'。"""
    secs = int(max(0, secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} 小时 {m} 分"
    if m:
        return f"{m} 分 {s} 秒"
    return f"{s} 秒"


def parse_clock(raw):
    """解析时刻输入（如 08:30），返回 (hour, minute) 或 (None, 错误信息)。"""
    raw = (raw or "").strip()
    if ":" not in raw:
        return None, "请输入时刻，如 08:30"
    try:
        hh, mm = raw.split(":")
        hh, mm = int(hh), int(mm)
    except ValueError:
        return None, "时间格式错误，请输入如 08:30"
    if not (0 <= hh < 24 and 0 <= mm < 60):
        return None, "时间格式错误，请输入如 08:30"
    return (hh, mm), None


def _normalize_daily_action(d):
    """兼容读取每日提醒动作：新数据读 action；旧数据 sleep=True → "sleep"、False → "none" """
    a = str(d.get("action") or "")
    if a in ("lock", "sleep", "shutdown"):
        return a
    return "sleep" if d.get("sleep") else "none"


# ---------- 开机自启（注册表 HKCU Run 键） ----------
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "收工喵"


def autostart_command():
    """生成开机自启命令行：打包(exe)直接指向真实 exe；未打包优先用 pythonw（无控制台窗口）"""
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return f'"{real_exe_path()}"'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    script = os.path.join(BASE_DIR, "main.py")
    return f'"{exe}" "{script}"'


def is_autostart_enabled(name=AUTOSTART_NAME):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
            winreg.QueryValueEx(k, name)
            return True
    except OSError:
        return False


def set_autostart(enabled, name=AUTOSTART_NAME):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass


# ---------- 数据读写（%APPDATA%\DoubaoPet\pet_data.json） ----------
def load_data():
    """读取数据文件，失败返回 None"""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_data(payload):
    """把字典整体写入数据文件；失败时写错误日志"""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:
        try:
            with open(os.path.join(DATA_DIR, "save_error.log"), "w",
                      encoding="utf-8") as f:
                f.write(repr(e))
        except Exception:
            pass
        return False


def load_saved_size():
    """读取持久化的宠物尺寸；无记录时返回 0（表示用默认值）"""
    data = load_data()
    try:
        return int((data or {}).get("size") or 0)
    except Exception:
        return 0


def load_saved_pos():
    """读取持久化的窗口位置 (x, y)；无记录时返回 None"""
    data = load_data()
    try:
        p = (data or {}).get("pos") or {}
        return int(p["x"]), int(p["y"])
    except Exception:
        return None


def load_saved_pet():
    """读取持久化的形象 key；无记录或未知形象时返回默认 cat"""
    data = load_data()
    try:
        pet = str((data or {}).get("pet") or "")
        return pet if pet in PET_KEYS else DEFAULT_PET
    except Exception:
        return DEFAULT_PET


# ---------- 提示语（按形象，含默认拟声 + 自定义覆盖） ----------
def get_pet_msgs(pet_key):
    """当前形象提示语：数据里自定义过用自定义（含空列表），否则用默认"""
    defaults = PET_MSGS.get(pet_key) or PET_MSGS["cat"]
    data = load_data()
    try:
        saved = (data or {}).get("pet_msgs") or {}
        saved = saved.get(pet_key) or {}
    except Exception:
        saved = {}
    out = {}
    for st, lst in defaults.items():
        sl = saved.get(st)
        out[st] = list(sl) if sl is not None else list(lst)
    return out


def save_pet_msgs(pet_key, msgs):
    """持久化某形象的提示语（合并写，不丢 reminders 等其他字段）"""
    data = load_data() or {}
    pet_msgs = dict(data.get("pet_msgs") or {})
    pet_msgs[pet_key] = {st: list(lst) for st, lst in msgs.items()}
    data["pet_msgs"] = pet_msgs
    save_data(data)


def pick_pet_msg(pet_key, state):
    """随机取一条提示语；该状态被删空时回退默认（cat）"""
    msgs = get_pet_msgs(pet_key).get(state) or []
    if not msgs:
        msgs = PET_MSGS["cat"].get(state) or ["喵～"]
    return random.choice(msgs)


def remove_pet_msgs(pet_key):
    """清除某形象的自定义提示语（恢复为默认拟声）"""
    data = load_data() or {}
    pet_msgs = dict(data.get("pet_msgs") or {})
    if pet_key in pet_msgs:
        del pet_msgs[pet_key]
        data["pet_msgs"] = pet_msgs
        save_data(data)


# ---------- 提醒列表 ↔ 数据文件 转换 ----------
def timers_from_entries(entries):
    """从数据文件的 reminders 列表恢复定时提醒。
    过期的一次性提醒不恢复；轮询提醒即使过期也顺延到下一个周期恢复。"""
    timers = []
    now = time.time()
    for r in entries or []:
        try:
            due = float(r["due"])
            msg = str(r.get("msg", "")).strip() or "时间到啦！"
        except Exception:
            continue
        repeat_min = r.get("repeat_min")
        if repeat_min:
            try:
                interval = max(1, int(repeat_min)) * 60
            except Exception:
                continue
            if due <= now:
                due += (int((now - due) // interval) + 1) * interval
            timers.append({"due": due, "msg": msg,
                           "repeat_min": max(1, int(repeat_min))})
        elif due > now:
            timers.append({"due": due, "msg": msg})
    return timers


def dailies_from_entries(entries):
    """从数据文件的 dailies 列表恢复每日提醒（含动作与倒计时）。"""
    dailies = []
    for d in entries or []:
        try:
            hour = int(d["hour"])
            minute = int(d["minute"])
        except Exception:
            continue
        if not (0 <= hour < 24 and 0 <= minute < 60):
            continue
        msg = str(d.get("msg", "")).strip() or "时间到啦！"
        dailies.append({"hour": hour, "minute": minute, "msg": msg,
                        "last": str(d.get("last") or ""),
                        "action": _normalize_daily_action(d),
                        "countdown": int(d.get("countdown")
                                         or SLEEP_COUNTDOWN_S)})
    return dailies


def reminders_payload(timers, dailies, size=None, pet=None, pos=None):
    """组装完整数据字典（提醒 + 每日提醒 + 尺寸 + 形象 + 位置）"""
    return {
        "reminders": [{"due": t["due"], "msg": t["msg"],
                       "repeat_min": t.get("repeat_min")}
                      for t in timers],
        "dailies": [{"hour": d["hour"], "minute": d["minute"],
                     "msg": d["msg"], "last": d.get("last") or "",
                     "action": _normalize_daily_action(d),
                     "countdown": int(d.get("countdown")
                                      or SLEEP_COUNTDOWN_S)}
                    for d in dailies],
        "size": size,
        "pos": pos,
        "pet": pet,
    }


def check_reminders(timers, dailies, now=None):
    """检查到点的定时/每日提醒（就地更新 timers/dailies）：
    - 定时提醒：到点触发；轮询的顺延到下一周期（保留），单次的移除
    - 每日提醒：到固定时刻且当天未提醒 → 标记当天并触发
    返回 (reminders_fired, dailies_fired, changed)：
    reminders_fired: [msg, ...]；dailies_fired: [daily_dict, ...]（已含当天标记）
    """
    now = time.time() if now is None else now
    fired_r, fired_d, changed = [], [], False
    for t in [x for x in timers if x["due"] <= now]:
        if t.get("repeat_min"):
            interval = max(1, int(t["repeat_min"])) * 60
            while t["due"] <= now:
                t["due"] += interval
        else:
            timers.remove(t)
        fired_r.append(t["msg"])
        changed = True
    lt = time.localtime(now)
    today = f"{lt.tm_year:04d}-{lt.tm_mon:02d}-{lt.tm_mday:02d}"
    for d in dailies:
        if (d["hour"], d["minute"]) == (lt.tm_hour, lt.tm_min) and d.get("last") != today:
            d["last"] = today
            fired_d.append(d)
            changed = True
    return fired_r, fired_d, changed


# ---------- 系统能力 ----------
def do_system_action(action):
    """执行每日提醒到点后的系统动作：lock=锁屏 / sleep=睡眠 / shutdown=关机"""
    try:
        if action == "lock":
            ctypes.windll.user32.LockWorkStation()
        elif action == "sleep":
            ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        elif action == "shutdown":
            # EWX_SHUTDOWN(0x01) | EWX_POWEROFF(0x08)：正常关机
            ctypes.windll.user32.ExitWindowsEx(0x09, 0)
    except Exception:
        pass


def get_tick64():
    """系统开机以来的毫秒数；睡眠/休眠期间停止增长，用于检测系统刚唤醒"""
    try:
        return ctypes.windll.kernel32.GetTickCount64()
    except Exception:
        return 0


def detect_resume(last_real, last_tick, now, tick, gap_s=RESUME_GAP_S):
    """用真实时间与系统滴答的差异判断是否刚从睡眠恢复。
    返回 True 表示真实时间走了 gap_s 以上而系统滴答几乎没动。"""
    if last_tick and tick:
        dt_real = now - last_real
        dt_tick = (tick - last_tick) / 1000.0
        if dt_real > gap_s and dt_tick < dt_real * 0.5:
            return True
    return False


def clamp_to_screen(x, y, win_w, win_h):
    """把坐标夹取到虚拟屏幕范围内（多显示器整体范围），防止窗口跑出屏幕"""
    try:
        vx = ctypes.windll.user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        vy = ctypes.windll.user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
        vw = ctypes.windll.user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        vh = ctypes.windll.user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
        x = max(vx, min(x, vx + vw - win_w))
        y = max(vy, min(y, vy + vh - win_h))
    except Exception:
        pass
    return x, y


def acquire_single_instance(name="Local\\ShouGongMiaoPetMutex"):
    """单实例互斥体：已有实例在运行时返回 False（新实例直接退出）。
    tk 版与 qt 版共用同一互斥体名，防止两个版本同时运行。"""
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, name)
        if not handle:
            return False
        if ctypes.windll.kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
            ctypes.windll.kernel32.CloseHandle(handle)
            return False
        return True
    except Exception:
        return True   # 无法创建互斥体时不阻塞运行


def set_dpi_aware():
    """进程级 DPI 感知（Per-Monitor V2），高分屏下窗口与图标清晰"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


__all__ = [
    "BASE_DIR", "RES_DIR", "SPRITE_DIR", "PETS", "PET_KEYS", "PET_LABEL",
    "PET_DIR", "DEFAULT_PET", "DATA_DIR", "DATA_FILE", "real_exe_path",
    "KEY", "DEFAULT_PET_SIZE", "MIN_PET_SIZE", "MAX_PET_SIZE", "SIZE_STEP",
    "WIN_MARGIN", "WIN_TOP", "PET_PAD", "FRAME_MS", "BUBBLE_SHOW_MS",
    "BUBBLE_INTERVAL", "REACT_MS", "STATE_SHOW_MS", "SLEEP_AUTO_WAKE_MS",
    "CLICK_DELAY_MS", "FOLLOW_STOP_DIST", "FOLLOW_STOP_HYST", "FOLLOW_WALK_DIST",
    "FOLLOW_HYST", "FOLLOW_WALK_STEP", "FOLLOW_RUN_STEP", "FOLLOW_MS",
    "MOVE_THRESHOLD", "RUN_FRAMES", "WALK_FRAMES", "FRAME_CHASE_MS",
    "FRAME_WALK_MS", "WATCHDOG_MS", "RESUME_GAP_S", "HOP_HEIGHT", "HOP_MS",
    "PARTICLE_LIFE_MS", "SLEEP_Z_MS", "HAPPY_PARTICLES", "CHAT_BUBBLE_MS",
    "SLEEP_COUNTDOWN_S", "DAILY_ACTIONS", "ACTION_LABEL", "ACTION_ICON",
    "ACTION_KEY", "SPRITES", "ANIM_SPRITES", "FONT", "FONT_BOLD",
    "UI_BG", "UI_BG2", "UI_FG", "UI_SUB", "UI_ACCENT", "UI_ACCENT_HI",
    "UI_ERR", "UI_INPUT_BD", "UI_MENU_HI", "MESSAGES", "PET_MSGS",
    "get_pet_msgs", "save_pet_msgs", "pick_pet_msg", "remove_pet_msgs",
    "parse_reminder", "fmt_remaining", "parse_clock", "_normalize_daily_action",
    "AUTOSTART_KEY", "AUTOSTART_NAME", "autostart_command",
    "is_autostart_enabled", "set_autostart",
    "load_data", "save_data", "load_saved_size", "load_saved_pos",
    "load_saved_pet", "timers_from_entries", "dailies_from_entries",
    "reminders_payload", "check_reminders",
    "do_system_action", "get_tick64", "detect_resume", "clamp_to_screen",
    "acquire_single_instance", "set_dpi_aware",
]
