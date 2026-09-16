# -*- coding: utf-8 -*-
"""AI 生成帧后处理：白底抠图(泛洪) + 朝向检测 + 600x600 裁剪 + 程序镜像"""
import os, sys
from collections import deque
import numpy as np
from PIL import Image

def cutout_white(img):
    """纯白背景转透明：泛洪填充清除与边缘相连的白色（保护体内白毛），并去边缘白边"""
    im = img.convert('RGBA')
    w, h = im.size
    arr = np.array(im).astype(np.int16)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    is_white = (r > 233) & (g > 233) & (b > 233)
    mask = np.zeros((h, w), dtype=bool)
    q = deque()
    def push(x, y):
        if not mask[y, x] and is_white[y, x]:
            mask[y, x] = True
            q.append((x, y))
    for x in range(w):
        push(x, 0); push(x, h - 1)
    for y in range(h):
        push(0, y); push(w - 1, y)
    while q:
        x, y = q.popleft()
        for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
            if 0 <= nx < w and 0 <= ny < h and not mask[ny, nx] and is_white[ny, nx]:
                mask[ny, nx] = True
                q.append((nx, ny))
    a = np.array(im.getchannel('A'))
    a[mask] = 0
    # 边缘白边去除：透明邻接的纯白像素
    a2 = a.copy()
    for y in range(h):
        for x in range(w):
            if a2[y, x] > 0 and is_white[y, x]:
                if (x > 0 and a2[y, x-1] == 0) or (x < w-1 and a2[y, x+1] == 0) \
                   or (y > 0 and a2[y-1, x] == 0) or (y < h-1 and a2[y+1, x] == 0):
                    a2[y, x] = 0
    out = im.copy()
    out.putalpha(Image.fromarray(a2))
    return out

def facing_ratio(img):
    """非透明像素的水平质心（0-1，0.5=居中）"""
    im = img.convert('RGBA')
    arr = np.array(im)
    a = arr[..., 3] > 8
    if not a.any():
        return 0.5
    ys, xs = np.nonzero(a)
    return xs.mean() / im.size[0]

def to_square(img, side=600):
    """等比缩放并居中到 side×side 透明画布"""
    im = img.convert('RGBA')
    w, h = im.size
    scale = side / max(w, h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - nw) // 2, (side - nh) // 2), im)
    return canvas

def process(src, out_base, ref=None):
    im = Image.open(src)
    cut = cutout_white(im)
    fr = facing_ratio(cut)
    flip = False
    if ref is not None:
        rr = facing_ratio(ref)
        # 若与参考朝向相反（质心分居 0.5 两侧且差距明显）→ 翻转对齐
        if (fr - 0.5) * (rr - 0.5) < 0 and abs(fr - rr) > 0.08:
            cut = cut.transpose(Image.FLIP_LEFT_RIGHT)
            flip = True
            fr = 1.0 - fr
    sq = to_square(cut)
    sq.save(out_base + '.png')
    sq.transpose(Image.FLIP_LEFT_RIGHT).save(out_base + '_l.png')
    return fr, flip, sq.size

if __name__ == '__main__':
    ref = cutout_white(Image.open(r'D:\tools\desktop-pet\sprites\run1.png'))
    fr, flip, sz = process(r'D:\tools\desktop-pet\.gen_test.png',
                           r'D:\tools\desktop-pet\.out_run5',
                           ref=ref)
    print('facing=%.3f flipped=%s size=%s' % (fr, flip, sz))
