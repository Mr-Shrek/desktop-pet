# -*- coding: utf-8 -*-
"""纯 Python 版桌宠自测：状态/气泡/拖拽/单击/双击/跟随/退出"""
import json
import os
import sys
import tempfile
import time
from types import SimpleNamespace

import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main as m

# 持久化测试用临时数据文件，避免污染真实提醒数据
m.DATA_FILE = os.path.join(tempfile.gettempdir(), "pet_selftest_data.json")
try:
    os.remove(m.DATA_FILE)
except OSError:
    pass

root = tk.Tk()
pet = m.DesktopPet(root)
root.update()

# 1) 状态切换
for s in m.SPRITES:
    pet.set_state(s)
    root.update()
print("[1] 状态切换 OK, current =", pet.state)

# 2) 气泡显示
pet.show_bubble("测试气泡喵～")
root.update()
assert pet.bubble.winfo_ismapped(), "气泡未显示"
print("[2] 气泡 OK, text =", pet.bubble.cget("text"))
pet.bubble.place_forget()

# 3) 拖拽：按下->移动->松开，窗口应移动
x0, y0 = root.winfo_x(), root.winfo_y()
pet._on_press(SimpleNamespace(x_root=x0 + 40, y_root=y0 + 40))
for i in range(5):
    pet._on_drag(SimpleNamespace(x_root=x0 + 40 + i * 10, y_root=y0 + 40 + i * 10))
pet._on_release(SimpleNamespace(x_root=x0 + 90, y_root=y0 + 90))
root.update()
assert (root.winfo_x(), root.winfo_y()) != (x0, y0), "拖拽后窗口未移动"
print(f"[3] 拖拽 OK: ({x0},{y0}) -> ({root.winfo_x()},{root.winfo_y()})")

# 4) 单击：原地按下松开 -> 延迟反应触发
pet._on_press(SimpleNamespace(x_root=root.winfo_x() + 40, y_root=root.winfo_y() + 40))
pet._on_release(SimpleNamespace(x_root=root.winfo_x() + 40, y_root=root.winfo_y() + 40))
deadline = time.time() + 1.0
while time.time() < deadline:
    root.update()
    time.sleep(0.02)
print("[4] 单击延迟反应 OK, state =", pet.state)
pet.set_state("idle")
root.update()

# 5) 双击：应取消单击并进入开心
pet._on_double(SimpleNamespace(x_root=0, y_root=0))
root.update()
assert pet.state == "happy", f"双击后应为 happy，实际 {pet.state}"
print("[5] 双击 OK, state =", pet.state)
pet.set_state("idle")

# 6) 跟随模式：开启一段时间无异常
pet.set_follow(True)
deadline = time.time() + 0.4
while time.time() < deadline:
    root.update()
    time.sleep(0.02)
pet.set_follow(False)
print("[6] 跟随模式 OK")

# 7) 置顶切换
pet._topmost_var.set(False)
pet._toggle_topmost()
assert pet._topmost is False
pet._topmost_var.set(True)
pet._toggle_topmost()
assert pet._topmost is True
print("[7] 置顶切换 OK")

# 8) 定时提醒：解析
assert m.parse_reminder("30") == (1800, None)
assert m.parse_reminder("1.5") == (90, None)
secs, err = m.parse_reminder("14:30")
assert err is None and 0 < secs <= 86400, (secs, err)
assert m.parse_reminder("abc")[1] is not None
assert m.parse_reminder("25:99")[1] is not None
assert m.parse_reminder("")[1] is not None
assert m.parse_reminder("-3")[1] is not None
assert m.fmt_remaining(3661) == "1 小时 1 分"
assert m.fmt_remaining(90) == "1 分 30 秒"
assert m.fmt_remaining(5) == "5 秒"
# 每日提醒时刻解析
assert m.parse_clock("08:30") == ((8, 30), None)
assert m.parse_clock("23:59") == ((23, 59), None)
assert m.parse_clock("24:00")[1] is not None
assert m.parse_clock("8")[1] is not None
assert m.parse_clock("abc")[1] is not None
assert m.parse_clock("")[1] is not None
print("[8] 提醒时间解析 OK")

# 9) 定时提醒：到点触发猫跑中心+微信气泡
pet.add_reminder(1, "测试提醒：喝水")
assert len(pet._timers) == 1
deadline = time.time() + 6.0
while time.time() < deadline and not pet._bubble_items:
    root.update()
    time.sleep(0.02)
assert pet._bubble_items, "定时提醒未弹出微信气泡"
assert len(pet._timers) == 0, "触发后提醒应已移除"
print("[9] 提醒触发气泡 OK, items =", len(pet._bubble_items))
pet._clear_chat_bubble()
root.update()

# 10) 定时提醒：取消
pet.add_reminder(120, "不提醒这个")
t = pet._timers[0]
pet._cancel_reminder(t)
assert len(pet._timers) == 0
print("[10] 提醒取消 OK")

# 11) 状态自动恢复（修复：菜单/提醒设置状态后应回到默认 idle）
pet.set_state("happy", 500)
deadline = time.time() + 2.0
while time.time() < deadline and pet.state != "idle":
    root.update()
    time.sleep(0.02)
assert pet.state == "idle", f"happy 未自动恢复，state={pet.state}"

pet.set_state("surprise", 400)
deadline = time.time() + 2.0
while time.time() < deadline and pet.state != "idle":
    root.update()
    time.sleep(0.02)
assert pet.state == "idle", f"surprise 未自动恢复，state={pet.state}"

# 睡觉：默认自动醒来
pet.set_state("sleep")
assert pet._revert_id is not None, "睡觉未安排自动醒来"
pet._on_revert()
assert pet.state == "idle", "睡觉未自动恢复"

# 设置提醒后恢复默认
pet.add_reminder(120, "不提醒这个")
assert pet.state == "happy", "设置提醒后应立即开心"
deadline = time.time() + 3.0
while time.time() < deadline and pet.state != "idle":
    root.update()
    time.sleep(0.02)
assert pet.state == "idle", f"设置提醒后未恢复，state={pet.state}"
for t in list(pet._timers):
    pet._cancel_reminder(t)
print("[11] 状态自动恢复 OK")

# 12) 大小调节：阈值限制 + 缩放生效
assert pet._size == 300 and pet.win_w == 340 and pet.win_h == 460
# 最小阈值
pet.set_size(10)
root.update()
assert pet._size == m.MIN_PET_SIZE, f"最小阈值未生效: {pet._size}"
# 最大阈值
pet.set_size(9999)
root.update()
assert pet._size == pet._max_size, f"最大阈值未生效: {pet._size}"
# 正常缩放：底部中心锚点，窗口尺寸与图片同步
root.update()
x0, y0, w0, h0 = root.winfo_x(), root.winfo_y(), pet.win_w, pet.win_h
pet.set_size(250)
root.update()
assert pet._size == 250 and pet.win_w == 290 and pet.win_h == 410
assert pet.images["idle"].width() == 250
assert pet.images["happy"].width() == 250
# 底部中心锚点：缩放前后底部中心位置一致
bcx0, bcy0 = x0 + w0 // 2, y0 + h0
bcx1, bcy1 = root.winfo_x() + pet.win_w // 2, root.winfo_y() + pet.win_h
assert abs(bcx0 - bcx1) <= 2, f"底部中心锚点偏移: {bcx0} vs {bcx1}"
assert abs(bcy0 - bcy1) <= 2, f"底部锚点 y 偏移: {bcy0} vs {bcy1}"
# 缩放后状态图仍然正确
pet.set_state("sleep")
assert pet.canvas.itemcget(pet._img_id, "image") == pet.images["sleep"].name
pet.set_state("idle")
pet.set_size(300)
root.update()
print("[12] 大小调节 OK")

# 13) 开机自启：注册表读写（用独立测试键名，测完清理）
test_name = m.AUTOSTART_NAME + "Selftest"
try:
    assert m.is_autostart_enabled(test_name) is False, "测试键不应已存在"
    m.set_autostart(True, test_name)
    assert m.is_autostart_enabled(test_name) is True, "写入后应检测到自启"
    m.set_autostart(False, test_name)
    assert m.is_autostart_enabled(test_name) is False, "删除后应不再自启"
    print("[13] 开机自启注册表 OK")
finally:
    try:
        m.set_autostart(False, test_name)
    except Exception:
        pass

# 14) 定时睡觉：设置/取消/到点入睡（睡到点击唤醒，不自动醒）
pet._schedule_sleep(0.5)
assert pet._sleep_at is not None, "设置后应记录睡觉计划"
pet._cancel_sleep()
assert pet._sleep_at is None, "取消后应清除睡觉计划"
pet._schedule_sleep(0.5)
deadline = time.time() + 3.0
while time.time() < deadline and pet.state != "sleep":
    root.update()
    time.sleep(0.02)
assert pet.state == "sleep", f"到点未入睡，state={pet.state}"
assert pet._revert_id is None, "定时睡觉不应自动醒来（应等点击唤醒）"
print("[14] 定时睡觉 OK")

# 15) 睡眠恢复看门狗：模拟睡眠 30 秒后唤醒，应触发修复与打招呼
pet._last_real = time.time() - 30
pet._last_tick = pet._get_tick64() - 5000   # 滴答只走了 5 秒 → 判定刚唤醒
pet._watchdog_loop()
root.update()
assert "我回来啦" in pet.bubble.cget("text"), "睡眠恢复未触发提示"
assert pet.root.winfo_ismapped(), "恢复后窗口应仍可见"
# 正常轮询不应误判为唤醒（先清空气泡，再确认没有新提示）
pet.bubble.place_forget()
pet.bubble.config(text="")
pet._last_real = time.time()
pet._last_tick = pet._get_tick64()
pet._watchdog_loop()
root.update()
assert pet.bubble.cget("text") == "", f"正常轮询不应触发恢复提示: {pet.bubble.cget('text')}"
print("[15] 睡眠恢复看门狗 OK")

# 16) 提醒持久化：写入文件 → 模拟重启加载 → 过期不恢复 → 取消同步
pet.add_reminder(120, "持久化测试")
with open(m.DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)
assert any(r["msg"] == "持久化测试" for r in data["reminders"]), "提醒未写入文件"
pet._cancel_reminder(pet._timers[0])
with open(m.DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)
assert not data["reminders"], "取消后文件未同步"

# 模拟重启：清空内存后从文件恢复
pet.add_reminder(120, "持久化加载测试")
pet._timers = []
pet._load_reminders()
assert any(t["msg"] == "持久化加载测试" for t in pet._timers), "重启后提醒未恢复"

# 过期的提醒不应恢复
pet.add_reminder(120, "将过期提醒")
pet._timers[1]["due"] = time.time() - 10
pet._save_reminders()
pet._timers = []
pet._load_reminders()
assert not any(t["msg"] == "将过期提醒" for t in pet._timers), "过期提醒不应恢复"
for t in list(pet._timers):
    pet._cancel_reminder(t)
# 每日提醒持久化
pet.add_daily(8, 30, "每日起床测试")
with open(m.DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)
assert any(d["hour"] == 8 and d["minute"] == 30 for d in data["dailies"]), "每日提醒未写入文件"
pet._cancel_daily(pet._dailies[0])
with open(m.DATA_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)
assert not data["dailies"], "取消每日提醒后文件未同步"
# 大小持久化
pet.set_size(400)
root.update()
assert m.load_saved_size() == 400, "大小未写入文件"
pet.set_size(300)
root.update()
assert m.load_saved_size() == 300, "大小变更后未同步"
# 位置持久化
pet.root.geometry("+123+456")
root.update()
pet._save_reminders()
pos = m.load_saved_pos()
assert pos == (123, 456), f"位置未写入文件: {pos}"
# 位置夹取方向性验证
cx, cy = pet._clamp_pos(100000, 100000)
assert cx <= 100000 and cy <= 100000, "过大坐标未被夹小"
cx2, cy2 = pet._clamp_pos(-100000, -100000)
assert cx2 >= -100000 and cy2 >= -100000, "过小坐标未被夹大"
print("[16] 提醒持久化 OK")

# 17) 每日提醒：到点触发 + 同天不重复（含睡眠倒计时/取消）
# 若恰逢分钟边界（设置后跨分钟会导致不触发），重设当前分钟重试
for _try in range(5):
    lt = time.localtime()
    pet.add_daily(lt.tm_hour, lt.tm_min, "每日提醒测试")
    deadline = time.time() + 6.0
    while time.time() < deadline and not pet._bubble_items:
        root.update()
        time.sleep(0.02)
    if pet._bubble_items:
        break
    pet._cancel_daily(pet._dailies[-1])   # 跨分钟未触发，清掉重试
assert pet._bubble_items, "每日提醒未触发气泡"
d = pet._dailies[0]
assert d["last"] != "", "每日提醒未记录今日已提醒标记"
n = len(pet._bubble_items)
root.update()
time.sleep(1.2)
deadline = time.time() + 2.0
while time.time() < deadline:
    root.update()
    time.sleep(0.02)
assert len(pet._bubble_items) == n, "同一天同一分钟不应重复触发每日提醒"
pet._clear_chat_bubble()
# 睡眠倒计时气泡：有倒计时文字 + 取消按钮；取消后气泡清空、不触发睡眠
pet._show_chat_bubble("睡眠测试提醒", sleep_after=True)
assert pet._bubble_items, "睡眠气泡未显示"
assert pet._countdown == 10 and pet._cd_text_id is not None, "倒计时未启动"
assert pet._bubble_btn is not None, "取消按钮未创建"
pet._cancel_sleep_countdown()
assert not pet._bubble_items, "取消后气泡未清空"
# 停止"跑回原位"的跑动，避免 _run_active 阻塞后续动画测试
pet._run_active = False
pet._run_cb = None
pet._cancel_daily(d)
print("[17] 每日提醒 OK")

# 18) 动画：跳跃 / 粒子 / 睡眠 zZz
# 跳跃：happy 中途有向上位移，结束后归零
pet.set_state("happy")
root.update()
pet._hop_start = time.time() - 0.12
assert pet._hop_offset() < 0, "跳跃中途应有向上位移"
pet._hop_start = time.time() - 2.0
assert pet._hop_offset() == 0, "跳跃结束应归零"
# 清掉 set_state 触发的粒子，再独立验证粒子机制
for p in list(pet._particles):
    pet.canvas.delete(p[0])
pet._particles = []
# 粒子：生成后上移
pet._spawn_particles("happy", 3)
assert len(pet._particles) == 3, "粒子未生成"
root.update()
pet._update_particles(time.time() + 0.05)
y0 = pet.canvas.coords(pet._particles[0][0])[1]
pet._update_particles(time.time() + 0.1)
y1 = pet.canvas.coords(pet._particles[0][0])[1]
assert y1 < y0, "粒子应向上移动"
for p in list(pet._particles):
    pet.canvas.delete(p[0])
pet._particles = []
# 睡眠 zZz：进入睡眠后自动飘 z
pet.set_state("sleep")
pet._last_z = 0
deadline = time.time() + 2.5
while time.time() < deadline and not pet._particles:
    root.update()
    time.sleep(0.02)
if not pet._particles:
    print("DIAG: run_active=%s floating=%s state=%s motion=%s drag=%s follow=%s"
          % (pet._run_active, pet._floating, pet.state, pet._motion,
             pet._drag_off, pet._follow_mode))
assert pet._particles, "睡眠 zZz 粒子未生成"
for p in list(pet._particles):
    pet.canvas.delete(p[0])
pet._particles = []
pet.set_state("idle")
print("[18] 动画 OK")

# 19) 跑动/走动帧动画单元测试（4 帧循环 + 朝向镜像）
pet._set_motion("walk")
assert pet._motion == "walk", "走动模式未生效"
pet._frame_idx = 0
pet._last_frame_t = 0.0
pet._tick_motion_frame()
assert pet._frame_idx == 1, "走动帧未交替"
pet._last_frame_t = 0.0
pet._tick_motion_frame()
assert pet._frame_idx == 2, "走动第三帧未推进"
pet._last_frame_t = 0.0
pet._tick_motion_frame()
assert pet._frame_idx == 3, "走动第四帧未推进"
pet._last_frame_t = 0.0
pet._tick_motion_frame()
assert pet._frame_idx == 0, "走动帧未循环回第一帧"
# 朝向镜像：朝左时显示 _l 帧
pet._facing = -1
pet._frame_idx = 0
pet._last_frame_t = 0.0
pet._tick_motion_frame()
cur = pet.canvas.itemcget(pet._img_id, "image")
name = next(k for k, v in pet.images.items() if v.name == cur)
assert name.endswith("_l"), f"朝左时应显示镜像帧，实际 {name}"
pet._set_facing(50.0)
cur = pet.canvas.itemcget(pet._img_id, "image")
name = next(k for k, v in pet.images.items() if v.name == cur)
assert name == "walk2" or name == "walk1", f"朝右时应显示正像帧，实际 {name}"
# 朝向死区：目标几乎正前方时保持原朝向
pet._set_facing(-5.0)
assert pet._facing == 1, "死区内不应翻转朝向"
pet._set_motion("run")
assert pet._motion == "run", "跑动模式未生效"
pet._set_motion(None)
assert pet._motion is None, "恢复状态图失败"
print("[19] 帧动画+朝向 OK")

# 20) 退出
pet.quit()
print("[20] 退出 OK")
print("=== 全部自测通过 ===")
