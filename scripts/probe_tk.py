# -*- coding: utf-8 -*-
"""Tk 能力探测：透明键色 + PNG 透明 + 置顶 + 无边框"""
import ctypes
import tkinter as tk

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

root = tk.Tk()
root.overrideredirect(True)
root.geometry("120x80+50+50")
root.configure(bg="#ff00fe")
try:
    root.attributes("-transparentcolor", "#ff00fe")
    print("transparentcolor: OK")
except Exception as e:
    print("transparentcolor FAIL:", repr(e))
try:
    root.attributes("-topmost", True)
    print("topmost: OK")
except Exception as e:
    print("topmost FAIL:", repr(e))
try:
    img = tk.PhotoImage(file=r"sprites\idle.png")
    print("PhotoImage PNG OK:", img.width(), "x", img.height())
except Exception as e:
    print("PhotoImage PNG FAIL:", repr(e))
root.after(300, root.destroy)
root.mainloop()
print("window cycle OK")
