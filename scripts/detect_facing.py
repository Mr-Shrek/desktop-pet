# -*- coding: utf-8 -*-
"""检测动作帧朝向：头部在内容上部，白脸/白口鼻是头部特征；
上部1/3高度内白色像素质心偏右=头朝右，偏左=头朝左"""
import os
import tkinter as tk

BASE = r"D:\tools\desktop-pet\sprites"
root = tk.Tk()
root.withdraw()
for name in ("run1", "run2", "run3", "run4", "walk1", "walk2", "walk3", "walk4"):
    img = tk.PhotoImage(file=os.path.join(BASE, name + ".png"))
    w, h = img.width(), img.height()
    # 内容 bbox（非透明区域）
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            rgb = img.get(x, y)
            if isinstance(rgb, str):
                rgb = tuple(int(v) for v in rgb.split())
            a = rgb[3] if len(rgb) > 3 else 255
            if a > 8:
                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
    if maxy < 0:
        print(f"{name}: EMPTY")
        continue
    top_h = miny + (maxy - miny) // 3   # 上部 1/3
    sx, cnt = 0, 0
    for y in range(miny, top_h + 1, 2):
        for x in range(minx, maxx + 1, 2):
            rgb = img.get(x, y)
            if isinstance(rgb, str):
                rgb = tuple(int(v) for v in rgb.split())
            r, g, b = rgb[:3]
            if r > 225 and g > 225 and b > 225:   # 白脸/白耳
                sx += x
                cnt += 1
    if cnt:
        rel = (sx / cnt - (minx + maxx) / 2) / (maxx - minx + 1) * 2
        print(f"{name}: white_top={cnt} rel={rel:+.2f} -> {'RIGHT' if rel > 0 else 'LEFT'}")
    else:
        print(f"{name}: no white in top area")
