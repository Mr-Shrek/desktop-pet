# -*- coding: utf-8 -*-
"""定时提醒弹窗演示：2 秒后触发一次提醒并弹出置顶窗口"""
import os
import sys
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main as m

root = tk.Tk()
pet = m.DesktopPet(root)
pet.add_reminder(2, "喝水时间到！起来活动一下，对眼睛好～")
root.after(8000, pet.quit)
root.mainloop()
print("demo done")
