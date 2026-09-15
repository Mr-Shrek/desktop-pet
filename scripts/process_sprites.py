# -*- coding: utf-8 -*-
"""把四宫格素材图切成 4 张透明 PNG 桌宠精灵。

流程：切片(2x2) -> 边缘泛洪去白底 -> alpha 羽化 + 预乘防白边 -> 按内容包围盒居中 -> 统一画布。
"""
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

SRC = "raw_sheet.jpg"
OUT_DIR = "sprites"
NAMES = ["idle", "happy", "sleep", "surprise"]  # 左上/右上/左下/右下
CANVAS = 600          # 输出画布边长
MAX_CONTENT = 560     # 内容最大边长（留边距）
WHITE_TH = 245        # 判定“接近白色”的通道阈值
BG_ALPHA = 8          # 小于该 alpha 视为背景


def flood_fill_bg(rgb):
    """从图像四边向内泛洪，标记与背景连通的近白区域。"""
    h, w, _ = rgb.shape
    bg = (rgb[:, :, 0] >= WHITE_TH) & (rgb[:, :, 1] >= WHITE_TH) & (rgb[:, :, 2] >= WHITE_TH)
    filled = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if bg[y, x] and not filled[y, x]:
                filled[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if bg[y, x] and not filled[y, x]:
                filled[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and bg[ny, nx] and not filled[ny, nx]:
                filled[ny, nx] = True
                q.append((ny, nx))
    return filled


def make_transparent(rgb):
    """去白底：背景 alpha=0，前景 255，羽化边缘并预乘防白边。"""
    filled = flood_fill_bg(rgb)
    alpha = np.where(filled, 0, 255).astype(np.uint8)
    alpha_img = Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(1.2))
    a = np.asarray(alpha_img).astype(np.float32) / 255.0
    rgba = np.zeros((rgb.shape[0], rgb.shape[1], 4), dtype=np.uint8)
    rgba[:, :, 3] = np.asarray(alpha_img)
    for c in range(3):
        rgba[:, :, c] = np.clip(rgb[:, :, c].astype(np.float32) * a, 0, 255).astype(np.uint8)
    return rgba


def center_on_canvas(rgba):
    """按 alpha 包围盒裁剪，等比缩放后居中放到统一画布。"""
    alpha = rgba[:, :, 3]
    ys, xs = np.where(alpha > BG_ALPHA)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    content = Image.fromarray(rgba[y0:y1, x0:x1], mode="RGBA")
    w, h = content.size
    scale = min(MAX_CONTENT / w, MAX_CONTENT / h, 1.0)
    if scale < 1.0:
        content = content.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(content, ((CANVAS - content.size[0]) // 2, (CANVAS - content.size[1]) // 2), content)
    return canvas, (x0, y0, x1, y1)


def main():
    sheet = Image.open(SRC).convert("RGB")
    w, h = sheet.size
    cw, ch = w // 2, h // 2
    boxes = [(0, 0), (cw, 0), (0, ch), (cw, ch)]
    for name, (bx, by) in zip(NAMES, boxes):
        cell = np.asarray(sheet.crop((bx, by, bx + cw, by + ch)), dtype=np.uint8)
        rgba = make_transparent(cell)
        canvas, bbox = center_on_canvas(rgba)
        out = f"{OUT_DIR}/{name}.png"
        canvas.save(out)
        print(f"{out}: {canvas.size}, content_bbox={bbox}")


if __name__ == "__main__":
    sys.exit(main())
