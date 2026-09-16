# -*- coding: utf-8 -*-
"""TPS 均匀化插帧：对差异>阈值的帧对插帧，质量检测，输出最终序列"""
import os
import numpy as np
import cv2
from PIL import Image

ROOT = r'D:\tools\desktop-pet'
OUT = os.path.join(ROOT, '.steps3')
os.makedirs(OUT, exist_ok=True)

# ---------- TPS 核心 ----------
def _load(path):
    im = Image.open(path).convert('RGBA')
    arr = np.array(im).astype(np.uint8)
    rgb = arr[..., :3].copy(); a = arr[..., 3]
    rgb[a < 8] = 255
    return rgb, a

def _k(r2):
    r2 = np.maximum(r2, 1e-10)
    return r2 * np.log(r2)

def tps_mid(p1, p2, t=0.5):
    rgb1, a1 = _load(p1); rgb2, a2 = _load(p2)
    h, w = rgb1.shape[:2]
    g1 = cv2.cvtColor(rgb1, cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(rgb2, cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(nfeatures=3000, scaleFactor=1.2, nlevels=8)
    k1, d1 = orb.detectAndCompute(g1, None)
    k2, d2 = orb.detectAndCompute(g2, None)
    if d1 is None or d2 is None:
        return None
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)
    matches = bf.knnMatch(d1, d2, k=2)
    good = [m[0] for m in matches if len(m) == 2 and m[0].distance < 0.8 * m[1].distance]
    if len(good) < 10:
        return None
    src = np.float32([k1[m.queryIdx].pt for m in good])
    dst = np.float32([k2[m.trainIdx].pt for m in good])
    corners_s = np.float32([[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]])
    src = np.vstack([src, corners_s]); dst = np.vstack([dst, corners_s.copy()])
    n = len(src)
    K = np.zeros((n, n))
    for i in range(n):
        d = src - src[i]
        K[i] = _k((d ** 2).sum(axis=1))
    P = np.hstack([np.ones((n, 1)), src])
    A = np.zeros((n + 3, n + 3))
    A[:n, :n] = K; A[:n, n:] = P; A[n:, :n] = P.T
    target = np.vstack([src * (1 - t) + dst * t, np.zeros((3, 2))])
    try:
        coefs = np.linalg.solve(A, target)
    except np.linalg.LinAlgError:
        return None
    wc, ac = coefs[:n], coefs[n:]
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    pts = np.stack([xs.ravel(), ys.ravel()], axis=1)
    d2 = ((pts[:, None, :] - src[None, :, :]) ** 2).sum(axis=2)
    mapped = _k(d2) @ wc + np.hstack([np.ones((h * w, 1)), pts]) @ ac
    mx = mapped[:, 0].reshape(h, w).astype(np.float32)
    my = mapped[:, 1].reshape(h, w).astype(np.float32)
    frgb = cv2.remap(rgb1, mx, my, cv2.INTER_LINEAR)
    fa = cv2.remap(a1, mx, my, cv2.INTER_LINEAR)
    out = np.dstack([frgb, fa])
    out[fa < 10, 3] = 0
    return Image.fromarray(out, 'RGBA')

# ---------- 工具 ----------
def diff_ratio(p1, p2):
    a = np.array(Image.open(p1).convert('RGBA').resize((300, 300), Image.LANCZOS)).astype(int)
    b = np.array(Image.open(p2).convert('RGBA').resize((300, 300), Image.LANCZOS)).astype(int)
    m = (a[..., 3] > 8) | (b[..., 3] > 8)
    if not m.any(): return 0
    d = (np.abs(a - b).sum(axis=-1) > 60) & m
    return d.sum() / m.sum()

def content_area(img):
    if isinstance(img, str):
        img = Image.open(img).convert('RGBA')
    a = np.array(img.convert('RGBA'))[..., 3] > 8
    return a.mean()

def area_penalty(mid, f1, f2):
    """插帧内容面积应介于两端之间，否则视为坏帧"""
    am = content_area(mid)
    a1, a2 = content_area(f1), content_area(f2)
    lo, hi = min(a1, a2), max(a1, a2)
    pad = (hi - lo) * 0.6 + 0.03
    return not (lo - pad <= am <= hi + pad)

# ---------- 主流程 ----------
PET_DIRS = {
    'cat': r'D:\tools\desktop-pet\sprites',
    'redpanda': r'D:\tools\desktop-pet\sprites\redpanda',
    'panda': r'D:\tools\desktop-pet\sprites\panda',
    'capybara': r'D:\tools\desktop-pet\sprites\capybara',
    'husky': r'D:\tools\desktop-pet\sprites\husky',
}
STEPS = os.path.join(ROOT, '.steps2', 'out')
ORDER = ['run1'] + ['step%d' % i for i in range(2, 8)] + ['close']

def build(pet, ddir, thresh=0.12):
    seq = []
    for n in ORDER:
        p = os.path.join(ddir, n + '.png') if n == 'run1' else os.path.join(STEPS, '%s_%s.png' % (pet, n))
        seq.append((n, p))
    out = [seq[0]]
    ins = []
    for i in range(8):
        n1, p1 = seq[i]
        n2, p2 = seq[(i + 1) % 8]
        d = diff_ratio(p1, p2)
        if d >= thresh:
            # 插帧数：diff 15% 插1，30% 插2，45%+ 插3
            k = 1 if d < 0.30 else (2 if d < 0.45 else 3)
            added = 0
            for j in range(1, k + 1):
                t = j / (k + 1)
                mid = tps_mid(p1, p2, t)
                if mid is None:
                    continue
                # 质量检测
                if area_penalty(mid, p1, p2):
                    continue
                p = os.path.join(OUT, '%s_%s_%s_%d.png' % (pet, n1, n2, j))
                mid.save(p)
                out.append((n1 + '+' + n2, p))
                added += 1
            if added:
                ins.append('%s->%s d=%.0f%% +%d' % (n1, n2, d * 100, added))
        if i < 7:
            out.append(seq[i + 1])
    # 最后闭环回 run1（循环）
    out.append(('loop->run1', seq[0][1]))
    return out, ins

# ---------- 拼图 ----------
def checker(w, h, cell=12):
    im = Image.new('RGB', (w, h), (232, 232, 232))
    px = im.load()
    for y in range(h):
        for x in range(w):
            if ((x // cell) + (y // cell)) % 2: px[x, y] = (246, 246, 246)
    return im

summary = {}
for pet, ddir in PET_DIRS.items():
    seq, ins = build(pet, ddir)
    summary[pet] = ins
    print('== %s == (%d frames)' % (pet, len(seq)))
    for s in ins: print('  ', s)
    # 拼图
    cell = 100
    frames = [Image.open(p).convert('RGBA') for _, p in seq]
    canvas = checker(len(frames) * cell, cell).convert('RGBA')
    for i, f in enumerate(frames):
        f2 = f.copy(); f2.thumbnail((cell, cell), Image.LANCZOS)
        canvas.paste(f2, (i * cell + (cell - f2.size[0]) // 2, (cell - f2.size[1]) // 2), f2)
    canvas.convert('RGB').save(os.path.join(OUT, 'final_%s.png' % pet))
    # 新序列的相邻差异
    diffs = []
    for i in range(len(seq)):
        diffs.append(diff_ratio(seq[i][1], seq[(i + 1) % len(seq)][1]))
    print('   adj diffs:', ' '.join('%.0f' % (d * 100) for d in diffs))
    print('   mean=%.0f%% max=%.0f%%' % (np.mean(diffs) * 100, np.max(diffs) * 100))
print('DONE')
