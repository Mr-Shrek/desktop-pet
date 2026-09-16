# -*- coding: utf-8 -*-
"""递进帧批量处理：下载/抠图/尺寸对齐参考帧/镜像/拼图"""
import os, sys, urllib.request, time
import numpy as np
from PIL import Image
import importlib.util

ROOT = r'D:\tools\desktop-pet'
BASE = os.path.join(ROOT, '.steps2')
os.makedirs(os.path.join(BASE, 'raw'), exist_ok=True)
os.makedirs(os.path.join(BASE, 'out'), exist_ok=True)

spec = importlib.util.spec_from_file_location('gf', os.path.join(ROOT, '.gen_frame.py'))
gf = importlib.util.module_from_spec(spec); spec.loader.exec_module(gf)

NEW = {
    'cat':      {'step2': '1oo4LK30GF', 'step3': '3SvsDnpYWw', 'step4': 'iDWJmRv4Mv',
                 'step5': 't3c27Ef33v', 'step6': 'ez7eYdV5BF', 'step7': '5bm6ddUBmi',
                 'close': 'FAnzXfxekO'},
    'redpanda': {'step2': 'VUv4qwtWKp', 'step3': '0K6T2CJKFv', 'step4': '3yVuAWElAJ',
                 'step5': 'YpqMKGBPR2', 'step6': 'u5FArFYvTj', 'step7': 'Zn7YA5eiaM',
                 'close': '12a365T87U'},
    'panda':    {'step2': '5qvOIE1RuI', 'step3': 'HBmMUjvmAa', 'step4': 'OhoYOugTNy',
                 'step5': 'FAUhaoL8z6', 'step6': 'WhQsy6UlU7', 'step7': '2s5T2UWVXA',
                 'close': 'n5sWUD2xlD'},
    'capybara': {'step2': 'tlkQiaZUJM', 'step3': 'dlRkoLW3SU', 'step4': 'iUR53QGceF',
                 'step5': 'FJW3qY0Ioq', 'step6': 'yySgjc8naU', 'step7': 'azaAy8U76q',
                 'close': 'LD61nihdmt'},
    'husky':    {'step2': 'E3UkHDoPwp', 'step3': 'oEWNSn8PIM', 'step4': 'VCZiFc8Vo6',
                 'step5': 'sCTwW7hU7r', 'step6': '6AwHIKFU9S', 'step7': 'yvV6tF3qTu',
                 'close': 'ZNffYRepB2'},
}
REFS = {
    'cat':      r'D:\tools\desktop-pet\sprites\run1.png',
    'redpanda': r'D:\tools\desktop-pet\sprites\redpanda\run1.png',
    'panda':    r'D:\tools\desktop-pet\sprites\panda\run1.png',
    'capybara': r'D:\tools\desktop-pet\sprites\capybara\run1.png',
    'husky':    r'D:\tools\desktop-pet\sprites\husky\run1.png',
}

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

def bbox(img):
    arr = np.array(img.convert('RGBA'))[..., 3] > 8
    ys, xs = np.nonzero(arr)
    return (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))

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

def align_ref(img, ref):
    """非cat：内容宽对齐参考帧 + 中心对齐参考帧"""
    rb = bbox(ref)
    rw, rcx, rcy = rb[2] - rb[0] + 1, (rb[0] + rb[2]) / 2.0, (rb[1] + rb[3]) / 2.0
    b = bbox(img)
    cw, ch = b[2] - b[0] + 1, b[3] - b[1] + 1
    scale = rw / cw
    nw, nh = max(1, int(round(cw * scale))), max(1, int(round(ch * scale)))
    crop = img.crop((b[0], b[1], b[2] + 1, b[3] + 1)).resize((nw, nh), Image.LANCZOS)
    x = int(round(rcx - nw / 2.0)); y = int(round(rcy - nh / 2.0))
    canvas = Image.new('RGBA', (600, 600), (0, 0, 0, 0))
    canvas.paste(crop, (x, y), crop)
    return canvas

print('== download ==')
for pet, steps in NEW.items():
    for name, code in steps.items():
        ok = download('%s_%s' % (pet, name), code)
        print(pet, name, 'OK' if ok else 'FAIL')

print('== process ==')
refs = {p: Image.open(rp).convert('RGBA') for p, rp in REFS.items()}
for pet, steps in NEW.items():
    ref = refs[pet]
    for name in steps:
        src = os.path.join(BASE, 'raw', '%s_%s.png' % (pet, name))
        if not os.path.exists(src): continue
        img = Image.open(src).convert('RGBA')
        cut = gf.cutout_white(img)
        sq = align_cat(cut) if pet == 'cat' else align_ref(cut, ref)
        out = os.path.join(BASE, 'out', '%s_%s' % (pet, name))
        sq.save(out + '.png')
        sq.transpose(Image.FLIP_LEFT_RIGHT).save(out + '_l.png')
    print('processed', pet)

print('== sheet ==')
def checker(w, h, cell=12):
    im = Image.new('RGB', (w, h), (232, 232, 232))
    px = im.load()
    for y in range(h):
        for x in range(w):
            if ((x // cell) + (y // cell)) % 2: px[x, y] = (246, 246, 246)
    return im
SPRD = {
    'cat': r'D:\tools\desktop-pet\sprites',
    'redpanda': r'D:\tools\desktop-pet\sprites\redpanda',
    'panda': r'D:\tools\desktop-pet\sprites\panda',
    'capybara': r'D:\tools\desktop-pet\sprites\capybara',
    'husky': r'D:\tools\desktop-pet\sprites\husky',
}
order = ['run1'] + ['step%d' % i for i in range(2, 8)] + ['close']
for pet in NEW:
    frames = []
    d = SPRD[pet]
    for n in order:
        p = os.path.join(d, n + '.png') if n == 'run1' else os.path.join(BASE, 'out', '%s_%s.png' % (pet, n))
        frames.append(Image.open(p).convert('RGBA'))
    cell = 130
    canvas = checker(8 * cell, cell).convert('RGBA')
    for i, f in enumerate(frames):
        f2 = f.copy(); f2.thumbnail((cell, cell), Image.LANCZOS)
        canvas.paste(f2, (i * cell + (cell - f2.size[0]) // 2, (cell - f2.size[1]) // 2), f2)
    canvas.convert('RGB').save(os.path.join(BASE, 'sheet_%s.png' % pet))
    print('sheet', pet)
print('done')
