# -*- coding: utf-8 -*-
"""cat 递进帧处理：下载/抠图/铺满600对齐/镜像/拼图"""
import os, sys, urllib.request, time
import numpy as np
from PIL import Image
import importlib.util

ROOT = r'D:\tools\desktop-pet'
BASE = os.path.join(ROOT, '.steps')
os.makedirs(os.path.join(BASE, 'raw'), exist_ok=True)
os.makedirs(os.path.join(BASE, 'out'), exist_ok=True)

spec = importlib.util.spec_from_file_location('gf', os.path.join(ROOT, '.gen_frame.py'))
gf = importlib.util.module_from_spec(spec); spec.loader.exec_module(gf)

# cat: run1(已有) + 7 新帧
NEW = {'step2': '1oo4LK30GF', 'step3': '3SvsDnpYWw', 'step4': 'iDWJmRv4Mv',
       'step5': 't3c27Ef33v', 'step6': 'ez7eYdV5BF', 'step7': '5bm6ddUBmi',
       'close': 'FAnzXfxekO'}

hdr = {'User-Agent': 'Mozilla/5.0'}
def download(name, code):
    dst = os.path.join(BASE, 'raw', name + '.png')
    if os.path.exists(dst) and os.path.getsize(dst) > 10000:
        return True
    for a in range(3):
        try:
            req = urllib.request.Request('https://aka.doubaocdn.com/s/%s' % code, headers=hdr)
            data = urllib.request.urlopen(req, timeout=60).read()
            open(dst, 'wb').write(data)
            return True
        except Exception as e:
            print('retry', name, a, repr(e)[:60]); time.sleep(2)
    return False

def align_cat(img, cy_target=385, w_target=600):
    arr = np.array(img.convert('RGBA'))[..., 3] > 8
    ys, xs = np.nonzero(arr)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    cw, ch = x1 - x0 + 1, y1 - y0 + 1
    scale = w_target / cw
    nw, nh = max(1, int(round(cw * scale))), max(1, int(round(ch * scale)))
    crop = img.crop((x0, y0, x1 + 1, y1 + 1)).resize((nw, nh), Image.LANCZOS)
    y_off = max(0, min(cy_target - nh // 2, 600 - nh))
    canvas = Image.new('RGBA', (600, 600), (0, 0, 0, 0))
    canvas.paste(crop, (0, y_off), crop)
    return canvas

for name, code in NEW.items():
    ok = download(name, code)
    if not ok:
        print('FAIL', name); continue
    img = Image.open(os.path.join(BASE, 'raw', name + '.png')).convert('RGBA')
    cut = gf.cutout_white(img)
    sq = align_cat(cut)
    out = os.path.join(BASE, 'out', name)
    sq.save(out + '.png')
    sq.transpose(Image.FLIP_LEFT_RIGHT).save(out + '_l.png')
    print('done', name, sq.size)

# 拼图：run1, step2..7, close（8帧）
def checker(w, h, cell=12):
    im = Image.new('RGB', (w, h), (232, 232, 232))
    px = im.load()
    for y in range(h):
        for x in range(w):
            if ((x // cell) + (y // cell)) % 2: px[x, y] = (246, 246, 246)
    return im
names = ['run1'] + ['step%d' % i for i in range(2, 8)] + ['close']
frames = []
for n in names:
    p = os.path.join(ROOT, 'sprites', n + '.png') if n == 'run1' else os.path.join(BASE, 'out', n + '.png')
    frames.append(Image.open(p).convert('RGBA'))
cell = 140
canvas = checker(8 * cell, cell).convert('RGBA')
for i, f in enumerate(frames):
    f2 = f.copy(); f2.thumbnail((cell, cell), Image.LANCZOS)
    canvas.paste(f2, (i * cell + (cell - f2.size[0]) // 2, (cell - f2.size[1]) // 2), f2)
canvas.convert('RGB').save(os.path.join(BASE, 'sheet_cat.png'))
# bbox 一致性检查
def bbox(path):
    im = Image.open(path).convert('RGBA')
    a = np.array(im)[..., 3] > 8
    ys, xs = np.nonzero(a)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
for n in names:
    p = os.path.join(ROOT, 'sprites', n + '.png') if n == 'run1' else os.path.join(BASE, 'out', n + '.png')
    b = bbox(p)
    print('bbox', n, 'w=%d h=%d cy=%d' % (b[2] - b[0], b[3] - b[1], (b[1] + b[3]) // 2))
print('sheet saved')
