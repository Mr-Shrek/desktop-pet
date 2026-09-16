# -*- coding: utf-8 -*-
"""豆包桌宠 —— Windows 桌面宠物

功能：
  · 透明无边框窗口，默认始终置顶，不占任务栏
  · 拖拽移动、单击惊讶反应、双击开心反应
  · 待机浮动动画 + 随机气泡说话
  · 四种状态：待机 / 开心 / 睡觉 / 惊讶（右键菜单切换）
  · 跟随鼠标模式（宠物会慢慢爬向光标）
  · 系统托盘：隐藏到托盘 / 退出
"""
import os
import random
import sys

from PyQt5.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPixmap, QGuiApplication, QCursor, QIcon
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QMenu, QSystemTrayIcon, QAction,
    QGraphicsOpacityEffect,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_DIR = os.path.join(BASE_DIR, "sprites")

WINDOW_SIZE = 260            # 桌宠窗口边长(px)
STATE_SIZE = 240             # 精灵显示尺寸(px)
FLOAT_AMP = 8                # 待机浮动幅度(px)
FLOAT_CYCLE = 2100           # 待机浮动周期(ms)
REACT_MS = 900               # 点击/双击反应时长(ms)
CLICK_DELAY_MS = 260         # 单击判定延迟（用于区分双击）
IDLE_BUBBLE_INTERVAL = (15000, 38000)  # 待机随机气泡间隔范围(ms)
BUBBLE_SHOW_MS = 2600        # 气泡显示时长(ms)
FOLLOW_STEP = 12             # 跟随模式每帧移动距离(px)
FOLLOW_INTERVAL = 30         # 跟随模式帧间隔(ms)
MOVE_THRESHOLD = 6           # 超过该位移视为拖拽而非点击

SPRITES = ["idle", "happy", "sleep", "surprise"]
# 浣熊：正常打招呼：啾噜 开心干饭：吱咔吱咔 生气警告：嘶 ——
MESSAGES = {
    "idle": [
        "喵～", "今天也要加油哦！", "摸摸我嘛～", "我在这里陪你～",
        "起来活动一下！", "写累了就休息会儿吧", "吃点什么好呢…",
    ],
    "happy": ["嘿嘿，好开心！", "被投喂啦！", "最喜欢你啦！", "再玩一次！"],
    "sleep": ["zZz…", "呼噜呼噜…", "别吵我…", "好困…"],
    "surprise": ["哇！", "吓我一跳！", "呜哇！"],
}


class PetWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WINDOW_SIZE, WINDOW_SIZE)

        self._state = "idle"
        self._sprites = self._load_sprites()
        self._base_pos = QPoint(200, 200)
        self.move(self._base_pos)

        # 精灵显示层
        self._label = QLabel(self)
        self._label.setGeometry(0, 0, STATE_SIZE, STATE_SIZE)
        self._label.setAlignment(Qt.AlignCenter)

        # 气泡层
        self._bubble = QLabel(self)
        self._bubble.setWordWrap(True)
        self._bubble.setMaximumWidth(220)
        self._bubble.setStyleSheet(
            "background:#ffffff; color:#333333; border:1px solid #cccccc;"
            "border-radius:10px; padding:6px 10px; font-size:13px;"
        )
        self._bubble.hide()
        self._bubble_effect = QGraphicsOpacityEffect(self._bubble)
        self._bubble.setGraphicsEffect(self._bubble_effect)

        # 动画与定时器
        self._float_anim = QPropertyAnimation(self, b"pos")
        self._float_anim.setDuration(FLOAT_CYCLE)
        self._float_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._hide_timer = QTimer(self)          # 隐藏气泡
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._bubble.hide)
        self._bubble_timer = QTimer(self)        # 计划下一次随机气泡
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._on_schedule_bubble)
        self._react_timer = QTimer(self)
        self._react_timer.setSingleShot(True)
        self._react_timer.timeout.connect(lambda: self.set_state("idle"))
        self._click_delay = QTimer(self)
        self._click_delay.setSingleShot(True)
        self._click_delay.timeout.connect(self._do_single_click_reaction)
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(FOLLOW_INTERVAL)
        self._follow_timer.timeout.connect(self._follow_step)

        # 交互状态
        self._drag_offset = None
        self._press_global = None
        self._follow_mode = False
        self._topmost = True
        self._suppress_click = False

        self.set_state("idle")
        self._schedule_idle_bubble()
        self._setup_tray()

    # ---------- 素材 ----------
    def _load_sprites(self):
        sprites = {}
        for name in SPRITES:
            path = os.path.join(SPRITE_DIR, f"{name}.png")
            if not os.path.exists(path):
                raise FileNotFoundError(f"缺少精灵素材：{path}")
            pm = QPixmap(path)
            if pm.isNull():
                raise RuntimeError(f"无法加载精灵素材：{path}")
            sprites[name] = pm.scaled(
                STATE_SIZE, STATE_SIZE, Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        return sprites

    # ---------- 状态 ----------
    def set_state(self, name):
        if name not in self._sprites:
            name = "idle"
        self._state = name
        self._label.setPixmap(self._sprites[name])
        if name == "sleep":
            self.stop_float()
        elif self._float_anim.state() != QPropertyAnimation.Running and not self._follow_mode:
            self.start_float()
        if name == "idle":
            self._schedule_idle_bubble()

    @property
    def state(self):
        return self._state

    # ---------- 待机浮动 ----------
    def start_float(self):
        self._float_anim.stop()
        top = QPoint(self._base_pos.x(), self._base_pos.y() - FLOAT_AMP)
        bottom = self._base_pos
        self._float_anim.setStartValue(top)
        self._float_anim.setKeyValueAt(0.5, bottom)
        self._float_anim.setEndValue(top)
        self._float_anim.start()

    def stop_float(self):
        self._float_anim.stop()
        self.move(self._base_pos)

    def set_base_pos(self, pos):
        self._base_pos = pos

    # ---------- 气泡 ----------
    def show_bubble(self, text, ms=BUBBLE_SHOW_MS):
        if not text:
            return
        self._bubble.setText(text)
        self._bubble.adjustSize()
        bw, bh = self._bubble.width(), self._bubble.height()
        x = (WINDOW_SIZE - bw) // 2
        y = -bh - 8
        self._bubble.move(x, y)
        self._bubble_effect.setOpacity(1.0)
        self._bubble.show()
        self._bubble.raise_()
        self._hide_timer.start(ms)

    def _schedule_idle_bubble(self):
        self._bubble_timer.stop()
        delay = random.randint(*IDLE_BUBBLE_INTERVAL)
        self._bubble_timer.start(delay)

    def _on_schedule_bubble(self):
        if self._state == "sleep":
            self.show_bubble(random.choice(MESSAGES["sleep"]), 1800)
        elif self._state == "idle":
            self.show_bubble(random.choice(MESSAGES["idle"]))
        self._schedule_idle_bubble()

    # ---------- 交互：拖拽 / 单击 / 双击 ----------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPos()
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            self.stop_float()
            self._click_delay.stop()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            new_pos = event.globalPos() - self._drag_offset
            self.move(new_pos)
            self.set_base_pos(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._suppress_click:
            # 刚处理过双击，忽略双击序列中的第二次 release
            self._suppress_click = False
            return
        moved = (
            self._press_global is not None
            and (event.globalPos() - self._press_global).manhattanLength() > MOVE_THRESHOLD
        )
        self._press_global = None
        self._drag_offset = None
        if not moved:
            # 延迟触发单击反应，给双击留出判定时间
            self._click_delay.start(CLICK_DELAY_MS)
        else:
            self._restore_idle_behavior()

    def mouseDoubleClickEvent(self, event):
        self._click_delay.stop()  # 取消单击反应
        self._suppress_click = True
        QTimer.singleShot(400, self._clear_suppress)
        self.set_state("happy")
        self.show_bubble(random.choice(MESSAGES["happy"]))
        self._react_timer.start(REACT_MS)

    def _clear_suppress(self):
        self._suppress_click = False

    def _do_single_click_reaction(self):
        self.set_state(random.choice(["surprise", "happy"]))
        self.show_bubble(random.choice(MESSAGES[self._state]))
        self._react_timer.start(REACT_MS)

    def _restore_idle_behavior(self):
        if self._state in ("surprise", "happy"):
            self._react_timer.stop()
        self.set_state("idle")

    # ---------- 跟随鼠标 ----------
    def set_follow(self, enabled):
        self._follow_mode = enabled
        if enabled:
            self.stop_float()
            self._follow_timer.start()
        else:
            self._follow_timer.stop()
            self.set_state(self._state)

    def _follow_step(self):
        if self._drag_offset is not None:
            return
        cursor = QCursor.pos()
        cx = self.x() + WINDOW_SIZE // 2
        cy = self.y() + WINDOW_SIZE // 2
        dx, dy = cursor.x() - cx, cursor.y() - cy
        dist = (dx * dx + dy * dy) ** 0.5
        if dist <= FOLLOW_STEP:
            return
        step_x = dx / dist * FOLLOW_STEP
        step_y = dy / dist * FOLLOW_STEP
        nx = int(self.x() + step_x)
        ny = int(self.y() + step_y)
        screen = QGuiApplication.screenAt(QCursor.pos())
        if screen is not None:
            geo = screen.availableGeometry()
            nx = max(geo.left(), min(nx, geo.right() - WINDOW_SIZE + 1))
            ny = max(geo.top(), min(ny, geo.bottom() - WINDOW_SIZE + 1))
        self.move(nx, ny)
        self.set_base_pos(QPoint(nx, ny))

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        for name, title in (("happy", "开心一下"), ("sleep", "睡觉"), ("surprise", "吓一跳")):
            act = QAction(title, menu)
            act.triggered.connect(lambda _=False, n=name: self.set_state(n))
            menu.addAction(act)
        menu.addSeparator()
        follow_act = QAction("跟随鼠标", menu)
        follow_act.setCheckable(True)
        follow_act.setChecked(self._follow_mode)
        follow_act.toggled.connect(self.set_follow)
        menu.addAction(follow_act)
        top_act = QAction("始终置顶", menu)
        top_act.setCheckable(True)
        top_act.setChecked(self._topmost)
        top_act.toggled.connect(self.toggle_topmost)
        menu.addAction(top_act)
        menu.addSeparator()
        hide_act = QAction("隐藏到托盘", menu)
        hide_act.triggered.connect(self.hide_pet)
        menu.addAction(hide_act)
        quit_act = QAction("退出", menu)
        quit_act.triggered.connect(self.quit_pet)
        menu.addAction(quit_act)
        menu.exec_(event.globalPos())

    def toggle_topmost(self, enabled):
        self._topmost = enabled
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    # ---------- 托盘 ----------
    def _setup_tray(self):
        self._tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = QIcon(os.path.join(SPRITE_DIR, "idle.png"))
        menu = QMenu()
        show_act = QAction("显示 / 隐藏", menu)
        show_act.triggered.connect(self.toggle_visible)
        menu.addAction(show_act)
        quit_act = QAction("退出", menu)
        quit_act.triggered.connect(self.quit_pet)
        menu.addAction(quit_act)
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip("豆包桌宠")
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray = tray

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick or reason == QSystemTrayIcon.Trigger:
            self.toggle_visible()

    def toggle_visible(self):
        if self.isVisible():
            self.hide_pet()
        else:
            self.show_pet()

    def hide_pet(self):
        self._bubble_timer.stop()
        self._follow_timer.stop()
        self.stop_float()
        self.hide()

    def show_pet(self):
        self.show()
        self._schedule_idle_bubble()
        if self._follow_mode:
            self._follow_timer.start()
        elif self._state != "sleep":
            self.start_float()

    def quit_pet(self):
        if self._tray is not None:
            self._tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        # 点关闭（如 Alt+F4）时隐藏到托盘而不是退出
        event.ignore()
        self.hide_pet()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = PetWindow()
    pet.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
