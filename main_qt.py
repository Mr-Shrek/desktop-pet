# -*- coding: utf-8 -*-
"""收工喵 —— PyQt5 版桌宠（UI 更精致、动画更流畅）

与 tkinter 版（main.py）共享 core.py 公共逻辑、sprites/ 素材与
%APPDATA%\\DoubaoPet\\pet_data.json 数据文件，两个版本数据互通。

启动方式：
    python main_qt.py            # 源码运行
    build_qt.bat 编译后的 exe    # 打包运行
"""
import ctypes
import ctypes.wintypes
import math
import os
import random
import sys
import time

from core import *   # 公共核心：路径/素材/数据/解析/调度/系统动作/单实例/DPI

from PyQt5.QtCore import (Qt, QTimer, QPoint, QRect, QSize, pyqtSignal)
from PyQt5.QtGui import (QPixmap, QPainter, QColor, QFont, QFontMetrics,
                         QPainterPath, QPen, QBrush, QIcon, QImage,
                         QTransform, QLinearGradient, QRadialGradient,
                         QPolygonF, QMouseEvent, QContextMenuEvent, QCursor)
from PyQt5.QtWidgets import (QApplication, QWidget, QLabel, QMenu,
                             QSystemTrayIcon, QDialog, QVBoxLayout,
                             QHBoxLayout, QLineEdit, QPushButton, QCheckBox,
                             QComboBox, QSpinBox, QGraphicsDropShadowEffect,
                             QFrame, QSizePolicy, QToolTip, QTabWidget,
                             QListWidget, QStackedWidget, QScrollArea,
                             QLayout)

APP_NAME = "收工喵"
MUTEX_NAME = "Local\\ShouGongMiaoPetMutex"   # 与 tk 版共用，双版本互斥


# --------------------------------------------------------------------------
# 精灵图缓存：按 (形象, 帧名, 朝向, 尺寸) 缓存已缩放的 QPixmap
# --------------------------------------------------------------------------
class SpriteCache:
    def __init__(self):
        self._native = {}    # (pet, name) -> QPixmap(原生 600x600)
        self._scaled = {}    # (pet, name, facing, size) -> QPixmap
        self._refs = {}      # 记录当前加载的形象，用于切换时清理

    def load_pet(self, pet):
        """预加载某个形象的 20 张原生帧"""
        d = PET_DIR.get(pet)
        if not d or not os.path.isdir(d):
            return False
        native = {}
        for name in ANIM_SPRITES:
            p = os.path.join(d, name + ".png")
            if not os.path.exists(p):
                return False
            pm = QPixmap(p)
            if pm.isNull():
                return False
            native[name] = pm
        # 清理该形象旧的缩放缓存
        for k in [k for k in self._scaled if k[0] == pet]:
            del self._scaled[k]
        self._native[pet] = native
        self._refs[pet] = True
        return True

    def release_pet(self, pet):
        """释放某个形象的原生帧与缩放缓存（切换形象时调用）"""
        self._native.pop(pet, None)
        self._refs.pop(pet, None)
        for k in [k for k in self._scaled if k[0] == pet]:
            del self._scaled[k]

    def frame(self, pet, name, facing, size):
        """取一帧：facing<0 取镜像帧；带缓存。返回 QPixmap 或 None"""
        real = name + "_l" if facing < 0 and name in (RUN_FRAMES + WALK_FRAMES) else name
        key = (pet, real, size)
        pm = self._scaled.get(key)
        if pm is None:
            src = (self._native.get(pet) or {}).get(real)
            if src is None:
                return None
            side = min(src.width(), src.height())
            pm = src.copy(0, 0, side, side).scaled(
                size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._scaled[key] = pm
        return pm

    def any_frame(self, pet, size):
        """取任意一帧（用于生成托盘图标等）"""
        native = self._native.get(pet)
        if not native:
            return QPixmap()
        pm = next(iter(native.values()))
        side = min(pm.width(), pm.height())
        return pm.copy(0, 0, side, side).scaled(size, size, Qt.KeepAspectRatio,
                                                Qt.SmoothTransformation)


# --------------------------------------------------------------------------
# 粒子（爱心 / zZz）：QWidget 内浮动的 emoji 标签，带淡出
# --------------------------------------------------------------------------
class Particle(QLabel):
    def __init__(self, parent, text, x, y, dx, dy, life_ms=PARTICLE_LIFE_MS):
        super().__init__(parent)
        self.setText(text)
        self.setStyleSheet("background:transparent;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        f = QFont(FONT[0], 13)
        self.setFont(f)
        self.adjustSize()
        self._x, self._y = float(x), float(y)
        self._dx, self._dy = dx, dy
        self._born = time.time()
        self._life = life_ms / 1000.0
        self._op = None
        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._op = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._op)
        self.move(int(self._x), int(self._y))
        self.show()

    def tick(self, now):
        self._x += self._dx
        self._y += self._dy
        self.move(int(self._x), int(self._y))
        age = now - self._born
        if self._life > 0:
            a = max(0.0, 1.0 - age / self._life)
            self._op.setOpacity(a)
        return age < self._life


# --------------------------------------------------------------------------
# 插画气泡（AI 素材：sprites/bubble_*.png 底图 + sprites/icon_*.png 图标）
# 底图用 QLabel 承载（禁 paintEvent 自绘，历史 native 崩溃 0xC0000409）
# --------------------------------------------------------------------------
BUBBLE_W, BUBBLE_H = 400, 300                    # 底图原生尺寸（4:3）
BUBBLE_SIZES = ((400, 300), (360, 270), (320, 240), (280, 210))   # 动态档位
_MARG_LR, _MARG_T, _MARG_B = 24, 14, 48          # 内容区边距（下边让尾巴）
_BUBBLE_PM = {}     # theme -> QPixmap
_ICON_PM = {}       # icon  -> QPixmap


def _wrap_lines(msg, fm, max_w):
    """按像素宽度换行（与布局一致的确定性换行）"""
    lines, cur = [], ""
    for ch in msg:
        if cur and fm.horizontalAdvance(cur + ch) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines or [""]


def _bubble_pixmap(theme):
    pm = _BUBBLE_PM.get(theme)
    if pm is None:
        pm = QPixmap(os.path.join(SPRITE_DIR, "bubble_%s.png" % theme))
        _BUBBLE_PM[theme] = pm
    return pm


def _icon_pixmap(name):
    pm = _ICON_PM.get(name)
    if pm is None:
        raw = QPixmap(os.path.join(SPRITE_DIR, "icon_%s.png" % name))
        pm = (raw.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
              if not raw.isNull() else QPixmap())
        _ICON_PM[name] = pm
    return pm


# 主题配色：文字 / 倒计时 / 按钮(底, 边, 字)
_THEME_FG = {"default": "#4a3b2a", "night": "#f4f1ff",
             "sunset": "#5a2d00", "alert": "#6b1a12"}
_THEME_CD = {"default": "#d35400", "night": "#ffd98a",
             "sunset": "#c0392b", "alert": "#b71c1c"}
_THEME_BTN = {"default": ("#ffffff", "#e8e6e3", "#d35400"),
              "night": ("#3a2d5f", "#57438c", "#ffffff"),
              "sunset": ("#ffffff", "#e8c9a8", "#c0392b"),
              "alert": ("#ffffff", "#e8c4c4", "#b71c1c")}


def pick_theme(msg, action):
    """提醒内容 -> 气泡主题：关机=警示、睡觉/锁屏=夜晚、下班/收工=夕阳、其余=普通"""
    if action == "shutdown":
        return "alert"
    if action in ("sleep", "lock"):
        return "night"
    if "下班" in msg or "收工" in msg:
        return "sunset"
    return "default"


def pick_icon(msg, action):
    """提醒内容 -> 主题图标：关机=警示、睡觉/锁屏=月亮、下班=夕阳、喝水=水滴、其余=铃铛"""
    if action == "shutdown":
        return "warn"
    if action in ("sleep", "lock"):
        return "moon"
    if "下班" in msg or "收工" in msg:
        return "sunset"
    if "喝水" in msg or "喝口" in msg:
        return "drop"
    return "bell"


class ChatBubble(QFrame):
    """插画风格气泡：AI 底图(QLabel) + 叠文字/图标/倒计时/取消按钮"""
    cancelled = pyqtSignal()
    countdown_finished = pyqtSignal()   # 保留定义（_show_bubble 引用）

    def __init__(self, msg, action="none", countdown=SLEEP_COUNTDOWN_S,
                 theme="default", icon="bell", font_size=12):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._action = action
        self._countdown = int(countdown)
        self._cd_label = None
        has_act = action not in (None, "", "none")

        # ---- 按内容选最小档位（4:3），文字多则气泡大 ----
        fm = QFontMetrics(QFont("Microsoft YaHei UI", font_size))
        line_h = fm.height() + 2
        act_h = (line_h + 8 + 34) if has_act else 0      # 倒计时行 + 按钮行
        sel_w, sel_h, lines = BUBBLE_W, BUBBLE_H, [msg]
        for w_, h_ in sorted(BUBBLE_SIZES):    # 从最小档位开始，取首个装得下的
            txt_w = w_ - _MARG_LR * 2 - 30               # 图标 22 + 间距 8
            ls = _wrap_lines(msg, fm, txt_w)
            need = 22 + 4 + len(ls) * line_h + 6 + act_h
            if need <= h_ - _MARG_T - _MARG_B:
                sel_w, sel_h, lines = w_, h_, ls
                break
        self.setFixedSize(sel_w, sel_h)

        # ---- 底图（按档位缩放，QLabel 承载，无自绘） ----
        bg = QLabel(self)
        pm = _bubble_pixmap(theme)
        if not pm.isNull() and (pm.width() != sel_w or pm.height() != sel_h):
            pm = pm.scaled(sel_w, sel_h, Qt.IgnoreAspectRatio,
                           Qt.SmoothTransformation)
        bg.setPixmap(pm)
        bg.setGeometry(0, 0, sel_w, sel_h)
        bg.setAttribute(Qt.WA_TransparentForMouseEvents)

        fg = _THEME_FG.get(theme, "#333333")

        # ---- 内容层（避开正下中央的尾巴尖） ----
        wrap = QWidget(self)
        wrap.setGeometry(_MARG_LR, _MARG_T, sel_w - _MARG_LR * 2,
                         sel_h - _MARG_T - _MARG_B)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        # 图标 + 多行文本（图标左上）
        top = QHBoxLayout()
        top.setSpacing(8)
        ic = QLabel(wrap)
        ic.setFixedSize(22, 22)
        ipm = _icon_pixmap(icon)
        if not ipm.isNull():
            ic.setPixmap(ipm)
        ic.setAttribute(Qt.WA_TransparentForMouseEvents)
        top.addWidget(ic, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        for line in lines:
            lb = QLabel(line, wrap)
            lb.setAttribute(Qt.WA_TransparentForMouseEvents)
            lb.setStyleSheet(
                "background:transparent; color:%s;"
                " font-family:'Microsoft YaHei UI'; font-size:%dpx;"
                " font-weight:bold;" % (fg, font_size))
            col.addWidget(lb)
        top.addLayout(col, 1)
        lay.addLayout(top)

        if has_act:
            cd_fg = _THEME_CD.get(theme, "#d35400")
            self._cd_label = QLabel(
                f"⏳ {self._countdown} 秒后自动{ACTION_LABEL.get(action)}", wrap)
            self._cd_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._cd_label.setStyleSheet(
                "background:transparent; color:%s;"
                " font-family:'Microsoft YaHei UI'; font-size:10px;"
                " font-weight:bold;" % cd_fg)
            lay.addWidget(self._cd_label, 0, Qt.AlignRight)
            bb, bd, bf = _THEME_BTN.get(theme, ("#ffffff", "#e8e6e3", "#d35400"))
            btn = QPushButton("取消", wrap)
            btn.setStyleSheet(
                "QPushButton { background:%s; color:%s; border:1px solid %s;"
                " border-radius:8px; padding:5px 22px;"
                " font-family:'Microsoft YaHei UI'; font-size:11px;"
                " font-weight:bold; }"
                "QPushButton:hover { background:%s; }" % (bb, bf, bd, bd))
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self.cancelled.emit)
            lay.addWidget(btn, 0, Qt.AlignRight)
        self.raise_()

    def countdown_left(self):
        return self._countdown

    def tick_countdown(self):
        self._countdown -= 1
        if self._cd_label:
            act = ACTION_LABEL.get(self._action, "操作")
            self._cd_label.setText(f"⏳ {self._countdown} 秒后自动{act}")
        return self._countdown > 0




# --------------------------------------------------------------------------
# 主桌宠窗口
# --------------------------------------------------------------------------
class PetWindow(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle(APP_NAME)

        # ---- 数据与素材 ----
        self._pet = load_saved_pet()
        self._cache = SpriteCache()
        if not self._cache.load_pet(self._pet):
            self._pet = DEFAULT_PET
            self._cache.load_pet(self._pet)
        self._size = max(MIN_PET_SIZE,
                         min(load_saved_size() or DEFAULT_PET_SIZE, MAX_PET_SIZE))
        self._max_size = MAX_PET_SIZE
        self.win_w = self._size + WIN_MARGIN * 2
        self.win_h = self._size + WIN_TOP
        self.setFixedSize(self.win_w, self.win_h)
        self._base_pet_y = self.win_h - self._size // 2 - PET_PAD

        # ---- 状态（须在 _set_pixmap 前初始化） ----
        self.state = "idle"
        self._state_revert = None      # 状态恢复定时器
        self._facing = 1
        self._motion = None            # None / "run" / "walk"
        self._frame_idx = 0
        self._last_frame_t = time.time()
        self._floating = False         # 默认状态无飘动（用户要求）
        self._follow_mode = False
        self._follow_gear = "stop"
        self._dragging = False
        self._drag_off = None
        self._press_xy = None
        self._click_timer = None
        self._suppress_click = False
        self._hidden = False

        # ---- 宠物图 ----
        self._img = QLabel(self)
        self._img.setStyleSheet("background:transparent;")
        self._img.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._place_img()
        self._set_pixmap("idle", 0)

        # ---- 提醒 ----
        self._timers = []
        self._dailies = []
        self._sleep_at = None
        self._sleep_fired_min = None    # 上次触发睡觉的 HH:MM，防同一分钟内重复入睡
        self._notify_from = None
        self._run_active = False
        self._run_cb = None
        self._run_tx = self._run_ty = 0
        self._bubble = None            # ChatBubble
        self._bubble_timer = None
        self._bubble_countdown_timer = None
        self._countdown_action = "none"

        # ---- 粒子 ----
        self._particles = []
        self._last_z = time.time()
        self._last_happy_p = 0

        # ---- 定时器 ----
        self._anim_t = QTimer(self)
        self._anim_t.timeout.connect(self._anim_tick)
        self._anim_t.start(FRAME_MS)
        self._follow_t = QTimer(self)
        self._follow_t.timeout.connect(self._follow_tick)
        self._follow_t.start(FOLLOW_MS)
        self._timer_t = QTimer(self)
        self._timer_t.timeout.connect(self._timer_tick)
        self._timer_t.start(1000)
        self._watchdog_t = QTimer(self)
        self._watchdog_t.timeout.connect(self._watchdog_tick)
        self._watchdog_t.start(WATCHDOG_MS)
        self._last_real = time.time()
        self._last_tick = get_tick64()
        self._random_bubble_t = QTimer(self)
        self._random_bubble_t.timeout.connect(self._random_bubble)
        self._random_bubble_t.start(random.randint(*BUBBLE_INTERVAL))

        # ---- 恢复数据 ----
        self._load_saved_data()
        self._restore_pos()

        # ---- 托盘 ----
        self._build_tray()

    # ================= 数据 =================
    def _load_saved_data(self):
        data = load_data() or {}
        self._timers = timers_from_entries(data.get("reminders", []))
        self._dailies = dailies_from_entries(data.get("dailies", []))
        try:
            sa = str(data.get("sleep_at") or "")
            if ":" in sa:
                hh, mm = sa.split(":")
                self._sleep_at = (int(hh), int(mm))
            else:
                self._sleep_at = None
        except Exception:
            self._sleep_at = None

    def _save_state(self, **extra):
        old = load_data() or {}
        payload = reminders_payload(self._timers, self._dailies,
                                    size=self._size, pet=self._pet,
                                    pos={"x": self.x(), "y": self.y()})
        payload["sleep_at"] = old.get("sleep_at")
        payload.update(extra)
        save_data(payload)

    def _restore_pos(self):
        p = load_saved_pos()
        if p:
            x, y = clamp_to_screen(p[0], p[1], self.win_w, self.win_h)
            self.move(x, y)

    # ================= 精灵 =================
    def _place_img(self):
        """把宠物 QLabel 定位在窗口底部中央（_base_pet_y 为宠物中心）"""
        x = (self.win_w - self._size) // 2
        y = self._base_pet_y - self._size // 2
        self._img_base = (x, y)
        self._img.setGeometry(x, y, self._size, self._size)

    def _set_pixmap(self, base, frame_idx=0):
        """显示一帧：base 为状态图或运动帧名；朝向镜像由缓存层处理"""
        if self._motion:
            frames = RUN_FRAMES if self._motion == "run" else WALK_FRAMES
            base = frames[frame_idx % len(frames)]
        pm = self._cache.frame(self._pet, base, self._facing, self._size)
        if pm is None:
            return
        self._img.setPixmap(pm)

    # ================= 状态 =================
    def set_state(self, name, revert_ms=None):
        self.state = name
        if self._motion is None:
            self._set_pixmap(name)
        if revert_ms:
            if self._state_revert:
                self._state_revert.stop()
            else:
                self._state_revert = QTimer(self)
                self._state_revert.setSingleShot(True)
                self._state_revert.timeout.connect(
                    lambda: self.set_state("idle"))
            self._state_revert.start(revert_ms)

    # ================= 动画循环 =================
    def _anim_tick(self):
        now = time.time()
        if self._run_active:
            return
        if self._dragging:
            return
        if self._motion is not None:
            # 移动帧推进由运动循环负责（_follow_tick/_run_loop）
            pass
        elif self.state == "happy":
            hop = HOP_HEIGHT * abs(math.sin(now * math.pi * 2 / (HOP_MS / 1000.0)))
            self._img.move(self._img_base[0], self._img_base[1] - int(hop))
        else:
            self._img.move(self._img_base[0], self._img_base[1])
        # 粒子
        if self.state == "sleep" and now - self._last_z > SLEEP_Z_MS / 1000.0:
            self._last_z = now
            self._spawn_particle("💤", self._size * 0.15, self._size * 0.05,
                                 random.uniform(-0.5, 0.5), -0.8, 1600)
        if self.state == "happy" and now - self._last_happy_p > 400 / 1000.0:
            self._last_happy_p = now
            for _ in range(HAPPY_PARTICLES):
                self._spawn_particle(random.choice(["🧡", "💛", "✨"]),
                                     random.uniform(0.3, 0.7) * self._size,
                                     self._size * 0.3,
                                     random.uniform(-0.6, 0.6),
                                     random.uniform(-1.6, -0.6), 1500)
        self._particles = [pt for pt in self._particles if pt.tick(now)]

    def _spawn_particle(self, text, x, y, dx, dy, life):
        pt = Particle(self, text, x, y, dx, dy, life)
        self._particles.append(pt)

    # ================= 拖拽 / 点击 =================
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press_xy = (ev.globalPos().x(), ev.globalPos().y())
            self._drag_off = (ev.globalPos().x() - self.x(),
                              ev.globalPos().y() - self.y())
            self._dragging = True
            if self._click_timer:
                self._click_timer.stop()
        elif ev.button() == Qt.RightButton:
            self._popup_menu(ev.globalPos())

    def mouseMoveEvent(self, ev):
        if self._dragging and self._drag_off:
            x = ev.globalPos().x() - self._drag_off[0]
            y = ev.globalPos().y() - self._drag_off[1]
            self.move(x, y)

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        was_dragging = self._dragging
        self._dragging = False
        moved = 0
        if self._press_xy:
            moved = (abs(ev.globalPos().x() - self._press_xy[0])
                     + abs(ev.globalPos().y() - self._press_xy[1]))
        self._press_xy = None
        self._drag_off = None
        if was_dragging and moved > MOVE_THRESHOLD:
            self._save_state()   # 记住新位置
            return
        if self._suppress_click:
            self._suppress_click = False
            return
        # 双击判定：先延迟
        if self._click_timer is None:
            self._click_timer = QTimer(self)
            self._click_timer.setSingleShot(True)
            self._click_timer.timeout.connect(self._single_click)
        # 判定窗口 >= 系统双击间隔：双击永远先于单击反应判定，消除连击感
        self._click_timer.start(QApplication.doubleClickInterval() + 50)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            if self._click_timer:
                self._click_timer.stop()
            self._suppress_click = True
            self.set_state("happy", REACT_MS)
            self.show_bubble(pick_pet_msg(self._pet, "happy"))

    def _single_click(self):
        name = random.choice(["surprise", "happy"])
        self.set_state(name, REACT_MS)
        self.show_bubble(pick_pet_msg(self._pet, name))

    # ================= 右键菜单 =================
    def _popup_menu(self, gpos):
        m = QMenu(self)
        m.setStyleSheet(self._menu_qss())
        # 显示/隐藏
        act_vis = m.addAction("🙈 隐藏桌宠" if not self._hidden else "👀 显示桌宠")
        act_vis.triggered.connect(self._toggle_visible)
        m.addSeparator()
        # 形象
        pet_menu = m.addMenu("🎭 选择形象")
        pet_grp = None
        from PyQt5.QtWidgets import QActionGroup
        pet_grp = QActionGroup(m)
        for key, label in PETS:
            a = pet_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(key == self._pet)
            pet_grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self._set_pet(k))
        # 大小
        size_menu = m.addMenu("📏 大小")
        a_big = size_menu.addAction("增大（+50）")
        a_big.triggered.connect(lambda: self.set_size(self._size + SIZE_STEP))
        a_small = size_menu.addAction("减小（-50）")
        a_small.triggered.connect(lambda: self.set_size(self._size - SIZE_STEP))
        size_menu.addSeparator()
        for _s in range(MIN_PET_SIZE, self._max_size + 1, SIZE_STEP):
            _a = size_menu.addAction(f"{_s}px")
            _a.setCheckable(True)
            _a.setChecked(_s == self._size)
            _a.triggered.connect(lambda _=False, v=_s: self.set_size(v))
        if (self._max_size - MIN_PET_SIZE) % SIZE_STEP:
            _a = size_menu.addAction(f"{self._max_size}px")
            _a.setCheckable(True)
            _a.setChecked(self._max_size == self._size)
            _a.triggered.connect(lambda _=False,
                                 v=self._max_size: self.set_size(v))
        m.addSeparator()
        # 跟随
        act_follow = m.addAction("🖱️ 跟随鼠标")
        act_follow.setCheckable(True)
        act_follow.setChecked(self._follow_mode)
        act_follow.triggered.connect(self.set_follow)
        a_msg = m.addAction("💬 提示语设置…")
        a_msg.triggered.connect(self._open_msg_dialog)
        # 定时提醒子菜单（含已设提醒列表，可点击取消）
        rem_menu = m.addMenu("⏰ 定时提醒")
        a_add = rem_menu.addAction("➕ 添加提醒…")
        a_add.triggered.connect(self._open_reminder_dialog)
        if self._timers:
            rem_menu.addSeparator()
            for t in list(self._timers):
                left = int(t["due"] - time.time())
                if t.get("repeat_min"):
                    lbl = (f"取消：{t['msg'][:10]}"
                           f"（每 {t['repeat_min']} 分钟，下次 {fmt_remaining(left)}）")
                else:
                    lbl = f"取消：{t['msg'][:10]}（剩 {fmt_remaining(left)}）"
                a = rem_menu.addAction(lbl)
                a.triggered.connect(lambda _=False, tt=t: self._cancel_reminder(tt))
        # 每日提醒子菜单（含已设提醒列表，可点击取消）
        daily_menu = m.addMenu("🔔 每日提醒")
        a_dadd = daily_menu.addAction("➕ 设置每日提醒…")
        a_dadd.triggered.connect(self._open_daily_dialog)
        if self._dailies:
            daily_menu.addSeparator()
            for d in list(self._dailies):
                act = d.get("action") or "none"
                if act not in (None, "", "none"):
                    mark = (f"{ACTION_LABEL.get(act, '')} "
                            f"{int(d.get('countdown') or SLEEP_COUNTDOWN_S)}s ")
                else:
                    mark = ""
                lbl = (f"取消：{mark}{d['msg'][:10]}"
                       f"（每天 {d['hour']:02d}:{d['minute']:02d}）")
                a = daily_menu.addAction(lbl)
                a.triggered.connect(lambda _=False, dd=d: self._cancel_daily(dd))
        # 定时睡觉子菜单
        sleep_menu = m.addMenu("😴 定时睡觉")
        a_sadd = sleep_menu.addAction("➕ 设置睡觉时间…")
        a_sadd.triggered.connect(self._open_sleep_dialog)
        if self._sleep_at:
            sleep_menu.addSeparator()
            a_s = sleep_menu.addAction("取消睡觉计划")
            a_s.triggered.connect(self._cancel_sleep_plan)
        m.addSeparator()
        # 开机自启
        act_auto = m.addAction("🚀 开机自启")
        act_auto.setCheckable(True)
        act_auto.setChecked(is_autostart_enabled())
        act_auto.triggered.connect(set_autostart)
        m.addSeparator()
        act_quit = m.addAction("❌ 退出")
        act_quit.triggered.connect(self.quit_app)
        m.exec_(gpos)

    def _menu_qss(self):
        return f"""
        QMenu {{ background:#ffffff; border:1px solid #eee0d0; border-radius:8px;
                  padding:6px; font-family:'Microsoft YaHei UI'; font-size:12px; color:{UI_FG}; }}
        QMenu::item {{ padding:6px 22px 6px 12px; border-radius:6px; }}
        QMenu::item:selected {{ background:{UI_MENU_HI}; color:{UI_ACCENT_HI}; }}
        QMenu::separator {{ height:1px; background:#f2e8dc; margin:4px 8px; }}
        QMenu::indicator {{ width:14px; height:14px; }}
        """

    def _toggle_visible(self):
        if self._hidden:
            self._hidden = False
            self.show()
        else:
            self._hidden = True
            self.hide()

    # ================= 形象切换 =================
    def _set_pet(self, pet):
        if pet == self._pet:
            return
        if not self._cache.load_pet(pet):
            self.show_bubble("形象素材不存在", 1800)
            return
        self._cache.release_pet(self._pet)
        self._pet = pet
        self._set_pixmap(self.state if self._motion is None else
                         (RUN_FRAMES if self._motion == "run" else WALK_FRAMES)[0],
                         self._frame_idx)
        self._save_state()
        self._update_tray_icon()
        self.show_bubble(f"已切换为{PET_LABEL.get(pet, pet)}", 2000)

    # ================= 大小 =================
    def set_size(self, size):
        size = max(MIN_PET_SIZE, min(self._max_size, int(size)))
        if size == self._size:
            self.show_bubble(f"已是{'最大' if size >= self._max_size else '最小'}尺寸", 1200)
            return
        bx = self.x() + self.win_w // 2
        by = self.y() + self.win_h
        self._size = size
        self.win_w = size + WIN_MARGIN * 2
        self.win_h = size + WIN_TOP
        self.setFixedSize(self.win_w, self.win_h)
        self._base_pet_y = self.win_h - size // 2 - PET_PAD
        self._place_img()
        self._set_pixmap(self.state if self._motion is None else
                         (RUN_FRAMES if self._motion == "run" else WALK_FRAMES)[0],
                         self._frame_idx)
        nx = bx - self.win_w // 2
        ny = by - self.win_h
        nx, ny = clamp_to_screen(nx, ny, self.win_w, self.win_h)
        self.move(nx, ny)
        self._save_state()
        self.show_bubble(f"大小：{size}px", 1200)

    # ================= 运动（跟随鼠标） =================
    def set_follow(self, enabled):
        self._follow_mode = bool(enabled)
        if self._follow_mode:
            self._floating = False
            self._follow_gear = "stop"

    def _follow_tick(self):
        if not self._follow_mode or self._dragging or self._run_active:
            return
        pos = QCursor.pos()
        cx, cy = pos.x(), pos.y()
        px, py = self.x(), self.y()
        dx, dy = cx - (px + self.win_w // 2), cy - (py + self.win_h // 2)
        dist = (dx * dx + dy * dy) ** 0.5
        in_window = (px <= cx <= px + self.win_w and
                     py <= cy <= py + self.win_h)
        if self._follow_gear == "stop":
            if not in_window and dist > FOLLOW_STOP_DIST + FOLLOW_STOP_HYST:
                gear = "run" if dist > FOLLOW_WALK_DIST + FOLLOW_HYST else "walk"
            else:
                gear = "stop"
        else:
            if in_window or dist <= FOLLOW_STOP_DIST:
                gear = "stop"
            elif self._follow_gear == "run":
                gear = "walk" if dist <= FOLLOW_WALK_DIST - FOLLOW_HYST else "run"
            else:
                gear = "run" if dist > FOLLOW_WALK_DIST + FOLLOW_HYST else "walk"
        if gear == "stop":
            if self._motion is not None:
                self._stop_motion()
        else:
            self._set_facing(dx)
            if self._motion != ("run" if gear == "run" else "walk"):
                self._start_motion("run" if gear == "run" else "walk")
            self._tick_motion_frame()
            step = FOLLOW_RUN_STEP if gear == "run" else FOLLOW_WALK_STEP
            nx = int(px + dx / dist * step)
            ny = int(py + dy / dist * step)
            sw, sh = QApplication.primaryScreen().availableGeometry().width(), \
                     QApplication.primaryScreen().availableGeometry().height()
            nx = max(0, min(nx, sw - self.win_w))
            ny = max(0, min(ny, sh - self.win_h))
            self.move(nx, ny)
        self._follow_gear = gear

    def _start_motion(self, mode):
        self._motion = mode
        self._frame_idx = 0
        self._last_frame_t = time.time()
        self._set_pixmap(self.state, self._frame_idx)

    def _stop_motion(self):
        self._motion = None
        self._set_pixmap(self.state)

    def _tick_motion_frame(self):
        if self._motion is None:
            return
        now = time.time()
        gap = (FRAME_CHASE_MS if self._motion == "run" else FRAME_WALK_MS) / 1000.0
        if now - self._last_frame_t >= gap:
            frames = RUN_FRAMES if self._motion == "run" else WALK_FRAMES
            self._frame_idx = (self._frame_idx + 1) % len(frames)
            self._last_frame_t = now
            self._set_pixmap(frames[self._frame_idx], self._frame_idx)

    def _set_facing(self, target_x):
        if abs(target_x) < 12:
            return
        f = 1 if target_x > 0 else -1
        if f != self._facing:
            self._facing = f
            if self._motion is not None:
                self._set_pixmap(self.state, self._frame_idx)
            else:
                self._set_pixmap(self.state)

    # ================= 跑动（提醒到点/回家） =================
    def _run_to(self, tx, ty, cb=None):
        tx = max(0, min(int(tx), self.screen().availableGeometry().width() - self.win_w))
        ty = max(0, min(int(ty), self.screen().availableGeometry().height() - self.win_h))
        self._run_tx, self._run_ty = tx, ty
        self._run_cb = cb
        self._run_active = True
        if self._follow_mode:
            self.set_follow(False)
        self._start_motion("run")
        self._run_tick()

    def _run_tick(self):
        if not self._run_active:
            return
        px, py = self.x(), self.y()
        dx, dy = self._run_tx - px, self._run_ty - py
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= FOLLOW_RUN_STEP:
            self.move(self._run_tx, self._run_ty)
            self._run_active = False
            self._stop_motion()
            cb = self._run_cb
            self._run_cb = None
            if cb:
                cb()
            return
        self._set_facing(dx)
        self._tick_motion_frame()
        nx = int(px + dx / dist * FOLLOW_RUN_STEP)
        ny = int(py + dy / dist * FOLLOW_RUN_STEP)
        ag = self.screen().availableGeometry()
        nx = max(0, min(nx, ag.width() - self.win_w))
        ny = max(0, min(ny, ag.height() - self.win_h))
        self.move(nx, ny)
        QTimer.singleShot(FRAME_MS, self._run_tick)

    # ================= 提醒触发 =================
    def _notify_cat(self, msg, action="none", countdown=SLEEP_COUNTDOWN_S):
        self._clear_bubble()
        if self._follow_mode:
            self.set_follow(False)
        if self.state == "sleep":
            self.set_state("idle")
        try:
            ctypes.windll.kernel32.Beep(880, 220)
            ctypes.windll.kernel32.Beep(660, 220)
        except Exception:
            pass
        ag = self.screen().availableGeometry()
        tx = max(0, (ag.width() - self.win_w) // 2)
        ty = max(0, (ag.height() - self.win_h) // 2)
        if self._dragging:
            self._notify_from = None
            self._show_bubble(msg, action, countdown)
            return
        self._notify_from = (self.x(), self.y())
        self._run_to(tx, ty, lambda: self._show_bubble(msg, action, countdown))

    def _return_home(self):
        if self._notify_from:
            fx, fy = self._notify_from
            self._notify_from = None
            self._run_to(fx, fy)

    def _fire_reminder(self, msg):
        self._notify_cat(msg)

    def _fire_daily(self, d):
        self._notify_cat(d["msg"], d.get("action", "none"),
                         d.get("countdown", SLEEP_COUNTDOWN_S))

    # ================= 气泡 =================
    def _show_bubble(self, msg, action="none", countdown=SLEEP_COUNTDOWN_S):
        self._clear_bubble()
        theme = pick_theme(msg, action)
        icon = pick_icon(msg, action)
        b = ChatBubble(msg, action, countdown, theme, icon)
        self._bubble = b
        self._countdown_action = action
        # 定位：宠物正上方居中，尾巴（底图正下）正对宠物；上方放不下则下方
        ag = QApplication.primaryScreen().availableGeometry()
        wx, wy = self.x(), self.y()
        cw, ch = b.width(), b.height()
        pet_top = wy + self._base_pet_y - self._size // 2 - 6
        bx = wx + self.win_w // 2 - cw // 2
        by = pet_top - ch
        if by < ag.top():
            by = wy + self._base_pet_y + self._size // 2 + 6
        bx = max(0, min(bx, ag.width() - cw))
        by = max(0, min(by, ag.height() - ch))
        b.move(bx, by)
        b.show()
        b.raise_()
        b.cancelled.connect(self._cancel_daily_action)
        if action not in (None, "", "none"):
            b.countdown_finished.connect(self._do_action_now)
            self._bubble_timer = QTimer(self)
            self._bubble_timer.timeout.connect(self._bubble_countdown_tick)
            self._bubble_timer.start(1000)
        else:
            self._bubble_timer = QTimer(self)
            self._bubble_timer.setSingleShot(True)
            self._bubble_timer.timeout.connect(self._bubble_timeout)
            self._bubble_timer.start(CHAT_BUBBLE_MS)

    def _bubble_countdown_tick(self):
        if self._bubble and self._bubble.tick_countdown():
            return
        # 倒计时结束
        self._clear_bubble()
        self._do_action_now()

    def _do_action_now(self):
        act = self._countdown_action
        self._clear_bubble()
        do_system_action(act)
        self._return_home()

    def _bubble_timeout(self):
        self._clear_bubble()
        self._return_home()

    def _cancel_daily_action(self):
        self._clear_bubble()
        self._return_home()
        self.show_bubble("已取消，电脑不会执行该操作", 2200)

    def _cancel_reminder(self, r):
        if r in self._timers:
            self._timers.remove(r)
        self._save_state()
        self.show_bubble("已取消提醒：" + r["msg"], 1800)

    def _cancel_daily(self, d):
        if d in self._dailies:
            self._dailies.remove(d)
        self._save_state()
        self.show_bubble("已取消每日提醒：" + d["msg"], 1800)

    def _clear_bubble(self):
        if self._bubble:
            try:
                self._bubble.hide()
                self._bubble.deleteLater()
            except Exception:
                pass
            self._bubble = None
        if self._bubble_timer:
            self._bubble_timer.stop()
            self._bubble_timer = None

    # ================= 小气泡（头顶提示） =================
    def show_bubble(self, text, ms=BUBBLE_SHOW_MS):
        self._clear_top_bubble()
        b = TopBubble(self, text)
        b.show()
        self._top_bubble = b
        self._top_timer = QTimer(self)
        self._top_timer.setSingleShot(True)
        self._top_timer.timeout.connect(self._clear_top_bubble)
        self._top_timer.start(ms)

    def _clear_top_bubble(self):
        if getattr(self, "_top_bubble", None):
            try:
                self._top_bubble.hide()
                self._top_bubble.deleteLater()
            except Exception:
                pass
            self._top_bubble = None
        if getattr(self, "_top_timer", None):
            self._top_timer.stop()
            self._top_timer = None

    # ================= 定时睡觉 =================
    def schedule_sleep(self, hour, minute):
        self._sleep_at = (hour, minute)
        self._sleep_fired_min = None   # 新计划立即可生效
        self._save_state(sleep_at=f"{hour:02d}:{minute:02d}")
        self.show_bubble(f"已设置：每天 {hour:02d}:{minute:02d} 睡觉", 3000)

    # ================= 设置对话框入口 =================
    def _open_reminder_dialog(self):
        d = ReminderDialog(self)
        d.exec_()

    def _open_daily_dialog(self):
        d = DailyDialog(self)
        d.exec_()

    def _open_sleep_dialog(self):
        d = SleepDialog(self)
        d.exec_()

    def _open_msg_dialog(self):
        d = MsgDialog(self)
        d.exec_()

    # ================= 定时提醒 =================
    def _timer_tick(self):
        fired_r, fired_d, changed = check_reminders(self._timers, self._dailies)
        for msg in fired_r:
            self._fire_reminder(msg)
        for d in fired_d:
            self._fire_daily(d)
        if changed:
            self._save_state()
        # 定时睡觉检查（同一分钟内只触发一次，被点击叫醒后不会马上又睡）
        if getattr(self, "_sleep_at", None):
            lt = time.localtime()
            key = f"{lt.tm_hour:02d}:{lt.tm_min:02d}"
            if ((lt.tm_hour, lt.tm_min) == self._sleep_at
                    and key != getattr(self, "_sleep_fired_min", None)):
                self._sleep_fired_min = key
                self.set_state("sleep", 0)
                self.show_bubble("到点啦，睡觉觉～（点我一下叫醒）", 3200)

    def _cancel_sleep_plan(self):
        self._sleep_at = None
        self._sleep_fired_min = None
        self._save_state(sleep_at="")
        self.show_bubble("已取消睡觉计划", 1800)

    def add_reminder(self, secs, msg, repeat_min=None):
        self._timers.append({"due": time.time() + secs, "msg": msg,
                             "repeat_min": repeat_min})
        self._save_state()
        self.set_state("happy", 2000)
        if repeat_min:
            self.show_bubble(f"已设提醒：{msg}（每 {repeat_min} 分钟重复）", 3000)
        else:
            self.show_bubble(f"已设提醒：{msg}（{fmt_remaining(secs)}后）", 3000)

    def add_daily(self, hour, minute, msg, action="none",
                  countdown=SLEEP_COUNTDOWN_S):
        self._dailies.append({"hour": hour, "minute": minute, "msg": msg,
                              "last": "", "action": action,
                              "countdown": int(countdown)})
        self._save_state()
        self.set_state("happy", 2000)
        act = ACTION_LABEL.get(action, "无操作")
        self.show_bubble(f"已设每日提醒：{msg}（每天 {hour:02d}:{minute:02d}）", 3200)

    # ================= 随机待机气泡 =================
    def _random_bubble(self):
        if self.state != "idle" or self._follow_mode or self._hidden:
            self._random_bubble_t.start(random.randint(*BUBBLE_INTERVAL))
            return
        self.show_bubble(pick_pet_msg(self._pet, "idle"), 2200)
        self._random_bubble_t.start(random.randint(*BUBBLE_INTERVAL))

    # ================= 看门狗（睡眠恢复） =================
    def _watchdog_tick(self):
        now = time.time()
        tick = get_tick64()
        if detect_resume(self._last_real, self._last_tick, now, tick):
            self._restore_window(resumed=True)
        else:
            # 窗口丢失置顶/映射时自愈（睡眠恢复后系统可能改变窗口状态）
            if not self._hidden:
                if not self.isVisible():
                    self.show()
                if not self.windowFlags() & Qt.WindowStaysOnTopHint:
                    self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                    self.show()
        self._last_real = now
        self._last_tick = tick

    def _restore_window(self, resumed=False):
        if self._hidden:
            self._hidden = False
        self.show()
        self.raise_()
        if resumed:
            self.show_bubble("电脑醒啦，我还在哦！", 2500)

    # ================= 系统托盘 =================
    def _build_tray(self):
        self._tray = QSystemTrayIcon(self)
        self._update_tray_icon()
        menu = QMenu()
        menu.setStyleSheet(self._menu_qss())
        act_show = menu.addAction("👀 显示/隐藏桌宠")
        act_show.triggered.connect(self._toggle_visible)
        menu.addSeparator()
        act_follow = menu.addAction("🖱️ 跟随鼠标")
        act_follow.setCheckable(True)
        act_follow.setChecked(self._follow_mode)
        act_follow.triggered.connect(self.set_follow)
        a_msg = menu.addAction("💬 提示语设置…")
        a_msg.triggered.connect(self._open_msg_dialog)
        menu.addSeparator()
        pet_menu = menu.addMenu("🎭 选择形象")
        from PyQt5.QtWidgets import QActionGroup
        grp = QActionGroup(menu)
        for key, label in PETS:
            a = pet_menu.addAction(label)
            a.setCheckable(True)
            a.setChecked(key == self._pet)
            grp.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self._set_pet(k))
        size_menu = menu.addMenu("📏 大小")
        a1 = size_menu.addAction("增大（+50）")
        a1.triggered.connect(lambda: self.set_size(self._size + SIZE_STEP))
        a2 = size_menu.addAction("减小（-50）")
        a2.triggered.connect(lambda: self.set_size(self._size - SIZE_STEP))
        size_menu.addSeparator()
        for _s in range(MIN_PET_SIZE, self._max_size + 1, SIZE_STEP):
            _a = size_menu.addAction(f"{_s}px")
            _a.setCheckable(True)
            _a.setChecked(_s == self._size)
            _a.triggered.connect(lambda _=False, v=_s: self.set_size(v))
        if (self._max_size - MIN_PET_SIZE) % SIZE_STEP:
            _a = size_menu.addAction(f"{self._max_size}px")
            _a.setCheckable(True)
            _a.setChecked(self._max_size == self._size)
            _a.triggered.connect(lambda _=False,
                                 v=self._max_size: self.set_size(v))
        menu.addSeparator()
        rem_menu = menu.addMenu("⏰ 定时提醒")
        a_add = rem_menu.addAction("➕ 添加提醒…")
        a_add.triggered.connect(self._open_reminder_dialog)
        if self._timers:
            rem_menu.addSeparator()
            for t in list(self._timers):
                left = int(t["due"] - time.time())
                if t.get("repeat_min"):
                    lbl = (f"取消：{t['msg'][:10]}"
                           f"（每 {t['repeat_min']} 分钟，下次 {fmt_remaining(left)}）")
                else:
                    lbl = f"取消：{t['msg'][:10]}（剩 {fmt_remaining(left)}）"
                a = rem_menu.addAction(lbl)
                a.triggered.connect(lambda _=False, tt=t: self._cancel_reminder(tt))
        daily_menu = menu.addMenu("🔔 每日提醒")
        a_dadd = daily_menu.addAction("➕ 设置每日提醒…")
        a_dadd.triggered.connect(self._open_daily_dialog)
        if self._dailies:
            daily_menu.addSeparator()
            for d in list(self._dailies):
                act = d.get("action") or "none"
                if act not in (None, "", "none"):
                    mark = (f"{ACTION_LABEL.get(act, '')} "
                            f"{int(d.get('countdown') or SLEEP_COUNTDOWN_S)}s ")
                else:
                    mark = ""
                lbl = (f"取消：{mark}{d['msg'][:10]}"
                       f"（每天 {d['hour']:02d}:{d['minute']:02d}）")
                a = daily_menu.addAction(lbl)
                a.triggered.connect(lambda _=False, dd=d: self._cancel_daily(dd))
        sleep_menu = menu.addMenu("😴 定时睡觉")
        a_sadd = sleep_menu.addAction("➕ 设置睡觉时间…")
        a_sadd.triggered.connect(self._open_sleep_dialog)
        if self._sleep_at:
            sleep_menu.addSeparator()
            a_s = sleep_menu.addAction("取消睡觉计划")
            a_s.triggered.connect(self._cancel_sleep_plan)
        menu.addSeparator()
        a_auto = menu.addAction("🚀 开机自启")
        a_auto.setCheckable(True)
        a_auto.setChecked(is_autostart_enabled())
        a_auto.triggered.connect(set_autostart)
        menu.addSeparator()
        a_quit = menu.addAction("❌ 退出")
        a_quit.triggered.connect(self.quit_app)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _update_tray_icon(self):
        pm = self._cache.any_frame(self._pet, 64)
        self._tray.setIcon(QIcon(pm))

    def _on_tray_activated(self, reason):
        # 单击切换显示/隐藏（类似微信）；双击不做任何事，避免连点
        if reason == QSystemTrayIcon.Trigger:
            self._toggle_visible()

    # ================= 退出 =================
    def quit_app(self):
        self._save_state()
        self._tray.hide()
        QApplication.quit()


# --------------------------------------------------------------------------
# 头顶小气泡（提示文本，跟随宠物窗口）
# --------------------------------------------------------------------------
class TopBubble(QLabel):
    def __init__(self, pet_win, text):
        super().__init__(pet_win)
        self.setStyleSheet(f"""
            background:#ffffff; color:#333333; border:1px solid #eee0d0;
            border-radius:10px; padding:6px 12px;
            font-family:'Microsoft YaHei UI'; font-size:11px; """)
        self.setText(text)
        # 长文本换行显示，且不超出宠物窗口宽度（避免内容被裁切）
        fm = QFontMetrics(self.font())
        max_w = min(300, pet_win.width() - 16)
        w = min(max_w, fm.horizontalAdvance(text) + 24)
        self.setFixedWidth(w)
        self.setWordWrap(True)
        self.adjustSize()
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        # 定位在宠物头顶正上方（宠物图片顶部为 _base_pet_y - size//2）
        pet_top = pet_win._base_pet_y - pet_win._size // 2
        y = pet_top - 4 - self.height()
        y = max(4, y)
        x = (pet_win.width() - self.width()) // 2
        self.move(x, y)
        self.raise_()


# --------------------------------------------------------------------------
# 轮询勾选图（橙色底 + 白色 √）
CHECK_IMG = os.path.join(SPRITE_DIR, "ui_check.png").replace("\\", "/")

# 设置对话框基类（暖橙主题 + 圆角 + 阴影）
# --------------------------------------------------------------------------
DIALOG_QSS = f"""
QDialog {{ background:{UI_BG}; border-radius:14px; }}
QLabel {{ color:{UI_FG}; font-family:'Microsoft YaHei UI'; font-size:12px;
         background:transparent; }}
QLabel#sub {{ color:{UI_SUB}; font-size:11px; }}
QLabel#err {{ color:{UI_ERR}; font-size:11px; }}
QLabel#title {{ font-size:15px; font-weight:bold; color:{UI_FG}; }}
QLineEdit {{ background:#ffffff; border:1px solid {UI_INPUT_BD}; border-radius:8px;
             padding:7px 10px; color:{UI_FG}; font-family:'Microsoft YaHei UI';
             font-size:12px; selection-background-color:{UI_ACCENT}; }}
QLineEdit:focus {{ border:1px solid {UI_ACCENT}; }}
QComboBox {{ background:#ffffff; border:1px solid {UI_INPUT_BD}; border-radius:8px;
             padding:6px 10px; color:{UI_FG}; font-family:'Microsoft YaHei UI';
             font-size:12px; }}
QComboBox:focus {{ border:1px solid {UI_ACCENT}; }}
QComboBox QAbstractItemView {{ background:#ffffff; border:1px solid {UI_INPUT_BD};
             border-radius:6px; selection-background-color:{UI_MENU_HI};
             selection-color:{UI_ACCENT_HI}; color:{UI_FG}; }}
QPushButton {{ background:{UI_ACCENT}; color:#ffffff; border:none; border-radius:8px;
               padding:8px 26px; font-family:'Microsoft YaHei UI'; font-size:12px;
               font-weight:bold; }}
QPushButton:hover {{ background:{UI_ACCENT_HI}; }}
QPushButton#secondary {{ background:#ffffff; color:{UI_FG}; border:1px solid {UI_INPUT_BD}; }}
QPushButton#secondary:hover {{ background:{UI_BG2}; }}
QCheckBox {{ color:{UI_FG}; font-family:'Microsoft YaHei UI'; font-size:12px;
             background:transparent; spacing:8px; }}
QCheckBox::indicator {{ width:17px; height:17px; border-radius:5px;
             border:1px solid {UI_INPUT_BD}; background:#ffffff; }}
QCheckBox::indicator:checked {{ background:{UI_ACCENT}; border:1px solid {UI_ACCENT};
             image:url({CHECK_IMG}); }}
"""


class BaseDialog(QDialog):
    def __init__(self, title):
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(DIALOG_QSS)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(10)
        t = QLabel(title)
        t.setObjectName("title")
        lay.addWidget(t)
        self._lay = lay
        self._err = None

    def _row(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        self._lay.addLayout(row)
        return row

    def _label(self, text, sub=False, err=False):
        lb = QLabel(text)
        if err:
            lb.setObjectName("err")
        elif sub:
            lb.setObjectName("sub")
        return lb

    def _btn_row(self, ok_cb, cancel_cb=None):
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("确定")
        ok.clicked.connect(ok_cb)
        row.addWidget(ok)
        if cancel_cb is not None:
            ca = QPushButton("取消")
            ca.setObjectName("secondary")
            ca.clicked.connect(cancel_cb)
            row.addWidget(ca)
        self._lay.addLayout(row)
        return ok

    def _err_label(self):
        lb = QLabel("")
        lb.setObjectName("err")
        self._lay.addWidget(lb)
        self._err = lb
        return lb

    def _set_err(self, text):
        if self._err:
            self._err.setText(text)

    def _center(self):
        ag = QApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(ag.center().x() - self.width() // 2,
                  ag.center().y() - self.height() // 2)


# --------------------------------------------------------------------------
# 定时提醒对话框
# --------------------------------------------------------------------------
class ReminderDialog(BaseDialog):
    def __init__(self, pet_win):
        super().__init__("⏰ 定时提醒")
        self._pet = pet_win
        r0 = self._row()
        r0.addWidget(self._label("提醒时间："))
        self._time_edit = QLineEdit()
        self._time_edit.setFixedWidth(90)
        self._time_edit.setPlaceholderText("如 30 / 14:30")
        r0.addWidget(self._time_edit)
        r0.addWidget(self._label("输入分钟数，或时刻如 14:30", sub=True))
        r0.addStretch(1)

        self._repeat_chk = QCheckBox("开启轮询：每隔相同分钟数重复提醒")
        self._lay.addWidget(self._repeat_chk)

        r1 = self._row()
        r1.addWidget(self._label("提醒内容："))
        self._msg_edit = QLineEdit()
        self._msg_edit.setText("该休息一下啦！")
        r1.addWidget(self._msg_edit, 1)

        self._err_label()
        ok = self._btn_row(self._do_ok, self.reject)
        ok.setDefault(True)
        self._time_edit.textChanged.connect(self._on_time_changed)
        self._on_time_changed()
        self._center()
        self._time_edit.setFocus()

    def _on_time_changed(self):
        txt = self._time_edit.text().strip()
        ok = False
        if txt and ":" not in txt:
            try:
                v = float(txt)
                ok = v > 0 and v.is_integer()
            except ValueError:
                ok = False
        self._repeat_chk.setEnabled(ok)
        if not ok:
            self._repeat_chk.setChecked(False)

    def _do_ok(self):
        secs, err = parse_reminder(self._time_edit.text())
        if err:
            self._set_err(err)
            return
        msg = self._msg_edit.text().strip() or "时间到啦！"
        repeat_min = None
        if self._repeat_chk.isChecked():
            try:
                repeat_min = int(float(self._time_edit.text().strip()))
            except ValueError:
                repeat_min = None
        self._pet.add_reminder(secs, msg, repeat_min)
        self.accept()


# --------------------------------------------------------------------------
# 每日提醒对话框
# --------------------------------------------------------------------------
class DailyDialog(BaseDialog):
    def __init__(self, pet_win):
        super().__init__("🔔 每日提醒")
        self._pet = pet_win
        r0 = self._row()
        r0.addWidget(self._label("提醒时间："))
        self._time_edit = QLineEdit()
        self._time_edit.setFixedWidth(90)
        self._time_edit.setPlaceholderText("如 08:30")
        r0.addWidget(self._time_edit)
        r0.addWidget(self._label("每天这个时间提醒", sub=True))
        r0.addStretch(1)

        r1 = self._row()
        r1.addWidget(self._label("提醒内容："))
        self._msg_edit = QLineEdit()
        self._msg_edit.setText("该休息一下啦！")
        r1.addWidget(self._msg_edit, 1)

        r2 = self._row()
        r2.addWidget(self._label("到点后动作："))
        self._act_combo = QComboBox()
        self._act_combo.addItems([lbl for _, lbl in DAILY_ACTIONS])
        r2.addWidget(self._act_combo)
        r2.addStretch(1)

        r3 = self._row()
        r3.addWidget(self._label("倒计时(秒)："))
        self._cd_edit = QLineEdit()
        self._cd_edit.setFixedWidth(70)
        self._cd_edit.setText(str(SLEEP_COUNTDOWN_S))
        r3.addWidget(self._cd_edit)
        r3.addWidget(self._label("选锁屏/睡眠/关机后生效", sub=True))
        r3.addStretch(1)

        self._err_label()
        ok = self._btn_row(self._do_ok, self.reject)
        ok.setDefault(True)
        self._act_combo.currentTextChanged.connect(self._on_action_changed)
        self._on_action_changed()
        self._center()
        self._time_edit.setFocus()

    def _on_action_changed(self):
        en = self._act_combo.currentText() != "无操作"
        self._cd_edit.setEnabled(en)

    def _do_ok(self):
        clock, err = parse_clock(self._time_edit.text())
        if err:
            self._set_err(err)
            return
        msg = self._msg_edit.text().strip() or "时间到啦！"
        act = ACTION_KEY.get(self._act_combo.currentText(), "none")
        cd = SLEEP_COUNTDOWN_S
        if act != "none":
            try:
                cd = int(self._cd_edit.text().strip())
                if cd < 1:
                    cd = 1
            except ValueError:
                self._set_err("倒计时必须是正整数秒")
                return
        self._pet.add_daily(clock[0], clock[1], msg, act, cd)
        self.accept()


# --------------------------------------------------------------------------
# 定时睡觉对话框
# --------------------------------------------------------------------------
class SleepDialog(BaseDialog):
    def __init__(self, pet_win):
        super().__init__("😴 定时睡觉")
        self._pet = pet_win
        r0 = self._row()
        r0.addWidget(self._label("睡觉时间："))
        self._time_edit = QLineEdit()
        self._time_edit.setFixedWidth(90)
        self._time_edit.setPlaceholderText("如 23:30")
        r0.addWidget(self._time_edit)
        r0.addWidget(self._label("到点后自动进入睡觉状态", sub=True))
        r0.addStretch(1)

        self._err_label()
        ok = self._btn_row(self._do_ok, self.reject)
        ok.setDefault(True)
        self._center()
        self._time_edit.setFocus()

    def _do_ok(self):
        clock, err = parse_clock(self._time_edit.text())
        if err:
            self._set_err(err)
            return
        self._pet.schedule_sleep(clock[0], clock[1])
        self.accept()


# --------------------------------------------------------------------------
# 流式布局：空间不足自动换行（Android 新闻 Tabs 式标签）
class _FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do(self, rect, test_only):
        m = self.contentsMargins()
        x, y = rect.x() + m.left(), rect.y() + m.top()
        line_h = 0
        for it in self._items:
            w, h = it.sizeHint().width(), it.sizeHint().height()
            if x + w > rect.right() - m.right() and line_h > 0:
                x = rect.x() + m.left()
                y += line_h + self.spacing()
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(x, y, w, h))
            x += w + self.spacing()
            line_h = max(line_h, h)
        return y + line_h - rect.y() + m.bottom()


# 提示语设置对话框（无边框 + 自绘标题 + 流式换行标签 + 可关闭 ×）
class MsgDialog(QDialog):
    """每个形象一个流式胶囊标签（自动换行，全部可见），标签带 × 删除：
    删除即清除该形象的自定义提示语（恢复默认拟声）并移除标签；
    末尾 "+" 可重新添加已移除的形象。"""
    STATE_NAMES = [("idle", "待机"), ("happy", "开心"),
                   ("sleep", "睡觉"), ("surprise", "惊喜")]
    _QSS = f"""
    QDialog {{ background:{UI_BG}; }}
    QLabel {{ color:{UI_FG}; font-family:'Microsoft YaHei UI'; font-size:12px;
             background:transparent; }}
    QLabel#m_title {{ font-size:14px; font-weight:bold; color:{UI_FG}; }}
    QLabel#m_hint {{ color:{UI_SUB}; font-size:11px; }}
    QComboBox {{ background:#ffffff; border:1px solid {UI_INPUT_BD}; border-radius:8px;
                 padding:6px 10px; color:{UI_FG}; font-family:'Microsoft YaHei UI';
                 font-size:12px; min-width:90px; }}
    QComboBox:focus {{ border:1px solid {UI_ACCENT}; }}
    QComboBox QAbstractItemView {{ background:#ffffff; border:1px solid {UI_INPUT_BD};
                 border-radius:6px; selection-background-color:{UI_MENU_HI};
                 selection-color:{UI_ACCENT_HI}; color:{UI_FG}; }}
    QListWidget {{ background:#ffffff; border:1px solid {UI_INPUT_BD}; border-radius:10px;
                 padding:6px; color:{UI_FG}; font-family:'Microsoft YaHei UI';
                 font-size:12px; outline:none; }}
    QListWidget::item {{ padding:7px 10px; border-radius:6px; }}
    QListWidget::item:hover {{ background:{UI_BG2}; }}
    QListWidget::item:selected {{ background:{UI_MENU_HI}; color:{UI_ACCENT_HI}; }}
    QLineEdit {{ background:#ffffff; border:1px solid {UI_INPUT_BD}; border-radius:8px;
                 padding:7px 10px; color:{UI_FG}; font-family:'Microsoft YaHei UI';
                 font-size:12px; selection-background-color:{UI_ACCENT}; }}
    QLineEdit:focus {{ border:1px solid {UI_ACCENT}; }}
    QPushButton#m_ok {{ background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                 stop:0 {UI_ACCENT}, stop:1 {UI_ACCENT_HI});
                 color:#ffffff; border:none; border-radius:8px; padding:8px 28px;
                 font-family:'Microsoft YaHei UI'; font-size:12px; font-weight:bold; }}
    QPushButton#m_ok:hover {{ background:{UI_ACCENT_HI}; }}
    QPushButton#m_sec {{ background:#ffffff; color:{UI_FG};
                 border:1px solid {UI_INPUT_BD}; border-radius:8px; padding:8px 18px;
                 font-family:'Microsoft YaHei UI'; font-size:12px; }}
    QPushButton#m_sec:hover {{ background:{UI_BG2}; }}
    QPushButton#m_close {{ background:transparent; border:none; color:{UI_SUB};
                 font-size:14px; border-radius:8px; padding:2px 10px; }}
    QPushButton#m_close:hover {{ background:{UI_ERR}; color:#ffffff; }}
    QPushButton#pet_tab {{ background:#ffffff; color:{UI_FG};
                 border:1px solid {UI_INPUT_BD}; border-radius:14px;
                 padding:5px 11px; font-family:'Microsoft YaHei UI'; font-size:12px; }}
    QPushButton#pet_tab:hover {{ border-color:{UI_ACCENT}; color:{UI_ACCENT}; }}
    QPushButton#pet_tab:checked {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
                 stop:0 {UI_ACCENT}, stop:1 {UI_ACCENT_HI});
                 color:#ffffff; border-color:{UI_ACCENT}; }}
    QPushButton#pet_close {{ background:transparent; border:none; color:{UI_SUB};
                 font-size:11px; padding:0 5px; border-radius:9px; }}
    QPushButton#pet_close:hover {{ background:{UI_ERR}; color:#ffffff; }}
    QPushButton#pet_add {{ background:#ffffff; color:{UI_ACCENT};
                 border:1px dashed {UI_ACCENT}; border-radius:14px; padding:5px 11px;
                 font-family:'Microsoft YaHei UI'; font-size:13px; }}
    QPushButton#pet_add:hover {{ background:{UI_BG2}; }}
    """

    def __init__(self, pet_win):
        super().__init__(None, Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint | Qt.Tool)
        self._pet = pet_win
        self.setWindowTitle("提示语设置")
        self.setModal(True)
        self.setStyleSheet(self._QSS)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # 自绘标题栏（可拖拽 + 关闭按钮）
        self._title_bar = QWidget(self)
        self._title_bar.setFixedHeight(44)
        self._title_bar.setStyleSheet(
            f"background:{UI_BG2}; border-top-left-radius:12px;"
            f"border-top-right-radius:12px;")
        tl = QHBoxLayout(self._title_bar)
        tl.setContentsMargins(16, 0, 8, 0)
        t = QLabel("💬 提示语设置")
        t.setObjectName("m_title")
        tl.addWidget(t)
        tl.addStretch(1)
        close_btn = QPushButton("✕")
        close_btn.setObjectName("m_close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.reject)
        tl.addWidget(close_btn)
        root.addWidget(self._title_bar)
        # 内容区
        body = QVBoxLayout()
        body.setContentsMargins(18, 12, 18, 16)
        body.setSpacing(10)
        # 流式标签栏（自动换行，全部可见）
        self._bar = QWidget(self)
        self._bar.setStyleSheet("background:transparent;")
        self._bar_lay = _FlowLayout(self._bar, margin=0, spacing=6)
        self._bar.setLayout(self._bar_lay)
        body.addWidget(self._bar)
        # 内容区
        self._stack = QStackedWidget(self)
        self._stack.setStyleSheet("QStackedWidget{background:transparent;}")
        body.addWidget(self._stack, 1)
        # 按钮行
        br = QHBoxLayout()
        br.addStretch(1)
        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("m_ok")
        ok_btn.clicked.connect(self.accept)
        br.addWidget(ok_btn)
        body.addLayout(br)
        root.addLayout(body)
        self._pages = {}      # key -> [page, tab_btn, close_btn]
        self._order = []
        self._edits = {}
        for key, label in PETS:
            self._add_pet_tab(key, label, select=True)
        self._make_add_btn()
        self.setMinimumWidth(560)
        self.adjustSize()
        self._center()

    # ---------- 标题栏拖拽 ----------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and ev.pos().y() <= 44:
            self._drag = (ev.globalPos()
                          - self.frameGeometry().topLeft())
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if getattr(self, "_drag", None) is not None:
            self.move(ev.globalPos() - self._drag)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._drag = None
        super().mouseReleaseEvent(ev)

    # ---------- 标签构建 ----------
    def _add_pet_tab(self, key, label, select=False):
        page = self._build_page(key, label)
        tbtn = QPushButton(label, self._bar)
        tbtn.setObjectName("pet_tab")
        tbtn.setCheckable(True)
        tbtn.setCursor(Qt.PointingHandCursor)
        tbtn.clicked.connect(lambda _=False, k=key: self._select(k))
        cbtn = QPushButton("✕", self._bar)
        cbtn.setObjectName("pet_close")
        cbtn.setCursor(Qt.PointingHandCursor)
        cbtn.clicked.connect(lambda _=False, k=key: self._remove_tab(k))
        self._bar_lay.addWidget(tbtn)
        self._bar_lay.addWidget(cbtn)
        self._pages[key] = [page, tbtn, cbtn]
        self._order.append(key)
        if select:
            self._select(key)
        return page

    def _build_page(self, key, label):
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(2, 4, 2, 0)
        pl.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._label(f"{label} · 状态："))
        cb = QComboBox()
        for _, nm in self.STATE_NAMES:
            cb.addItem(nm)
        row.addWidget(cb)
        row.addStretch(1)
        pl.addLayout(row)
        lst = QListWidget(page)
        pl.addWidget(lst, 1)
        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        inp = QLineEdit(page)
        inp.setPlaceholderText("输入新提示语，回车或点添加…")
        add_btn = QPushButton("添加")
        add_btn.setObjectName("m_sec")
        del_btn = QPushButton("删除选中")
        del_btn.setObjectName("m_sec")
        add_row.addWidget(inp, 1)
        add_row.addWidget(add_btn)
        add_row.addWidget(del_btn)
        pl.addLayout(add_row)
        self._edits[key] = {"cb": cb, "lst": lst, "inp": inp}
        self._reload(key)
        cb.currentIndexChanged.connect(lambda _=0, k=key: self._reload(k))
        add_btn.clicked.connect(lambda _=False, k=key: self._add_msg(k))
        del_btn.clicked.connect(lambda _=False, k=key: self._del_msg(k))
        inp.returnPressed.connect(lambda k=key: self._add_msg(k))
        self._stack.addWidget(page)
        return page

    def _label(self, text, sub=False):
        lb = QLabel(text)
        if sub:
            lb.setObjectName("m_hint")
        return lb

    def _make_add_btn(self):
        ab = QPushButton("＋", self._bar)
        ab.setObjectName("pet_add")
        ab.setCursor(Qt.PointingHandCursor)
        ab.clicked.connect(self._add_missing_menu)
        self._bar_lay.addWidget(ab)
        self._add_btn = ab

    def _add_missing_menu(self):
        missing = [k for k, _ in PETS if k not in self._pages]
        if not missing:
            return
        mm = QMenu(self)
        mm.setStyleSheet(self._pet._menu_qss())
        for key in missing:
            a = mm.addAction(PET_LABEL.get(key, key))
            a.triggered.connect(lambda _=False, k=key: self._add_pet_tab(
                k, PET_LABEL.get(k, k), select=True))
        mm.exec_(self._add_btn.mapToGlobal(
            self._add_btn.rect().bottomLeft()))
        self.adjustSize()

    # ---------- 标签交互 ----------
    def _select(self, key):
        idx = self._stack.indexOf(self._pages[key][0])
        if idx >= 0:
            self._stack.setCurrentIndex(idx)
        for k, (_, tb, _) in self._pages.items():
            tb.setChecked(k == key)

    def _remove_tab(self, key):
        if key not in self._pages:
            return
        remove_pet_msgs(key)     # 清除自定义 → 恢复默认拟声
        page, tbtn, cbtn = self._pages.pop(key)
        self._bar_lay.takeAt(self._bar_lay.indexOf(tbtn))
        tbtn.deleteLater()
        self._bar_lay.takeAt(self._bar_lay.indexOf(cbtn))
        cbtn.deleteLater()
        self._stack.removeWidget(page)
        page.deleteLater()
        self._order.remove(key)
        if self._stack.count() == 0:
            empty = QLabel("已移除全部形象，点右下“＋”重新添加", self._stack)
            empty.setAlignment(Qt.AlignCenter)
            empty.setObjectName("m_hint")
            self._stack.addWidget(empty)
            self._stack.setCurrentWidget(empty)
        else:
            n = self._stack.count()
            self._stack.setCurrentIndex(min(self._stack.currentIndex(), n - 1))
            self._select(self._order[-1])
        self._pet.show_bubble(f"已移除{PET_LABEL.get(key, key)}提示语（恢复默认）", 1800)
        self.adjustSize()

    # ---------- 状态/增删 ----------
    def _state_of(self, key):
        return self.STATE_NAMES[self._edits[key]["cb"].currentIndex()][0]

    def _reload(self, key):
        msgs = get_pet_msgs(key)
        st = self._state_of(key)
        lst = self._edits[key]["lst"]
        lst.clear()
        for m in msgs[st]:
            lst.addItem(m)

    def _add_msg(self, key):
        inp = self._edits[key]["inp"]
        text = inp.text().strip()
        if not text:
            return
        msgs = get_pet_msgs(key)
        st = self._state_of(key)
        if text not in msgs[st]:
            msgs[st].append(text)
            save_pet_msgs(key, msgs)
            inp.clear()
        self._reload(key)

    def _del_msg(self, key):
        lst = self._edits[key]["lst"]
        row = lst.currentRow()
        if row < 0:
            return
        msgs = get_pet_msgs(key)
        st = self._state_of(key)
        if 0 <= row < len(msgs[st]):
            msgs[st].pop(row)
            save_pet_msgs(key, msgs)
        self._reload(key)

    def _center(self):
        ag = QApplication.primaryScreen().availableGeometry()
        self.move(ag.center().x() - self.width() // 2,
                  ag.center().y() - self.height() // 2)


# 主程序
# --------------------------------------------------------------------------
def main():
    set_dpi_aware()
    if not acquire_single_instance(MUTEX_NAME):
        QApplication.instance() or QApplication(sys.argv)
        return   # 已有实例在运行，直接退出
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 桌宠常驻，不随窗口关闭退出
    app.setApplicationName(APP_NAME)
    w = PetWindow()
    w.show()
    app.exec_()


if __name__ == "__main__":
    main()

